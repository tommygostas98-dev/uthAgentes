"""Vigilancia 24/7 de alertas críticas (modo vigía).

Revisa si hay alertas CRÍTICAS (predictivo crítico / preventivo vencido /
anomalías de severidad alta) y, si procede, las envía por correo
automáticamente. Funciona SIN abrir la app Streamlit. Comparte el estado de
deduplicación con la app a través de la tabla `config` de la base de datos, así
que nunca duplica un aviso.

Dos modos:
  python vigilancia_alertas.py            -> una sola revisión (Tarea Programada).
  python vigilancia_alertas.py --loop 2   -> modo vigía CONTINUO cada 2 s.

Cada evento relevante se registra en  data/vigilancia.log. En modo continuo NO
se loguea cada tick (sería gigantesco): solo el arranque, los cambios de estado,
los envíos, los errores y un heartbeat cada 5 minutos.
"""
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")  # carga las credenciales aunque cambie el directorio actual

from src import database, notificaciones  # noqa: E402  (debe ir tras load_dotenv)

LOG = BASE / "data" / "vigilancia.log"

# --- Watcher de archivos nuevos --------------------------------------------
CARPETA_VIGILADA = BASE                       # la carpeta del proyecto
DIR_REPORTES = BASE / "reportes_fallas"       # PDFs generados (NO se vigila)
VISTOS_JSON = BASE / "data" / "archivos_vistos.json"
# «Cualquier archivo nuevo que llegue»: se vigila TODA extensión EXCEPTO
# código, logs y artefactos internos (que cambian al desarrollar y no son
# datos/documentos que "llegan"). Lista NEGRA en vez de blanca, para no
# perderse un export con una extensión inesperada (.txt, .dat, sin extensión…).
EXT_IGNORADAS = {".py", ".pyc", ".pyo", ".pyd", ".log", ".vbs", ".bat",
                 ".ini", ".md", ".example", ".tmp", ".lock"}
NOMBRES_IGNORADOS = {"archivos_vistos.json"}
# Archivos PARCIALES de escritura atómica (se crean y luego se renombran al
# final). Hay que ignorarlos: si no, el watcher procesa el temporal Y el final,
# mandando un correo de más. Cubre patrones tipo `x.csv.tmp.1196.ab12cd`,
# `x.part`, `x.crdownload`, `x~`.
_MARCAS_PARCIALES = (".tmp.", ".tmp~")
_SUFIJOS_PARCIALES = (".part", ".partial", ".crdownload", ".swp", "~")


def _es_parcial(nombre: str) -> bool:
    bajo = nombre.lower()
    return any(m in bajo for m in _MARCAS_PARCIALES) or bajo.endswith(_SUFIJOS_PARCIALES)
# Serializa el procesamiento de archivos entre el hilo del observador (evento
# instantáneo) y el bucle principal (sondeo de respaldo), para no procesar dos
# veces el mismo archivo ni pisar `vistos`/`archivos_vistos.json` a la vez.
_LOCK_ARCHIVOS = threading.Lock()


def _log(linea: str) -> None:
    LOG.parent.mkdir(exist_ok=True)
    sello = datetime.now().isoformat(timespec="seconds")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{sello}  {linea}\n")


def _revisar(estado: dict | None = None) -> dict:
    """Una revisión. Si se pasa `estado` (modo continuo), loguea solo cuando algo
    cambia respecto al tick anterior, para no inflar el log a 2 s/tick."""
    try:
        res = notificaciones.revisar_y_enviar_auto()
        motivo = res.get("motivo")
        if res.get("enviado"):
            _log(f"ENVIADO {res.get('n')} alerta(s) critica(s) -> {res.get('destino')}")
            if estado is not None:
                estado["motivo"] = "enviado"
                estado.pop("error", None)
        elif estado is None:
            _log(f"sin envio ({motivo})")
        elif estado.get("motivo") != motivo:          # solo transiciones de estado
            _log(f"sin envio ({motivo})")
            estado["motivo"] = motivo
            estado.pop("error", None)
        return res
    except Exception as e:  # nunca debe tumbar la vigilancia
        if estado is None or estado.get("error") != str(e):
            _log(f"ERROR {type(e).__name__}: {e}")
            if estado is not None:
                estado["error"] = str(e)
        return {"enviado": False, "motivo": "error"}


# Un archivo recién guardado debe "asentarse" este tiempo (su mtime debe quedar
# al menos así de viejo) antes de procesarlo: así no lo leemos a medio escribir
# ni lo procesamos dos veces mientras el editor aún está volcando bytes.
SETTLE_SEGUNDOS = 1.0


def _instantanea_actual() -> dict[str, float]:
    """Mapa {nombre: mtime} de los archivos «que llegan» en la carpeta vigilada
    (no recursivo): cualquier archivo salvo código/logs/internos y ocultos (los
    que empiezan con punto). El mtime permite detectar un archivo REGUARDADO con
    el mismo nombre (la dedup ya no es solo por nombre)."""
    res: dict[str, float] = {}
    try:
        for nombre in os.listdir(CARPETA_VIGILADA):
            ruta = CARPETA_VIGILADA / nombre
            if not ruta.is_file():
                continue
            if nombre.startswith(".") or nombre in NOMBRES_IGNORADOS:
                continue
            if _es_parcial(nombre):          # temporal de escritura aún sin renombrar
                continue
            if ruta.suffix.lower() in EXT_IGNORADAS:
                continue
            try:
                res[nombre] = ruta.stat().st_mtime
            except OSError:
                continue
    except OSError:
        pass
    return res


def _cargar_vistos() -> dict[str, float]:
    """Estado de archivos ya procesados como {nombre: mtime}. Compatible con el
    formato viejo (lista de nombres): en ese caso adopta como base los mtime
    ACTUALES, para no reprocesar de golpe todo lo que ya existía."""
    try:
        datos = json.loads(VISTOS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(datos, dict):
        return {str(k): float(v) for k, v in datos.items()}
    # formato viejo (lista de nombres) -> migrar a {nombre: mtime_actual}
    actuales = _instantanea_actual()
    return {n: actuales[n] for n in datos if n in actuales}


def _guardar_vistos(vistos: dict[str, float]) -> None:
    try:
        VISTOS_JSON.parent.mkdir(exist_ok=True)
        VISTOS_JSON.write_text(json.dumps(vistos, ensure_ascii=False, sort_keys=True),
                               encoding="utf-8")
    except OSError:
        pass


def _es_archivo_lecturas(nombre: str) -> bool:
    """True si el archivo es un lote de lecturas a importar (p. ej.
    `lecturas_nuevas_W46.csv`). El prefijo es configurable en `config`."""
    patron = (database.obtener_config("watcher_patron_lecturas", "lecturas_nuevas") or "").lower()
    ext = Path(nombre).suffix.lower()
    return bool(patron) and nombre.lower().startswith(patron) and ext in {".csv", ".xlsx", ".xls"}


def _equipo_destino_lecturas() -> tuple[int | None, str]:
    """Equipo al que se importan las lecturas automáticas (config
    `watcher_equipo_lecturas`, default 'U14'); si no existe, el primer equipo."""
    from src import models

    cod = (database.obtener_config("watcher_equipo_lecturas", "U14") or "U14").strip()
    equipos = models.listar_equipos()
    for e in equipos:
        if (e["codigo"] or "").strip().lower() == cod.lower():
            return e["id"], e["codigo"]
    return (equipos[0]["id"], equipos[0]["codigo"]) if equipos else (None, cod)


def _esperar_estable(ruta: Path, intentos: int = 15, espera: float = 0.4) -> bool:
    """Espera a que el archivo termine de copiarse: su tamaño debe repetirse en
    dos lecturas seguidas (>0 bytes). Evita leer un CSV/Excel a medio copiar
    cuando «cae» a la carpeta. True si se estabilizó."""
    ultimo = -1
    for _ in range(intentos):
        try:
            tam = ruta.stat().st_size
        except OSError:
            return False
        if tam == ultimo and tam > 0:
            return True
        ultimo = tam
        time.sleep(espera)
    return ruta.exists()


def _importar_archivo_lecturas(nombre: str) -> dict:
    """Importa de inmediato las lecturas de un archivo a su equipo destino.
    Devuelve un resumen {nombre, equipo, insertados, errores}."""
    import pandas as pd

    from src import predictivo

    equipo_id, equipo_cod = _equipo_destino_lecturas()
    res = {"nombre": nombre, "equipo": equipo_cod, "insertados": 0, "errores": []}
    if equipo_id is None:
        _log(f"watcher: no hay equipo destino para {nombre}; no se importa")
        return res
    ruta = CARPETA_VIGILADA / nombre
    _esperar_estable(ruta)   # espera a que termine de copiarse antes de leer
    try:
        if ruta.suffix.lower() == ".csv":
            df = pd.read_csv(ruta, encoding="utf-8-sig")   # utf-8-sig: ignora el BOM
        else:
            df = pd.read_excel(ruta)
        registros = df.to_dict("records")
        imp = predictivo.importar_lecturas(equipo_id, registros)
        res.update(insertados=imp["insertados"], errores=imp["errores"],
                   duplicados=imp.get("duplicados", []))
        _log(f"watcher: importadas {imp['insertados']} lectura(s) de {nombre} -> {equipo_cod}"
             + (f"; {len(imp['errores'])} con error" if imp["errores"] else "")
             + (f"; {len(imp['duplicados'])} duplicada(s) omitida(s)" if imp.get("duplicados") else ""))
    except Exception as e:
        _log(f"ERROR importando {nombre}: {type(e).__name__}: {e}")
        res["errores"] = [("-", f"{type(e).__name__}: {e}")]
    return res


def _alarma_archivo_nuevo(nuevos: list[str], importes: list[dict] | None = None) -> None:
    """Genera el PDF de la falla y manda la alarma por los dos canales:
    A = correo (con el PDF adjunto), B = difusión por el túnel MCP (si está activo).
    `importes` resume las lecturas auto-importadas (para incluirlo en el aviso);
    el análisis (alertas/anomalías) ya refleja esos datos recién importados."""
    from src import canal_mcp, reportes

    ahora = datetime.now()
    fecha_iso = ahora.isoformat(timespec="seconds")
    evento = "Archivo(s) nuevo(s) recibido(s): " + ", ".join(nuevos)
    if importes:
        detalle_imp = "; ".join(
            f"{i['nombre']}: {i['insertados']} lectura(s) importadas a {i['equipo']}"
            + (f" ({len(i['errores'])} omitidas)" if i["errores"] else "")
            for i in importes
        )
        evento += " | ANALIZADO -> " + detalle_imp
    lineas = notificaciones.alertas_criticas()
    anoms = notificaciones.anomalias_altas()

    # --- Reporte de falla en PDF (para poder verlo) ---
    pdf_path = None
    try:
        pdf = reportes.generar_pdf_falla(evento, lineas, anoms, fecha=fecha_iso)
        DIR_REPORTES.mkdir(exist_ok=True)
        stamp = ahora.strftime("%Y%m%d_%H%M%S")
        pdf_path = DIR_REPORTES / f"falla_{stamp}.pdf"
        pdf_path.write_bytes(pdf)
        _log(f"PDF de falla generado: reportes_fallas/{pdf_path.name}")
    except Exception as e:
        _log(f"ERROR generando PDF: {type(e).__name__}: {e}")

    asunto = f"🔴 MotoVigia: archivo nuevo + {len(lineas)} alerta(s) critica(s)"
    cuerpo = evento + "\n\n" + notificaciones.texto_alertas()

    # --- Canal A: correo (con PDF adjunto) ---
    try:
        destino = database.obtener_config("auto_alertas_destino", "") or notificaciones.destino_por_defecto()
        if notificaciones.configurado() and destino:
            notificaciones.enviar(destino, asunto, cuerpo,
                                  adjuntos=[pdf_path] if pdf_path else None)
            _log(f"CANAL A (correo) -> {destino}" + (" con PDF" if pdf_path else ""))
        else:
            _log("CANAL A omitido (sin credenciales SMTP o sin destino)")
    except Exception as e:
        _log(f"ERROR canal A (correo): {type(e).__name__}: {e}")

    # --- Canal B: difusión MCP (solo si el túnel/MCP está activo) ---
    try:
        res = canal_mcp.enviar_difusion(asunto, cuerpo[:1500])
        if res.get("ok"):
            _log("CANAL B (MCP difusion) -> clase")
        else:
            _log(f"CANAL B no enviado ({res.get('motivo')})")
    except Exception as e:
        _log(f"ERROR canal B (MCP): {type(e).__name__}: {e}")


# --- Modo AGENTE IA: el vigía invoca a Claude para analizar y enviar ---------
CLAUDE_EXE = os.environ.get("CLAUDE_EXE", r"C:\Users\Admin\.local\bin\claude.exe")
_AGENTE_LOCK = threading.Lock()          # una invocación de Claude a la vez
_PROMPT_AGENTE = (
    "Eres MotoVigia, agente de mantenimiento del motor Wartsila U14 (planta PAVANA III). "
    "Acaba de llegar el archivo {contexto} con nuevas lecturas, ya importadas a la base. "
    "Tu tarea como agente:\n"
    "1. Ejecuta: python -c \"from src import notificaciones; print(notificaciones.texto_alertas())\" "
    "para ver las fallas criticas actuales.\n"
    "2. Analiza con criterio de ingeniero de mantenimiento: cual es la falla MAS grave, su causa "
    "probable y la accion recomendada.\n"
    "3. Redacta una alarma BREVE: asunto corto + cuerpo de maximo 8 lineas con tu diagnostico.\n"
    "4. Envia la alarma ejecutando: python enviar_alarma.py \"<asunto>\" \"<cuerpo>\"\n"
    "5. Responde en 3 lineas: que detectaste y que enviaste."
)


def _invocar_agente_ia(contexto: str) -> None:
    """Lanza a Claude (CLI) en segundo plano para que, como agente, analice el
    estado y envíe la alarma. Un lock evita ráfagas: si ya hay una invocación en
    curso, se omite (esa ya verá el estado completo, incluidos los nuevos datos)."""
    def _run():
        if not _AGENTE_LOCK.acquire(blocking=False):
            _log("agente IA: ya hay una invocacion en curso; se omite (cubrira estos datos)")
            return
        try:
            import subprocess
            _log(f"agente IA: invocando a Claude para analizar y enviar ({contexto})...")
            r = subprocess.run(
                [CLAUDE_EXE, "-p", _PROMPT_AGENTE.format(contexto=contexto),
                 "--dangerously-skip-permissions", "--add-dir", str(BASE)],
                cwd=str(BASE), capture_output=True, text=True, timeout=300,
            )
            if r.returncode == 0:
                _log("agente IA: el agente analizo y envio la alarma")
            else:
                _log(f"agente IA: fallo (codigo {r.returncode}): {((r.stderr or r.stdout) or '')[:200]}")
        except Exception as e:
            _log(f"agente IA ERROR: {type(e).__name__}: {e}")
        finally:
            _AGENTE_LOCK.release()
    threading.Thread(target=_run, daemon=True).start()


def _modo_agente_ia() -> bool:
    return database.obtener_config("modo_agente_ia", "0") == "1"


def _revisar_archivos(vistos: dict[str, float]) -> None:
    """Detecta archivos NUEVOS o REGUARDADOS (nombre nuevo, o mismo nombre con
    mtime distinto al ya procesado). Los lotes de lecturas (`lecturas_nuevas_*`)
    se IMPORTAN de inmediato. Luego, según el modo:
    - modo_agente_ia=1: el vigía INVOCA a Claude (agente) para analizar y enviar.
    - modo_agente_ia=0: envío determinista por reglas (`_alarma_archivo_nuevo`).
    Muta `vistos`. Protegido por lock: evento y sondeo no se pisan."""
    with _LOCK_ARCHIVOS:
        snapshot = _instantanea_actual()
        ahora = time.time()
        # Nuevo o modificado (mtime != el ya visto) y ya «asentado» (terminó de
        # escribirse): los que aún se escriben se toman en el próximo ciclo.
        nuevos = sorted(
            n for n, m in snapshot.items()
            if vistos.get(n) != m and ahora - m >= SETTLE_SEGUNDOS
        )
        if not nuevos:
            return
        _log("watcher: archivo(s) NUEVO(s)/MODIFICADO(s): " + ", ".join(nuevos))
        importes = [_importar_archivo_lecturas(n) for n in nuevos if _es_archivo_lecturas(n)]
        if _modo_agente_ia():
            _invocar_agente_ia(", ".join(nuevos))     # Claude analiza y envía
        else:
            _alarma_archivo_nuevo(nuevos, importes)    # reglas deterministas
        vistos.update({n: snapshot[n] for n in nuevos})
        _guardar_vistos(vistos)


def main() -> None:
    """Revisión única (para la Tarea Programada en modo disparo puntual)."""
    _revisar()


_MUTEX_HANDLE = None  # se conserva vivo mientras corra el proceso


def _instancia_unica(nombre: str = "MotoVigia_VigiaLoop") -> bool:
    """True si esta es la única instancia del vigía; False si ya hay otra viva.

    Usa un mutex con nombre de Windows: el SO lo libera solo cuando el proceso
    muere, así que evita que dos lanzadores (carpeta de Inicio + arranque manual)
    levanten dos bucles a la vez. Si el chequeo falla, no bloquea (devuelve True).
    """
    try:
        import ctypes
        global _MUTEX_HANDLE
        kernel32 = ctypes.windll.kernel32
        _MUTEX_HANDLE = kernel32.CreateMutexW(None, False, "Local\\" + nombre)
        return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return True


def main_loop(intervalo: float) -> None:
    """Modo vigía continuo: revisa cada `intervalo` segundos, indefinidamente."""
    if not _instancia_unica():
        _log("ya hay un vigia continuo en ejecucion; esta instancia no arranca")
        return
    _log(f"== modo vigia CONTINUO iniciado (cada {intervalo:g}s) ==")
    estado: dict = {}

    # Watcher: baseline para NO disparar con los archivos que ya existen (se
    # guardan con su mtime actual; si luego se REGUARDAN, el mtime cambia y sí
    # se reprocesan).
    if VISTOS_JSON.exists():
        vistos = _cargar_vistos()
    else:
        vistos = _instantanea_actual()
        _guardar_vistos(vistos)
        _log(f"watcher: baseline de {len(vistos)} archivo(s); vigilando la carpeta del proyecto")

    # Detección INSTANTÁNEA por evento del sistema de archivos (watchdog): en
    # cuanto un archivo CAE a la carpeta, se procesa al momento, sin esperar al
    # sondeo. El sondeo del bucle queda como respaldo (por si se pierde un evento).
    observer = _arrancar_observador(vistos)

    heartbeat_cada = 300.0          # segundos entre latidos de "sigo vivo"
    proximo_heartbeat = time.monotonic() + heartbeat_cada
    try:
        while True:
            # Blindaje: ningún error puntual (BD, red, archivo corrupto) debe
            # tumbar al vigía. Se loguea una vez y el bucle continúa vivo.
            try:
                _revisar(estado)
                _revisar_archivos(vistos)
            except Exception as e:
                if estado.get("error_ciclo") != str(e):
                    _log(f"ERROR en ciclo (continuo vivo): {type(e).__name__}: {e}")
                    estado["error_ciclo"] = str(e)
            if time.monotonic() >= proximo_heartbeat:
                _log(f"heartbeat (vigia activo · estado={estado.get('motivo', 'inicial')})")
                proximo_heartbeat = time.monotonic() + heartbeat_cada
            time.sleep(intervalo)
    except KeyboardInterrupt:
        _log("== modo vigia detenido (KeyboardInterrupt) ==")
    finally:
        if observer is not None:
            try:
                observer.stop()
                observer.join(timeout=3)
            except Exception:
                pass


def _arrancar_observador(vistos: set[str]):
    """Inicia un observador watchdog que procesa al INSTANTE los archivos que
    caen a la carpeta. Devuelve el observer (o None si watchdog no está). El
    procesamiento real lo hace `_revisar_archivos` (con lock), igual que el
    sondeo, así que ambos caminos son seguros y idempotentes."""
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except Exception as e:
        _log(f"watcher: sin deteccion por evento ({type(e).__name__}); queda el sondeo")
        return None

    def _disparar():
        try:
            _revisar_archivos(vistos)
        except Exception as e:
            _log(f"ERROR watcher (evento): {type(e).__name__}: {e}")

    class _Manejador(FileSystemEventHandler):
        def on_created(self, event):
            if not event.is_directory:
                _disparar()

        def on_moved(self, event):
            if not event.is_directory:
                _disparar()

        def on_modified(self, event):
            # Reguardar un archivo existente (mismo nombre) dispara modificación,
            # no creación. La dedup por mtime + el «asentado» de SETTLE_SEGUNDOS
            # hacen que esto sea idempotente (no procesa a medio escribir).
            if not event.is_directory:
                _disparar()

    try:
        observer = Observer()
        observer.schedule(_Manejador(), str(CARPETA_VIGILADA), recursive=False)
        observer.start()
        _log("watcher: deteccion INSTANTANEA por evento ACTIVADA (watchdog)")
        return observer
    except Exception as e:
        _log(f"watcher: no se pudo iniciar el observador ({type(e).__name__}); queda el sondeo")
        return None


def main_supervisor(intervalo: float) -> None:
    """Mantiene el vigía SIEMPRE vivo: lanza el worker (`--loop`) como subproceso
    y, si termina por cualquier causa (crash, cierre forzado, error fatal), lo
    relanza tras una breve espera. El supervisor en sí es trivial, así que casi
    nunca falla; si lo hiciera, el lanzador de Inicio lo revive al iniciar sesión.
    """
    import subprocess

    if not _instancia_unica("MotoVigia_Supervisor"):
        _log("ya hay un supervisor en ejecucion; esta instancia no arranca")
        return
    _log("== SUPERVISOR iniciado (mantiene el vigia siempre activo) ==")
    espera_reinicio = 5
    while True:
        try:
            proc = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--loop", str(intervalo)],
                cwd=str(BASE),
            )
            proc.wait()
            _log(f"el vigia worker termino (codigo {proc.returncode}); relanzando en {espera_reinicio}s")
        except Exception as e:
            _log(f"SUPERVISOR error al lanzar el worker: {type(e).__name__}: {e}")
        try:
            time.sleep(espera_reinicio)
        except KeyboardInterrupt:
            _log("== SUPERVISOR detenido (KeyboardInterrupt) ==")
            return


def _segundos_arg(args: list[str], default: float = 2.0) -> float:
    try:
        return max(0.5, float(args[1])) if len(args) > 1 else default
    except ValueError:
        return default


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--supervisor":
        main_supervisor(_segundos_arg(args))
    elif args and args[0] == "--loop":
        main_loop(_segundos_arg(args))   # piso de seguridad: 0.5 s
    else:
        main()

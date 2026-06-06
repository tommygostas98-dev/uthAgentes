"""MotoVigia — versión orientada a objetos (POO) del modo vigía.

Refactoriza la lógica de `vigilancia_alertas.py` (que es procedural) a clases con
una sola responsabilidad cada una, manteniendo la MISMA funcionalidad:

    - Logger ............ registro de eventos en data/vigilancia.log
    - InstanciaUnica .... mutex de Windows para no correr dos veces a la vez
    - CanalCorreo ....... canal A: alarma por correo (SMTP)         [Canal]
    - CanalMCP .......... canal B: difusión a los otros agentes      [Canal]
    - ReporteFalla ...... genera el PDF de la falla
    - ImportadorLecturas  importa un archivo `lecturas_nuevas_*` a un equipo
    - AgenteIA .......... invoca a Claude para analizar y enviar la alarma
    - WatcherArchivos ... detecta archivos nuevos (evento + sondeo) en la carpeta
    - Vigia ............. orquesta el bucle: revisa alertas y procesa archivos
    - Supervisor ........ mantiene el Vigia vivo (lo relanza si muere)

La lógica de negocio (análisis de límites/anomalías, formato de correo, cliente
MCP, generación de PDF) se reutiliza de los módulos `src/*`, que ya están
probados; estas clases solo encapsulan la ORQUESTACIÓN.

Uso:
    python motovigia.py                 # una sola revisión
    python motovigia.py --loop 2        # vigía continuo cada 2 s
    python motovigia.py --supervisor 2  # supervisor (mantiene el vigía vivo)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

# La lógica de negocio vive en src/* (ya probada); aquí solo la orquestamos.
from src import (  # noqa: E402
    canal_mcp as _mcp,
    database as _db,
    notificaciones as _noti,
    predictivo as _pred,
    reportes as _rep,
)


# ===========================================================================
# Registro de eventos
# ===========================================================================
class Logger:
    """Escribe eventos con marca de tiempo en un archivo de log (append)."""

    def __init__(self, ruta: Path):
        self.ruta = ruta

    def log(self, mensaje: str) -> None:
        self.ruta.parent.mkdir(exist_ok=True)
        sello = datetime.now().isoformat(timespec="seconds")
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(f"{sello}  {mensaje}\n")


# ===========================================================================
# Instancia única (mutex de Windows)
# ===========================================================================
class InstanciaUnica:
    """Garantiza que solo corra una instancia con un nombre dado, usando un
    mutex con nombre de Windows (el SO lo libera al morir el proceso)."""

    def __init__(self, nombre: str):
        self.nombre = nombre
        self._handle = None  # se conserva vivo mientras corra el proceso

    def adquirir(self) -> bool:
        """True si esta es la única instancia; False si ya hay otra viva."""
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            self._handle = kernel32.CreateMutexW(None, False, "Local\\" + self.nombre)
            return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS
        except Exception:
            return True


# ===========================================================================
# Canales de alarma (patrón: clase base abstracta + implementaciones)
# ===========================================================================
class Canal(ABC):
    """Interfaz común de un canal de alarma."""

    nombre = "canal"

    @abstractmethod
    def enviar(self, asunto: str, cuerpo: str, adjuntos: list[Path] | None = None) -> str:
        """Envía la alarma. Devuelve un texto de resultado para el log."""


class CanalCorreo(Canal):
    """Canal A: envía la alarma por correo (SMTP) con adjunto opcional."""

    nombre = "A (correo)"

    def destino(self) -> str:
        return _db.obtener_config("auto_alertas_destino", "") or _noti.destino_por_defecto()

    def enviar(self, asunto: str, cuerpo: str, adjuntos: list[Path] | None = None) -> str:
        destino = self.destino()
        if not (_noti.configurado() and destino):
            return "omitido (sin credenciales SMTP o sin destino)"
        try:
            _noti.enviar(destino, asunto, cuerpo, adjuntos=adjuntos)
            return f"-> {destino}" + (" con PDF" if adjuntos else "")
        except Exception as e:
            return f"ERROR: {type(e).__name__}: {e}"


class CanalMCP(Canal):
    """Canal B: difunde la alarma a los otros agentes por el túnel MCP."""

    nombre = "B (otros agentes)"

    def activo(self) -> bool:
        return _mcp.mcp_activo()

    def enviar(self, asunto: str, cuerpo: str, adjuntos: list[Path] | None = None) -> str:
        res = _mcp.enviar_difusion(asunto, cuerpo[:1500])
        return "enviado" if res.get("ok") else f"no enviado ({res.get('motivo')})"


# ===========================================================================
# Generación del reporte de falla
# ===========================================================================
class ReporteFalla:
    """Genera (y guarda) el PDF del reporte de falla con el estado actual."""

    def __init__(self, carpeta_salida: Path):
        self.carpeta = carpeta_salida

    def generar(self, evento: str, importes: list[dict] | None = None) -> Path | None:
        lineas = _noti.alertas_criticas()
        anomalias = _noti.anomalias_altas()
        if importes:
            evento += " | ANALIZADO -> " + "; ".join(
                f"{i['nombre']}: {i['insertados']} lectura(s) a {i['equipo']}" for i in importes
            )
        try:
            pdf = _rep.generar_pdf_falla(
                evento, lineas, anomalias, fecha=datetime.now().isoformat(timespec="seconds")
            )
            self.carpeta.mkdir(exist_ok=True)
            ruta = self.carpeta / f"falla_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            ruta.write_bytes(pdf)
            return ruta
        except Exception:
            return None


# ===========================================================================
# Importación de lecturas
# ===========================================================================
class ImportadorLecturas:
    """Importa un archivo `lecturas_nuevas_*` al equipo destino configurado."""

    EXT_VALIDAS = {".csv", ".xlsx", ".xls"}

    def __init__(self, carpeta: Path, logger: Logger):
        self.carpeta = carpeta
        self.log = logger.log

    def es_archivo_lecturas(self, nombre: str) -> bool:
        patron = (_db.obtener_config("watcher_patron_lecturas", "lecturas_nuevas") or "").lower()
        return bool(patron) and nombre.lower().startswith(patron) \
            and Path(nombre).suffix.lower() in self.EXT_VALIDAS

    def equipo_destino(self) -> tuple[int | None, str]:
        from src import models
        cod = (_db.obtener_config("watcher_equipo_lecturas", "U14") or "U14").strip()
        equipos = models.listar_equipos()
        for e in equipos:
            if (e["codigo"] or "").strip().lower() == cod.lower():
                return e["id"], e["codigo"]
        return (equipos[0]["id"], equipos[0]["codigo"]) if equipos else (None, cod)

    @staticmethod
    def _esperar_estable(ruta: Path, intentos: int = 15, espera: float = 0.4) -> bool:
        """Espera a que el archivo termine de copiarse (tamaño estable)."""
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

    def importar(self, nombre: str) -> dict:
        import pandas as pd
        equipo_id, equipo_cod = self.equipo_destino()
        res = {"nombre": nombre, "equipo": equipo_cod, "insertados": 0, "errores": []}
        if equipo_id is None:
            self.log(f"watcher: no hay equipo destino para {nombre}")
            return res
        ruta = self.carpeta / nombre
        self._esperar_estable(ruta)
        try:
            if ruta.suffix.lower() == ".csv":
                df = pd.read_csv(ruta, encoding="utf-8-sig")
            else:
                df = pd.read_excel(ruta)
            imp = _pred.importar_lecturas(equipo_id, df.to_dict("records"))
            res.update(insertados=imp["insertados"], errores=imp["errores"])
            self.log(f"watcher: importadas {imp['insertados']} lectura(s) de {nombre} -> {equipo_cod}")
        except Exception as e:
            self.log(f"ERROR importando {nombre}: {type(e).__name__}: {e}")
            res["errores"] = [("-", str(e))]
        return res


# ===========================================================================
# Agente IA: invoca a Claude para analizar y enviar la alarma
# ===========================================================================
class AgenteIA:
    """Invoca a Claude (CLI) en segundo plano para que, como agente, analice el
    estado y envíe la alarma. Un lock evita ráfagas de invocaciones."""

    PROMPT = (
        "Eres MotoVigia, agente de mantenimiento del motor Wartsila U14 (planta PAVANA III). "
        "Acaba de llegar el archivo {contexto} con nuevas lecturas, ya importadas. Tu tarea:\n"
        "1. Ejecuta: python -c \"from src import notificaciones; print(notificaciones.texto_alertas())\"\n"
        "2. Analiza con criterio de ingeniero: la falla MAS grave, su causa probable y la accion.\n"
        "3. Redacta una alarma BREVE: asunto corto + cuerpo de max 8 lineas.\n"
        "4. Envia con: python enviar_alarma.py \"<asunto>\" \"<cuerpo>\"\n"
        "5. Responde en 3 lineas que detectaste y enviaste."
    )

    def __init__(self, base: Path, logger: Logger):
        self.base = base
        self.log = logger.log
        self.exe = os.environ.get("CLAUDE_EXE", r"C:\Users\Admin\.local\bin\claude.exe")
        self._lock = threading.Lock()

    def activo(self) -> bool:
        return _db.obtener_config("modo_agente_ia", "0") == "1"

    def invocar(self, contexto: str) -> None:
        threading.Thread(target=self._run, args=(contexto,), daemon=True).start()

    def _run(self, contexto: str) -> None:
        if not self._lock.acquire(blocking=False):
            self.log("agente IA: ya hay una invocacion en curso; se omite")
            return
        try:
            self.log(f"agente IA: invocando a Claude ({contexto})...")
            r = subprocess.run(
                [self.exe, "-p", self.PROMPT.format(contexto=contexto),
                 "--dangerously-skip-permissions", "--add-dir", str(self.base)],
                cwd=str(self.base), capture_output=True, text=True, timeout=300,
            )
            if r.returncode == 0:
                self.log("agente IA: el agente analizo y envio la alarma")
            else:
                self.log(f"agente IA: fallo ({r.returncode}): {((r.stderr or r.stdout) or '')[:200]}")
        except Exception as e:
            self.log(f"agente IA ERROR: {type(e).__name__}: {e}")
        finally:
            self._lock.release()


# ===========================================================================
# Watcher de archivos
# ===========================================================================
class WatcherArchivos:
    """Detecta archivos nuevos en la carpeta (sondeo + evento watchdog) y los
    procesa: importa lecturas y dispara la alarma (por agente IA o por reglas)."""

    EXT_IGNORADAS = {".py", ".pyc", ".pyo", ".pyd", ".log", ".vbs", ".bat",
                     ".ini", ".md", ".example", ".tmp", ".lock"}
    NOMBRES_IGNORADOS = {"archivos_vistos.json"}
    MARCAS_PARCIALES = (".tmp.", ".tmp~")
    SUFIJOS_PARCIALES = (".part", ".partial", ".crdownload", ".swp", "~")
    # Un archivo recién guardado debe "asentarse" este tiempo (mtime así de viejo)
    # antes de procesarlo: ni se lee a medio escribir ni se procesa dos veces.
    SETTLE_SEGUNDOS = 1.0

    def __init__(self, carpeta: Path, vistos_json: Path, logger: Logger,
                 importador: ImportadorLecturas, agente: AgenteIA,
                 reporte: ReporteFalla, canales: list[Canal]):
        self.carpeta = carpeta
        self.vistos_json = vistos_json
        self.log = logger.log
        self.importador = importador
        self.agente = agente
        self.reporte = reporte
        self.canales = canales
        self._lock = threading.Lock()
        self.vistos: dict[str, float] = {}   # {nombre: mtime} ya procesado
        self._observer = None

    # --- detección ----------------------------------------------------------
    def _es_parcial(self, nombre: str) -> bool:
        bajo = nombre.lower()
        return any(m in bajo for m in self.MARCAS_PARCIALES) or bajo.endswith(self.SUFIJOS_PARCIALES)

    def instantanea_actual(self) -> dict[str, float]:
        """Mapa {nombre: mtime} de los archivos «que llegan». El mtime permite
        detectar un archivo REGUARDADO con el mismo nombre (dedup no solo por
        nombre)."""
        res: dict[str, float] = {}
        try:
            for nombre in os.listdir(self.carpeta):
                ruta = self.carpeta / nombre
                if not ruta.is_file() or nombre.startswith(".") or nombre in self.NOMBRES_IGNORADOS:
                    continue
                if self._es_parcial(nombre) or ruta.suffix.lower() in self.EXT_IGNORADAS:
                    continue
                try:
                    res[nombre] = ruta.stat().st_mtime
                except OSError:
                    continue
        except OSError:
            pass
        return res

    # --- persistencia del baseline -----------------------------------------
    def cargar_baseline(self) -> None:
        if self.vistos_json.exists():
            try:
                datos = json.loads(self.vistos_json.read_text(encoding="utf-8"))
            except Exception:
                datos = {}
            if isinstance(datos, dict):
                self.vistos = {str(k): float(v) for k, v in datos.items()}
            else:
                # formato viejo (lista de nombres) -> adoptar mtime actuales, para
                # no reprocesar de golpe todo lo que ya existía.
                actuales = self.instantanea_actual()
                self.vistos = {n: actuales[n] for n in datos if n in actuales}
        else:
            self.vistos = self.instantanea_actual()
            self._guardar()
            self.log(f"watcher: baseline de {len(self.vistos)} archivo(s)")

    def _guardar(self) -> None:
        try:
            self.vistos_json.parent.mkdir(exist_ok=True)
            self.vistos_json.write_text(
                json.dumps(self.vistos, ensure_ascii=False, sort_keys=True),
                encoding="utf-8")
        except OSError:
            pass

    # --- procesamiento ------------------------------------------------------
    def revisar(self) -> None:
        with self._lock:
            snapshot = self.instantanea_actual()
            ahora = time.time()
            # Nuevo o REGUARDADO (mtime != el ya visto) y ya «asentado»: los que
            # aún se escriben se toman en el próximo ciclo.
            nuevos = sorted(
                n for n, m in snapshot.items()
                if self.vistos.get(n) != m and ahora - m >= self.SETTLE_SEGUNDOS
            )
            if not nuevos:
                return
            self.log("watcher: archivo(s) NUEVO(s)/MODIFICADO(s): " + ", ".join(nuevos))
            importes = [self.importador.importar(n) for n in nuevos
                        if self.importador.es_archivo_lecturas(n)]
            if self.agente.activo():
                self.agente.invocar(", ".join(nuevos))          # Claude analiza y envía
            else:
                self._alarma_reglas(nuevos, importes)           # reglas + canales
            self.vistos.update({n: snapshot[n] for n in nuevos})
            self._guardar()

    def _alarma_reglas(self, nuevos: list[str], importes: list[dict]) -> None:
        evento = "Archivo(s) nuevo(s): " + ", ".join(nuevos)
        pdf = self.reporte.generar(evento, importes)
        asunto = f"MotoVigia: archivo nuevo + {len(_noti.alertas_criticas())} alerta(s) critica(s)"
        cuerpo = evento + "\n\n" + _noti.texto_alertas()
        adj = [pdf] if pdf else None
        for canal in self.canales:
            self.log(f"CANAL {canal.nombre}: {canal.enviar(asunto, cuerpo, adj)}")

    # --- observador instantáneo (watchdog) ----------------------------------
    def iniciar_observador(self) -> None:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except Exception:
            self.log("watcher: sin watchdog; solo sondeo")
            return

        watcher = self

        class _Handler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    watcher.revisar()

            def on_moved(self, event):
                if not event.is_directory:
                    watcher.revisar()

            def on_modified(self, event):
                # Reguardar un archivo existente dispara modificación, no creación.
                # La dedup por mtime + SETTLE_SEGUNDOS lo hacen idempotente.
                if not event.is_directory:
                    watcher.revisar()

        try:
            self._observer = Observer()
            self._observer.schedule(_Handler(), str(self.carpeta), recursive=False)
            self._observer.start()
            self.log("watcher: deteccion INSTANTANEA por evento ACTIVADA (watchdog)")
        except Exception as e:
            self.log(f"watcher: no se pudo iniciar el observador ({type(e).__name__})")

    def detener_observador(self) -> None:
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=3)
            except Exception:
                pass


# ===========================================================================
# El Vigía (orquestador del bucle)
# ===========================================================================
class Vigia:
    """Orquesta el modo vigía: en cada ciclo revisa alertas críticas (envío
    desatendido con dedup) y procesa los archivos nuevos de la carpeta."""

    def __init__(self, base: Path = BASE):
        self.base = base
        self.logger = Logger(base / "data" / "vigilancia.log")
        self.mutex = InstanciaUnica("MotoVigia_VigiaLoop")
        self.canales: list[Canal] = [CanalCorreo(), CanalMCP()]
        importador = ImportadorLecturas(base, self.logger)
        agente = AgenteIA(base, self.logger)
        reporte = ReporteFalla(base / "reportes_fallas")
        self.watcher = WatcherArchivos(
            base, base / "data" / "archivos_vistos.json",
            self.logger, importador, agente, reporte, self.canales,
        )
        self._estado: dict = {}

    @property
    def log(self):
        return self.logger.log

    def revisar_alertas(self) -> None:
        """Envío desatendido de alertas críticas (dedup/cooldown en src)."""
        try:
            res = _noti.revisar_y_enviar_auto()
            motivo = res.get("motivo")
            if res.get("enviado"):
                self.log(f"ENVIADO {res.get('n')} alerta(s) critica(s) -> {res.get('destino')}")
                self._estado["motivo"] = "enviado"
            elif self._estado.get("motivo") != motivo:
                self.log(f"sin envio ({motivo})")
                self._estado["motivo"] = motivo
        except Exception as e:
            if self._estado.get("error") != str(e):
                self.log(f"ERROR {type(e).__name__}: {e}")
                self._estado["error"] = str(e)

    def revision_unica(self) -> None:
        self.revisar_alertas()

    def correr(self, intervalo: float) -> None:
        if not self.mutex.adquirir():
            self.log("ya hay un vigia en ejecucion; esta instancia no arranca")
            return
        self.log(f"== MotoVigia (POO) iniciado (cada {intervalo:g}s) ==")
        self.watcher.cargar_baseline()
        self.watcher.iniciar_observador()
        heartbeat = time.monotonic() + 300
        try:
            while True:
                try:
                    self.revisar_alertas()
                    self.watcher.revisar()
                except Exception as e:
                    self.log(f"ERROR en ciclo (sigo vivo): {type(e).__name__}: {e}")
                if time.monotonic() >= heartbeat:
                    self.log("heartbeat (vigia activo)")
                    heartbeat = time.monotonic() + 300
                time.sleep(intervalo)
        except KeyboardInterrupt:
            self.log("== MotoVigia detenido ==")
        finally:
            self.watcher.detener_observador()


# ===========================================================================
# Supervisor (mantiene el vigía siempre vivo)
# ===========================================================================
class Supervisor:
    """Lanza el Vigía como subproceso y lo relanza si muere por cualquier causa."""

    def __init__(self, base: Path = BASE):
        self.base = base
        self.logger = Logger(base / "data" / "vigilancia.log")
        self.mutex = InstanciaUnica("MotoVigia_Supervisor")

    def correr(self, intervalo: float, espera_reinicio: int = 5) -> None:
        if not self.mutex.adquirir():
            self.logger.log("ya hay un supervisor en ejecucion; esta instancia no arranca")
            return
        self.logger.log("== SUPERVISOR (POO) iniciado ==")
        while True:
            try:
                proc = subprocess.Popen(
                    [sys.executable, str(Path(__file__).resolve()), "--loop", str(intervalo)],
                    cwd=str(self.base),
                )
                proc.wait()
                self.logger.log(f"el vigia termino (codigo {proc.returncode}); relanzando en {espera_reinicio}s")
            except Exception as e:
                self.logger.log(f"SUPERVISOR error: {type(e).__name__}: {e}")
            try:
                time.sleep(espera_reinicio)
            except KeyboardInterrupt:
                self.logger.log("== SUPERVISOR detenido ==")
                return


# ===========================================================================
# Punto de entrada (CLI)
# ===========================================================================
def _segundos(args: list[str], default: float = 2.0) -> float:
    try:
        return max(0.5, float(args[1])) if len(args) > 1 else default
    except ValueError:
        return default


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--supervisor":
        Supervisor().correr(_segundos(args))
    elif args and args[0] == "--loop":
        Vigia().correr(_segundos(args))
    else:
        Vigia().revision_unica()


if __name__ == "__main__":
    main()

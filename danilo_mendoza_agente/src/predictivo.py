"""Mantenimiento predictivo: lecturas de sensores, límites y proyección de tendencia.

Idea central: se registran lecturas de parámetros (temperatura, presión,
vibración, etc.) a lo largo del tiempo. Con dos o más lecturas se ajusta una
recta (regresión lineal) sobre las horas de operación para estimar cuándo el
parámetro alcanzará su límite. Esto anticipa la falla antes de que ocurra.

Es la base sobre la que puede crecer MotorVigia.
"""

import numpy as np

from .database import get_connection


# ---------------------------------------------------------------------------
# LECTURAS
# ---------------------------------------------------------------------------
def registrar_lectura(
    equipo_id: int,
    parametro: str,
    valor: float,
    unidad: str | None = None,
    horas_operacion: float | None = None,
    fecha: str | None = None,
) -> int:
    """Guarda una lectura de sensor. `fecha` opcional en formato 'YYYY-MM-DD HH:MM'."""
    conn = get_connection()
    if fecha:
        cur = conn.execute(
            """INSERT INTO lecturas (equipo_id, parametro, valor, unidad, horas_operacion, fecha)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (equipo_id, parametro, valor, unidad, horas_operacion, fecha),
        )
    else:
        cur = conn.execute(
            """INSERT INTO lecturas (equipo_id, parametro, valor, unidad, horas_operacion)
               VALUES (?, ?, ?, ?, ?)""",
            (equipo_id, parametro, valor, unidad, horas_operacion),
        )
    conn.commit()
    nuevo_id = cur.lastrowid
    conn.close()
    return nuevo_id


def lecturas_de(equipo_id: int, parametro: str | None = None) -> list[dict]:
    conn = get_connection()
    sql = "SELECT * FROM lecturas WHERE equipo_id = ?"
    params: list = [equipo_id]
    if parametro:
        sql += " AND parametro = ?"
        params.append(parametro)
    sql += " ORDER BY fecha"
    filas = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(f) for f in filas]


def _clave_dedup(parametro: str, horas: float | None, fecha: str | None,
                 valor: float) -> tuple | None:
    """Identifica una lectura de forma estable para detectar duplicados.

    NO usa la fecha que la base auto-estampa (cambia en cada importación); solo
    el ancla temporal fiable: las horas de operación si existen, o la fecha
    EXPLÍCITA del archivo en su defecto. Si la lectura no trae ninguna de las
    dos, devuelve None (sin ancla no se puede afirmar que sea un duplicado, así
    que se inserta). Los números se redondean para evitar ruido de punto flotante.
    """
    if horas is not None:
        return (parametro, round(float(horas), 6), round(float(valor), 6))
    if fecha:
        return (parametro, fecha, round(float(valor), 6))
    return None


def importar_lecturas(equipo_id: int, registros: list[dict]) -> dict:
    """Inserta varias lecturas de una sola vez (carga masiva desde CSV/Excel).

    Cada registro es un dict con al menos 'parametro' y 'valor'; opcionalmente
    'unidad', 'horas_operacion' y 'fecha' (texto 'YYYY-MM-DD' o 'YYYY-MM-DD HH:MM').
    Devuelve {'insertados': int, 'errores': [(fila, motivo), ...],
    'duplicados': [(fila, motivo), ...]}.

    Omite (sin insertar):
      - filas con error de validación → 'errores'.
      - filas que repiten una lectura ya existente en la base O una ya vista
        antes en el mismo archivo → 'duplicados'. El cotejo es por
        parametro + horas_operacion + valor (o + fecha explícita si no hay
        horas), de modo que volver a cargar el mismo lote no duplica datos.
    """
    conn = get_connection()
    insertados = 0
    errores: list[tuple[int, str]] = []
    duplicados: list[tuple[int, str]] = []

    def _vacio(v) -> bool:
        # Trata None, cadena vacía y NaN (de pandas) como "sin valor".
        return v is None or v != v or (isinstance(v, str) and v.strip() == "")

    # Semilla de claves ya existentes en la base, para este equipo y solo los
    # parámetros presentes en el lote (consulta acotada).
    params_lote = {str(r.get("parametro")).strip() for r in registros
                   if not _vacio(r.get("parametro"))}
    vistos: set[tuple] = set()
    if params_lote:
        marcadores = ",".join("?" * len(params_lote))
        filas = conn.execute(
            f"""SELECT parametro, horas_operacion, fecha, valor FROM lecturas
                WHERE equipo_id = ? AND parametro IN ({marcadores})""",
            (equipo_id, *params_lote),
        ).fetchall()
        for f in filas:
            k = _clave_dedup(f["parametro"], f["horas_operacion"], f["fecha"], f["valor"])
            if k is not None:
                vistos.add(k)

    for i, r in enumerate(registros):
        try:
            parametro = r.get("parametro")
            if _vacio(parametro):
                raise ValueError("parámetro vacío")
            parametro = str(parametro).strip()

            if _vacio(r.get("valor")):
                raise ValueError("valor vacío")
            valor = float(r["valor"])

            unidad = r.get("unidad")
            unidad = str(unidad).strip() if not _vacio(unidad) else None

            horas = r.get("horas_operacion")
            horas = float(horas) if not _vacio(horas) else None

            fecha = r.get("fecha")
            fecha = str(fecha).strip() if not _vacio(fecha) else None

            # ¿Duplicado? (ya en la base o ya visto en este mismo archivo)
            clave = _clave_dedup(parametro, horas, fecha, valor)
            if clave is not None and clave in vistos:
                ancla = f"{horas:g} h" if horas is not None else f"fecha {fecha}"
                duplicados.append(
                    (i + 2, f"duplicado: {parametro}={valor:g} @ {ancla} ya existe")
                )
                continue

            if fecha:
                conn.execute(
                    """INSERT INTO lecturas
                       (equipo_id, parametro, valor, unidad, horas_operacion, fecha)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (equipo_id, parametro, valor, unidad, horas, fecha),
                )
            else:
                conn.execute(
                    """INSERT INTO lecturas
                       (equipo_id, parametro, valor, unidad, horas_operacion)
                       VALUES (?, ?, ?, ?, ?)""",
                    (equipo_id, parametro, valor, unidad, horas),
                )
            if clave is not None:
                vistos.add(clave)
            insertados += 1
        except (ValueError, TypeError, KeyError) as e:
            # fila + 2 = número de fila en la hoja (1 = encabezado)
            errores.append((i + 2, str(e)))

    conn.commit()
    conn.close()
    return {"insertados": insertados, "errores": errores, "duplicados": duplicados}


def parametros_de(equipo_id: int) -> list[str]:
    """Lista los nombres de parámetros que tienen lecturas para un equipo."""
    conn = get_connection()
    filas = conn.execute(
        "SELECT DISTINCT parametro FROM lecturas WHERE equipo_id = ? ORDER BY parametro",
        (equipo_id,),
    ).fetchall()
    conn.close()
    return [f["parametro"] for f in filas]


# ---------------------------------------------------------------------------
# LÍMITES
# ---------------------------------------------------------------------------
def definir_limite(
    equipo_id: int,
    parametro: str,
    limite_alerta: float | None,
    limite_critico: float | None,
    unidad: str | None = None,
    direccion: str = "alta",
) -> None:
    """Crea o actualiza el umbral de un parámetro.

    `direccion` define de qué lado está el peligro:
    - 'alta' (techo): el valor es peligroso cuando SUBE por encima del umbral
      (temperaturas, holguras/desgaste, vibración).
    - 'baja' (piso): el valor es peligroso cuando BAJA por debajo del umbral
      (presiones de aceite, combustible, aire de arranque).
    """
    direccion = direccion if direccion in ("alta", "baja") else "alta"
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO limites (equipo_id, parametro, limite_alerta, limite_critico, unidad, direccion)
        VALUES (:eq, :p, :a, :c, :u, :d)
        ON CONFLICT (equipo_id, parametro) DO UPDATE SET
            limite_alerta = :a, limite_critico = :c, unidad = :u, direccion = :d
        """,
        {"eq": equipo_id, "p": parametro, "a": limite_alerta, "c": limite_critico,
         "u": unidad, "d": direccion},
    )
    conn.commit()
    conn.close()


def obtener_limite(equipo_id: int, parametro: str) -> dict | None:
    conn = get_connection()
    fila = conn.execute(
        "SELECT * FROM limites WHERE equipo_id = ? AND parametro = ?",
        (equipo_id, parametro),
    ).fetchone()
    conn.close()
    return dict(fila) if fila else None


# ---------------------------------------------------------------------------
# ANÁLISIS PREDICTIVO
# ---------------------------------------------------------------------------
def _ajuste_lineal(x: list[float], y: list[float]) -> tuple[float, float]:
    """Devuelve (pendiente, intercepto) de la recta que mejor ajusta los puntos."""
    pendiente, intercepto = np.polyfit(np.array(x), np.array(y), 1)
    return float(pendiente), float(intercepto)


def analizar_parametro(equipo_id: int, parametro: str) -> dict:
    """Analiza un parámetro: estado actual, tendencia y proyección al límite.

    Devuelve un diccionario con:
    - valor_actual, unidad
    - estado: 'normal' | 'alerta' | 'critico' | 'sin_limite'
    - pendiente_por_hora: cuánto cambia el parámetro por hora de operación
    - horas_a_limite: horas estimadas hasta alcanzar el límite de alerta (o None)
    - mensaje: texto interpretable para mostrar
    """
    lecturas = lecturas_de(equipo_id, parametro)
    resultado = {
        "parametro": parametro,
        "n_lecturas": len(lecturas),
        "valor_actual": None,
        "unidad": None,
        "estado": "sin_datos",
        "direccion": "alta",
        "pendiente_por_hora": None,
        "horas_a_limite": None,
        "mensaje": "Sin lecturas registradas.",
    }
    if not lecturas:
        return resultado

    ultima = lecturas[-1]
    resultado["valor_actual"] = ultima["valor"]
    resultado["unidad"] = ultima["unidad"]

    limite = obtener_limite(equipo_id, parametro)

    # Estado actual según límites (respeta la dirección: techo 'alta' o piso 'baja')
    if limite:
        lc = limite["limite_critico"]
        la = limite["limite_alerta"]
        direccion = limite.get("direccion") or "alta"
        resultado["direccion"] = direccion
        val = ultima["valor"]
        # 'baja' (piso): peligro al CAER por debajo del umbral; 'alta' (techo): al subir.
        rebasa = (lambda u: val <= u) if direccion == "baja" else (lambda u: val >= u)
        if lc is not None and rebasa(lc):
            resultado["estado"] = "critico"
        elif la is not None and rebasa(la):
            resultado["estado"] = "alerta"
        else:
            resultado["estado"] = "normal"
    else:
        resultado["estado"] = "sin_limite"

    # Tendencia y proyección (requiere >= 2 lecturas con horas de operación)
    puntos = [(l["horas_operacion"], l["valor"]) for l in lecturas if l["horas_operacion"] is not None]
    if len(puntos) >= 2 and len({p[0] for p in puntos}) >= 2:
        xs = [p[0] for p in puntos]
        ys = [p[1] for p in puntos]
        pendiente, _ = _ajuste_lineal(xs, ys)
        resultado["pendiente_por_hora"] = pendiente

        objetivo = None
        if limite:
            objetivo = limite["limite_alerta"] if limite["limite_alerta"] is not None else limite["limite_critico"]

        if objetivo is not None and abs(pendiente) > 1e-9:
            faltante = objetivo - ultima["valor"]
            # avanza hacia el límite solo si la pendiente apunta en esa dirección
            if (faltante > 0 and pendiente > 0) or (faltante < 0 and pendiente < 0):
                horas = faltante / pendiente
                if horas > 0:
                    resultado["horas_a_limite"] = horas

    # Mensaje interpretable
    resultado["mensaje"] = _mensaje(resultado)
    return resultado


def _mensaje(r: dict) -> str:
    u = r["unidad"] or ""
    val = r["valor_actual"]
    if r.get("direccion") == "baja":
        rebase = {
            "critico": "🔴 CRÍTICO: por debajo del límite crítico",
            "alerta": "🟠 ALERTA: por debajo del límite de alerta",
        }
    else:
        rebase = {
            "critico": "🔴 CRÍTICO: supera el límite crítico",
            "alerta": "🟠 ALERTA: supera el límite de alerta",
        }
    estado_txt = {
        **rebase,
        "normal": "🟢 Normal",
        "sin_limite": "ℹ️ Sin límite definido",
        "sin_datos": "Sin datos",
    }[r["estado"]]

    partes = [f"{estado_txt} — valor actual: {val:.1f} {u}".rstrip()]
    if r["horas_a_limite"] is not None:
        partes.append(
            f"Tendencia: alcanzaría el límite en ~{r['horas_a_limite']:.0f} h de operación."
        )
    elif r["pendiente_por_hora"] is not None and abs(r["pendiente_por_hora"]) <= 1e-9:
        partes.append("Tendencia estable.")
    return " ".join(partes)


def analizar_equipo(equipo_id: int) -> list[dict]:
    """Analiza todos los parámetros con lecturas de un equipo."""
    return [analizar_parametro(equipo_id, p) for p in parametros_de(equipo_id)]


def alertas_predictivas() -> list[dict]:
    """Recorre todos los equipos y devuelve los parámetros en estado alerta/crítico
    o con una proyección de alcanzar el límite pronto (< 200 h)."""
    from . import models

    alertas = []
    for eq in models.listar_equipos():
        for a in analizar_equipo(eq["id"]):
            riesgo = a["estado"] in ("alerta", "critico") or (
                a["horas_a_limite"] is not None and a["horas_a_limite"] < 200
            )
            if riesgo:
                alertas.append({"equipo_codigo": eq["codigo"], "equipo_nombre": eq["nombre"], **a})
    # crítico primero, luego por horas al límite
    orden_estado = {"critico": 0, "alerta": 1, "normal": 2, "sin_limite": 3, "sin_datos": 4}
    return sorted(
        alertas,
        key=lambda a: (orden_estado.get(a["estado"], 9), a["horas_a_limite"] or 1e9),
    )

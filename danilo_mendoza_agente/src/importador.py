"""Importación masiva de equipos y órdenes de trabajo desde Excel/CSV.

La lógica de validación es PURA (no toca Streamlit ni, en el caso de equipos,
la base de datos directamente): recibe un DataFrame y devuelve
`(filas_validas, errores)`. Así la interfaz puede mostrar una vista previa con
los problemas ANTES de escribir nada, y la lógica es testeable de forma aislada.

Flujo típico desde la UI:
    df = pd.read_excel(archivo)
    validas, errores = validar_equipos(df, codigos_existentes())
    # ...mostrar vista previa y errores...
    n = importar_equipos(validas)   # solo si el usuario confirma

Las columnas del archivo usan los mismos nombres que los campos de la base de
datos (para órdenes, `equipo_codigo` en lugar del id interno). El cotejo de
encabezados es flexible: ignora mayúsculas, espacios y acentos.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime

import pandas as pd

from . import models

# --- Definición de columnas -------------------------------------------------
# (nombre_columna, obligatoria, ejemplo_para_la_plantilla)
COLUMNAS_EQUIPOS = [
    ("codigo", True, "MOT-010"),
    ("nombre", True, "Motor bomba de agua cruda"),
    ("tipo", False, "Motor eléctrico"),
    ("ubicacion", False, "Casa de máquinas - Nivel 1"),
    ("fabricante", False, "Siemens"),
    ("modelo", False, "1LA7"),
    ("fecha_instalacion", False, "2024-03-15"),
    ("estado", False, "operativo"),
    ("frecuencia_preventivo_dias", False, "90"),
    ("horas_operacion", False, "1200"),
    ("frecuencia_preventivo_horas", False, "4000"),
    ("notas", False, "Equipo de respaldo"),
]

COLUMNAS_ORDENES = [
    ("equipo_codigo", True, "U14"),
    ("tipo", False, "correctivo"),
    ("descripcion", True, "Cambio de filtro de aceite"),
    ("prioridad", False, "media"),
    ("estado", False, "abierta"),
    ("responsable", False, "J. Pérez"),
    ("fecha_programada", False, "2026-07-01"),
]


# --- Helpers ----------------------------------------------------------------
def _normalizar(texto: str) -> str:
    """Minúsculas, sin acentos ni espacios extremos: para cotejar encabezados."""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.strip().lower().replace(" ", "_")


def _texto(valor) -> str:
    """Convierte una celda a texto limpio; NaN/None → ''."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    s = str(valor).strip()
    return "" if s.lower() in ("nan", "nat", "none") else s


def _mapa_columnas(df: pd.DataFrame, columnas) -> dict:
    """Relaciona cada columna esperada con la columna real del DataFrame
    (cotejo flexible). Devuelve {nombre_esperado: nombre_real_o_None}."""
    reales = {_normalizar(c): c for c in df.columns}
    return {nombre: reales.get(_normalizar(nombre)) for nombre, _o, _e in columnas}


def _fila_a_dict(fila, mapa: dict) -> dict:
    """Extrae los campos esperados de una fila usando el mapa de columnas."""
    return {
        nombre: _texto(fila[real]) if real is not None else ""
        for nombre, real in mapa.items()
    }


def _parse_fecha(valor: str) -> tuple[str | None, bool]:
    """Devuelve (fecha_iso, ok). Acepta YYYY-MM-DD y formatos comunes de Excel.
    '' → (None, True): fecha opcional ausente es válida."""
    if not valor:
        return None, True
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y"):
        try:
            return datetime.strptime(valor[:19], fmt).date().isoformat(), True
        except ValueError:
            continue
    return None, False


def _parse_int(valor: str) -> tuple[int | None, bool]:
    if not valor:
        return None, True
    try:
        return int(float(valor)), True
    except ValueError:
        return None, False


def _parse_float(valor: str) -> tuple[float | None, bool]:
    if not valor:
        return None, True
    try:
        return float(valor), True
    except ValueError:
        return None, False


def columnas_faltantes(df: pd.DataFrame, columnas) -> list[str]:
    """Columnas OBLIGATORIAS que no aparecen en el archivo (cotejo flexible)."""
    mapa = _mapa_columnas(df, columnas)
    return [n for n, oblig, _e in columnas if oblig and mapa[n] is None]


# --- Plantillas descargables ------------------------------------------------
def plantilla_df(columnas) -> pd.DataFrame:
    """DataFrame de una fila de ejemplo, con todas las columnas en orden."""
    return pd.DataFrame([{n: ej for n, _o, ej in columnas}], columns=[n for n, _o, _e in columnas])


def plantilla_equipos_df() -> pd.DataFrame:
    return plantilla_df(COLUMNAS_EQUIPOS)


def plantilla_ordenes_df() -> pd.DataFrame:
    return plantilla_df(COLUMNAS_ORDENES)


# --- Catálogos de valores válidos ------------------------------------------
def codigos_existentes() -> set[str]:
    """Códigos de equipo ya registrados, en minúsculas (para detectar choques)."""
    return {(e["codigo"] or "").strip().lower() for e in models.listar_equipos()}


def mapa_codigo_a_id() -> dict[str, int]:
    """{codigo_en_minuscula: equipo_id} para resolver órdenes por código."""
    return {(e["codigo"] or "").strip().lower(): e["id"] for e in models.listar_equipos()}


# --- Validación de EQUIPOS --------------------------------------------------
def validar_equipos(df: pd.DataFrame, ya_existentes: set[str] | None = None):
    """Valida un DataFrame de equipos.

    Devuelve (validas, errores):
      - validas: list[dict] listos para `models.crear_equipo`.
      - errores: list[dict] {fila, campo, problema} (fila = nº de fila de datos,
        1-based, como la ve el usuario en Excel sin contar el encabezado).
    Detecta códigos duplicados tanto contra la base (`ya_existentes`) como
    dentro del propio archivo.
    """
    ya_existentes = {c.lower() for c in (ya_existentes or set())}
    mapa = _mapa_columnas(df, COLUMNAS_EQUIPOS)
    validas: list[dict] = []
    errores: list[dict] = []
    vistos_en_archivo: set[str] = set()

    for i, (_idx, fila) in enumerate(df.iterrows(), start=1):
        d = _fila_a_dict(fila, mapa)
        errs_fila = []

        codigo = d["codigo"]
        if not codigo:
            errs_fila.append(("codigo", "obligatorio (vacío)"))
        else:
            clave = codigo.lower()
            if clave in ya_existentes:
                errs_fila.append(("codigo", f"ya existe en la base ({codigo})"))
            elif clave in vistos_en_archivo:
                errs_fila.append(("codigo", f"duplicado dentro del archivo ({codigo})"))

        if not d["nombre"]:
            errs_fila.append(("nombre", "obligatorio (vacío)"))

        estado = d["estado"] or "operativo"
        if estado not in models.ESTADOS_EQUIPO:
            errs_fila.append(("estado", f"valor inválido '{estado}'; usa uno de {models.ESTADOS_EQUIPO}"))

        fecha_inst, ok = _parse_fecha(d["fecha_instalacion"])
        if not ok:
            errs_fila.append(("fecha_instalacion", f"fecha inválida '{d['fecha_instalacion']}' (usa YYYY-MM-DD)"))

        frec_dias, ok = _parse_int(d["frecuencia_preventivo_dias"])
        if not ok:
            errs_fila.append(("frecuencia_preventivo_dias", f"no es entero '{d['frecuencia_preventivo_dias']}'"))

        horas_op, ok = _parse_float(d["horas_operacion"])
        if not ok:
            errs_fila.append(("horas_operacion", f"no es número '{d['horas_operacion']}'"))

        frec_horas, ok = _parse_int(d["frecuencia_preventivo_horas"])
        if not ok:
            errs_fila.append(("frecuencia_preventivo_horas", f"no es entero '{d['frecuencia_preventivo_horas']}'"))

        if errs_fila:
            errores.extend({"fila": i, "campo": c, "problema": p} for c, p in errs_fila)
            continue

        if codigo:
            vistos_en_archivo.add(codigo.lower())
        validas.append({
            "codigo": codigo,
            "nombre": d["nombre"],
            "tipo": d["tipo"] or None,
            "ubicacion": d["ubicacion"] or None,
            "fabricante": d["fabricante"] or None,
            "modelo": d["modelo"] or None,
            "fecha_instalacion": fecha_inst,
            "estado": estado,
            "frecuencia_preventivo_dias": frec_dias if frec_dias is not None else 90,
            "horas_operacion": horas_op if horas_op is not None else 0.0,
            "frecuencia_preventivo_horas": frec_horas or None,
            "notas": d["notas"] or None,
        })

    return validas, errores


# --- Validación de ÓRDENES --------------------------------------------------
def validar_ordenes(df: pd.DataFrame, cod_a_id: dict[str, int] | None = None):
    """Valida un DataFrame de órdenes contra el catálogo de equipos.

    `cod_a_id` mapea código de equipo (minúscula) → id. Si no se pasa, se lee
    de la base. Devuelve (validas, errores) con el mismo formato que equipos;
    cada fila válida ya trae `equipo_id` resuelto.
    """
    if cod_a_id is None:
        cod_a_id = mapa_codigo_a_id()
    cod_a_id = {k.lower(): v for k, v in cod_a_id.items()}
    mapa = _mapa_columnas(df, COLUMNAS_ORDENES)
    validas: list[dict] = []
    errores: list[dict] = []

    for i, (_idx, fila) in enumerate(df.iterrows(), start=1):
        d = _fila_a_dict(fila, mapa)
        errs_fila = []

        cod = d["equipo_codigo"]
        equipo_id = None
        if not cod:
            errs_fila.append(("equipo_codigo", "obligatorio (vacío)"))
        else:
            equipo_id = cod_a_id.get(cod.lower())
            if equipo_id is None:
                errs_fila.append(("equipo_codigo", f"no existe un equipo con código '{cod}'"))

        if not d["descripcion"]:
            errs_fila.append(("descripcion", "obligatoria (vacía)"))

        tipo = d["tipo"] or "correctivo"
        if tipo not in models.TIPOS_ORDEN:
            errs_fila.append(("tipo", f"valor inválido '{tipo}'; usa uno de {models.TIPOS_ORDEN}"))

        prioridad = d["prioridad"] or "media"
        if prioridad not in models.PRIORIDADES:
            errs_fila.append(("prioridad", f"valor inválido '{prioridad}'; usa uno de {models.PRIORIDADES}"))

        estado = d["estado"] or "abierta"
        if estado not in models.ESTADOS_ORDEN:
            errs_fila.append(("estado", f"valor inválido '{estado}'; usa uno de {models.ESTADOS_ORDEN}"))

        fecha_prog, ok = _parse_fecha(d["fecha_programada"])
        if not ok:
            errs_fila.append(("fecha_programada", f"fecha inválida '{d['fecha_programada']}' (usa YYYY-MM-DD)"))

        if errs_fila:
            errores.extend({"fila": i, "campo": c, "problema": p} for c, p in errs_fila)
            continue

        validas.append({
            "equipo_id": equipo_id,
            "tipo": tipo,
            "descripcion": d["descripcion"],
            "prioridad": prioridad,
            "estado": estado,
            "responsable": d["responsable"] or None,
            "fecha_programada": fecha_prog,
        })

    return validas, errores


# --- Inserción --------------------------------------------------------------
def importar_equipos(validas: list[dict]) -> int:
    """Inserta las filas ya validadas. Devuelve cuántas se crearon."""
    n = 0
    for datos in validas:
        models.crear_equipo(datos)
        n += 1
    return n


def importar_ordenes(validas: list[dict]) -> int:
    """Inserta las órdenes ya validadas. Devuelve cuántas se crearon."""
    n = 0
    for datos in validas:
        models.crear_orden(datos)
        n += 1
    return n

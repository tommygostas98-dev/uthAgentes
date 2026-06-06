"""Programa de mantenimiento preventivo del fabricante (catálogo del Cap. 4) y
cálculo de las próximas tareas según las horas de operación del equipo.

El catálogo se carga con `cargar_plan_mantenimiento.py` en la tabla
`plan_mantenimiento`, ligado al MODELO del motor (p. ej. 'W46').

NOTA sobre el cálculo: el sistema no registra (todavía) la fecha/horas de la
última vez que se ejecutó cada tarea individual. Por eso el cálculo muestra la
PRÓXIMA ocurrencia de cada tarea según las horas actuales del equipo, asumiendo
que el plan se ha cumplido al día. No es un "vencido" real por tarea.
"""

import math

from . import models
from .database import get_connection


def modelo_plan(modelo_equipo: str | None) -> str:
    """Mapea el modelo de un equipo al modelo del plan de mantenimiento.

    La familia Wärtsilä 46 (W46, 18V46, 12V46, 16V46, ...) comparte el plan 'W46'.
    """
    if modelo_equipo and "46" in modelo_equipo.upper():
        return "W46"
    return modelo_equipo or "W46"


def listar_plan(modelo: str = "W46") -> list[dict]:
    """Devuelve todas las tareas del plan de un modelo, ordenadas por intervalo."""
    conn = get_connection()
    filas = conn.execute(
        "SELECT * FROM plan_mantenimiento WHERE modelo = ? ORDER BY orden, componente",
        (modelo,),
    ).fetchall()
    conn.close()
    return [dict(f) for f in filas]


def tareas_por_horas(modelo: str = "W46") -> list[dict]:
    """Tareas cuyo intervalo es por horas de operación."""
    return [t for t in listar_plan(modelo) if t["intervalo_horas"] is not None]


def tareas_calendario(modelo: str = "W46") -> list[dict]:
    """Tareas de rutina por calendario (diario / cada 2 días / semanal)."""
    return [t for t in listar_plan(modelo) if t["intervalo_calendario"]]


def modelos_con_plan() -> list[str]:
    """Lista los modelos que tienen un plan cargado."""
    conn = get_connection()
    filas = conn.execute(
        "SELECT DISTINCT modelo FROM plan_mantenimiento ORDER BY modelo"
    ).fetchall()
    conn.close()
    return [f["modelo"] for f in filas]


def calcular_tareas(equipo_id: int) -> dict:
    """Calcula el estado del plan por horas para un equipo concreto.

    Para cada tarea con intervalo I y horas de operación actuales H:
      - proxima_h    = menor múltiplo de I mayor que H  = ceil(H/I) * I
      - restantes_h  = proxima_h - H   (horas que faltan para la próxima)
      - ciclos       = H // I          (cuántas veces ya debió ejecutarse)

    Devuelve un dict con:
      - equipo, modelo, horas
      - tareas:     lista por-horas ordenada por restantes_h (la más próxima primero)
      - calendario: tareas de rutina (no dependen de horas)
    Devuelve {} si el equipo no existe.
    """
    eq = models.obtener_equipo(equipo_id)
    if not eq:
        return {}

    modelo = modelo_plan(eq.get("modelo"))
    horas = float(eq.get("horas_operacion") or 0)

    tareas = []
    for t in tareas_por_horas(modelo):
        intervalo = t["intervalo_horas"]
        ciclos = int(horas // intervalo)
        proxima = (ciclos + 1) * intervalo
        tareas.append(
            {
                **t,
                "proxima_h": proxima,
                "restantes_h": proxima - horas,
                "ciclos": ciclos,
            }
        )
    tareas.sort(key=lambda x: x["restantes_h"])

    return {
        "equipo": eq,
        "modelo": modelo,
        "horas": horas,
        "tareas": tareas,
        "calendario": tareas_calendario(modelo),
    }


def proximas_tareas(equipo_id: int, horizonte_horas: float = 500) -> list[dict]:
    """Tareas por horas que vencen dentro del horizonte indicado (en horas)."""
    data = calcular_tareas(equipo_id)
    return [t for t in data.get("tareas", []) if t["restantes_h"] <= horizonte_horas]

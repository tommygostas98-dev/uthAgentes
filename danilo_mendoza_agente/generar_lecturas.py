"""generar_lecturas.py — Generador de archivos `lecturas_nuevas_W##.csv`.

Simula NUEVAS lecturas de sensores del motor U14 (Wärtsilä 18V46, planta
PAVANA III) para alimentar al vigía (vigilancia_alertas.py / motovigia.py).
Continúa la serie temporal donde la dejó `lecturas_nuevas_W46.csv` (mismas
horas de operación y fechas, mismo formato de columnas).

Cada archivo simula UN escenario de falla, para mostrar por separado cada
detector del sistema:

  - devanado_critico : temperatura_devanado_A sube y cruza el crítico (155 °C)
                       -> LÍMITE 'alta'  => predictivo CRÍTICO
  - presion_baja     : presion_aceite cae bajo el piso (alerta 3.0 / crít 2.0)
                       -> LÍMITE 'baja'  => predictivo CRÍTICO
  - salto_escape     : temperatura_gases_escape da un pico súbito y vuelve
                       -> ANOMALÍA/SALTO (estadístico, sin depender de límites)
  - normal           : todo estable dentro de rango (control: NO debe alarmar)

El modo 'auto' (por defecto) asigna a cada semana un escenario distinto:
  W47 -> devanado_critico,  W48 -> presion_baja,  W49 -> salto_escape,
  y de ahí en adelante cicla esos tres (W50, W51, W52, ...).

Formato de salida (idéntico a lecturas_nuevas_W46.csv):
    parametro,valor,unidad,horas_operacion,fecha

Uso:
    python generar_lecturas.py W47 W48 W49          # variado (auto), a _simulaciones/
    python generar_lecturas.py W50 --escenario normal
    python generar_lecturas.py W47 --escenario presion_baja --lecturas 8
    python generar_lecturas.py W47 W48 W49 --desplegar   # ¡escribe en la carpeta
                                                          #  VIGILADA (dispara el vigía)!

POR SEGURIDAD: por defecto los archivos se generan en la subcarpeta
`_simulaciones/` (que el vigía NO vigila). Para que el vigía los procese, muévelos
a la carpeta del proyecto, o usa --desplegar (avisa antes, porque el vigía
reaccionará: importa las lecturas y envía la alarma).
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
DIR_STAGING = BASE / "_simulaciones"

# --- Anclas de continuidad: dónde terminó W46 -------------------------------
# W46: 6 lecturas diarias, horas 16400..16600 (+40/lectura), fechas 2026-05-29..06-03.
ANCLA_SEMANA = 46
ANCLA_HORAS_INICIO = 16400      # primera hora de W46
PASO_HORAS = 40                 # incremento de horas_operacion por lectura
LECTURAS_POR_SEMANA = 6         # nº de lecturas (días) que ocupa cada semana
ANCLA_FECHA = date(2026, 5, 29)  # primera fecha de W46

# --- Parámetros y su línea base SANA ----------------------------------------
# (parametro, unidad, base_sana, amplitud_ruido). El ruido es pequeño y
# determinista (no cruza límites ni crea saltos): para una semana "normal".
PARAMS: list[tuple[str, str, float, float]] = [
    ("temperatura_devanado_A",  "C",   122.0, 1.0),
    ("temperatura_devanado_B",  "C",   121.0, 1.0),
    ("temperatura_devanado_C",  "C",   120.0, 1.0),
    ("temperatura_aceite",      "C",    66.0, 1.0),
    ("temperatura_agua",        "C",    97.0, 1.0),
    ("temperatura_agua_LT",     "C",    44.0, 1.0),
    ("temperatura_aire_carga",  "C",    60.0, 1.0),
    ("temperatura_gases_escape", "C",  446.0, 2.0),
    ("presion_aceite",          "bar",   4.3, 0.1),
    ("presion_aceite_turbo_A",  "bar",   3.8, 0.1),
    ("vibracion_motor",         "mm/s",  2.9, 0.1),
]

# Pequeño patrón de variación (no negativo, sin escalones grandes): da realismo
# a la serie "sana" sin disparar el detector de saltos ni cruzar un límite.
_WIGGLE = [0, 1, 1, 0, 1, 0]

ESCENARIOS = ("auto", "devanado_critico", "presion_baja", "salto_escape", "normal")
_CICLO = ["devanado_critico", "presion_baja", "salto_escape"]
_MAPA_VARIADO = {47: "devanado_critico", 48: "presion_baja", 49: "salto_escape"}


# --- Generadores de series --------------------------------------------------
def _serie_estable(base: float, amp: float, n: int) -> list[float]:
    """Serie sana: base + ruidito determinista (se mantiene dentro de rango)."""
    return [round(base + amp * _WIGGLE[i % len(_WIGGLE)], 1) for i in range(n)]


def _rampa(inicio: float, fin: float, n: int) -> list[float]:
    """Rampa lineal de `inicio` a `fin` en `n` puntos (incluye ambos extremos)."""
    if n == 1:
        return [round(fin, 1)]
    paso = (fin - inicio) / (n - 1)
    return [round(inicio + paso * i, 1) for i in range(n)]


def escenario_de_semana(n: int) -> str:
    """Escenario que el modo 'auto' (variado) asigna a la semana n."""
    if n in _MAPA_VARIADO:
        return _MAPA_VARIADO[n]
    return _CICLO[(n - 47) % len(_CICLO)] if n >= 47 else "normal"


def construir_series(escenario: str, n: int) -> dict[str, list[float]]:
    """Devuelve {parametro: [valores...]} para `n` lecturas, según el escenario.

    Todos los parámetros arrancan en su línea base SANA; el escenario solo
    reemplaza la serie del parámetro protagonista de la falla.
    """
    series = {p: _serie_estable(base, amp, n) for p, _u, base, amp in PARAMS}

    if escenario == "normal":
        pass

    elif escenario == "devanado_critico":
        # Sube desde justo por encima de donde quedó W46 (149) y cruza el
        # crítico (155). Termina ~182 °C: CRÍTICO inequívoco.
        series["temperatura_devanado_A"] = _rampa(154.0, 154.0 + 5.6 * (n - 1), n)

    elif escenario == "presion_baja":
        # Cae desde 3.8 y termina en ~1.9 bar: cruza alerta (3.0) y crítico (2.0).
        # Es límite 'baja' (peligro al CAER). El turbo se mantiene sano.
        series["presion_aceite"] = _rampa(3.8, 1.9, n)

    elif escenario == "salto_escape":
        # Pico súbito a mitad de la serie y regreso a lo normal: lo atrapa el
        # detector estadístico de SALTO, no el de límite (la última lectura
        # vuelve a rango). El valor del pico se fija tras verificarlo (ver abajo).
        mitad = n // 2
        serie = _serie_estable(446.0, 2.0, n)
        serie[mitad] = 510.0   # pico (< 550 crítico); regresa a ~446 después
        series["temperatura_gases_escape"] = serie

    else:
        raise ValueError(f"escenario desconocido: {escenario!r}")

    return series


# --- Continuidad temporal ---------------------------------------------------
def horas_y_fechas(n_semana: int, n_lecturas: int) -> tuple[list[int], list[str]]:
    """Horas de operación y fechas para la semana `n_semana`, continuando W46."""
    offset_lecturas = (n_semana - ANCLA_SEMANA) * LECTURAS_POR_SEMANA
    horas = [ANCLA_HORAS_INICIO + (offset_lecturas + i) * PASO_HORAS
             for i in range(n_lecturas)]
    fechas = [(ANCLA_FECHA + timedelta(days=offset_lecturas + i)).isoformat()
              for i in range(n_lecturas)]
    return horas, fechas


# --- Escritura del CSV ------------------------------------------------------
def escribir_csv(ruta: Path, series: dict[str, list[float]],
                 horas: list[int], fechas: list[str]) -> int:
    """Escribe el CSV en orden por parámetro (como W46). Devuelve nº de filas."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    unidad = {p: u for p, u, _b, _a in PARAMS}
    filas = 0
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["parametro", "valor", "unidad", "horas_operacion", "fecha"])
        for parametro, _u, _b, _a in PARAMS:        # respeta el orden de PARAMS
            valores = series[parametro]
            for i, valor in enumerate(valores):
                w.writerow([parametro, f"{valor:.1f}", unidad[parametro],
                            horas[i], fechas[i]])
                filas += 1
    return filas


def _parsear_semana(token: str) -> int:
    """'W47' / 'w47' / '47' -> 47."""
    t = token.strip().lower().lstrip("w")
    if not t.isdigit():
        raise argparse.ArgumentTypeError(f"semana inválida: {token!r} (usa W47, 47, ...)")
    return int(t)


def _alarma_esperada(escenario: str) -> str:
    return {
        "devanado_critico": "PREDICTIVO CRÍTICO en temperatura_devanado_A (límite 'alta')",
        "presion_baja": "PREDICTIVO CRÍTICO en presion_aceite (límite 'baja')",
        "salto_escape": "ANOMALÍA ALTA (salto) en temperatura_gases_escape",
        "normal": "ninguna (operación normal / control)",
    }[escenario]


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Genera archivos lecturas_nuevas_W##.csv para simular nuevas lecturas.")
    ap.add_argument("semanas", nargs="+", type=_parsear_semana,
                    help="semanas a generar, p. ej. W47 W48 W49")
    ap.add_argument("--escenario", choices=ESCENARIOS, default="auto",
                    help="escenario a usar (default: auto = variado por semana)")
    ap.add_argument("--lecturas", type=int, default=LECTURAS_POR_SEMANA,
                    help=f"nº de lecturas por archivo (default {LECTURAS_POR_SEMANA})")
    ap.add_argument("--salida", type=Path, default=None,
                    help="carpeta de salida (default: _simulaciones/)")
    ap.add_argument("--desplegar", action="store_true",
                    help="escribe en la carpeta VIGILADA del proyecto (¡el vigía reaccionará!)")
    args = ap.parse_args()

    # La consola de Windows suele ser cp1252: evita que un carácter no mapeable
    # tumbe el script al imprimir.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    if args.salida is not None:
        destino = args.salida
    elif args.desplegar:
        destino = BASE
    else:
        destino = DIR_STAGING

    if destino.resolve() == BASE.resolve():
        print("[AVISO] Escribiendo en la carpeta VIGILADA del proyecto.")
        print("    El vigia detectara cada archivo en ~2 s: importara las lecturas")
        print("    y enviara la alarma (correo/MCP). Usalo solo para el demo real.\n")

    for n in args.semanas:
        escenario = escenario_de_semana(n) if args.escenario == "auto" else args.escenario
        series = construir_series(escenario, args.lecturas)
        horas, fechas = horas_y_fechas(n, args.lecturas)
        nombre = f"lecturas_nuevas_W{n}.csv"
        ruta = destino / nombre
        filas = escribir_csv(ruta, series, horas, fechas)
        print(f"[OK] {nombre}  [{escenario}]")
        print(f"    {filas} filas | horas {horas[0]}-{horas[-1]} | fechas {fechas[0]}..{fechas[-1]}")
        print(f"    alarma esperada: {_alarma_esperada(escenario)}")
        print(f"    -> {ruta}")
    print(f"\nListo: {len(args.semanas)} archivo(s) en {destino}")
    if destino.resolve() != BASE.resolve():
        print("Para el demo, mueve el archivo a la carpeta del proyecto (el vigía lo procesará),")
        print("o regenera con --desplegar.")


if __name__ == "__main__":
    main()

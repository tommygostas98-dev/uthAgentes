"""reiniciar_baseline_u14.py — Deja las lecturas OPERATIVAS de U14 en una línea
base SANA, para demos limpios ("1 falla por archivo").

Pasos (en orden):
  1) RESPALDA la base de datos -> data/mantenimiento.db.bak-<sello>  (reversible).
  2) BORRA todas las lecturas operativas (sensores) de U14, CONSERVANDO el
     análisis de aceite de laboratorio (parámetros 'aceite_*'). NO toca equipos,
     límites, configuración ni los datos de otros equipos.
  3) SIEMBRA una línea base SANA (valores normales, estables) para los parámetros
     del demo, terminando justo donde arranca W47 (≈16600 h / 2026-06-03), para
     dar continuidad.

Tras correrlo, `notificaciones.alertas_criticas()` debe quedar VACÍO; así, al
soltar un archivo de escenario (W47/W48/W49) solo aparece SU falla. Pensado para
correrlo ENTRE escenarios (resetear -> soltar un archivo -> observar -> repetir).

Uso:
    python reiniciar_baseline_u14.py             # respalda + resetea + siembra
    python reiniciar_baseline_u14.py --solo-respaldo
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "mantenimiento.db"

# Reutiliza la definición de parámetros y la serie sana del generador (DRY).
from generar_lecturas import PARAMS, _serie_estable  # noqa: E402

# La base termina donde arranca W47, para dar continuidad a la serie.
N_BASELINE = 10          # nº de lecturas sanas por parámetro
PASO_HORAS = 40
FIN_HORAS = 16600        # última hora de operación de la base (= fin de W46)
FIN_FECHA = date(2026, 6, 3)
EQUIPO = "U14"


def respaldar() -> Path:
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = DB.with_name(f"mantenimiento.db.bak-{sello}")
    shutil.copy2(DB, bak)
    return bak


def main() -> None:
    ap = argparse.ArgumentParser(description="Reinicia U14 a una línea base sana (con respaldo).")
    ap.add_argument("--solo-respaldo", action="store_true",
                    help="solo hace la copia de seguridad; no borra ni siembra nada")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    if not DB.exists():
        raise SystemExit(f"No existe la base de datos: {DB}")

    bak = respaldar()
    print(f"[OK] Respaldo creado: data/{bak.name}")
    if args.solo_respaldo:
        print("Solo respaldo: no se borró ni sembró nada.")
        return

    con = sqlite3.connect(DB)
    fila = con.execute("SELECT id FROM equipos WHERE lower(codigo)=lower(?)", (EQUIPO,)).fetchone()
    if not fila:
        con.close()
        raise SystemExit(f"No se encontró el equipo {EQUIPO}.")
    uid = fila[0]

    # 1) Borra TODAS las operativas (todo salvo el laboratorio de aceite 'aceite*').
    borradas = con.execute(
        "DELETE FROM lecturas WHERE equipo_id=? AND parametro NOT LIKE 'aceite%'",
        (uid,),
    ).rowcount

    # 2) Siembra la línea base sana de los parámetros del demo, terminando en FIN_HORAS.
    horas = [FIN_HORAS - (N_BASELINE - 1 - i) * PASO_HORAS for i in range(N_BASELINE)]
    fechas = [(FIN_FECHA - timedelta(days=N_BASELINE - 1 - i)).isoformat() for i in range(N_BASELINE)]
    sembradas = 0
    for parametro, unidad, base, amp in PARAMS:
        valores = _serie_estable(base, amp, N_BASELINE)
        for i in range(N_BASELINE):
            con.execute(
                "INSERT INTO lecturas (equipo_id, parametro, valor, unidad, horas_operacion, fecha) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (uid, parametro, valores[i], unidad, horas[i], fechas[i]),
            )
            sembradas += 1
    con.commit()
    con.close()
    print(f"[OK] Borradas {borradas} lectura(s) operativa(s) de {EQUIPO}; "
          f"sembradas {sembradas} de baseline ({N_BASELINE} x {len(PARAMS)} parametros).")
    print(f"     Baseline: horas {horas[0]}-{horas[-1]} | fechas {fechas[0]}..{fechas[-1]}")

    # 3) Verifica que quedó limpio.
    from dotenv import load_dotenv
    load_dotenv(BASE / ".env")
    from src import notificaciones as n
    crit = n.alertas_criticas()
    print(f"[VERIF] alertas_criticas() tras el reset: {len(crit)}")
    for c in crit:
        print("   -", c[:100])
    if not crit:
        print("Listo: BD limpia. Cada archivo de escenario mostrara ahora SOLO su falla.")
    else:
        print("AVISO: quedaron alertas; revisa si vienen de otro equipo o de preventivo.")


if __name__ == "__main__":
    main()

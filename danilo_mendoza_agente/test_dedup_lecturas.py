"""Pruebas de la deduplicación en `predictivo.importar_lecturas`.

Usa una base de datos SQLite temporal (no toca la real). Correr:
    python test_dedup_lecturas.py
"""
import tempfile
from pathlib import Path

from src import database


def _ok(cond, msg):
    print(("OK  " if cond else "FALLO ") + msg)
    assert cond, msg


# --- Parte pura: la clave de deduplicación ---------------------------------
def test_clave_dedup():
    from src import predictivo as P
    # Con horas: la clave ignora la fecha (que la BD auto-estampa).
    k1 = P._clave_dedup("temp", 100.0, "2026-06-03 19:39:11", 80.0)
    k2 = P._clave_dedup("temp", 100.0, "2026-06-03 19:40:22", 80.0)
    _ok(k1 == k2, "clave: con horas, la misma lectura coincide aunque cambie la fecha")
    # Distinta hora o distinto valor => clave distinta.
    _ok(k1 != P._clave_dedup("temp", 160.0, None, 80.0), "clave: distinta hora => distinta")
    _ok(k1 != P._clave_dedup("temp", 100.0, None, 81.0), "clave: distinto valor => distinta")
    # Ruido de punto flotante no debe romper la coincidencia.
    _ok(P._clave_dedup("p", 0.1 + 0.2, None, 1.0) == P._clave_dedup("p", 0.3, None, 1.0),
        "clave: tolera ruido de punto flotante en las horas")
    # Sin horas pero con fecha explícita: la fecha ancla la clave.
    _ok(P._clave_dedup("p", None, "2026-06-03", 5.0) is not None, "clave: usa fecha explícita si no hay horas")
    # Sin ancla temporal: no se puede deduplicar => None.
    _ok(P._clave_dedup("p", None, None, 5.0) is None, "clave: sin horas ni fecha => None (no deduplica)")


# --- Parte con BD: reimportar el mismo lote no duplica ----------------------
def test_reimportar_no_duplica():
    # Redirige la BD a un archivo temporal y la inicializa desde cero.
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    database.DB_DIR = tmp.parent
    database.DB_PATH = tmp
    database.init_db()
    from src import predictivo as P, models

    eq = models.crear_equipo({"codigo": "TST-1", "nombre": "Equipo de prueba"})

    lote = [
        {"parametro": "temp", "valor": 80.0, "unidad": "C", "horas_operacion": 100},
        {"parametro": "temp", "valor": 82.0, "unidad": "C", "horas_operacion": 160},
        {"parametro": "temp", "valor": 96.0, "unidad": "C", "horas_operacion": 220},
    ]

    r1 = P.importar_lecturas(eq, lote)
    _ok(r1["insertados"] == 3, "1ª importación: inserta las 3 lecturas")
    _ok(r1["duplicados"] == [], "1ª importación: sin duplicados")

    r2 = P.importar_lecturas(eq, lote)          # mismo lote otra vez
    _ok(r2["insertados"] == 0, "2ª importación: NO inserta nada")
    _ok(len(r2["duplicados"]) == 3, "2ª importación: las 3 marcadas como duplicadas")
    _ok(len(P.lecturas_de(eq, "temp")) == 3, "la BD sigue con 3 lecturas, no 6")

    # Lote mixto: 1 repetida + 1 nueva => 1 insertada, 1 duplicada.
    mixto = [
        {"parametro": "temp", "valor": 96.0, "horas_operacion": 220},   # repetida
        {"parametro": "temp", "valor": 110.0, "horas_operacion": 280},  # nueva
    ]
    r3 = P.importar_lecturas(eq, mixto)
    _ok(r3["insertados"] == 1, "lote mixto: inserta solo la nueva")
    _ok(len(r3["duplicados"]) == 1, "lote mixto: marca la repetida como duplicada")

    # Duplicado DENTRO del mismo archivo (misma lectura dos veces en un lote).
    intra = [
        {"parametro": "vib", "valor": 2.5, "horas_operacion": 300},
        {"parametro": "vib", "valor": 2.5, "horas_operacion": 300},
    ]
    r4 = P.importar_lecturas(eq, intra)
    _ok(r4["insertados"] == 1, "intra-archivo: inserta una sola vez")
    _ok(len(r4["duplicados"]) == 1, "intra-archivo: la segunda copia se marca duplicada")


if __name__ == "__main__":
    test_clave_dedup()
    test_reimportar_no_duplica()
    print("\nTODOS LOS TESTS DE DEDUPLICACION PASARON")

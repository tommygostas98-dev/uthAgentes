"""Carga los límites oficiales del fabricante (Wärtsilä 46) en la tabla `limites`.

Fuente: "_datos/Manual de instruccion Motor W46.pdf" (instalación PA-III, motor 18V46).
        (archivo privado, no expuesto en la app)
- Datos de operación recomendados ......... Cap. 1.2 (pág. física 52, pág. manual 01-2)
- Holguras y límites de desgaste para V46 .. Cap. 6.2 (págs. físicas 178-185, manual 06-2..06-9)

ALCANCE: solo se cargan parámetros donde "más alto = peligro" (encaja con la
lógica actual de predictivo.py, que marca alerta/crítico cuando valor >= límite).
Los límites de presión (donde el peligro es que el valor BAJE) NO se cargan aquí;
requieren extender el modelo con una dirección 'baja' (pendiente).

Convención: limite_alerta = umbral de aviso, limite_critico = umbral de paro/desecho.
Es idempotente: usa ON CONFLICT (equipo_id, parametro) -> actualiza.

Uso:  python cargar_limites_manual.py
"""

from src.predictivo import definir_limite
from src import models

# (parametro, limite_alerta, limite_critico, unidad, fuente)
LIMITES_W46 = [
    # --- Cap. 1.2  Datos de operación (temperaturas, más alto = peligro) ---
    #  parametro                    alerta  critico  unidad        fuente
    ("temperatura_aceite",           70.0,   80.0,   "C",   "Manual 01-2: Lub oil before engine (alarma 70 / paro 80)"),
    ("temperatura_agua_HT",         105.0,  110.0,   "C",   "Manual 01-2: HT water after engine (alarma 105 / paro 110)"),
    ("temperatura_aire_carga",       75.0,   None,   "C",   "Manual 01-2: Charge air in air receiver (alarma 75)"),
    ("temperatura_gases_escape",    490.0,  550.0,   "C",   "Manual 01-2: Exhaust gas after cylinder (alarma 490 / paro 550)"),

    # --- Cap. 6.2  Holguras / límites de desgaste (la holgura crece con el desgaste) ---
    # Cuando el manual da columna 'Wear limit', se usa como crítico y el máx. nominal como alerta.
    ("holgura_cojinete_bancada",         0.570,  None,  "mm", "Manual 06-2: Main bearing clearance, máx nominal 0.570 (sin wear limit publicado)"),
    ("holgura_cojinete_biela",           0.580,  None,  "mm", "Manual 06-3: Big end bearing clearance, máx nominal 0.580 (sin wear limit publicado)"),
    ("holgura_axial_cojinete_empuje",    1.050,  1.500, "mm", "Manual 06-2: Thrust bearing axial clearance (nom máx 1.050 / wear 1.500)"),
    ("holgura_cojinete_arbol_levas",     0.362,  0.400, "mm", "Manual 06-2: Camshaft bearing clearance (nom máx 0.362 / wear 0.400)"),
    ("holgura_axial_empuje_arbol_levas", 0.440,  0.700, "mm", "Manual 06-2: Camshaft thrust bearing axial clearance (nom máx 0.440 / wear 0.700)"),
    ("holgura_vastago_valvula",          0.199,  0.450, "mm", "Manual 06-4: Valve stem clearance (nom máx 0.199 / wear 0.450)"),
    ("holgura_cojinete_eng_intermedio",  0.350,  0.500, "mm", "Manual 06-5: Intermediate gear bearing clearance (nom máx 0.350 / wear 0.5)"),
    ("luz_aro_compresion_1",             1.500,  3.000, "mm", "Manual 06-3: Piston ring gap, compression ring 1 (nom máx 1.50 / wear 3.0)"),
    ("luz_aro_compresion_2",             2.600,  3.000, "mm", "Manual 06-3: Piston ring gap, compression ring 2 (nom máx 2.60 / wear 3.0)"),
    ("luz_aro_rascador_aceite",          1.950,  3.000, "mm", "Manual 06-3: Piston ring gap, oil scraper ring (nom máx 1.95 / wear 3.0)"),
]


def equipo_id_por_codigo(codigo: str) -> int:
    for e in models.listar_equipos():
        if e["codigo"] == codigo:
            return e["id"]
    raise SystemExit(f"No se encontró el equipo con código {codigo!r}")


def main():
    eq_id = equipo_id_por_codigo("U14")
    print(f"Cargando límites oficiales W46 en equipo U14 (id={eq_id})...\n")
    for parametro, alerta, critico, unidad, fuente in LIMITES_W46:
        definir_limite(eq_id, parametro, alerta, critico, unidad)
        crit = f"{critico}" if critico is not None else "—"
        print(f"  ✓ {parametro:34s} alerta={alerta:<7} critico={crit:<7} {unidad}")
        print(f"      ({fuente})")
    print(f"\nListo: {len(LIMITES_W46)} límites cargados/actualizados.")


if __name__ == "__main__":
    main()

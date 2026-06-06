"""Carga el programa de mantenimiento del fabricante (Wärtsilä 46) en la tabla
`plan_mantenimiento`.

Fuente: "_datos/Manual de instruccion Motor W46.pdf" (privado), Cap. 4 "Maintenance schedule"
        (4.2 Maintenance schedule for HFO operation), págs. físicas 119-128
        (manual 04-1 .. 04-10). Aplica a operación con HFO (combustible pesado),
        que es el caso de la planta PA-III.

ALCANCE: catálogo consultable del programa preventivo, ligado al MODELO 'W46'
(aplica a la U14 y a cualquier otro motor W46). No incluye lógica de cálculo de
vencimientos ni interfaz; eso queda como paso siguiente.

La última columna 'seccion_manual' remite a los capítulos del manual a leer
ANTES de ejecutar cada tarea (como indica la nota 1 del Cap. 4.1).

Es idempotente: borra las filas previas del modelo y vuelve a insertarlas.

Uso:  python cargar_plan_mantenimiento.py
"""

from src.database import get_connection, init_db

MODELO = "W46"

# Orden de las tareas de calendario (van antes que las de horas).
ORDEN_CAL = {"diario": 1, "cada_2_dias": 2, "semanal": 3}

# Cada bloque: (intervalo_horas, intervalo_calendario, [ (componente, tarea, seccion), ... ])
# intervalo_horas y intervalo_calendario son mutuamente excluyentes (uno es None).
PLAN = [
    # ---------------- Rutinas de calendario ----------------
    (None, "diario", [
        ("Air coolers", "Comprobar el drenaje de los enfriadores de aire (tubo de drenaje abierto, sin fugas)", "3.6.2, 15"),
        ("Enfriadores/filtros de aire de carga, filtros de combustible y aceite", "Comprobar indicadores de caída de presión; cambiar cartuchos si la caída es alta", "3.6.2, 17, 18"),
        ("Instrumentos (manómetros y termómetros)", "Tomar y registrar todas las lecturas de temperatura y presión a la misma carga", "3.6.2"),
        ("Gobernador / actuador", "Comprobar nivel de aceite del gobernador y buscar fugas", "2, 22"),
        ("Sistema de inyección y combustible", "Comprobar la cantidad de combustible de fuga de bombas e inyectores", "3.6.2, 17"),
        ("Turbocompresor", "Lavado con agua del compresor", "15"),
        ("Turbocompresor", "Comprobar niveles de aceite del turbo y buscar fugas", "15, 2"),
        ("Sistema de agua de refrigeración", "Comprobar nivel de agua (tanque de expansión / presión estática)", "19"),
        ("Sistema de aceite lubricante", "Comprobar nivel de aceite lubricante", "18"),
        ("Detector de neblina de aceite (OMD)", "Observar funcionamiento normal", "—"),
        ("Sistema neumático", "Drenar el agua condensada", "21.5"),
        ("Mecanismo de control", "Comprobar libre movimiento", "22"),
    ]),
    (None, "cada_2_dias", [
        ("Cigüeñal", "Con el motor parado, girar el cigüeñal a una nueva posición", "3"),
    ]),
    (None, "semanal", [
        ("Proceso de arranque", "Arranque de prueba (si el motor está en stand-by)", "3"),
    ]),

    # ---------------- Intervalos por horas de operación ----------------
    (100, None, [
        ("Turbocompresor (TPL)", "Lavado con agua de la turbina (más a menudo si es necesario)", "15"),
    ]),
    (250, None, [
        ("Mecanismo de control", "Inspección visual y lubricación del mecanismo de control y cremalleras de combustible", "16.2.2, 22"),
        ("Turbocompresor (VTR, Napier)", "Lavado con agua de la turbina", "15"),
        ("Filtro(s) de aire (turbo Napier)", "Limpiar filtro(s) de aire del turbo según el fabricante", "15"),
        ("Filtro centrífugo (opcional)", "Limpiar filtro centrífugo (abrir la válvula previa tras la limpieza)", "18"),
    ]),
    (500, None, [
        ("Agua de refrigeración", "Comprobar calidad del agua (contenido de aditivos)", "19, 2"),
        ("Presión de cilindros", "Comprobar presión de cilindros (registrar presiones de combustión y parámetros)", "12, 3.6.4"),
        ("Aceite lubricante", "Tomar muestra de aceite para análisis de laboratorio", "2.2.3"),
        ("Acumulador de baja presión (opcional)", "Comprobar presión de aire del acumulador de baja", "18"),
        ("Válvula waste gate (opcional)", "Comprobación de funcionamiento", "15"),
        ("Válvula by-pass (opcional)", "Comprobación de funcionamiento", "15"),
        ("Detector de neblina de aceite (OMD)", "Comprobación de funcionamiento", "—"),
    ]),
    (1000, None, [
        ("Filtro(s) de aire (turbo VTR)", "Limpiar filtro(s) de aire del turbo según el fabricante", "15"),
        ("Pernos de anclaje del motor", "Comprobar el apriete (en instalaciones nuevas)", "—"),
    ]),
    (1500, None, [
        ("Turbocompresor (sist. de aceite separado)", "Cambiar el aceite lubricante del turbo (no mezclar con el del motor)", "2, 15"),
    ]),
    (2000, None, [
        ("Instrumentos de medición", "Comprobar manómetros, sensores y cableado; reemplazar los defectuosos", "23"),
        ("Sistemas de seguridad y control", "Comprobación funcional de alarmas y paros automáticos", "23, 1"),
        ("Gobernador", "Cambiar el aceite lubricante del gobernador", "2, 22"),
        ("Dispositivo mecánico de sobrevelocidad", "Comprobar función y velocidad de disparo", "22, 6"),
        ("Dispositivo electro-neumático de sobrevelocidad", "Comprobar función y velocidad de disparo", "22, 6"),
        ("Válvulas", "Comprobar holguras de yugo y de válvulas", "6, 12"),
        ("Rotadores de válvula", "Inspección visual", "12"),
        ("Mecanismo de control", "Comprobar mecanismo de control y cremalleras (desgaste y libre movimiento)", "22.1.2"),
        ("Detector de neblina de aceite (OMD)", "Cambiar el filtro de aire fresco", "—"),
    ]),
    (2500, None, [
        ("Turbocompresor (sist. de aceite separado)", "Cambiar el aceite lubricante del turbo (no mezclar con el del motor)", "2, 15"),
    ]),
    (3000, None, [
        ("Válvulas de inyección", "Probar inyectores (presión de apertura); reemplazar o-rings exteriores", "16.6"),
    ]),
    (4000, None, [
        ("Cigüeñal", "Comprobar alineación del cigüeñal (form. 4611V005, motor caliente)", "11"),
        ("Acumulador de baja presión (opcional)", "Comprobar estado de la membrana del acumulador de baja", "18"),
        ("Montaje flexible (si se usa)", "Comprobar alineación y apriete de los elementos de goma de empuje", "Documentos técnicos"),
    ]),
    (6000, None, [
        ("Enfriadores de aire", "Limpiar enfriador(es) de aire de carga (según caída de presión)", "15"),
        ("Válvulas de inyección", "Inspeccionar inyectores (cambiar toberas, comprobar lift de aguja, resortes, o-rings, ajustar presión)", "16.5"),
        ("Colector de escape", "Comprobar fuelles de expansión y soportes; reemplazar si es necesario", "20"),
        ("Conexiones flexibles de tubería", "Inspeccionar (marina) / seguir el plan de la instalación (planta eléctrica)", "—"),
    ]),
    (8000, None, [
        ("Dispositivo de viraje (turning device)", "Engrasar el eje secundario del engranaje de viraje", "3.1.2"),
        ("Turbocompresores Napier", "Desmontar y limpiar el turbo completo; revisar cojinetes", "15, 19"),
        ("Sistema de combustible", "Comprobar el ajuste de la válvula de control de presión", "17"),
        ("Detector de neblina de aceite (OMD)", "Reemplazar el filtro de aire de alimentación del OMD", "—"),
    ]),
    (12000, None, [
        ("Camisas de cilindro", "Inspeccionar camisas (medir diámetro form. 4610V001, bruñir, cambiar anillos antipulido)", "10, 6"),
        ("Bielas", "Inspeccionar cojinete de cabeza de biela (uno/banco) y cojinete de pie + bulón (uno/banco)", "11, 6"),
        ("Pistón", "Comprobar depósitos de la galería de refrigeración (uno/banco); medir ranuras de aros; anillos de retención", "11"),
        ("Pistón", "Inspeccionar la falda del pistón; limpiar las toberas de aceite", "11.2.3"),
        ("Aros de pistón", "Reemplazar los aros de pistón (seguir programa de rodaje)", "11"),
        ("Culatas", "Overhaul de culatas (desmontar y limpiar, esmerilar asientos y válvulas, o-rings, válvulas de arranque y seguridad)", "2.3, 12, 19"),
        ("Rotadores de válvula", "Desmontar, inspeccionar y limpiar", "12.5"),
        ("Engranaje de accionamiento del árbol de levas", "Inspeccionar dientes y patrón de contacto", "13, 6"),
        ("Turbocompresores VTR", "Inspeccionar y limpiar (compresor, turbina, conductos de agua)", "15, 19"),
        ("Turbocompresores VTR con rodamientos", "Reemplazar cojinetes del turbo (según fabricante)", "—"),
        ("Turbocompresores con cojinetes lisos", "Inspeccionar cojinetes del turbo (según fabricante)", "—"),
        ("Turbocompresores TPL", "Desmontar y limpiar; comprobar tolerancias, eje y cojinetes, carcasas y nozzle ring", "15"),
        ("Bomba de inyección de combustible", "Overhaul de bombas de inyección (limpiar, inspeccionar, cambiar partes y tapones de erosión)", "16"),
        ("Válvulas de inyección piloto (opcional)", "Reemplazar toberas piloto", "16.5"),
        ("Engranaje de bomba de aceite (si instalada)", "Inspeccionar engranaje de accionamiento de la bomba de aceite", "18, 6"),
        ("Engranaje de bomba de agua HT (si instalada)", "Inspeccionar engranaje de accionamiento de la bomba HT", "19, 6"),
        ("Engranaje de bomba de agua LT (si instalada)", "Inspeccionar engranaje de accionamiento de la bomba LT", "19, 6"),
        ("Filtro de aire (sistema neumático)", "Limpiar el inserto y el interior del filtro", "21"),
        ("Conexiones flexibles de tubería", "Reemplazar (marina) / seguir el plan de la instalación (planta eléctrica)", "—"),
    ]),
    (18000, None, [
        ("Dispositivo de viraje (turning device)", "Cambiar el aceite lubricante del dispositivo de viraje", "3, 2"),
        ("Cigüeñal", "Inspeccionar un cojinete de bancada (si hay defectos, abrir todos incl. el del volante)", "10, 6"),
        ("Cigüeñal", "Comprobar holgura axial del cojinete de empuje", "11, 6"),
        ("Amortiguador de vibraciones extremo libre árbol de levas (viscoso, opcional)", "Tomar muestra de aceite para evaluar el amortiguador", "7, 14"),
        ("Bomba de aceite lubricante (opcional)", "Inspeccionar; reemplazar cojinetes y sello del eje", "18"),
        ("Bomba de agua HT (opcional)", "Inspeccionar; reemplazar cojinetes y sello del eje", "19"),
        ("Bomba de agua LT (opcional)", "Inspeccionar; reemplazar cojinetes y sello del eje", "19"),
        ("Gobernador / actuador", "Overhaul general y prueba", "22"),
        ("Pernos de fijación del motor", "Comprobar el apriete de los pernos de fijación del motor", "7"),
    ]),
    (24000, None, [
        ("Pistón", "Inspeccionar la galería de refrigeración del pistón en todos los cilindros; limpiar si es necesario", "11"),
        ("Válvulas", "Cambiar válvulas de admisión y escape", "12.3"),
        ("Rotadores y guías de válvula", "Cambiar rotadores y guías de válvula", "12.3"),
        ("Turbocompresores Napier", "Verificar el balance del eje del rotor (a más tardar cada 32000 h / 4 años)", "—"),
        ("Bomba de inyección de combustible", "Cambiar elementos de la bomba de inyección", "16"),
        ("Válvula termostática de aceite (opcional)", "Limpiar e inspeccionar la válvula termostática de aceite", "18"),
        ("Válvula termostática de agua HT (opcional)", "Limpiar e inspeccionar la válvula termostática HT", "19"),
        ("Válvula termostática de agua LT (opcional)", "Limpiar e inspeccionar la válvula termostática LT", "19"),
        ("Colector de escape", "Cambiar fuelles de expansión entre secciones de tubo de escape", "20"),
        ("Válvula principal de arranque", "Overhaul general de la válvula principal de arranque", "21"),
        ("Accionamiento del gobernador", "Inspección visual de los engranajes de accionamiento del gobernador", "22, 6"),
    ]),
    (36000, None, [
        ("Cojinetes de bancada", "Cambiar casquillos de cojinetes de bancada, del volante y mitades del cojinete de empuje", "10"),
        ("Cigüeñal", "Cambiar el sello del cigüeñal", "11"),
        ("Amortiguador de vibraciones extremo libre cigüeñal (resorte, opcional)", "Desmontar y comprobar (solo personal autorizado)", "7, 11"),
        ("Camisas de cilindro", "Limpiar espacios de agua de refrigeración de las camisas y cambiar o-rings", "10"),
        ("Bielas", "Cambiar casquillos de cojinete de cabeza y de pie de biela", "11"),
        ("Mecanismo de válvulas", "Comprobar holguras en taqués y balancines; cambiar casquillos del rodillo del taqué", "14, 12, 6"),
        ("Asientos de válvula", "Cambiar asientos de válvula de admisión y escape", "12.4"),
        ("Árbol de levas", "Inspeccionar casquillo de cojinete del árbol de levas (uno/banco)", "10.4, 6"),
        ("Amortiguador de vibraciones extremo libre árbol de levas (resorte, opcional)", "Desmontar y comprobar (solo personal autorizado)", "7, 14"),
        ("Acoplamiento elástico extremo de accionamiento árbol de levas (opcional)", "Overhaul general del acoplamiento elástico (personal autorizado)", "7, 14"),
        ("Turbocompresor con cojinetes lisos", "Cambiar cojinetes (según fabricante)", "—"),
        ("Enfriador de aire", "Cambiar enfriador(es) de aire de carga", "15"),
        ("Bomba de inyección de combustible", "Cambiar pasadores del rodillo del taqué, casquillo y cremallera de control", "16"),
        ("Colector de escape", "Cambiar placas de soporte del tubo de escape", "—"),
        ("Distribuidor de aire de arranque", "Overhaul general del distribuidor de aire de arranque", "21.3"),
        ("Pistón", "Cambiar coronas de pistón (HFO 2: 36000 h / HFO 1: 48000 h, ver 2.1.3)", "11.2"),
    ]),
    (48000, None, [
        ("Turbocompresores VTR (rueda de compresor de aleación ligera)", "Reemplazar la rueda del compresor (según fabricante)", "—"),
        ("Fuelle de aire de carga", "Cambiar fuelle(s) de expansión entre el turbo y la caja de admisión de aire", "—"),
        ("Mecanismo de control", "Cambiar casquillos, arandelas de empuje y rótulas del eje de control", "22"),
    ]),
    (60000, None, [
        ("Accionamiento del gobernador", "Cambiar casquillos del eje vertical y del eje horizontal del accionamiento", "22"),
        ("Cojinetes del árbol de levas", "Cambiar cojinetes del árbol de levas, casquillo del extremo de accionamiento y cojinetes de empuje", "10, 13"),
        ("Engranaje intermedio", "Cambiar cojinete de empuje y casquillos del engranaje intermedio", "13"),
        ("Pistón", "Cambiar faldas de pistón y bulones", "11"),
        ("Culatas", "Cambiar culatas", "12"),
        ("Mecanismo de válvulas", "Cambiar casquillos de cojinete de los balancines", "12"),
        ("Sistema de combustible", "Cambiar tuberías principales de inyección y tuberías piloto (opcional)", "16.4"),
        ("Válvulas de inyección", "Cambiar portatoberas, toberas principales y toberas piloto (opcional)", "16.5"),
        ("Montaje flexible (si se usa)", "Cambiar los elementos de goma", "—"),
    ]),
    (72000, None, [
        ("Camisas de cilindro", "Cambiar camisas de cilindro (HFO 2: 72000 h / HFO 1: 96000 h, ver 2.1.3)", "10, 6"),
    ]),
]


def main():
    init_db()  # asegura que la tabla plan_mantenimiento exista
    conn = get_connection()

    # Idempotente: limpiar el plan previo de este modelo.
    conn.execute("DELETE FROM plan_mantenimiento WHERE modelo = ?", (MODELO,))

    total = 0
    for intervalo_horas, intervalo_cal, tareas in PLAN:
        orden = intervalo_horas if intervalo_horas is not None else ORDEN_CAL[intervalo_cal]
        for componente, tarea, seccion in tareas:
            conn.execute(
                """
                INSERT INTO plan_mantenimiento
                    (modelo, intervalo_horas, intervalo_calendario, orden, componente, tarea, seccion_manual)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (MODELO, intervalo_horas, intervalo_cal, orden, componente, tarea, seccion),
            )
            total += 1

    conn.commit()

    # Resumen por intervalo
    print(f"Plan de mantenimiento '{MODELO}' cargado: {total} tareas.\n")
    print(f"{'Intervalo':<16}{'Tareas':>7}")
    print("-" * 23)
    filas = conn.execute(
        """
        SELECT COALESCE(intervalo_calendario, intervalo_horas || ' h') AS intervalo,
               COUNT(*) AS n
        FROM plan_mantenimiento WHERE modelo = ?
        GROUP BY orden ORDER BY orden
        """,
        (MODELO,),
    ).fetchall()
    for f in filas:
        print(f"{f['intervalo']:<16}{f['n']:>7}")
    conn.close()


if __name__ == "__main__":
    main()

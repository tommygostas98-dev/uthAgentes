"""Pruebas de la lógica de validación del importador (sin tocar la BD real).

Se pasa `ya_existentes` / `cod_a_id` como argumento, así que la validación es
pura: no abre conexiones. Correr:  python test_importador.py
"""
import pandas as pd

from src import importador as imp


def _ok(cond, msg):
    print(("OK  " if cond else "FALLO ") + msg)
    assert cond, msg


def test_equipos_validos():
    df = pd.DataFrame([
        {"codigo": "MOT-001", "nombre": "Motor A", "estado": "operativo",
         "frecuencia_preventivo_dias": "30", "horas_operacion": "100.5",
         "frecuencia_preventivo_horas": "4000", "fecha_instalacion": "2024-01-15"},
        {"codigo": "MOT-002", "nombre": "Motor B"},  # mínimos: solo obligatorios
    ])
    validas, errores = imp.validar_equipos(df, ya_existentes=set())
    _ok(len(validas) == 2 and not errores, "equipos: 2 filas válidas, 0 errores")
    _ok(validas[0]["frecuencia_preventivo_dias"] == 30, "equipos: frecuencia días parseada")
    _ok(validas[0]["horas_operacion"] == 100.5, "equipos: horas float parseadas")
    _ok(validas[0]["fecha_instalacion"] == "2024-01-15", "equipos: fecha ISO")
    _ok(validas[1]["estado"] == "operativo", "equipos: estado default operativo")
    _ok(validas[1]["frecuencia_preventivo_dias"] == 90, "equipos: frecuencia días default 90")
    _ok(validas[1]["frecuencia_preventivo_horas"] is None, "equipos: frec_horas vacía -> None")


def test_equipos_errores():
    df = pd.DataFrame([
        {"codigo": "", "nombre": "Sin código"},                       # codigo vacío
        {"codigo": "DUP", "nombre": "Choca con base"},                 # ya existe en base
        {"codigo": "NEW", "nombre": ""},                               # nombre vacío
        {"codigo": "X", "nombre": "Estado malo", "estado": "volando"}, # estado inválido
        {"codigo": "Y", "nombre": "Fecha mala", "fecha_instalacion": "15/13/2024"},
        {"codigo": "Z", "nombre": "Núm malo", "horas_operacion": "abc"},
        {"codigo": "REP", "nombre": "Primera"},                        # duplicado en archivo...
        {"codigo": "rep", "nombre": "Segunda (case-insensitive)"},     # ...detectado sin importar mayúsculas
    ])
    validas, errores = imp.validar_equipos(df, ya_existentes={"dup"})
    campos = {(e["fila"], e["campo"]) for e in errores}
    _ok((1, "codigo") in campos, "equipos: detecta código vacío")
    _ok((2, "codigo") in campos, "equipos: detecta choque con la base")
    _ok((3, "nombre") in campos, "equipos: detecta nombre vacío")
    _ok((4, "estado") in campos, "equipos: detecta estado inválido")
    _ok((5, "fecha_instalacion") in campos, "equipos: detecta fecha inválida")
    _ok((6, "horas_operacion") in campos, "equipos: detecta número inválido")
    _ok((8, "codigo") in campos, "equipos: detecta duplicado en archivo (case-insensitive)")
    _ok(len(validas) == 1, "equipos: solo 1 fila válida (REP), el resto omitidas")
    _ok(validas[0]["codigo"] == "REP", "equipos: la válida es REP")


def test_ordenes():
    cod_a_id = {"u14": 2, "mci-w46-001": 3}
    df = pd.DataFrame([
        {"equipo_codigo": "U14", "descripcion": "Cambio de filtro",
         "tipo": "preventivo", "prioridad": "alta", "estado": "abierta"},
        {"equipo_codigo": "u14", "descripcion": "Otra (código en minúscula)"},  # default
        {"equipo_codigo": "NOEXISTE", "descripcion": "Equipo fantasma"},        # FK falla
        {"equipo_codigo": "U14", "descripcion": ""},                            # desc vacía
        {"equipo_codigo": "U14", "descripcion": "Tipo malo", "tipo": "mágico"}, # tipo inválido
    ])
    validas, errores = imp.validar_ordenes(df, cod_a_id)
    campos = {(e["fila"], e["campo"]) for e in errores}
    _ok(len(validas) == 2, "ordenes: 2 válidas")
    _ok(validas[0]["equipo_id"] == 2, "ordenes: resuelve equipo_id por código")
    _ok(validas[1]["tipo"] == "correctivo", "ordenes: tipo default correctivo")
    _ok(validas[1]["prioridad"] == "media", "ordenes: prioridad default media")
    _ok((3, "equipo_codigo") in campos, "ordenes: detecta equipo inexistente")
    _ok((4, "descripcion") in campos, "ordenes: detecta descripción vacía")
    _ok((5, "tipo") in campos, "ordenes: detecta tipo inválido")


def test_columnas_y_plantillas():
    # Cotejo flexible de encabezados: con acentos, mayúsculas y espacios.
    df = pd.DataFrame([{"Código": "A", "NOMBRE": "x", "Ubicación": "y"}])
    _ok(imp.columnas_faltantes(df, imp.COLUMNAS_EQUIPOS) == [],
        "columnas: cotejo flexible (Código/NOMBRE) reconoce obligatorias")
    validas, errores = imp.validar_equipos(df, set())
    _ok(len(validas) == 1 and validas[0]["ubicacion"] == "y",
        "columnas: lee 'Ubicación' con acento y mayúscula")

    df_falta = pd.DataFrame([{"nombre": "x"}])  # falta 'codigo'
    _ok(imp.columnas_faltantes(df_falta, imp.COLUMNAS_EQUIPOS) == ["codigo"],
        "columnas: reporta obligatoria faltante")

    pe = imp.plantilla_equipos_df()
    po = imp.plantilla_ordenes_df()
    _ok(list(pe.columns)[0] == "codigo" and len(pe) == 1, "plantilla equipos: 1 fila de ejemplo")
    _ok(list(po.columns)[0] == "equipo_codigo" and len(po) == 1, "plantilla órdenes: 1 fila de ejemplo")
    # La plantilla de equipos debe pasar su propia validación (ejemplo sano).
    v, e = imp.validar_equipos(pe, set())
    _ok(len(v) == 1 and not e, "plantilla equipos: el ejemplo es válido")


if __name__ == "__main__":
    test_equipos_validos()
    test_equipos_errores()
    test_ordenes()
    test_columnas_y_plantillas()
    print("\nTODOS LOS TESTS PASARON")

"""Pruebas de la lógica de detección de anomalías (pura, sin BD).

Correr:  python test_anomalias.py
"""
from src import anomalias as an


def _ok(cond, msg):
    print(("OK  " if cond else "FALLO ") + msg)
    assert cond, msg


def test_outlier():
    # Serie estable alrededor de 50 con un pico claro al final.
    vals = [50, 51, 49, 50, 52, 48, 51, 50, 49, 51, 95]
    res = an.detectar_outliers(vals)
    _ok(len(res) == 1, "outlier: detecta exactamente 1 valor atípico")
    _ok(res[0]["indice"] == 10, "outlier: lo ubica en la última lectura (95)")
    _ok(res[0]["valor"] == 95, "outlier: reporta el valor 95")
    _ok(res[0]["severidad"] == "alta", "outlier: severidad alta (muy lejos del umbral)")


def test_salto():
    # Baseline ruidoso ~50 que da un salto súbito a ~85 (patrón de disparo).
    vals = [50.0, 50.3, 49.8, 50.1, 49.9, 50.2, 50.0, 49.7,
            85.0, 85.2, 84.8, 85.1]
    res = an.detectar_saltos(vals)
    indices = [a["indice"] for a in res]
    _ok(8 in indices, "salto: detecta el cambio abrupto en la lectura 8 (50→85)")
    _ok(res[0]["score"] > 0, "salto: el score indica que SUBIÓ (positivo)")


def test_cambio_nivel():
    # Rampa suave 80→95: ninguna lectura es outlier ni hay salto brusco,
    # pero el nivel medio de la 2ª mitad difiere claramente de la 1ª.
    vals = [80 + i for i in range(16)]
    res = an.detectar_cambio_nivel(vals)
    _ok(len(res) == 1, "nivel: detecta un cambio de régimen")
    _ok(res[0]["score"] > 0, "nivel: el nivel SUBIÓ entre mitades")
    # Aislamiento: la rampa uniforme no debe disparar saltos ni outliers.
    _ok(an.detectar_saltos(vals) == [], "nivel: la rampa uniforme NO dispara saltos")
    _ok(an.detectar_outliers(vals) == [], "nivel: la rampa uniforme NO dispara outliers")


def test_rampa_regular_no_dispara_saltos():
    # Rampa de escalones casi idénticos (caso real: presion_combustible cayendo
    # -0.2 bar por lectura). La MAD de las diferencias es ~0 pero, por ruido de
    # punto flotante, no es 0 exacto; sin el piso relativo en detectar_saltos,
    # cada escalón se marcaba como un salto de ~1e14× la variación típica.
    vals = [4.8, 4.6, 4.5, 4.3, 4.1, 3.8, 3.6, 3.4, 3.1, 2.9, 2.7, 2.4]
    res = an.detectar_saltos(vals)
    scores = [a["score"] for a in res]
    _ok(all(abs(s) < 1e6 for s in scores),
        "rampa: ningún salto reporta un score numéricamente absurdo")
    # El cambio de régimen SÍ debe seguir detectándose (la deriva es real).
    _ok(len(an.detectar_cambio_nivel(vals)) == 1,
        "rampa: el cambio de régimen sí se detecta")

    # Rampa perfectamente uniforme (sin ruido): no debe marcar ningún salto.
    uniforme = [10.0 - 0.5 * i for i in range(12)]
    _ok(an.detectar_saltos(uniforme) == [],
        "rampa: una rampa uniforme no dispara saltos")


def test_sin_falsos_positivos():
    # Serie limpia con ruido mínimo: no debe marcar nada.
    vals = [50.0, 50.2, 49.9, 50.1, 49.8, 50.3, 49.7, 50.0, 50.1, 49.9]
    res = an.analizar_serie(vals)
    _ok(res["n"] == 0, "limpia: 0 anomalías en serie estable")
    _ok(res["severidad_max"] is None, "limpia: severidad_max None")

    # Serie constante: tampoco debe romper ni marcar.
    const = [42.0] * 12
    rc = an.analizar_serie(const)
    _ok(rc["n"] == 0, "constante: 0 anomalías (sin división por cero)")


def test_series_cortas():
    _ok(an.detectar_outliers([1, 2, 3]) == [], "corta: <5 puntos no da outliers")
    _ok(an.analizar_serie([1, 2]) ["n"] == 0, "corta: 2 puntos no da anomalías")


def test_analizar_serie_integra():
    # Mezcla: baseline + outlier + verifica tendencia con eje propio.
    vals = [10, 10.1, 9.9, 10, 10.2, 9.8, 10.1, 9.9, 10, 40]
    x = list(range(len(vals)))
    res = an.analizar_serie(vals, x_eje=x)
    _ok(res["n"] >= 1, "integra: encuentra al menos la anomalía del 40")
    tipos = {a["tipo"] for a in res["anomalias"]}
    _ok("outlier" in tipos or "salto" in tipos, "integra: clasifica como outlier o salto")
    _ok(res["tendencia"]["pendiente"] is not None, "integra: calcula pendiente de tendencia")
    _ok(res["severidad_max"] in ("alta", "media", "baja"), "integra: asigna severidad_max")


def test_tendencia():
    vals = [0, 1, 2, 3, 4, 5]          # recta perfecta pendiente 1
    t = an.resumen_tendencia(vals)
    _ok(abs(t["pendiente"] - 1.0) < 1e-9, "tendencia: pendiente = 1")
    _ok(abs(t["r2"] - 1.0) < 1e-9, "tendencia: R² = 1 (ajuste perfecto)")


if __name__ == "__main__":
    test_outlier()
    test_salto()
    test_cambio_nivel()
    test_rampa_regular_no_dispara_saltos()
    test_sin_falsos_positivos()
    test_series_cortas()
    test_analizar_serie_integra()
    test_tendencia()
    print("\nTODOS LOS TESTS DE ANOMALIAS PASARON")

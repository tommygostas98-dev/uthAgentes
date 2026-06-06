"""Detección de anomalías avanzada sobre series de lecturas de sensores.

Complementa a `predictivo.py`: aquel compara contra LÍMITES FIJOS definidos por
el usuario (techo/piso) y proyecta una tendencia lineal. Este módulo encuentra
comportamientos anómalos SIN necesidad de que existan límites, aprendiendo el
patrón normal de la propia serie histórica. Tres familias de detección:

1. OUTLIERS — valores que se apartan del grueso de la serie. Se usa el
   "modified z-score" de Iglewicz-Hoaglin (mediana + MAD), robusto a valores
   extremos; cae a z-score clásico (media + desv. estándar) si la MAD es 0.
2. SALTOS BRUSCOS — cambios abruptos entre lecturas consecutivas, medidos
   contra la variación típica de los incrementos (MAD de las diferencias).
   Es el patrón de un disparo o de un evento súbito (p.ej. el OMD de la U14).
3. CAMBIO DE RÉGIMEN — la serie cambia de nivel medio entre su primera y su
   segunda mitad (deriva sostenida), aunque ninguna lectura sea un outlier.

Toda la lógica numérica es PURA (recibe listas de números), así que es
testeable sin base de datos. La capa `detectar_anomalias_equipo` la conecta a
las lecturas reales vía `predictivo`.
"""

from __future__ import annotations

import numpy as np

# Constantes de los estimadores robustos.
_MAD_A_SIGMA = 1.4826   # escala MAD → desviación estándar (dist. normal)
_MZ_CONST = 0.6745      # constante del modified z-score (Iglewicz-Hoaglin)

# Umbrales por defecto (configurables desde la UI).
UMBRAL_OUTLIER = 3.5    # |modified z-score| para marcar outlier
UMBRAL_SALTO = 4.0      # nº de sigmas-de-diferencias para marcar salto
UMBRAL_NIVEL = 3.0      # nº de errores estándar entre mitades para cambio de régimen
MIN_PUNTOS = 5          # mínimo de lecturas para estadística confiable


def _severidad(score: float, umbral: float) -> str:
    """Clasifica una anomalía por cuánto excede su umbral (baja/media/alta)."""
    r = abs(score) / umbral if umbral else 0
    if r >= 2.5:
        return "alta"
    if r >= 1.6:
        return "media"
    return "baja"


# --- 1. Outliers (modified z-score robusto, con respaldo z clásico) --------
def detectar_outliers(valores: list[float], umbral: float = UMBRAL_OUTLIER) -> list[dict]:
    """Marca lecturas cuyo modified z-score supera `umbral` en valor absoluto."""
    x = np.asarray(valores, dtype=float)
    n = len(x)
    if n < MIN_PUNTOS:
        return []
    mediana = float(np.median(x))
    mad = float(np.median(np.abs(x - mediana)))

    if mad > 0:
        scores = _MZ_CONST * (x - mediana) / mad
        metodo = "MAD (modified z-score)"
        ref = mediana
    else:
        # Serie casi constante: MAD=0 anularía todo. Recurre a media+desv.estándar.
        mu = float(np.mean(x))
        sigma = float(np.std(x, ddof=1))
        if sigma == 0:
            return []
        scores = (x - mu) / sigma
        metodo = "z-score"
        ref = mu

    anomalias = []
    for i in range(n):
        s = float(scores[i])
        if abs(s) > umbral:
            direccion = "por encima" if x[i] > ref else "por debajo"
            anomalias.append({
                "tipo": "outlier",
                "metodo": metodo,
                "indice": i,
                "valor": float(x[i]),
                "score": s,
                "severidad": _severidad(s, umbral),
                "detalle": (f"valor atípico ({direccion} de lo normal): "
                            f"{x[i]:.2f} vs referencia {ref:.2f} "
                            f"(score {s:+.1f}, umbral ±{umbral:g})"),
            })
    return anomalias


# --- 2. Saltos bruscos entre lecturas consecutivas -------------------------
def detectar_saltos(valores: list[float], umbral: float = UMBRAL_SALTO) -> list[dict]:
    """Marca un salto cuando |lectura - anterior| supera `umbral` veces la
    variación típica de los incrementos (estimada con MAD, robusta)."""
    x = np.asarray(valores, dtype=float)
    if len(x) < max(3, MIN_PUNTOS - 1):
        return []
    diffs = np.diff(x)
    mad_d = float(np.median(np.abs(diffs - np.median(diffs))))
    sigma_d = _MAD_A_SIGMA * mad_d
    # Umbral de "variación despreciable" relativo a la escala de la serie: una
    # rampa muy regular deja una MAD ~0 que, por ruido de punto flotante, NO es
    # exactamente 0 (p.ej. 4.8-4.6 = 0.2000000000000002). Sin este piso, dividir
    # por ese residuo (~1e-16) marcaría CADA escalón como un salto gigantesco.
    escala = float(np.median(np.abs(x))) or 1.0
    piso = 1e-9 * escala
    if sigma_d <= piso:
        sigma_d = float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0
    if sigma_d <= piso:
        return []

    anomalias = []
    for i, d in enumerate(diffs):
        ratio = d / sigma_d
        if abs(ratio) > umbral:
            sentido = "subió" if d > 0 else "cayó"
            anomalias.append({
                "tipo": "salto",
                "metodo": "salto brusco (MAD de diferencias)",
                "indice": i + 1,          # la lectura DESPUÉS del salto
                "valor": float(x[i + 1]),
                "score": float(ratio),
                "severidad": _severidad(ratio, umbral),
                "detalle": (f"cambio abrupto: {sentido} {abs(d):.2f} respecto a la "
                            f"lectura previa ({x[i]:.2f} → {x[i + 1]:.2f}; "
                            f"{abs(ratio):.1f}× la variación típica)"),
            })
    return anomalias


# --- 3. Cambio de régimen (deriva de nivel entre mitades) ------------------
def detectar_cambio_nivel(valores: list[float], umbral: float = UMBRAL_NIVEL) -> list[dict]:
    """Detecta si la media de la segunda mitad de la serie difiere de la primera
    más de `umbral` errores estándar (prueba tipo Welch). Señala una deriva
    sostenida aunque ninguna lectura sea, por sí sola, un outlier."""
    x = np.asarray(valores, dtype=float)
    n = len(x)
    if n < 2 * MIN_PUNTOS:        # se necesitan ~5 puntos por mitad
        return []
    medio = n // 2
    a, b = x[:medio], x[medio:]
    ma, mb = float(np.mean(a)), float(np.mean(b))
    va, vb = float(np.var(a, ddof=1)), float(np.var(b, ddof=1))
    se = float(np.sqrt(va / len(a) + vb / len(b)))
    if se == 0:
        if ma == mb:
            return []
        se = 1e-9
    n_sigmas = (mb - ma) / se
    if abs(n_sigmas) <= umbral:
        return []

    sentido = "subió" if mb > ma else "bajó"
    return [{
        "tipo": "nivel",
        "metodo": "cambio de régimen (mitades)",
        "indice": medio,
        "valor": mb,
        "score": float(n_sigmas),
        "severidad": _severidad(n_sigmas, umbral),
        "detalle": (f"el nivel medio {sentido}: {ma:.2f} → {mb:.2f} "
                    f"entre la 1ª y la 2ª mitad de la serie "
                    f"({abs(n_sigmas):.1f}σ de diferencia)"),
    }]


# --- Tendencia (contexto, reutiliza la idea lineal de predictivo) ----------
def resumen_tendencia(valores: list[float], x_eje: list[float] | None = None) -> dict:
    """Pendiente y bondad de ajuste (R²) de la recta sobre la serie.
    `x_eje` son las horas de operación si están disponibles; si no, el índice."""
    y = np.asarray(valores, dtype=float)
    n = len(y)
    if n < 2:
        return {"pendiente": None, "r2": None}
    x = np.asarray(x_eje, dtype=float) if x_eje is not None and len(x_eje) == n else np.arange(n, dtype=float)
    if len(np.unique(x)) < 2:
        return {"pendiente": None, "r2": None}
    pendiente, intercepto = np.polyfit(x, y, 1)
    pred = pendiente * x + intercepto
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    return {"pendiente": float(pendiente), "r2": r2}


# --- Orquestador puro sobre una serie --------------------------------------
def analizar_serie(
    valores: list[float],
    x_eje: list[float] | None = None,
    umbral_outlier: float = UMBRAL_OUTLIER,
    umbral_salto: float = UMBRAL_SALTO,
    umbral_nivel: float = UMBRAL_NIVEL,
) -> dict:
    """Corre las tres detecciones sobre una serie y agrega un resumen.

    Devuelve {'n': int, 'anomalias': [...], 'tendencia': {...},
    'severidad_max': 'alta'|'media'|'baja'|None}. Cada anomalía trae
    tipo/metodo/indice/valor/score/severidad/detalle.
    """
    anomalias = (
        detectar_outliers(valores, umbral_outlier)
        + detectar_saltos(valores, umbral_salto)
        + detectar_cambio_nivel(valores, umbral_nivel)
    )
    anomalias.sort(key=lambda a: a["indice"])
    rango = {"alta": 3, "media": 2, "baja": 1}
    sev_max = None
    if anomalias:
        sev_max = max((a["severidad"] for a in anomalias), key=lambda s: rango[s])
    return {
        "n": len(anomalias),
        "anomalias": anomalias,
        "tendencia": resumen_tendencia(valores, x_eje),
        "severidad_max": sev_max,
    }


# --- Capa conectada a la base de datos -------------------------------------
def analizar_parametro(equipo_id: int, parametro: str, **umbrales) -> dict:
    """Analiza la serie de un parámetro de un equipo (lee las lecturas reales).

    Mapea cada anomalía a su lectura concreta (valor, horas_operacion, fecha)
    para poder ubicarla en el tiempo. Usa horas de operación como eje si todas
    las lecturas las tienen; si no, el orden cronológico.
    """
    from . import predictivo

    lecturas = predictivo.lecturas_de(equipo_id, parametro)
    valores = [l["valor"] for l in lecturas]
    horas = [l["horas_operacion"] for l in lecturas]
    x_eje = horas if all(h is not None for h in horas) and len(horas) > 0 else None

    res = analizar_serie(valores, x_eje, **{
        k: v for k, v in umbrales.items()
        if k in ("umbral_outlier", "umbral_salto", "umbral_nivel")
    })

    unidad = lecturas[-1]["unidad"] if lecturas else None
    for a in res["anomalias"]:
        l = lecturas[a["indice"]]
        a["fecha"] = l.get("fecha")
        a["horas_operacion"] = l.get("horas_operacion")
        a["unidad"] = unidad
    res.update({"parametro": parametro, "n_lecturas": len(lecturas), "unidad": unidad})
    return res


def detectar_anomalias_equipo(equipo_id: int, **umbrales) -> list[dict]:
    """Devuelve el análisis de anomalías de cada parámetro del equipo que
    tenga al menos una anomalía, ordenado por severidad (alta primero)."""
    from . import predictivo

    rango = {"alta": 0, "media": 1, "baja": 2, None: 3}
    resultados = []
    for p in predictivo.parametros_de(equipo_id):
        res = analizar_parametro(equipo_id, p, **umbrales)
        if res["n"] > 0:
            resultados.append(res)
    resultados.sort(key=lambda r: rango.get(r["severidad_max"], 3))
    return resultados


def resumen_global() -> list[dict]:
    """Recorre todos los equipos y devuelve los parámetros con anomalías,
    con contexto de equipo. Para el panel principal y alertas."""
    from . import models

    salida = []
    for eq in models.listar_equipos():
        for res in detectar_anomalias_equipo(eq["id"]):
            salida.append({
                "equipo_id": eq["id"],
                "equipo_codigo": eq["codigo"],
                "equipo_nombre": eq["nombre"],
                **res,
            })
    rango = {"alta": 0, "media": 1, "baja": 2, None: 3}
    salida.sort(key=lambda r: rango.get(r["severidad_max"], 3))
    return salida

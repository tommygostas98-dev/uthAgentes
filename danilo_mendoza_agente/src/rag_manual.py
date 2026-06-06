"""RAG sobre el manual Wärtsilä 46 (PDF) con recuperación BM25 local.

El asistente IA usa este módulo para fundamentar sus respuestas en el manual del
fabricante y poder citar la página. No requiere API de embeddings ni dependencias
nuevas: extrae el texto con `pypdf` y ordena los fragmentos con BM25 (Python puro).

Detalle importante: el manual está en INGLÉS y las consultas llegan en ESPAÑOL.
Por eso la consulta se expande con un glosario ES->EN de vocabulario de motores
antes de buscar (p. ej. 'presión de aceite' -> 'pressure oil'). Así una pregunta
en español recupera el texto correcto del manual en inglés.

La extracción del PDF (lo lento) se cachea en disco; el índice BM25 se arma en
memoria una sola vez por proceso (singleton).
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
PDF_MANUAL = _BASE / "_datos" / "Manual de instruccion Motor W46.pdf"
_CACHE = _BASE / "data" / "manual_w46_chunks.json"
_OBJETIVO_CHARS = 800          # tamaño objetivo de cada fragmento
_VERSION_CACHE = 1             # subir si cambia el troceado, para invalidar el caché

# Glosario español -> inglés de vocabulario de mantenimiento de motores. Permite
# que una consulta en español recupere texto del manual (en inglés). Las claves
# van sin acentos y en minúscula (igual que la tokenización).
GLOSARIO: dict[str, list[str]] = {
    "aceite": ["oil", "lube", "lubricating"],
    "lubricante": ["oil", "lube", "lubricating"],
    "presion": ["pressure"],
    "temperatura": ["temperature", "temp"],
    "agua": ["water"],
    "refrigerante": ["cooling", "coolant"],
    "enfriamiento": ["cooling"],
    "cojinete": ["bearing"],
    "bancada": ["main"],
    "biela": ["connecting", "rod"],
    "ciguenal": ["crankshaft"],
    "piston": ["piston"],
    "cilindro": ["cylinder"],
    "camisa": ["liner"],
    "culata": ["head", "cylinder"],
    "valvula": ["valve"],
    "inyector": ["injector", "nozzle"],
    "bomba": ["pump"],
    "combustible": ["fuel"],
    "escape": ["exhaust"],
    "gases": ["gas", "exhaust"],
    "admision": ["inlet", "intake", "charge"],
    "aire": ["air"],
    "arranque": ["starting", "start"],
    "turbo": ["turbocharger"],
    "turbocompresor": ["turbocharger"],
    "holgura": ["clearance", "backlash"],
    "desgaste": ["wear"],
    "limite": ["limit"],
    "alarma": ["alarm"],
    "parada": ["stop", "shutdown"],
    "paro": ["stop", "shutdown"],
    "velocidad": ["speed"],
    "revoluciones": ["speed", "rpm"],
    "potencia": ["power", "output"],
    "carga": ["load"],
    "vibracion": ["vibration"],
    "nivel": ["level"],
    "filtro": ["filter"],
    "enfriador": ["cooler"],
    "intercambiador": ["exchanger"],
    "segmento": ["ring"],
    "anillo": ["ring"],
    "engranaje": ["gear"],
    "eje": ["shaft"],
    "sello": ["seal"],
    "reten": ["seal"],
    "junta": ["gasket"],
    "empaque": ["gasket"],
    "par": ["torque"],
    "torque": ["torque"],
    "apriete": ["tightening", "torque"],
    "mantenimiento": ["maintenance"],
    "inspeccion": ["inspection", "check"],
    "revision": ["inspection", "overhaul"],
    "cambio": ["change", "replacement"],
    "reemplazo": ["replacement"],
    "montaje": ["mounting", "assembly"],
    "desmontaje": ["dismantling", "removal"],
    "ajuste": ["adjustment", "adjusting"],
    "termostato": ["thermostat"],
    "sensor": ["sensor", "transmitter"],
    "detector": ["detector"],
    "neblina": ["mist"],
    "balancin": ["rocker"],
    "leva": ["cam", "camshaft"],
    "levas": ["camshaft"],
    "volante": ["flywheel"],
    "amortiguador": ["damper"],
    "precalentamiento": ["preheating"],
    "separadora": ["separator", "centrifugal"],
    "centrifuga": ["separator", "centrifugal"],
    "motor": ["engine"],
    "fuga": ["leak", "leakage"],
    "fisura": ["crack"],
    "grieta": ["crack"],
    "operacion": ["operating", "operation"],
    "funcionamiento": ["operating", "operation"],
}

# Palabras muy comunes que no aportan a la búsqueda (ES e EN).
_VACIAS = {
    "de", "la", "el", "los", "las", "un", "una", "y", "o", "en", "del", "al",
    "que", "cual", "cuales", "cuanto", "cuanta", "como", "para", "por", "con",
    "es", "son", "se", "su", "sus", "lo", "the", "of", "and", "to", "in",
    "for", "is", "are", "on", "at", "be",
}


def disponible() -> bool:
    """¿Está el PDF del manual disponible para consultarlo?"""
    return PDF_MANUAL.exists()


def _normaliza(texto: str) -> str:
    """Minúsculas y sin acentos, para comparar de forma robusta."""
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return t.lower()


def _tokeniza(texto: str) -> list[str]:
    """Texto -> tokens alfanuméricos normalizados (>= 2 caracteres)."""
    return [tok for tok in re.findall(r"[a-z0-9]+", _normaliza(texto)) if len(tok) >= 2]


def _expandir_consulta(consulta: str) -> list[str]:
    """Tokens de la consulta + sus traducciones EN del glosario, sin stopwords."""
    expandida: list[str] = []
    for t in _tokeniza(consulta):
        if t in _VACIAS:
            continue
        expandida.append(t)
        expandida.extend(GLOSARIO.get(t, []))
    return expandida


def _trocear(texto: str, objetivo: int = _OBJETIVO_CHARS) -> list[str]:
    """Parte un texto en fragmentos de ~objetivo caracteres respetando palabras."""
    fragmentos: list[str] = []
    actual: list[str] = []
    largo = 0
    for palabra in texto.split():
        actual.append(palabra)
        largo += len(palabra) + 1
        if largo >= objetivo:
            fragmentos.append(" ".join(actual))
            actual, largo = [], 0
    if actual:
        fragmentos.append(" ".join(actual))
    return fragmentos


def _extraer_chunks() -> list[dict]:
    """Extrae el PDF a fragmentos [{'pagina': int, 'texto': str}], con caché en disco."""
    if _CACHE.exists():
        try:
            data = json.loads(_CACHE.read_text(encoding="utf-8"))
            if data.get("version") == _VERSION_CACHE:
                return data["chunks"]
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    import pypdf

    lector = pypdf.PdfReader(str(PDF_MANUAL))
    chunks: list[dict] = []
    for n, pagina in enumerate(lector.pages, start=1):
        texto = (pagina.extract_text() or "").strip()
        if len(texto) < 15:
            continue
        for frag in _trocear(texto):
            if len(frag) >= 15:
                chunks.append({"pagina": n, "texto": frag})

    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(
        json.dumps({"version": _VERSION_CACHE, "chunks": chunks}, ensure_ascii=False),
        encoding="utf-8",
    )
    return chunks


class _BM25:
    """Ranking BM25 (Okapi) sobre una colección de documentos ya tokenizados."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.N = len(docs)
        self.doclen = [len(d) for d in docs]
        self.avgdl = (sum(self.doclen) / self.N) if self.N else 0.0
        self.tf = [Counter(d) for d in docs]
        # Índice invertido: término -> [(doc, frecuencia), ...]
        self.postings: dict[str, list[tuple[int, int]]] = {}
        df: Counter = Counter()
        for i, c in enumerate(self.tf):
            for term, f in c.items():
                self.postings.setdefault(term, []).append((i, f))
                df[term] += 1
        self.idf = {
            term: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for term, n in df.items()
        }

    def buscar(self, terminos: list[str], k: int) -> list[tuple[int, float]]:
        scores: dict[int, float] = {}
        for term in terminos:
            idf = self.idf.get(term)
            if idf is None or self.avgdl == 0:
                continue
            for i, f in self.postings[term]:
                denom = f + self.k1 * (1 - self.b + self.b * self.doclen[i] / self.avgdl)
                scores[i] = scores.get(i, 0.0) + idf * (f * (self.k1 + 1)) / denom
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]


_INDICE: tuple[list[dict], _BM25] | None = None


def _obtener_indice() -> tuple[list[dict], _BM25]:
    """Construye (una vez por proceso) y devuelve (chunks, índice BM25)."""
    global _INDICE
    if _INDICE is None:
        chunks = _extraer_chunks()
        bm25 = _BM25([_tokeniza(c["texto"]) for c in chunks])
        _INDICE = (chunks, bm25)
    return _INDICE


def buscar(consulta: str, k: int = 6) -> list[dict]:
    """Devuelve los k fragmentos más relevantes: [{'pagina', 'texto', 'score'}]."""
    if not disponible():
        return []
    chunks, bm25 = _obtener_indice()
    terminos = _expandir_consulta(consulta)
    if not terminos:
        return []
    return [{**chunks[i], "score": round(s, 3)} for i, s in bm25.buscar(terminos, k)]


def contexto_para(consulta: str, k: int = 6, max_chars: int = 4000) -> tuple[str, list[int]]:
    """Arma el bloque de contexto (con citas de página) para inyectar al LLM.

    Devuelve (texto_contexto, paginas_citadas). Si no hay manual o no hay
    coincidencias, devuelve ("", []).
    """
    resultados = buscar(consulta, k)
    if not resultados:
        return "", []
    lineas = ["=== MANUAL Wärtsilä 46 · fragmentos relevantes (cita la página) ==="]
    paginas: list[int] = []
    usados = 0
    for r in resultados:
        bloque = f"[pág. {r['pagina']}] {r['texto']}"
        if usados + len(bloque) > max_chars and paginas:
            break
        lineas.append(bloque)
        usados += len(bloque)
        if r["pagina"] not in paginas:
            paginas.append(r["pagina"])
    return "\n\n".join(lineas), paginas

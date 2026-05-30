"""Capa SQLite del servidor MCP de la clase uthAgentes.

Toda la logica de datos vive aqui (sin dependencias de MCP), para poder probarla
sola. El servidor (server.py) solo envuelve estas funciones como herramientas.

Tablas:
- estudiantes : el registro de cada participante.
- mensajes    : bandeja comun (directos por slug, o difusion al destino especial).
- lecturas    : por estudiante, el id de mensaje mas alto ya visto (para que las
                difusiones se marquen como vistas una sola vez por lector).
"""
from __future__ import annotations

import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(
    os.environ.get("UTHAGENTES_DB", Path(__file__).resolve().parent / "data" / "uthagentes.db")
)

# Destino interno para difusiones. Lleva caracteres que slug() nunca produce, asi
# que no puede colisionar con el slug de ningun estudiante real.
DESTINO_TODOS = "*todos*"
# Palabras que el usuario puede escribir para difundir a toda la clase.
_ALIAS_TODOS = {"todos", "todas", "all", "broadcast", "clase"}

# Limites de tamano (anti-DoS por volumen y respuestas acotadas).
MAX_NOMBRE = 120
MAX_CAMPO = 500
MAX_ASUNTO = 200
MAX_CUERPO = 4000
LIMITE_LISTA = 500
LIMITE_MENSAJES = 500

ESQUEMA = """
CREATE TABLE IF NOT EXISTS estudiantes (
  slug           TEXT PRIMARY KEY,
  nombre         TEXT NOT NULL,
  github         TEXT DEFAULT '',
  variante       TEXT DEFAULT '',
  agente         TEXT DEFAULT '',
  canal          TEXT DEFAULT '',
  repo           TEXT DEFAULT '',
  estado         TEXT DEFAULT '',
  registrado_en  TEXT NOT NULL,
  actualizado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mensajes (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  de        TEXT DEFAULT '',
  destino   TEXT NOT NULL,        -- slug del destinatario, o DESTINO_TODOS para difusion
  asunto    TEXT DEFAULT '',
  cuerpo    TEXT DEFAULT '',
  creado_en TEXT NOT NULL,
  leido     INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_mensajes_destino ON mensajes(destino);
CREATE TABLE IF NOT EXISTS lecturas (
  lector    TEXT PRIMARY KEY,     -- slug del lector
  ultimo_id INTEGER NOT NULL DEFAULT 0
);
"""


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slug(nombre: str) -> str:
    """Convierte un nombre a identificador estable: 'Maria Lopez' -> 'maria_lopez'."""
    s = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return s or "anon"


def conectar(db_path: str | os.PathLike | None = None) -> sqlite3.Connection:
    ruta = Path(db_path) if db_path else DB_PATH
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta, timeout=5.0)  # espera explicita si la DB esta bloqueada
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")  # recomendado con WAL
    con.execute("PRAGMA busy_timeout=5000")
    return con


def init_db(con: sqlite3.Connection | None = None) -> None:
    cerrar = con is None
    con = con or conectar()
    con.executescript(ESQUEMA)
    con.commit()
    if cerrar:
        con.close()


# --- Estudiantes -----------------------------------------------------------

def obtener_estudiante(con: sqlite3.Connection, identificador: str) -> dict | None:
    cur = con.execute("SELECT * FROM estudiantes WHERE slug=?", (slug(identificador),))
    row = cur.fetchone()
    return dict(row) if row else None


def listar_estudiantes(con: sqlite3.Connection) -> list[dict]:
    cur = con.execute("SELECT * FROM estudiantes ORDER BY nombre LIMIT ?", (LIMITE_LISTA,))
    return [dict(r) for r in cur.fetchall()]


def registrar_estudiante(
    con: sqlite3.Connection,
    nombre: str,
    github: str = "",
    variante: str = "",
    agente: str = "",
    canal: str = "",
    repo: str = "",
    estado: str = "",
) -> dict:
    """Inserta o actualiza un estudiante (clave: slug del nombre).

    Rechaza nombres vacios o reservados ('todos', 'clase', etc.) para no colapsar
    bandejas ni colisionar con la difusion. En actualizacion solo sobreescribe los
    campos que llegan con valor.
    """
    s = slug(nombre)
    if s == "anon" or s in _ALIAS_TODOS:
        raise ValueError(f"nombre invalido o reservado: {nombre!r}")
    nombre = nombre.strip()[:MAX_NOMBRE]
    github, variante, agente, canal, repo, estado = (
        (v or "").strip()[:MAX_CAMPO] for v in (github, variante, agente, canal, repo, estado)
    )
    ahora = _ahora()
    if obtener_estudiante(con, s) is None:
        con.execute(
            "INSERT INTO estudiantes(slug,nombre,github,variante,agente,canal,repo,estado,"
            "registrado_en,actualizado_en) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (s, nombre, github, variante, agente, canal, repo, estado, ahora, ahora),
        )
    else:
        con.execute(
            """UPDATE estudiantes SET nombre=?,
                 github   = CASE WHEN ?<>'' THEN ? ELSE github   END,
                 variante = CASE WHEN ?<>'' THEN ? ELSE variante END,
                 agente   = CASE WHEN ?<>'' THEN ? ELSE agente   END,
                 canal    = CASE WHEN ?<>'' THEN ? ELSE canal    END,
                 repo     = CASE WHEN ?<>'' THEN ? ELSE repo     END,
                 estado   = CASE WHEN ?<>'' THEN ? ELSE estado   END,
                 actualizado_en=?
               WHERE slug=?""",
            (nombre, github, github, variante, variante, agente, agente,
             canal, canal, repo, repo, estado, estado, ahora, s),
        )
    con.commit()
    return obtener_estudiante(con, s)


# --- Estado de lectura -----------------------------------------------------

def _get_hwm(con: sqlite3.Connection, lector: str) -> int:
    r = con.execute("SELECT ultimo_id FROM lecturas WHERE lector=?", (lector,)).fetchone()
    return int(r[0]) if r else 0


def _set_hwm(con: sqlite3.Connection, lector: str, valor: int) -> None:
    con.execute(
        "INSERT INTO lecturas(lector,ultimo_id) VALUES(?,?) "
        "ON CONFLICT(lector) DO UPDATE SET ultimo_id=MAX(ultimo_id, excluded.ultimo_id)",
        (lector, valor),
    )


def contar_no_leidos(con: sqlite3.Connection, identificador: str) -> int:
    """No leidos = directos con leido=0 + difusiones mas nuevas que el ultimo visto."""
    s = slug(identificador)
    hwm = _get_hwm(con, s)
    directos = con.execute(
        "SELECT COUNT(*) FROM mensajes WHERE destino=? AND leido=0", (s,)
    ).fetchone()[0]
    difusiones = con.execute(
        "SELECT COUNT(*) FROM mensajes WHERE destino=? AND id>?", (DESTINO_TODOS, hwm)
    ).fetchone()[0]
    return int(directos + difusiones)


def consultar_estado(con: sqlite3.Connection, identificador: str) -> dict | None:
    est = obtener_estudiante(con, identificador)
    if est is None:
        return None
    return {**est, "mensajes_no_leidos": contar_no_leidos(con, identificador)}


# --- Mensajes --------------------------------------------------------------

def enviar_mensaje(
    con: sqlite3.Connection, destino: str, asunto: str, cuerpo: str, de: str = ""
) -> dict:
    """Encola un mensaje para un estudiante (por slug) o 'todos' (difusion)."""
    es_difusion = slug(destino) in _ALIAS_TODOS
    dest = DESTINO_TODOS if es_difusion else slug(destino)
    de_slug = slug(de) if de and de.strip() else ""
    asunto = (asunto or "")[:MAX_ASUNTO]
    cuerpo = (cuerpo or "")[:MAX_CUERPO]
    ahora = _ahora()
    cur = con.execute(
        "INSERT INTO mensajes(de,destino,asunto,cuerpo,creado_en) VALUES(?,?,?,?,?)",
        (de_slug, dest, asunto, cuerpo, ahora),
    )
    con.commit()
    existe = es_difusion or obtener_estudiante(con, dest) is not None
    return {
        "id": cur.lastrowid,
        "de": de_slug,
        "destino": "todos" if es_difusion else dest,
        "asunto": asunto,
        "creado_en": ahora,
        "destino_existe": existe,
    }


def historial_mensajes(
    con: sqlite3.Connection,
    identificador: str,
    solo_no_leidos: bool = False,
    marcar_leidos: bool = True,
) -> list[dict]:
    """Bandeja de un estudiante: sus mensajes directos + las difusiones.

    Devuelve los mas recientes primero. Con marcar_leidos=True marca como leidos
    SOLO los mensajes efectivamente devueltos (los directos por su id, las
    difusiones avanzando el 'ultimo visto'), evitando perder un mensaje que llegue
    entre la lectura y el marcado. Con solo_no_leidos=True trae unicamente las
    novedades (ideal para revisar cada cierto tiempo).
    """
    s = slug(identificador)
    hwm = _get_hwm(con, s)
    if solo_no_leidos:
        q = (
            "SELECT * FROM mensajes "
            "WHERE (destino=? AND leido=0) OR (destino=? AND id>?) "
            "ORDER BY id DESC LIMIT ?"
        )
        rows = [dict(r) for r in con.execute(q, (s, DESTINO_TODOS, hwm, LIMITE_MENSAJES)).fetchall()]
    else:
        q = "SELECT * FROM mensajes WHERE destino=? OR destino=? ORDER BY id DESC LIMIT ?"
        rows = [dict(r) for r in con.execute(q, (s, DESTINO_TODOS, LIMITE_MENSAJES)).fetchall()]

    if marcar_leidos and rows:
        ids_directos = [r["id"] for r in rows if r["destino"] == s and not r["leido"]]
        if ids_directos:
            marcas = ",".join("?" * len(ids_directos))
            con.execute(f"UPDATE mensajes SET leido=1 WHERE id IN ({marcas})", ids_directos)
        _set_hwm(con, s, max(r["id"] for r in rows))  # cubre las difusiones devueltas
        con.commit()

    # Presenta el destino de difusion de forma amistosa.
    for r in rows:
        if r["destino"] == DESTINO_TODOS:
            r["destino"] = "todos"
    return rows

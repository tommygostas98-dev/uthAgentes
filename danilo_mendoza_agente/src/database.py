"""Conexión y esquema de la base de datos SQLite.

Se usa SQLite porque es un archivo local, no requiere servidor y es
suficiente para una herramienta de mantenimiento de una planta pequeña/mediana.
Si en el futuro crece, el esquema es migrable a PostgreSQL casi sin cambios.
"""

import sqlite3
from pathlib import Path

# La base de datos vive en la carpeta data/ junto al proyecto.
DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DB_DIR / "mantenimiento.db"


def get_connection() -> sqlite3.Connection:
    """Devuelve una conexión a SQLite con filas accesibles por nombre de columna."""
    DB_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row          # filas como diccionarios
    conn.execute("PRAGMA foreign_keys = ON")  # respetar llaves foráneas
    return conn


def init_db() -> None:
    """Crea las tablas si no existen. Es seguro llamarla en cada arranque."""
    conn = get_connection()
    cur = conn.cursor()

    # --- Equipos / activos de la planta ---------------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS equipos (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo                    TEXT UNIQUE NOT NULL,
            nombre                    TEXT NOT NULL,
            tipo                      TEXT,
            ubicacion                 TEXT,
            fabricante                TEXT,
            modelo                    TEXT,
            fecha_instalacion         TEXT,
            estado                    TEXT NOT NULL DEFAULT 'operativo',
            frecuencia_preventivo_dias INTEGER DEFAULT 90,
            ultimo_mantenimiento      TEXT,
            horas_operacion           REAL DEFAULT 0,
            frecuencia_preventivo_horas INTEGER,
            horas_ultimo_mantenimiento REAL DEFAULT 0,
            notas                     TEXT,
            creado_en                 TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
        """
    )

    # --- Órdenes de trabajo --------------------------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ordenes (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo_id        INTEGER NOT NULL,
            tipo             TEXT NOT NULL DEFAULT 'correctivo',
            descripcion      TEXT NOT NULL,
            prioridad        TEXT NOT NULL DEFAULT 'media',
            estado           TEXT NOT NULL DEFAULT 'abierta',
            responsable      TEXT,
            fecha_creacion   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            fecha_programada TEXT,
            fecha_cierre     TEXT,
            solucion         TEXT,
            costo            REAL DEFAULT 0,
            FOREIGN KEY (equipo_id) REFERENCES equipos (id) ON DELETE CASCADE
        )
        """
    )

    # --- Lecturas de sensores (mantenimiento predictivo) ---------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS lecturas (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo_id       INTEGER NOT NULL,
            parametro       TEXT NOT NULL,
            valor           REAL NOT NULL,
            unidad          TEXT,
            horas_operacion REAL,
            fecha           TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (equipo_id) REFERENCES equipos (id) ON DELETE CASCADE
        )
        """
    )

    # --- Límites por parámetro (umbrales de alerta/crítico) ------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS limites (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo_id      INTEGER NOT NULL,
            parametro      TEXT NOT NULL,
            limite_alerta  REAL,
            limite_critico REAL,
            unidad         TEXT,
            direccion      TEXT NOT NULL DEFAULT 'alta',
            UNIQUE (equipo_id, parametro),
            FOREIGN KEY (equipo_id) REFERENCES equipos (id) ON DELETE CASCADE
        )
        """
    )

    # --- Plan de mantenimiento del fabricante (catálogo Cap. 4) --------
    # Es el programa de mantenimiento preventivo según el manual, ligado al
    # MODELO de motor (p. ej. 'W46'), no a un equipo concreto: aplica a todos
    # los equipos de ese modelo. Cada fila es una tarea con su intervalo, ya
    # sea por horas de operación o de calendario (diario/semanal).
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_mantenimiento (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            modelo               TEXT NOT NULL DEFAULT 'W46',
            intervalo_horas      INTEGER,          -- horas de operación (NULL si es de calendario)
            intervalo_calendario TEXT,             -- 'diario' | 'cada_2_dias' | 'semanal' (NULL si es por horas)
            orden                INTEGER NOT NULL,  -- clave para ordenar el plan de menor a mayor intervalo
            componente           TEXT NOT NULL,
            tarea                TEXT NOT NULL,
            seccion_manual       TEXT               -- referencia a la(s) sección(es) del manual
        )
        """
    )

    # --- Configuración clave/valor (preferencias de la app) ------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS config (
            clave TEXT PRIMARY KEY,
            valor TEXT
        )
        """
    )

    conn.commit()

    # --- Migraciones para bases de datos ya existentes ------------------
    _agregar_columna_si_falta(conn, "equipos", "horas_operacion", "REAL DEFAULT 0")
    _agregar_columna_si_falta(conn, "equipos", "frecuencia_preventivo_horas", "INTEGER")
    _agregar_columna_si_falta(conn, "equipos", "horas_ultimo_mantenimiento", "REAL DEFAULT 0")
    _agregar_columna_si_falta(conn, "ordenes", "reporte", "TEXT")
    _agregar_columna_si_falta(conn, "limites", "direccion", "TEXT NOT NULL DEFAULT 'alta'")

    conn.commit()
    conn.close()


def _agregar_columna_si_falta(conn, tabla: str, columna: str, definicion: str) -> None:
    """Agrega una columna a una tabla solo si todavía no existe.

    Permite evolucionar el esquema sin borrar la base de datos existente.
    """
    columnas = {fila["name"] for fila in conn.execute(f"PRAGMA table_info({tabla})")}
    if columna not in columnas:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


# --- Configuración clave/valor ---------------------------------------------

def obtener_config(clave: str, default: str | None = None) -> str | None:
    """Lee un valor de la tabla `config` (o `default` si no existe)."""
    conn = get_connection()
    fila = conn.execute("SELECT valor FROM config WHERE clave = ?", (clave,)).fetchone()
    conn.close()
    return fila["valor"] if fila else default


def guardar_config(clave: str, valor: str) -> None:
    """Crea o actualiza un valor de la tabla `config`."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO config (clave, valor) VALUES (?, ?) "
        "ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor",
        (clave, str(valor)),
    )
    conn.commit()
    conn.close()

"""Funciones de acceso a datos (CRUD) para equipos y órdenes de trabajo.

Cada función abre y cierra su propia conexión para mantenerse simple y segura
en el contexto de Streamlit (que re-ejecuta el script en cada interacción).
"""

from datetime import date, datetime, timedelta

from .database import get_connection

# Valores permitidos (se usan también para poblar los menús en la interfaz).
ESTADOS_EQUIPO = ["operativo", "en_falla", "en_mantenimiento", "fuera_servicio"]
TIPOS_ORDEN = ["preventivo", "correctivo", "predictivo"]
PRIORIDADES = ["baja", "media", "alta", "critica"]
ESTADOS_ORDEN = ["abierta", "en_proceso", "completada", "cancelada"]


# ---------------------------------------------------------------------------
# EQUIPOS
# ---------------------------------------------------------------------------
def crear_equipo(datos: dict) -> int:
    """Inserta un equipo y devuelve su id."""
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO equipos
            (codigo, nombre, tipo, ubicacion, fabricante, modelo,
             fecha_instalacion, estado, frecuencia_preventivo_dias,
             ultimo_mantenimiento, horas_operacion, frecuencia_preventivo_horas,
             horas_ultimo_mantenimiento, notas)
        VALUES (:codigo, :nombre, :tipo, :ubicacion, :fabricante, :modelo,
                :fecha_instalacion, :estado, :frecuencia_preventivo_dias,
                :ultimo_mantenimiento, :horas_operacion, :frecuencia_preventivo_horas,
                :horas_ultimo_mantenimiento, :notas)
        """,
        {
            "codigo": datos["codigo"],
            "nombre": datos["nombre"],
            "tipo": datos.get("tipo"),
            "ubicacion": datos.get("ubicacion"),
            "fabricante": datos.get("fabricante"),
            "modelo": datos.get("modelo"),
            "fecha_instalacion": datos.get("fecha_instalacion"),
            "estado": datos.get("estado", "operativo"),
            "frecuencia_preventivo_dias": datos.get("frecuencia_preventivo_dias", 90),
            "ultimo_mantenimiento": datos.get("ultimo_mantenimiento"),
            "horas_operacion": datos.get("horas_operacion", 0),
            "frecuencia_preventivo_horas": datos.get("frecuencia_preventivo_horas"),
            "horas_ultimo_mantenimiento": datos.get("horas_ultimo_mantenimiento", 0),
            "notas": datos.get("notas"),
        },
    )
    conn.commit()
    nuevo_id = cur.lastrowid
    conn.close()
    return nuevo_id


def listar_equipos() -> list[dict]:
    conn = get_connection()
    filas = conn.execute("SELECT * FROM equipos ORDER BY codigo").fetchall()
    conn.close()
    return [dict(f) for f in filas]


def obtener_equipo(equipo_id: int) -> dict | None:
    conn = get_connection()
    fila = conn.execute("SELECT * FROM equipos WHERE id = ?", (equipo_id,)).fetchone()
    conn.close()
    return dict(fila) if fila else None


def actualizar_equipo(equipo_id: int, datos: dict) -> None:
    """Actualiza solo los campos presentes en `datos`."""
    if not datos:
        return
    columnas = ", ".join(f"{k} = :{k}" for k in datos)
    datos = {**datos, "id": equipo_id}
    conn = get_connection()
    conn.execute(f"UPDATE equipos SET {columnas} WHERE id = :id", datos)
    conn.commit()
    conn.close()


def registrar_horas(equipo_id: int, horas: float) -> None:
    """Actualiza la lectura actual de horas de operación del equipo."""
    conn = get_connection()
    conn.execute("UPDATE equipos SET horas_operacion = ? WHERE id = ?", (horas, equipo_id))
    conn.commit()
    conn.close()


def eliminar_equipo(equipo_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM equipos WHERE id = ?", (equipo_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# ÓRDENES DE TRABAJO
# ---------------------------------------------------------------------------
def crear_orden(datos: dict) -> int:
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO ordenes
            (equipo_id, tipo, descripcion, prioridad, estado,
             responsable, fecha_programada)
        VALUES (:equipo_id, :tipo, :descripcion, :prioridad, :estado,
                :responsable, :fecha_programada)
        """,
        {
            "equipo_id": datos["equipo_id"],
            "tipo": datos.get("tipo", "correctivo"),
            "descripcion": datos["descripcion"],
            "prioridad": datos.get("prioridad", "media"),
            "estado": datos.get("estado", "abierta"),
            "responsable": datos.get("responsable"),
            "fecha_programada": datos.get("fecha_programada"),
        },
    )
    conn.commit()
    nuevo_id = cur.lastrowid
    conn.close()
    return nuevo_id


def listar_ordenes(estado: str | None = None) -> list[dict]:
    """Lista órdenes con el nombre del equipo. Filtra por estado si se indica."""
    conn = get_connection()
    sql = """
        SELECT o.*, e.codigo AS equipo_codigo, e.nombre AS equipo_nombre
        FROM ordenes o
        JOIN equipos e ON e.id = o.equipo_id
    """
    params: tuple = ()
    if estado:
        sql += " WHERE o.estado = ?"
        params = (estado,)
    sql += " ORDER BY o.fecha_creacion DESC"
    filas = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(f) for f in filas]


def ordenes_de_equipo(equipo_id: int) -> list[dict]:
    conn = get_connection()
    filas = conn.execute(
        "SELECT * FROM ordenes WHERE equipo_id = ? ORDER BY fecha_creacion DESC",
        (equipo_id,),
    ).fetchall()
    conn.close()
    return [dict(f) for f in filas]


def cerrar_orden(orden_id: int, solucion: str, costo: float = 0) -> None:
    """Marca una orden como completada, registra solución y costo,
    y actualiza la fecha de último mantenimiento del equipo."""
    conn = get_connection()
    fila = conn.execute("SELECT equipo_id FROM ordenes WHERE id = ?", (orden_id,)).fetchone()
    conn.execute(
        """
        UPDATE ordenes
        SET estado = 'completada',
            solucion = ?,
            costo = ?,
            fecha_cierre = datetime('now','localtime')
        WHERE id = ?
        """,
        (solucion, costo, orden_id),
    )
    if fila:
        # Al cerrar, "reinicia" el contador de preventivo: la fecha y la
        # lectura de horas actuales pasan a ser la referencia del último mantenimiento.
        conn.execute(
            """
            UPDATE equipos
            SET ultimo_mantenimiento = date('now','localtime'),
                horas_ultimo_mantenimiento = horas_operacion
            WHERE id = ?
            """,
            (fila["equipo_id"],),
        )
    conn.commit()
    conn.close()


def vincular_reporte(orden_id: int, nombre_archivo: str | None) -> None:
    """Asocia (o desvincula con None) un documento de reporte a una orden."""
    conn = get_connection()
    conn.execute("UPDATE ordenes SET reporte = ? WHERE id = ?", (nombre_archivo, orden_id))
    conn.commit()
    conn.close()


def actualizar_orden(orden_id: int, datos: dict) -> None:
    if not datos:
        return
    columnas = ", ".join(f"{k} = :{k}" for k in datos)
    datos = {**datos, "id": orden_id}
    conn = get_connection()
    conn.execute(f"UPDATE ordenes SET {columnas} WHERE id = :id", datos)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# MANTENIMIENTO PREVENTIVO / ALERTAS
# ---------------------------------------------------------------------------
def equipos_con_preventivo_vencido() -> list[dict]:
    """Devuelve alertas de mantenimiento preventivo vencido o próximo a vencer.

    Soporta dos criterios y elige el más urgente por equipo:
    - Por HORAS de operación: si el equipo tiene frecuencia_preventivo_horas,
      próxima = horas_ultimo_mantenimiento + frecuencia; alerta si faltan <= 50 h.
    - Por DÍAS (calendario): próxima fecha = base + frecuencia_preventivo_dias,
      donde base es el último mantenimiento o, en su defecto, la instalación;
      alerta si faltan <= 7 días.

    Cada alerta incluye: tipo_alerta ('horas'|'dias'), detalle (texto),
    urgencia ('vencido'|'por_vencer') y orden (clave de prioridad, menor = más urgente).
    """
    hoy = date.today()
    alertas = []

    for eq in listar_equipos():
        candidatos = []

        # --- Criterio por horas de operación ---------------------------
        frec_horas = eq.get("frecuencia_preventivo_horas")
        if frec_horas:
            horas_actuales = eq.get("horas_operacion") or 0
            horas_base = eq.get("horas_ultimo_mantenimiento") or 0
            proxima_horas = horas_base + frec_horas
            horas_restantes = proxima_horas - horas_actuales
            if horas_restantes <= 50:
                candidatos.append(
                    {
                        "tipo_alerta": "horas",
                        "detalle": (
                            f"{horas_actuales:.0f} h de {proxima_horas:.0f} h "
                            f"(intervalo {frec_horas} h)"
                        ),
                        "restante": horas_restantes,
                        "unidad": "h",
                        "orden": horas_restantes,
                    }
                )

        # --- Criterio por días (calendario) ----------------------------
        # Si el equipo se gestiona por horas y todavía no tiene un
        # mantenimiento registrado, NO se usa la fecha de instalación como
        # base (generaría un "vencido" engañoso de años). En ese caso el
        # criterio por horas es el que manda.
        if frec_horas and not eq["ultimo_mantenimiento"]:
            base = None
        else:
            base = eq["ultimo_mantenimiento"] or eq["fecha_instalacion"]
        frec_dias = eq["frecuencia_preventivo_dias"] or 90
        if base:
            try:
                base_fecha = datetime.strptime(base[:10], "%Y-%m-%d").date()
                proxima = base_fecha + timedelta(days=frec_dias)
                dias_restantes = (proxima - hoy).days
                if dias_restantes <= 7:
                    candidatos.append(
                        {
                            "tipo_alerta": "dias",
                            "detalle": f"próxima fecha {proxima.isoformat()}",
                            "restante": dias_restantes,
                            "unidad": "día(s)",
                            # se normaliza a una escala comparable con las horas
                            "orden": dias_restantes,
                        }
                    )
            except (ValueError, TypeError):
                pass

        if not candidatos:
            continue

        # Se reporta el criterio más urgente (menor "orden").
        c = min(candidatos, key=lambda x: x["orden"])
        alertas.append(
            {
                **eq,
                "tipo_alerta": c["tipo_alerta"],
                "detalle": c["detalle"],
                "restante": c["restante"],
                "unidad": c["unidad"],
                "urgencia": "vencido" if c["restante"] < 0 else "por_vencer",
                "orden": c["orden"],
            }
        )

    return sorted(alertas, key=lambda x: x["orden"])


# ---------------------------------------------------------------------------
# INDICADORES (para el panel principal)
# ---------------------------------------------------------------------------
def resumen_indicadores() -> dict:
    conn = get_connection()
    total_equipos = conn.execute("SELECT COUNT(*) FROM equipos").fetchone()[0]
    en_falla = conn.execute(
        "SELECT COUNT(*) FROM equipos WHERE estado = 'en_falla'"
    ).fetchone()[0]
    ordenes_abiertas = conn.execute(
        "SELECT COUNT(*) FROM ordenes WHERE estado IN ('abierta','en_proceso')"
    ).fetchone()[0]
    conn.close()
    return {
        "total_equipos": total_equipos,
        "equipos_en_falla": en_falla,
        "ordenes_abiertas": ordenes_abiertas,
        "preventivos_pendientes": len(equipos_con_preventivo_vencido()),
    }

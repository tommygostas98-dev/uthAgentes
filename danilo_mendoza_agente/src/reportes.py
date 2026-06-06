"""Reportes: indicadores, costos de mantenimiento e historial de órdenes.

Devuelve DataFrames de pandas listos para mostrar, graficar o exportar.
"""

import pandas as pd

from .database import get_connection


def ordenes_completadas() -> pd.DataFrame:
    """Historial de órdenes cerradas, con datos del equipo."""
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT o.id AS orden, e.codigo AS equipo, e.nombre AS equipo_nombre,
               o.tipo, o.prioridad, o.descripcion, o.solucion,
               o.responsable, o.fecha_creacion, o.fecha_cierre, o.costo
        FROM ordenes o
        JOIN equipos e ON e.id = o.equipo_id
        WHERE o.estado = 'completada'
        ORDER BY o.fecha_cierre DESC
        """,
        conn,
    )
    conn.close()
    return df


def costo_por_equipo() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT e.codigo AS equipo,
               COUNT(o.id)            AS ordenes,
               COALESCE(SUM(o.costo), 0) AS costo_total
        FROM equipos e
        LEFT JOIN ordenes o ON o.equipo_id = e.id AND o.estado = 'completada'
        GROUP BY e.id
        ORDER BY costo_total DESC
        """,
        conn,
    )
    conn.close()
    return df


def costo_por_tipo() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT tipo,
               COUNT(*)               AS ordenes,
               COALESCE(SUM(costo), 0) AS costo_total
        FROM ordenes
        WHERE estado = 'completada'
        GROUP BY tipo
        ORDER BY costo_total DESC
        """,
        conn,
    )
    conn.close()
    return df


def costo_por_mes() -> pd.DataFrame:
    """Costo de mantenimiento agrupado por mes de cierre (YYYY-MM)."""
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT substr(fecha_cierre, 1, 7) AS mes,
               COUNT(*)               AS ordenes,
               COALESCE(SUM(costo), 0) AS costo_total
        FROM ordenes
        WHERE estado = 'completada' AND fecha_cierre IS NOT NULL
        GROUP BY mes
        ORDER BY mes
        """,
        conn,
    )
    conn.close()
    return df


def ordenes_por_estado() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT estado, COUNT(*) AS cantidad FROM ordenes GROUP BY estado",
        conn,
    )
    conn.close()
    return df


def resumen_costos() -> dict:
    conn = get_connection()
    fila = conn.execute(
        """
        SELECT COALESCE(SUM(costo), 0) AS total,
               COUNT(*)                AS ordenes,
               COALESCE(AVG(costo), 0) AS promedio
        FROM ordenes WHERE estado = 'completada'
        """
    ).fetchone()
    conn.close()
    return {"costo_total": fila["total"], "ordenes": fila["ordenes"], "costo_promedio": fila["promedio"]}


def generar_pdf_costos(fecha: str = "", autor: str = "Luis Loo") -> bytes:
    """Genera el reporte de costos de mantenimiento en PDF (en memoria).

    Devuelve los bytes del PDF para usarse con st.download_button.
    Requiere reportlab y matplotlib.
    """
    import io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    )

    AZUL = colors.HexColor("#1f4e79")
    GRIS = colors.HexColor("#f0f0f0")

    def moneda(x):
        return f"$ {x:,.2f}"

    rc = resumen_costos()
    df_eq = costo_por_equipo()
    df_tipo = costo_por_tipo()
    df_mes = costo_por_mes()
    df_hist = ordenes_completadas()

    # --- Gráfico en memoria ---
    chart_buf = io.BytesIO()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3))
    eq = df_eq[df_eq["costo_total"] > 0]
    if not eq.empty:
        ax1.bar(eq["equipo"], eq["costo_total"], color="#1f4e79")
    ax1.set_title("Costo por equipo", fontsize=10)
    ax1.set_ylabel("$")
    ax1.tick_params(axis="x", labelsize=8)
    tp = df_tipo[df_tipo["costo_total"] > 0]
    if not tp.empty:
        ax2.pie(tp["costo_total"], labels=tp["tipo"], autopct="%1.0f%%",
                colors=["#1f4e79", "#5b9bd5", "#a6c8e0"], textprops={"fontsize": 8})
    ax2.set_title("Distribución por tipo", fontsize=10)
    fig.tight_layout()
    fig.savefig(chart_buf, dpi=130, format="png")
    plt.close(fig)
    chart_buf.seek(0)

    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("t", parent=estilos["Title"], textColor=AZUL, fontSize=18)
    h2 = ParagraphStyle("h2", parent=estilos["Heading2"], textColor=AZUL, fontSize=12)
    normal = estilos["Normal"]
    small = ParagraphStyle("s", parent=normal, fontSize=8)

    def _tabla(data, widths):
        t = Table(data, colWidths=widths)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), AZUL),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS]),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        return t

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            leftMargin=1.8 * cm, rightMargin=1.8 * cm)
    el = [
        Paragraph("Reporte de Costos de Mantenimiento", titulo),
        Paragraph("Reporte y Análisis de falla en motor de combustión Wärtsilä W46", normal),
        Paragraph(f"Fecha de emisión: {fecha} &nbsp;|&nbsp; Elaborado por: {autor}", small),
        Spacer(1, 0.5 * cm),
        Paragraph("Resumen", h2),
    ]
    kpis = [
        ["Costo total de mantenimiento", moneda(rc["costo_total"])],
        ["Órdenes completadas", str(rc["ordenes"])],
        ["Costo promedio por orden", moneda(rc["costo_promedio"])],
    ]
    tk = Table(kpis, colWidths=[8 * cm, 6 * cm])
    tk.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), GRIS),
        ("TEXTCOLOR", (1, 0), (1, -1), AZUL),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    el += [tk, Spacer(1, 0.4 * cm), Image(chart_buf, width=16 * cm, height=6 * cm),
           Spacer(1, 0.4 * cm)]

    el.append(Paragraph("Costo por equipo", h2))
    data = [["Equipo", "Órdenes", "Costo total"]]
    for _, r in df_eq.iterrows():
        data.append([r["equipo"], str(int(r["ordenes"])), moneda(r["costo_total"])])
    el += [_tabla(data, [7 * cm, 3 * cm, 5 * cm]), Spacer(1, 0.3 * cm)]

    el.append(Paragraph("Costo por tipo de mantenimiento", h2))
    data = [["Tipo", "Órdenes", "Costo total"]]
    for _, r in df_tipo.iterrows():
        data.append([r["tipo"], str(int(r["ordenes"])), moneda(r["costo_total"])])
    el += [_tabla(data, [7 * cm, 3 * cm, 5 * cm]), Spacer(1, 0.3 * cm)]

    if not df_mes.empty:
        el.append(Paragraph("Costo por mes", h2))
        data = [["Mes", "Órdenes", "Costo total"]]
        for _, r in df_mes.iterrows():
            data.append([r["mes"], str(int(r["ordenes"])), moneda(r["costo_total"])])
        el += [_tabla(data, [7 * cm, 3 * cm, 5 * cm]), Spacer(1, 0.4 * cm)]

    el.append(Paragraph("Detalle de órdenes completadas", h2))
    data = [["OT", "Equipo", "Tipo", "Cierre", "Costo", "Solución"]]
    for _, r in df_hist.iterrows():
        sol = (r["solucion"] or "")
        sol = sol[:60] + ("…" if len(sol) > 60 else "")
        data.append([str(r["orden"]), r["equipo"], r["tipo"],
                     (r["fecha_cierre"] or "")[:10], moneda(r["costo"]),
                     Paragraph(sol, small)])
    th = Table(data, colWidths=[1 * cm, 2.5 * cm, 2 * cm, 2.2 * cm, 2.8 * cm, 5.5 * cm])
    th.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS]),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    el.append(th)

    doc.build(el)
    return buf.getvalue()


def generar_pdf_falla(
    evento: str,
    lineas_criticas: list[str],
    anomalias: list[dict] | None = None,
    fecha: str = "",
) -> bytes:
    """Genera en memoria el PDF del reporte de falla (estado crítico actual).

    `evento` describe qué lo disparó (p. ej. «Archivo nuevo: lecturas.csv»).
    `lineas_criticas` son las líneas de `notificaciones.alertas_criticas()` y
    `anomalias` la lista de `notificaciones.anomalias_altas()`. No consulta la
    base: recibe los datos ya calculados, para no acoplarse a otros módulos.
    Devuelve los bytes del PDF. Requiere reportlab.
    """
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )

    anomalias = anomalias or []
    ROJO = colors.HexColor("#b91c1c")
    AZUL = colors.HexColor("#1f4e79")
    GRIS = colors.HexColor("#f0f0f0")

    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("t", parent=estilos["Title"], textColor=ROJO, fontSize=18)
    h2 = ParagraphStyle("h2", parent=estilos["Heading2"], textColor=AZUL, fontSize=12)
    normal = estilos["Normal"]
    small = ParagraphStyle("s", parent=normal, fontSize=8)
    celda = ParagraphStyle("c", parent=normal, fontSize=8, leading=10)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            leftMargin=1.8 * cm, rightMargin=1.8 * cm)
    el = [
        Paragraph("🔴 Reporte de Falla — Alerta de Mantenimiento", titulo),
        Paragraph("Reporte y Análisis de falla en motor de combustión Wärtsilä W46", normal),
        Paragraph(f"Fecha de emisión: {fecha} &nbsp;|&nbsp; Generado por: El Agente te informa de una alarma generada en la U14", small),
        Spacer(1, 0.3 * cm),
        Paragraph(f"<b>Disparador:</b> {evento}", normal),
        Spacer(1, 0.5 * cm),
    ]

    # --- Resumen ---
    el.append(Paragraph("Resumen de la situación", h2))
    resumen = [
        ["Alertas críticas totales", str(len(lineas_criticas))],
        ["Anomalías de severidad alta", str(len(anomalias))],
    ]
    tr = Table(resumen, colWidths=[9 * cm, 5 * cm])
    tr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), GRIS),
        ("TEXTCOLOR", (1, 0), (1, -1), ROJO),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("PADDING", (0, 0), (-1, -1), 7),
    ]))
    el += [tr, Spacer(1, 0.5 * cm)]

    # --- Alertas críticas ---
    el.append(Paragraph("Alertas críticas vigentes", h2))
    if lineas_criticas:
        data = [["#", "Detalle de la alerta"]]
        for i, linea in enumerate(lineas_criticas, 1):
            data.append([str(i), Paragraph(linea, celda)])
        t = Table(data, colWidths=[1 * cm, 15 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ROJO),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS]),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        el.append(t)
    else:
        el.append(Paragraph("Sin alertas críticas vigentes al momento del reporte.", normal))
    el.append(Spacer(1, 0.5 * cm))

    # --- Anomalías de severidad alta ---
    if anomalias:
        el.append(Paragraph("Anomalías detectadas (severidad alta)", h2))
        data = [["Equipo", "Parámetro", "Cuándo", "Valor", "Detalle"]]
        for a in anomalias:
            cuando = (a.get("fecha") or
                      (f"{a['horas_operacion']:.0f} h" if a.get("horas_operacion") is not None
                       else f"#{a.get('indice', 0) + 1}"))
            data.append([
                a.get("equipo_codigo", ""),
                Paragraph(str(a.get("parametro", "")), celda),
                str(cuando)[:16],
                f"{a.get('valor', 0):.1f}",
                Paragraph(a.get("detalle", ""), celda),
            ])
        t = Table(data, colWidths=[2 * cm, 3 * cm, 2.6 * cm, 1.6 * cm, 6.8 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), AZUL),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS]),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        el.append(t)
        el.append(Spacer(1, 0.5 * cm))

    el.append(Paragraph(
        "Documento generado automáticamente por el modo vigía. Revise el equipo "
        "afectado y, de confirmarse, abra una orden de trabajo correctiva.", small))

    doc.build(el)
    return buf.getvalue()


def _equipos_afectados(lineas_criticas: list[str],
                       anomalias: list[dict] | None = None) -> list[str]:
    """Códigos de equipo afectados (únicos, en orden de aparición), extraídos de
    los `[CODIGO]` de las líneas críticas y del campo equipo_codigo de las
    anomalías."""
    import re

    codigos: list[str] = []
    for ln in lineas_criticas:
        m = re.search(r"\[([^\]]+)\]", ln)
        if m:
            codigos.append(m.group(1).strip())
    for a in (anomalias or []):
        if a.get("equipo_codigo"):
            codigos.append(str(a["equipo_codigo"]).strip())
    vistos: list[str] = []
    for c in codigos:
        if c and c not in vistos:
            vistos.append(c)
    return vistos


def _filas_diagnostico(diagnostico: str) -> list[tuple[str, str]]:
    """Convierte el texto del diagnóstico del agente en filas (aspecto, detalle)
    para una tabla legible. Una línea «Etiqueta: contenido» se parte en las dos
    columnas; una línea sin etiqueta corta queda como detalle con aspecto vacío.
    Limpia viñetas iniciales (-, •, *)."""
    # El agente suele pasar el cuerpo en UN solo argumento de línea de comandos
    # con los saltos de línea ESCAPADOS (\n literal, dos caracteres). Los
    # normalizamos a saltos reales para poder separar el diagnóstico en filas.
    texto = (diagnostico or "").replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    filas: list[tuple[str, str]] = []
    for linea in texto.split("\n"):
        linea = linea.strip().lstrip("-•*").strip()
        if not linea:
            continue
        if ":" in linea:
            etiqueta, _, resto = linea.partition(":")
            etiqueta, resto = etiqueta.strip(), resto.strip()
            # Etiqueta válida: corta y sin signos de medición (=, paréntesis,
            # corchetes), para no partir líneas como «Temp B2 = 268C (ref: 171C)».
            if resto and 0 < len(etiqueta) <= 35 and not any(c in etiqueta for c in "=()[]"):
                filas.append((etiqueta, resto))
                continue
        filas.append(("", linea))
    return filas or [("", "Sin diagnóstico detallado.")]


def generar_pdf_gerencial(
    asunto: str,
    diagnostico: str,
    lineas_criticas: list[str],
    anomalias: list[dict] | None = None,
    fecha: str = "",
) -> bytes:
    """Genera en memoria el REPORTE GERENCIAL (resumen ejecutivo, 1 página) de la
    alarma del momento, para dirección/gerencia.

    A diferencia de `generar_pdf_falla` (técnico, con todas las alertas y
    anomalías), este es breve y de alto nivel: equipo(s) afectado(s), severidad,
    magnitud del evento y el diagnóstico/acción recomendada redactados por el
    agente (`diagnostico`, normalmente el cuerpo de la alarma). Recibe los datos
    ya calculados; no consulta la base. Devuelve los bytes del PDF (reportlab).
    """
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )

    anomalias = anomalias or []
    ROJO = colors.HexColor("#b91c1c")
    ROJO_CLARO = colors.HexColor("#fde8e8")
    NARANJA = colors.HexColor("#c2410c")
    NARANJA_CLARO = colors.HexColor("#fef0e0")
    AZUL = colors.HexColor("#1f4e79")
    GRIS = colors.HexColor("#f0f0f0")
    GRIS_TEXTO = colors.HexColor("#6b7280")

    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("t", parent=estilos["Title"], textColor=AZUL, fontSize=18)
    h2 = ParagraphStyle("h2", parent=estilos["Heading2"], textColor=AZUL, fontSize=12)
    normal = estilos["Normal"]
    small = ParagraphStyle("s", parent=normal, fontSize=8)
    cuerpo = ParagraphStyle("cu", parent=normal, fontSize=10, leading=14)
    celda = ParagraphStyle("c", parent=normal, fontSize=9, leading=12)
    kpi_val = ParagraphStyle("kv", parent=normal, fontSize=18, leading=20,
                             alignment=1, fontName="Helvetica-Bold", textColor=AZUL)
    kpi_lbl = ParagraphStyle("kl", parent=normal, fontSize=7.5, leading=9,
                             alignment=1, textColor=GRIS_TEXTO)

    equipos = _equipos_afectados(lineas_criticas, anomalias)
    equipos_txt = ", ".join(equipos) if equipos else "Por confirmar"
    severidad = "CRÍTICA" if lineas_criticas else "ALTA"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            leftMargin=1.8 * cm, rightMargin=1.8 * cm)
    el = [
        Paragraph("Reporte Gerencial — Alarma de Mantenimiento", titulo),
        Paragraph("Planta PAVANA III · Motor Wärtsilä W46 (U14 18V46)", normal),
        Paragraph(f"Fecha de emisión: {fecha} &nbsp;|&nbsp; Generado por: El Agente te informa de una alarma generada en la U14", small),
        Spacer(1, 0.4 * cm),
        Paragraph(f"<b>Alarma:</b> {asunto}", cuerpo),
        Spacer(1, 0.4 * cm),
    ]

    # --- Resumen ejecutivo (tarjetas KPI de alto nivel) ---
    el.append(Paragraph("Resumen ejecutivo", h2))
    el.append(Spacer(1, 0.1 * cm))
    sev_color = ROJO if severidad == "CRÍTICA" else NARANJA
    sev_fondo = ROJO_CLARO if severidad == "CRÍTICA" else NARANJA_CLARO

    def _tarjeta(valor: str, etiqueta: str, color):
        """Celda-tarjeta: valor grande arriba, etiqueta pequeña abajo."""
        v = ParagraphStyle("kvx", parent=kpi_val, textColor=color)
        return [Paragraph(valor, v), Spacer(1, 2), Paragraph(etiqueta, kpi_lbl)]

    n_crit = len(lineas_criticas)
    n_anom = len(anomalias)
    tarjetas = [[
        _tarjeta(equipos_txt, "EQUIPO(S) AFECTADO(S)", AZUL),
        "",
        _tarjeta(severidad, "SEVERIDAD", sev_color),
        "",
        _tarjeta(str(n_crit), "ALERTAS CRÍTICAS", ROJO if n_crit else AZUL),
        "",
        _tarjeta(str(n_anom), "ANOMALÍAS (SEV. ALTA)", NARANJA if n_anom else AZUL),
    ]]
    # 4 tarjetas (cols 0,2,4,6) separadas por columnas-espaciador (1,3,5).
    tk = Table(tarjetas, colWidths=[3.7 * cm, 0.3 * cm, 3.7 * cm, 0.3 * cm,
                                    3.7 * cm, 0.3 * cm, 3.7 * cm])
    estilo_tk = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for c in (0, 2, 4, 6):                      # estilo solo a las tarjetas
        fondo = sev_fondo if c == 2 else GRIS
        borde = sev_color if c == 2 else colors.HexColor("#d1d5db")
        estilo_tk.append(("BACKGROUND", (c, 0), (c, 0), fondo))
        estilo_tk.append(("BOX", (c, 0), (c, 0), 0.8, borde))
    tk.setStyle(TableStyle(estilo_tk))
    el += [tk, Spacer(1, 0.5 * cm)]

    # --- Diagnóstico y acción recomendada (tabla, para lectura gerencial) ---
    el.append(Paragraph("Diagnóstico y acción recomendada", h2))
    data = [["Aspecto", "Detalle"]]
    for aspecto, detalle in _filas_diagnostico(diagnostico):
        data.append([
            Paragraph(f"<b>{aspecto}</b>", celda) if aspecto else "",
            Paragraph(detalle, celda),
        ])
    td = Table(data, colWidths=[4.5 * cm, 11.5 * cm])
    td.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS]),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    el += [td, Spacer(1, 0.5 * cm)]

    el.append(Paragraph(
        "Resumen ejecutivo generado automáticamente por el modo vigía a partir de la "
        "alarma del momento. Para el detalle técnico completo, consulte el reporte de "
        "falla y el historial del equipo.", small))

    doc.build(el)
    return buf.getvalue()


def exportar_excel(hojas: dict[str, pd.DataFrame]) -> bytes:
    """Genera un archivo Excel (en memoria) con una hoja por cada DataFrame.

    Requiere openpyxl. Devuelve los bytes para usarse con st.download_button.
    """
    import io

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for nombre, df in hojas.items():
            df.to_excel(writer, sheet_name=nombre[:31], index=False)
    return buffer.getvalue()

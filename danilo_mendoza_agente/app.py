"""Reporte y Análisis de falla en motor de combustión Wärtsilä W46 — interfaz web (Streamlit).

Ejecutar con:  streamlit run app.py
"""

import io
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import matplotlib
matplotlib.use("Agg")          # backend sin ventana (para Streamlit/servidor)
import matplotlib.pyplot as plt  # noqa: E402

from src import (
    agente_ia,
    anomalias,
    importador,
    models,
    notificaciones,
    plan,
    predictivo,
    rag_manual,
    reportes,
)
from src.database import guardar_config, init_db, obtener_config

load_dotenv()          # carga ANTHROPIC_API_KEY desde .env
init_db()              # crea las tablas si no existen

st.set_page_config(
    page_title="Reporte y Análisis de falla en motor de combustión Wärtsilä W46",
    page_icon="🔧",
    layout="wide",
)


# ===========================================================================
# PANEL PRINCIPAL
# ===========================================================================
def vista_panel():
    st.header("📊 Panel de control")
    ind = models.resumen_indicadores()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Equipos registrados", ind["total_equipos"])
    c2.metric("Equipos en falla", ind["equipos_en_falla"])
    c3.metric("Órdenes abiertas", ind["ordenes_abiertas"])
    c4.metric("Preventivos por vencer", ind["preventivos_pendientes"])

    st.divider()

    alertas = models.equipos_con_preventivo_vencido()
    st.subheader("⏰ Alertas de mantenimiento preventivo")
    if not alertas:
        st.success("No hay mantenimientos preventivos vencidos ni próximos a vencer. ✅")
    else:
        for a in alertas:
            estado = "🔴 VENCIDO" if a["urgencia"] == "vencido" else "🟡 Por vencer"
            criterio = "por horas" if a["tipo_alerta"] == "horas" else "por calendario"
            restante = abs(a["restante"])
            texto = "vencido hace" if a["restante"] < 0 else "vence en"
            # las horas se muestran sin decimales
            valor = f"{restante:.0f}" if a["unidad"] == "h" else f"{restante}"
            st.warning(
                f"{estado} ({criterio}) — **[{a['codigo']}] {a['nombre']}** "
                f"({a['ubicacion'] or 'sin ubicación'}): "
                f"preventivo {texto} {valor} {a['unidad']} · {a['detalle']}"
            )

    st.divider()
    st.subheader("🔮 Alertas predictivas (sensores)")
    pred = predictivo.alertas_predictivas()
    if not pred:
        st.success("Sin anomalías ni tendencias de riesgo en los parámetros monitoreados. ✅")
    else:
        for a in pred:
            texto = f"**[{a['equipo_codigo']}] {a['parametro']}** — {a['mensaje']}"
            if a["estado"] == "critico":
                st.error(texto)
            else:
                st.warning(texto)


# ===========================================================================
# EQUIPOS
# ===========================================================================
def vista_equipos():
    st.header("📋 Equipos")

    tab_lista, tab_nuevo = st.tabs(["Listado", "➕ Registrar equipo"])

    with tab_lista:
        equipos = models.listar_equipos()
        if not equipos:
            st.info("Aún no hay equipos. Usa la pestaña «Registrar equipo».")
        else:
            df = pd.DataFrame(equipos)[
                ["codigo", "nombre", "tipo", "ubicacion", "estado",
                 "fabricante", "modelo", "horas_operacion",
                 "ultimo_mantenimiento"]
            ]
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.subheader("Detalle / edición")
            opciones = {f"[{e['codigo']}] {e['nombre']}": e["id"] for e in equipos}
            sel = st.selectbox("Selecciona un equipo", list(opciones.keys()))
            _detalle_equipo(opciones[sel])

    with tab_nuevo:
        _formulario_nuevo_equipo()


def _formulario_nuevo_equipo():
    with st.form("nuevo_equipo", clear_on_submit=True):
        col1, col2 = st.columns(2)
        codigo = col1.text_input("Código *", placeholder="MOT-001")
        nombre = col2.text_input("Nombre *", placeholder="Motor banda transportadora")
        tipo = col1.text_input("Tipo", placeholder="Motor eléctrico")
        ubicacion = col2.text_input("Ubicación", placeholder="Línea 1 - Sección A")
        fabricante = col1.text_input("Fabricante", placeholder="Siemens")
        modelo = col2.text_input("Modelo", placeholder="1LA7")
        fecha_inst = col1.date_input("Fecha de instalación", value=None, format="YYYY-MM-DD")
        estado = col2.selectbox("Estado", models.ESTADOS_EQUIPO)
        frecuencia = col1.number_input(
            "Frecuencia preventivo (días)", min_value=1, value=90
        )
        horas_op = col2.number_input(
            "Horas de operación actuales", min_value=0.0, value=0.0, step=10.0
        )
        frec_horas = col1.number_input(
            "Frecuencia preventivo (horas, 0 = no aplica)", min_value=0, value=0, step=50
        )
        notas = st.text_area("Notas", placeholder="Observaciones, datos de placa, etc.")

        if st.form_submit_button("Guardar equipo", type="primary"):
            if not codigo or not nombre:
                st.error("Código y nombre son obligatorios.")
                return
            try:
                models.crear_equipo(
                    {
                        "codigo": codigo.strip(),
                        "nombre": nombre.strip(),
                        "tipo": tipo,
                        "ubicacion": ubicacion,
                        "fabricante": fabricante,
                        "modelo": modelo,
                        "fecha_instalacion": fecha_inst.isoformat() if fecha_inst else None,
                        "estado": estado,
                        "frecuencia_preventivo_dias": int(frecuencia),
                        "horas_operacion": float(horas_op),
                        "frecuencia_preventivo_horas": int(frec_horas) or None,
                        "notas": notas,
                    }
                )
                st.success(f"Equipo {codigo} registrado.")
            except Exception as e:  # p.ej. código duplicado
                st.error(f"No se pudo guardar: {e}")


def _detalle_equipo(equipo_id: int):
    eq = models.obtener_equipo(equipo_id)
    if not eq:
        return

    # --- Acceso rápido: registrar lectura de horas ----------------------
    st.markdown("**🕒 Registrar horas de operación**")
    hc1, hc2 = st.columns([3, 1])
    nuevas_horas = hc1.number_input(
        "Lectura actual del horómetro (h)",
        min_value=0.0,
        value=float(eq["horas_operacion"] or 0),
        step=10.0,
        key=f"horas_{equipo_id}",
    )
    if hc2.button("Guardar horas", key=f"savehoras_{equipo_id}"):
        models.registrar_horas(equipo_id, float(nuevas_horas))
        st.success("Horas actualizadas.")
        st.rerun()

    st.divider()

    # --- Edición completa de datos --------------------------------------
    st.markdown("**✏️ Editar datos del equipo**")
    with st.form(f"editar_equipo_{equipo_id}"):
        c1, c2 = st.columns(2)
        codigo = c1.text_input("Código", value=eq["codigo"])
        nombre = c2.text_input("Nombre", value=eq["nombre"])
        tipo = c1.text_input("Tipo", value=eq["tipo"] or "")
        ubicacion = c2.text_input("Ubicación", value=eq["ubicacion"] or "")
        fabricante = c1.text_input("Fabricante", value=eq["fabricante"] or "")
        modelo = c2.text_input("Modelo", value=eq["modelo"] or "")
        estado = c1.selectbox(
            "Estado", models.ESTADOS_EQUIPO,
            index=models.ESTADOS_EQUIPO.index(eq["estado"])
            if eq["estado"] in models.ESTADOS_EQUIPO else 0,
        )
        frec_dias = c2.number_input(
            "Frecuencia preventivo (días)", min_value=1,
            value=int(eq["frecuencia_preventivo_dias"] or 90),
        )
        frec_horas = c1.number_input(
            "Frecuencia preventivo (horas, 0 = no aplica)", min_value=0,
            value=int(eq["frecuencia_preventivo_horas"] or 0), step=50,
        )
        notas = st.text_area("Notas", value=eq["notas"] or "")

        if st.form_submit_button("💾 Guardar cambios", type="primary"):
            try:
                models.actualizar_equipo(
                    equipo_id,
                    {
                        "codigo": codigo.strip(),
                        "nombre": nombre.strip(),
                        "tipo": tipo,
                        "ubicacion": ubicacion,
                        "fabricante": fabricante,
                        "modelo": modelo,
                        "estado": estado,
                        "frecuencia_preventivo_dias": int(frec_dias),
                        "frecuencia_preventivo_horas": int(frec_horas) or None,
                        "notas": notas,
                    },
                )
                st.success("Equipo actualizado.")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo guardar: {e}")

    if st.button("🗑️ Eliminar equipo", key=f"del_{equipo_id}"):
        models.eliminar_equipo(equipo_id)
        st.warning("Equipo eliminado.")
        st.rerun()

    # Historial de órdenes de este equipo
    st.markdown("**Historial de mantenimiento**")
    ordenes = models.ordenes_de_equipo(equipo_id)
    if ordenes:
        df = pd.DataFrame(ordenes)[
            ["id", "tipo", "descripcion", "estado", "fecha_creacion", "fecha_cierre", "costo"]
        ]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("Sin órdenes registradas para este equipo.")


# ===========================================================================
# ÓRDENES DE TRABAJO
# ===========================================================================
def vista_ordenes():
    st.header("🔧 Órdenes de trabajo")

    equipos = models.listar_equipos()
    if not equipos:
        st.info("Primero registra al menos un equipo en la sección «Equipos».")
        return

    tab_lista, tab_nueva = st.tabs(["Listado", "➕ Nueva orden"])

    with tab_lista:
        filtro = st.selectbox("Filtrar por estado", ["(todas)"] + models.ESTADOS_ORDEN)
        ordenes = models.listar_ordenes(None if filtro == "(todas)" else filtro)
        if not ordenes:
            st.info("No hay órdenes con ese filtro.")
        else:
            df = pd.DataFrame(ordenes)[
                ["id", "equipo_codigo", "tipo", "prioridad", "estado",
                 "descripcion", "responsable", "fecha_programada", "reporte"]
            ]
            st.dataframe(df, use_container_width=True, hide_index=True)
            _reportes_orden_ui(ordenes)
            _cerrar_orden_ui(ordenes)

    with tab_nueva:
        _formulario_nueva_orden(equipos)


def _formulario_nueva_orden(equipos):
    opciones = {f"[{e['codigo']}] {e['nombre']}": e["id"] for e in equipos}
    with st.form("nueva_orden", clear_on_submit=True):
        equipo_label = st.selectbox("Equipo *", list(opciones.keys()))
        col1, col2 = st.columns(2)
        tipo = col1.selectbox("Tipo", models.TIPOS_ORDEN)
        prioridad = col2.selectbox("Prioridad", models.PRIORIDADES, index=1)
        responsable = col1.text_input("Responsable", placeholder="Nombre del técnico")
        fecha_prog = col2.date_input("Fecha programada", value=None, format="YYYY-MM-DD")
        descripcion = st.text_area("Descripción de la falla / trabajo *")

        if st.form_submit_button("Crear orden", type="primary"):
            if not descripcion:
                st.error("La descripción es obligatoria.")
                return
            models.crear_orden(
                {
                    "equipo_id": opciones[equipo_label],
                    "tipo": tipo,
                    "descripcion": descripcion,
                    "prioridad": prioridad,
                    "responsable": responsable,
                    "fecha_programada": fecha_prog.isoformat() if fecha_prog else None,
                }
            )
            st.success("Orden creada.")


def _reportes_orden_ui(ordenes):
    st.subheader("📎 Reporte de la orden")
    base = Path(__file__).resolve().parent
    docs = sorted(p.name for p in _documentos_disponibles(base))
    opciones = {
        f"OT#{o['id']} [{o['equipo_codigo']}] - {o['descripcion'][:35]}": o for o in ordenes
    }
    sel = st.selectbox("Selecciona una orden", list(opciones.keys()), key="rep_orden_sel")
    o = opciones[sel]
    actual = o.get("reporte")

    # Reporte actualmente vinculado: descargar
    if actual:
        ruta = base / actual
        if ruta.exists():
            with open(ruta, "rb") as fh:
                st.download_button(
                    f"⬇️ Descargar reporte vinculado ({actual})",
                    data=fh.read(),
                    file_name=actual,
                    mime=_MIME.get(ruta.suffix.lower(), "application/octet-stream"),
                    key=f"dlrep_{o['id']}",
                )
        else:
            st.warning(f"El archivo vinculado «{actual}» no está en la carpeta.")
    else:
        st.caption("Esta orden no tiene reporte vinculado.")

    # Vincular / cambiar
    lista = ["(ninguno)"] + docs
    idx = lista.index(actual) if actual in docs else 0
    nuevo = st.selectbox("Vincular documento", lista, index=idx, key=f"vinc_{o['id']}")
    if st.button("🔗 Guardar vínculo", key=f"savevinc_{o['id']}"):
        models.vincular_reporte(o["id"], None if nuevo == "(ninguno)" else nuevo)
        st.success("Vínculo actualizado.")
        st.rerun()


def _cerrar_orden_ui(ordenes):
    abiertas = [o for o in ordenes if o["estado"] in ("abierta", "en_proceso")]
    if not abiertas:
        return
    st.subheader("Cerrar orden")
    opciones = {
        f"OT#{o['id']} [{o['equipo_codigo']}] - {o['descripcion'][:40]}": o["id"]
        for o in abiertas
    }
    sel = st.selectbox("Orden a cerrar", list(opciones.keys()))
    solucion = st.text_area("Solución aplicada", key="solucion_cierre")
    costo = st.number_input("Costo ($)", min_value=0.0, value=0.0, step=10.0)
    if st.button("✅ Marcar como completada", type="primary"):
        models.cerrar_orden(opciones[sel], solucion, costo)
        st.success("Orden completada y último mantenimiento actualizado.")
        st.rerun()


# ===========================================================================
# ASISTENTE IA
# ===========================================================================
def vista_asistente():
    st.header("🤖 Asistente de mantenimiento (IA)")

    if not agente_ia.cliente_disponible():
        st.warning(
            "El asistente necesita una clave de API de Claude. "
            "Copia `.env.example` a `.env`, agrega tu `ANTHROPIC_API_KEY` y reinicia la app."
        )

    st.caption(
        "Pregunta sobre diagnóstico de fallas, procedimientos o repuestos. "
        "El asistente conoce los equipos y órdenes registrados en el sistema."
    )

    usar_contexto = st.toggle("Usar datos de la planta como contexto", value=True)
    usar_manual = st.toggle(
        "📘 Consultar el manual Wärtsilä 46 (RAG)",
        value=rag_manual.disponible(),
        disabled=not rag_manual.disponible(),
        help="Recupera fragmentos del manual del fabricante y cita la página en la respuesta.",
    )

    if "chat" not in st.session_state:
        st.session_state.chat = []

    # Mostrar historial
    for msg in st.session_state.chat:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    pregunta = st.chat_input("Escribe tu consulta…")
    if pregunta:
        st.session_state.chat.append({"role": "user", "content": pregunta})
        with st.chat_message("user"):
            st.markdown(pregunta)
        with st.chat_message("assistant"):
            with st.spinner("Analizando…"):
                try:
                    respuesta = agente_ia.responder(
                        st.session_state.chat,
                        usar_contexto=usar_contexto,
                        usar_manual=usar_manual,
                    )
                except Exception as e:
                    respuesta = f"⚠️ Error al consultar la IA: {e}"
            st.markdown(respuesta)
            if usar_manual:
                fuentes = rag_manual.buscar(pregunta, k=6)
                if fuentes:
                    with st.expander(f"📖 Fuentes del manual ({len(fuentes)} fragmentos)"):
                        for f in fuentes:
                            st.caption(f"**pág. {f['pagina']}** — {f['texto'][:170]}…")
        st.session_state.chat.append({"role": "assistant", "content": respuesta})

    if st.session_state.chat and st.button("🧹 Limpiar conversación"):
        st.session_state.chat = []
        st.rerun()


# ===========================================================================
# MANTENIMIENTO PREDICTIVO
# ===========================================================================
def vista_predictivo():
    st.header("🔮 Mantenimiento predictivo")
    st.caption(
        "Registra lecturas de sensores (temperatura, presión, vibración…), "
        "define límites y el sistema proyecta cuándo se alcanzará el umbral."
    )

    equipos = models.listar_equipos()
    if not equipos:
        st.info("Primero registra un equipo en la sección «Equipos».")
        return

    # Alertas predictivas globales
    alertas = predictivo.alertas_predictivas()
    if alertas:
        st.subheader("🚨 Alertas predictivas")
        for a in alertas:
            texto = f"**[{a['equipo_codigo']}] {a['parametro']}** — {a['mensaje']}"
            if a["estado"] == "critico":
                st.error(texto)
            else:
                st.warning(texto)
    st.divider()

    opciones = {f"[{e['codigo']}] {e['nombre']}": e["id"] for e in equipos}
    sel = st.selectbox("Equipo", list(opciones.keys()))
    equipo_id = opciones[sel]

    tab_analisis, tab_anomalias, tab_lectura, tab_importar, tab_limites = st.tabs(
        ["📈 Análisis", "🔎 Anomalías", "➕ Registrar lectura",
         "📥 Importar CSV/Excel", "🎯 Definir límites"]
    )

    with tab_analisis:
        _analisis_predictivo(equipo_id)
    with tab_anomalias:
        _anomalias_ui(equipo_id)
    with tab_lectura:
        _registrar_lectura_ui(equipo_id)
    with tab_importar:
        _importar_lecturas_ui(equipo_id)
    with tab_limites:
        _definir_limites_ui(equipo_id)


def _analisis_predictivo(equipo_id: int):
    parametros = predictivo.parametros_de(equipo_id)
    if not parametros:
        st.info("Este equipo aún no tiene lecturas. Usa «Registrar lectura».")
        return

    for analisis in predictivo.analizar_equipo(equipo_id):
        p = analisis["parametro"]
        with st.container(border=True):
            st.markdown(f"### {p}")
            st.markdown(analisis["mensaje"])

            c1, c2, c3 = st.columns(3)
            c1.metric("Valor actual", f"{analisis['valor_actual']:.1f} {analisis['unidad'] or ''}")
            if analisis["pendiente_por_hora"] is not None:
                c2.metric("Tendencia", f"{analisis['pendiente_por_hora']:+.3f} /h")
            if analisis["horas_a_limite"] is not None:
                c3.metric("Horas al límite", f"~{analisis['horas_a_limite']:.0f} h")

            # Gráfico de la serie de lecturas vs horas de operación
            lecturas = predictivo.lecturas_de(equipo_id, p)
            puntos = [(l["horas_operacion"], l["valor"]) for l in lecturas
                      if l["horas_operacion"] is not None]
            if len(puntos) >= 2:
                df = pd.DataFrame(puntos, columns=["horas_operacion", p]).set_index("horas_operacion")
                lim = predictivo.obtener_limite(equipo_id, p)
                if lim:
                    if lim["limite_alerta"] is not None:
                        df["límite alerta"] = lim["limite_alerta"]
                    if lim["limite_critico"] is not None:
                        df["límite crítico"] = lim["limite_critico"]
                st.line_chart(df)


def _grafico_anomalias(equipo_id: int, res: dict):
    """Serie del parámetro con los puntos anómalos resaltados por severidad."""
    lecturas = predictivo.lecturas_de(equipo_id, res["parametro"])
    valores = [l["valor"] for l in lecturas]
    if len(valores) < 2:
        return None
    horas = [l["horas_operacion"] for l in lecturas]
    usar_horas = all(h is not None for h in horas)
    x = horas if usar_horas else list(range(len(valores)))

    colores = {"alta": "#dc2626", "media": "#ea580c", "baja": "#ca8a04"}
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.plot(x, valores, "-o", color="#3b82f6", ms=3, lw=1, label=res["parametro"])
    etiquetados = set()
    for a in res["anomalias"]:
        xi = x[a["indice"]]
        sev = a["severidad"]
        ax.scatter([xi], [a["valor"]], color=colores.get(sev, "#dc2626"),
                   s=90, zorder=5, edgecolors="black", linewidths=0.6,
                   label=None if sev in etiquetados else f"anomalía {sev}")
        etiquetados.add(sev)
    ax.set_xlabel("Horas de operación" if usar_horas else "Nº de lectura")
    ax.set_ylabel(res["unidad"] or "valor")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    return fig


def _anomalias_ui(equipo_id: int):
    st.markdown(
        "Detección automática de comportamientos anómalos **sin necesidad de "
        "definir límites**: valores atípicos, saltos bruscos y cambios de "
        "régimen, aprendidos del propio histórico de cada parámetro. "
        "Complementa al análisis por umbrales."
    )

    if not predictivo.parametros_de(equipo_id):
        st.info("Este equipo aún no tiene lecturas. Usa «Registrar lectura» o importa un histórico.")
        return

    with st.expander("⚙️ Sensibilidad (avanzado)"):
        st.caption("Umbrales más **bajos** = más sensible (detecta más, con más falsos positivos).")
        c1, c2, c3 = st.columns(3)
        u_out = c1.slider("Valores atípicos (z robusto)", 2.0, 6.0,
                          float(anomalias.UMBRAL_OUTLIER), 0.5,
                          help="Modified z-score (mediana + MAD).")
        u_salto = c2.slider("Saltos bruscos (σ de cambios)", 2.0, 8.0,
                            float(anomalias.UMBRAL_SALTO), 0.5)
        u_nivel = c3.slider("Cambio de régimen (σ)", 1.5, 6.0,
                            float(anomalias.UMBRAL_NIVEL), 0.5)

    resultados = anomalias.detectar_anomalias_equipo(
        equipo_id, umbral_outlier=u_out, umbral_salto=u_salto, umbral_nivel=u_nivel
    )
    if not resultados:
        st.success("✅ Sin anomalías detectadas en los parámetros de este equipo "
                   "con la sensibilidad actual.")
        return

    total = sum(r["n"] for r in resultados)
    st.warning(f"Se detectaron **{total}** anomalía(s) en **{len(resultados)}** parámetro(s).")
    iconos = {"alta": "🔴", "media": "🟠", "baja": "🟡"}

    for res in resultados:
        sev = res["severidad_max"]
        with st.container(border=True):
            st.markdown(f"### {iconos.get(sev, '')} {res['parametro']} — {res['n']} anomalía(s)")
            t = res["tendencia"]
            if t["pendiente"] is not None:
                txt = f"Tendencia general: {t['pendiente']:+.3f} por unidad de eje"
                if t["r2"] is not None:
                    txt += f" · ajuste lineal R²={t['r2']:.2f}"
                st.caption(txt)

            filas = []
            for a in res["anomalias"]:
                if a.get("fecha"):
                    cuando = str(a["fecha"])[:16]
                elif a.get("horas_operacion") is not None:
                    cuando = f"{a['horas_operacion']:.0f} h"
                else:
                    cuando = f"lectura #{a['indice'] + 1}"
                filas.append({
                    "cuándo": cuando,
                    "valor": round(a["valor"], 2),
                    "tipo": {"outlier": "valor atípico", "salto": "salto brusco",
                             "nivel": "cambio de régimen"}.get(a["tipo"], a["tipo"]),
                    "severidad": a["severidad"],
                    "detalle": a["detalle"],
                })
            st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

            fig = _grafico_anomalias(equipo_id, res)
            if fig is not None:
                st.pyplot(fig)
                plt.close(fig)


def _registrar_lectura_ui(equipo_id: int):
    eq = models.obtener_equipo(equipo_id)
    horas_actuales = float(eq["horas_operacion"] or 0)

    existentes = predictivo.parametros_de(equipo_id)
    with st.form(f"lectura_{equipo_id}", clear_on_submit=True):
        col1, col2 = st.columns(2)
        if existentes:
            param_sel = col1.selectbox("Parámetro", existentes + ["➕ Nuevo…"])
        else:
            param_sel = "➕ Nuevo…"
            col1.caption("Aún no hay parámetros; crea el primero.")
        param_nuevo = col2.text_input("Nuevo parámetro", placeholder="temperatura_aceite")

        col3, col4, col5 = st.columns(3)
        valor = col3.number_input("Valor", value=0.0, step=0.1, format="%.2f")
        unidad = col4.text_input("Unidad", placeholder="°C, bar, mm/s…")
        horas = col5.number_input("Horas de operación", min_value=0.0,
                                  value=horas_actuales, step=10.0)

        if st.form_submit_button("Guardar lectura", type="primary"):
            parametro = param_nuevo.strip() if param_nuevo.strip() else (
                param_sel if param_sel != "➕ Nuevo…" else "")
            if not parametro:
                st.error("Indica un parámetro.")
                return
            predictivo.registrar_lectura(
                equipo_id, parametro, float(valor),
                unidad or None, float(horas))
            st.success(f"Lectura de «{parametro}» registrada.")


def _importar_lecturas_ui(equipo_id: int):
    eq = models.obtener_equipo(equipo_id)
    st.markdown(
        f"Carga masiva de lecturas para **[{eq['codigo']}] {eq['nombre']}** "
        "desde un archivo CSV o Excel (por ejemplo, un export de tu SCADA o histórico)."
    )

    # --- Plantilla descargable ------------------------------------------
    plantilla = pd.DataFrame(
        {
            "parametro": ["temperatura_aceite", "temperatura_aceite", "vibracion"],
            "valor": [88.0, 90.0, 2.5],
            "unidad": ["C", "C", "mm/s"],
            "horas_operacion": [11900, 11960, 11960],
            "fecha": ["2026-05-20", "2026-05-28", "2026-05-28"],
        }
    )
    st.download_button(
        "⬇️ Descargar plantilla (CSV)",
        data=plantilla.to_csv(index=False).encode("utf-8-sig"),
        file_name="plantilla_lecturas.csv",
        mime="text/csv",
    )
    st.caption(
        "Columnas: **parametro** y **valor** son obligatorias; "
        "*unidad*, *horas_operacion* y *fecha* son opcionales (pero las horas "
        "son necesarias para proyectar tendencias)."
    )

    archivo = st.file_uploader("Sube tu archivo", type=["csv", "xlsx", "xls"])
    if not archivo:
        return

    # --- Leer el archivo ------------------------------------------------
    try:
        if archivo.name.lower().endswith(".csv"):
            df = pd.read_csv(archivo)
        else:
            df = pd.read_excel(archivo)
    except Exception as e:
        st.error(f"No se pudo leer el archivo: {e}")
        return

    if df.empty:
        st.warning("El archivo no tiene filas.")
        return

    st.markdown("**Vista previa del archivo:**")
    st.dataframe(df.head(20), use_container_width=True)

    # --- Mapeo de columnas ----------------------------------------------
    st.markdown("**Asocia las columnas de tu archivo con los campos del sistema:**")
    cols = list(df.columns)
    opciones = ["(ninguna)"] + cols

    def _default(nombre):
        # preselecciona si existe una columna con ese nombre
        return cols.index(nombre) + 1 if nombre in cols else 0

    c1, c2, c3 = st.columns(3)
    map_param = c1.selectbox("Parámetro *", opciones, index=_default("parametro"))
    map_valor = c2.selectbox("Valor *", opciones, index=_default("valor"))
    map_unidad = c3.selectbox("Unidad", opciones, index=_default("unidad"))
    c4, c5 = st.columns(2)
    map_horas = c4.selectbox("Horas de operación", opciones, index=_default("horas_operacion"))
    map_fecha = c5.selectbox("Fecha", opciones, index=_default("fecha"))

    if st.button("📥 Importar lecturas", type="primary"):
        if map_param == "(ninguna)" or map_valor == "(ninguna)":
            st.error("Parámetro y Valor son obligatorios.")
            return

        registros = []
        for _, fila in df.iterrows():
            registros.append(
                {
                    "parametro": fila[map_param],
                    "valor": fila[map_valor],
                    "unidad": fila[map_unidad] if map_unidad != "(ninguna)" else None,
                    "horas_operacion": fila[map_horas] if map_horas != "(ninguna)" else None,
                    "fecha": fila[map_fecha] if map_fecha != "(ninguna)" else None,
                }
            )

        res = predictivo.importar_lecturas(equipo_id, registros)
        if res["insertados"]:
            st.success(f"✅ {res['insertados']} lectura(s) importada(s).")
        if res.get("duplicados"):
            st.warning(
                f"🔁 {len(res['duplicados'])} fila(s) omitida(s) por estar ya "
                "registradas (no se duplicaron):"
            )
            st.dataframe(
                pd.DataFrame(res["duplicados"], columns=["fila", "motivo"]),
                use_container_width=True,
                hide_index=True,
            )
        if res["errores"]:
            st.warning(f"⚠️ {len(res['errores'])} fila(s) omitida(s) por errores:")
            st.dataframe(
                pd.DataFrame(res["errores"], columns=["fila", "motivo"]),
                use_container_width=True,
                hide_index=True,
            )
        if res["insertados"]:
            st.info("Ve a la pestaña «📈 Análisis» para ver las tendencias actualizadas.")


def _definir_limites_ui(equipo_id: int):
    parametros = predictivo.parametros_de(equipo_id)
    nombre = st.text_input("Parámetro", placeholder="temperatura_aceite",
                           value=parametros[0] if parametros else "")
    actual = predictivo.obtener_limite(equipo_id, nombre) if nombre else None

    col1, col2, col3 = st.columns(3)
    alerta = col1.number_input("Límite de alerta", value=float(actual["limite_alerta"]) if actual and actual["limite_alerta"] is not None else 0.0, step=1.0)
    critico = col2.number_input("Límite crítico", value=float(actual["limite_critico"]) if actual and actual["limite_critico"] is not None else 0.0, step=1.0)
    unidad = col3.text_input("Unidad", value=(actual["unidad"] if actual else "") or "")

    opciones_dir = {
        "Techo ↑ — peligro si el valor SUBE (temperatura, vibración, desgaste)": "alta",
        "Piso ↓ — peligro si el valor BAJA (presión de aceite/combustible/aire)": "baja",
    }
    etiquetas = list(opciones_dir)
    dir_actual = (actual.get("direccion") or "alta") if actual else "alta"
    etiqueta_sel = st.radio(
        "Dirección del límite",
        etiquetas,
        index=(0 if dir_actual == "alta" else 1),
        help="Define de qué lado del umbral está el peligro. Para presiones, usa «Piso ↓».",
    )
    direccion = opciones_dir[etiqueta_sel]

    if st.button("💾 Guardar límite", type="primary"):
        if not nombre.strip():
            st.error("Indica el parámetro.")
            return
        predictivo.definir_limite(
            equipo_id, nombre.strip(),
            alerta or None, critico or None, unidad or None, direccion)
        st.success(f"Límite de «{nombre}» ({'piso ↓' if direccion == 'baja' else 'techo ↑'}) guardado.")
        st.rerun()


# ===========================================================================
# PLAN DE MANTENIMIENTO (programa del fabricante, Cap. 4 del manual)
# ===========================================================================
def _fmt_intervalo(t: dict) -> str:
    """Texto legible del intervalo de una tarea del plan."""
    if t["intervalo_horas"] is not None:
        return f"{t['intervalo_horas']:,} h".replace(",", " ")
    return {
        "diario": "Diario",
        "cada_2_dias": "Cada 2 días",
        "semanal": "Semanal",
    }.get(t["intervalo_calendario"], t["intervalo_calendario"] or "—")


def vista_plan():
    st.header("📅 Plan de mantenimiento preventivo")
    st.caption(
        "Programa de mantenimiento del fabricante (manual Wärtsilä 46, Cap. 4 — "
        "operación con HFO). Catálogo de tareas por intervalo y cálculo de las "
        "próximas tareas según las horas de operación de cada equipo."
    )

    if not plan.modelos_con_plan():
        st.warning(
            "No hay ningún plan cargado. Ejecuta `python cargar_plan_mantenimiento.py` "
            "para cargar el programa del Cap. 4."
        )
        return

    tab_proximas, tab_catalogo = st.tabs(
        ["⏱️ Próximas tareas por equipo", "📋 Catálogo del plan"]
    )

    with tab_proximas:
        _plan_proximas_ui()
    with tab_catalogo:
        _plan_catalogo_ui()


def _plan_proximas_ui():
    equipos = models.listar_equipos()
    if not equipos:
        st.info("Primero registra un equipo en la sección «Equipos».")
        return

    opciones = {f"[{e['codigo']}] {e['nombre']}": e["id"] for e in equipos}
    sel = st.selectbox("Equipo", list(opciones.keys()))
    data = plan.calcular_tareas(opciones[sel])
    if not data or not data["tareas"]:
        st.info("Este equipo no tiene un plan asociado a su modelo.")
        return

    c1, c2 = st.columns(2)
    c1.metric("Horas de operación", f"{data['horas']:,.0f} h".replace(",", " "))
    c2.metric("Plan aplicado", data["modelo"])

    if data["horas"] == 0:
        st.info(
            "Este equipo está en **0 h** de operación. Registra sus horas reales en "
            "«Equipos» para que el cálculo de próximas tareas sea útil."
        )

    horizonte = st.slider(
        "Horizonte: mostrar tareas que vencen dentro de…",
        min_value=100, max_value=12000, value=500, step=100,
        help="Horas de operación hacia adelante.",
    )

    proximas = [t for t in data["tareas"] if t["restantes_h"] <= horizonte]
    st.markdown(
        f"**{len(proximas)}** tarea(s) por horas vencen dentro de las próximas "
        f"**{horizonte:,} h**".replace(",", " ")
    )
    st.caption(
        "ℹ️ Se muestra la *próxima ocurrencia* de cada tarea según las horas "
        "actuales (asume el plan al día). No es un vencido real por tarea."
    )

    if proximas:
        df = pd.DataFrame(
            [
                {
                    "Restan (h)": round(t["restantes_h"]),
                    "Próxima a las (h)": t["proxima_h"],
                    "Intervalo": _fmt_intervalo(t),
                    "Componente": t["componente"],
                    "Tarea": t["tarea"],
                    "Sección manual": t["seccion_manual"],
                }
                for t in proximas
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Descargar próximas tareas (CSV)",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"proximas_tareas_{data['equipo']['codigo']}.csv",
            mime="text/csv",
        )
    else:
        st.success("No hay tareas por horas dentro de ese horizonte. ✅")

    # Rutinas de calendario (no dependen de horas)
    st.divider()
    st.subheader("🔁 Rutinas de calendario")
    st.caption("Tareas periódicas que no dependen de las horas de operación.")
    cal = pd.DataFrame(
        [
            {
                "Frecuencia": _fmt_intervalo(t),
                "Componente": t["componente"],
                "Tarea": t["tarea"],
                "Sección manual": t["seccion_manual"],
            }
            for t in data["calendario"]
        ]
    )
    st.dataframe(cal, use_container_width=True, hide_index=True)


def _plan_catalogo_ui():
    modelos = plan.modelos_con_plan()
    modelo = st.selectbox("Modelo de motor", modelos)
    tareas = plan.listar_plan(modelo)

    n_horas = sum(1 for t in tareas if t["intervalo_horas"] is not None)
    n_cal = len(tareas) - n_horas
    c1, c2, c3 = st.columns(3)
    c1.metric("Tareas totales", len(tareas))
    c2.metric("Por horas", n_horas)
    c3.metric("De calendario", n_cal)

    st.caption("Programa completo agrupado por intervalo. Despliega cada bloque.")

    # Agrupar por intervalo respetando el orden
    grupos: dict[str, list[dict]] = {}
    for t in tareas:
        grupos.setdefault(_fmt_intervalo(t), []).append(t)

    for etiqueta, items in grupos.items():
        with st.expander(f"**{etiqueta}** — {len(items)} tarea(s)"):
            df = pd.DataFrame(
                [
                    {
                        "Componente": t["componente"],
                        "Tarea": t["tarea"],
                        "Sección manual": t["seccion_manual"],
                    }
                    for t in items
                ]
            )
            st.dataframe(df, use_container_width=True, hide_index=True)

    # Exportar plan completo
    df_full = pd.DataFrame(
        [
            {
                "Intervalo": _fmt_intervalo(t),
                "Componente": t["componente"],
                "Tarea": t["tarea"],
                "Sección manual": t["seccion_manual"],
            }
            for t in tareas
        ]
    )
    st.download_button(
        "⬇️ Descargar plan completo (CSV)",
        data=df_full.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"plan_mantenimiento_{modelo}.csv",
        mime="text/csv",
    )


# ===========================================================================
# REPORTES
# ===========================================================================
def vista_reportes():
    st.header("📈 Reportes")

    rc = reportes.resumen_costos()
    c1, c2, c3 = st.columns(3)
    c1.metric("Costo total mantenimiento", f"$ {rc['costo_total']:,.2f}")
    c2.metric("Órdenes completadas", rc["ordenes"])
    c3.metric("Costo promedio/orden", f"$ {rc['costo_promedio']:,.2f}")
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Costo por equipo")
        df_eq = reportes.costo_por_equipo()
        st.dataframe(df_eq, use_container_width=True, hide_index=True)
        if not df_eq.empty and df_eq["costo_total"].sum() > 0:
            st.bar_chart(df_eq.set_index("equipo")["costo_total"])
    with col2:
        st.subheader("Costo por tipo")
        df_tipo = reportes.costo_por_tipo()
        st.dataframe(df_tipo, use_container_width=True, hide_index=True)

    st.subheader("Costo por mes")
    df_mes = reportes.costo_por_mes()
    if df_mes.empty:
        st.caption("Aún no hay órdenes completadas con costo.")
    else:
        st.line_chart(df_mes.set_index("mes")["costo_total"])

    st.subheader("Historial de órdenes completadas")
    df_hist = reportes.ordenes_completadas()
    st.dataframe(df_hist, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("⬇️ Exportar")
    cexp1, cexp2, cexp3 = st.columns(3)
    cexp1.download_button(
        "Descargar historial (CSV)",
        data=df_hist.to_csv(index=False).encode("utf-8-sig"),
        file_name="historial_mantenimiento.csv",
        mime="text/csv",
    )
    try:
        excel_bytes = reportes.exportar_excel(
            {
                "Costo por equipo": df_eq,
                "Costo por tipo": df_tipo,
                "Costo por mes": df_mes,
                "Historial": df_hist,
            }
        )
        cexp2.download_button(
            "Descargar reporte completo (Excel)",
            data=excel_bytes,
            file_name="reporte_mantenimiento.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        cexp2.caption(f"Excel no disponible: {e}")

    # Reporte de costos en PDF (se genera al pulsar, para no recalcular en cada interacción)
    if cexp3.button("📄 Generar reporte PDF"):
        try:
            with st.spinner("Generando PDF…"):
                pdf_bytes = reportes.generar_pdf_costos(fecha=date.today().strftime("%d/%m/%Y"))
            cexp3.download_button(
                "⬇️ Descargar reporte de costos (PDF)",
                data=pdf_bytes,
                file_name="Reporte_Costos_Mantenimiento.pdf",
                mime="application/pdf",
            )
        except Exception as e:
            cexp3.error(f"PDF no disponible: {e}")


# ===========================================================================
# DOCUMENTOS / REPORTES GENERADOS
# ===========================================================================
_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# Carpeta privada: sus archivos NO se exponen en la app (ni en Documentos, ni en
# Órdenes, ni en Correo). Guarda material confidencial (datos de planta, manuales,
# análisis) que solo el dueño debe consultar fuera de la aplicación.
CARPETA_PRIVADA = "_datos"
_EXT_DOCS = (".docx", ".pdf", ".xlsx")


def _documentos_disponibles(base: Path) -> list[Path]:
    """Documentos del proyecto visibles para la app, excluyendo la carpeta privada `_datos/`."""
    privada = base / CARPETA_PRIVADA
    return [
        p
        for p in base.iterdir()
        if p.is_file() and p.suffix.lower() in _EXT_DOCS and privada not in p.parents
    ]


def vista_documentos():
    st.header("📄 Documentos y reportes")
    st.caption(
        "Reportes de falla, análisis y documentos generados para esta planta. "
        "Descárgalos directamente desde aquí."
    )

    base = Path(__file__).resolve().parent
    archivos = sorted(
        _documentos_disponibles(base),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not archivos:
        st.info("Aún no hay documentos en la carpeta del proyecto.")
        return

    for f in archivos:
        tam = f.stat().st_size // 1024
        col1, col2 = st.columns([4, 1])
        icono = "📕" if f.suffix.lower() == ".pdf" else "📘" if f.suffix.lower() == ".docx" else "📊"
        col1.markdown(f"{icono} **{f.name}**  \n<small>{tam} KB</small>", unsafe_allow_html=True)
        with open(f, "rb") as fh:
            col2.download_button(
                "⬇️ Descargar",
                data=fh.read(),
                file_name=f.name,
                mime=_MIME.get(f.suffix.lower(), "application/octet-stream"),
                key=f"dl_{f.name}",
            )
        st.divider()


# ===========================================================================
# ENVÍO POR CORREO
# ===========================================================================
def vista_correo():
    st.header("📧 Enviar por correo")
    st.caption(
        "Sin contraseñas: la app **prepara** el correo y lo abres en **tu propio** "
        "Gmail u Outlook (donde ya tienes la sesión iniciada) para darle Enviar."
    )

    destino = st.text_input("Correo de destino", value=notificaciones.destino_por_defecto(),
                            placeholder="destinatario@gmail.com")

    base = Path(__file__).resolve().parent

    # --- Enviar reportes (con adjuntos vía .eml) ---
    st.subheader("📎 Enviar reportes")
    docs = sorted(p.name for p in _documentos_disponibles(base))
    seleccion = st.multiselect("Documentos a adjuntar", docs)
    asunto_r = st.text_input("Asunto", value="Reportes de mantenimiento — U14",
                             key="asunto_rep")
    mensaje_r = st.text_area("Mensaje", value="Adjunto los reportes solicitados.",
                             key="msg_rep")
    if seleccion:
        eml = notificaciones.construir_eml(
            destino, asunto_r, mensaje_r, [base / d for d in seleccion])
        st.download_button(
            "⬇️ Preparar correo con adjuntos (.eml)",
            data=eml,
            file_name="reportes_mantenimiento.eml",
            mime="message/rfc822",
            type="primary",
            help="Descarga el archivo y ábrelo con doble clic: tu correo se abre "
                 "con los reportes ya adjuntos, listo para enviar.",
        )
        st.caption("Ábrelo con doble clic; se abre en tu correo con los adjuntos incluidos.")
    else:
        st.info("Selecciona al menos un documento para preparar el correo con adjuntos.")
    st.link_button(
        "✉️ Abrir solo el mensaje en Gmail (sin adjuntos)",
        notificaciones.gmail_url(destino, asunto_r, mensaje_r),
    )

    st.divider()

    # --- Enviar alertas (texto) ---
    st.subheader("🚨 Enviar alertas")
    cuerpo = notificaciones.texto_alertas()
    st.code(cuerpo, language="text")
    col1, col2 = st.columns(2)
    col1.link_button(
        "✉️ Abrir en Gmail",
        notificaciones.gmail_url(destino, "Alertas de mantenimiento — Agente", cuerpo),
    )
    col2.download_button(
        "⬇️ Descargar como .eml",
        data=notificaciones.construir_eml(
            destino, "Alertas de mantenimiento — Agente", cuerpo),
        file_name="alertas_mantenimiento.eml",
        mime="message/rfc822",
        key="eml_alertas",
    )

    st.divider()

    # --- Alertas automáticas (avanzado: envío desatendido, requiere credenciales) ---
    with st.expander("⚙️ Alertas automáticas (avanzado · requiere credenciales)", expanded=False):
        st.caption(
            "Envío **desatendido**: la app revisa en cada carga si hay alertas "
            "CRÍTICAS (predictivo crítico, preventivo vencido o **anomalías de "
            "severidad alta** de la detección avanzada) y las manda sola, sin que "
            "estés presente. Como nadie da clic, esto sí necesita credenciales "
            "SMTP (`GMAIL_USER` y `GMAIL_APP_PASSWORD` en `.env`). "
            "Si no las configuras, queda desactivado."
        )
        if not notificaciones.configurado():
            st.warning(
                "Sin credenciales SMTP. Define `GMAIL_USER` y `GMAIL_APP_PASSWORD` en "
                "`.env` (contraseña de aplicación de Gmail) y reinicia la app para "
                "usar el envío automático. Guía: https://myaccount.google.com/apppasswords"
            )
        else:
            st.success(f"SMTP configurado. Envía desde: {os.getenv('GMAIL_USER')}")
        auto_activo = st.toggle(
            "Enviar alertas críticas automáticamente",
            value=obtener_config("auto_alertas_activo", "0") == "1",
            disabled=not notificaciones.configurado(),
        )
        col_a, col_b = st.columns(2)
        auto_destino = col_a.text_input(
            "Destino de las alertas automáticas",
            value=obtener_config("auto_alertas_destino", "") or notificaciones.destino_por_defecto(),
            placeholder="destinatario@gmail.com",
        )
        auto_cooldown = col_b.number_input(
            "Espera entre reenvíos (horas)",
            min_value=0.0, step=1.0,
            value=float(obtener_config("auto_alertas_cooldown_horas", "6") or 6),
        )
        if st.button("💾 Guardar alertas automáticas"):
            guardar_config("auto_alertas_activo", "1" if auto_activo else "0")
            guardar_config("auto_alertas_destino", auto_destino.strip())
            guardar_config("auto_alertas_cooldown_horas", str(auto_cooldown))
            st.success("Preferencias de alertas automáticas guardadas.")
        ultimo = obtener_config("auto_alertas_ultimo_envio", "")
        if ultimo:
            st.caption(f"Último envío automático: {ultimo}")
        st.caption(f"Alertas críticas ahora mismo: {len(notificaciones.alertas_criticas())}")


# ===========================================================================
# NAVEGACIÓN
# ===========================================================================
# ===========================================================================
# IMPORTAR DESDE EXCEL
# ===========================================================================
def _df_a_excel_bytes(df: pd.DataFrame) -> bytes:
    """Serializa un DataFrame a un .xlsx en memoria (para st.download_button)."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="plantilla")
    return buf.getvalue()


def vista_importar():
    st.header("📥 Importar desde Excel")
    st.caption(
        "Carga masiva de equipos y órdenes desde un archivo .xlsx o .csv. "
        "Descarga la plantilla, llénala y súbela: verás una vista previa y los "
        "errores **antes** de guardar nada. Las filas con error se omiten; "
        "solo se importan las válidas."
    )
    tab_eq, tab_ord = st.tabs(["📋 Equipos", "🔧 Órdenes de trabajo"])
    with tab_eq:
        _importar_tab("equipos")
    with tab_ord:
        _importar_tab("ordenes")


def _importar_tab(tipo: str):
    if tipo == "equipos":
        columnas = importador.COLUMNAS_EQUIPOS
        plantilla = importador.plantilla_equipos_df()
        nombre_base, etiqueta = "plantilla_equipos", "equipos"
    else:
        columnas = importador.COLUMNAS_ORDENES
        plantilla = importador.plantilla_ordenes_df()
        nombre_base, etiqueta = "plantilla_ordenes", "órdenes"

    # 1) Plantilla -------------------------------------------------------
    obligatorias = [n for n, oblig, _e in columnas if oblig]
    st.markdown("**1. Descarga la plantilla y llénala**")
    st.caption("Columnas obligatorias: " + ", ".join(obligatorias) +
               ". Las demás son opcionales. Fechas en formato YYYY-MM-DD.")
    c1, c2 = st.columns(2)
    c1.download_button(
        "⬇️ Plantilla Excel (.xlsx)",
        data=_df_a_excel_bytes(plantilla),
        file_name=f"{nombre_base}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"tpl_xlsx_{tipo}",
    )
    c2.download_button(
        "⬇️ Plantilla CSV",
        data=plantilla.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{nombre_base}.csv",
        mime="text/csv",
        key=f"tpl_csv_{tipo}",
    )
    if tipo == "ordenes":
        st.info("La columna **equipo_codigo** debe coincidir con el código de un "
                "equipo ya registrado (importa primero los equipos si hace falta).")

    # 2) Subir archivo ---------------------------------------------------
    st.markdown("**2. Sube tu archivo lleno**")
    archivo = st.file_uploader(
        "Archivo .xlsx o .csv", type=["xlsx", "csv"], key=f"up_{tipo}"
    )
    if not archivo:
        return
    try:
        if archivo.name.lower().endswith(".csv"):
            df = pd.read_csv(archivo, dtype=str)
        else:
            df = pd.read_excel(archivo, dtype=str)
    except Exception as e:
        st.error(f"No se pudo leer el archivo: {e}")
        return
    if df.empty:
        st.warning("El archivo no tiene filas.")
        return

    faltan = importador.columnas_faltantes(df, columnas)
    if faltan:
        st.error("Faltan columnas obligatorias: " + ", ".join(faltan))
        st.caption("Encabezados detectados en tu archivo: " +
                   ", ".join(str(c) for c in df.columns))
        return

    # 3) Validar y previsualizar ----------------------------------------
    if tipo == "equipos":
        validas, errores = importador.validar_equipos(df, importador.codigos_existentes())
    else:
        validas, errores = importador.validar_ordenes(df, importador.mapa_codigo_a_id())

    st.markdown("**3. Vista previa**")
    st.dataframe(df, use_container_width=True, hide_index=True)
    m1, m2, m3 = st.columns(3)
    m1.metric("Filas en el archivo", len(df))
    m2.metric("Válidas", len(validas))
    m3.metric("Con error", len(df) - len(validas))

    if errores:
        st.error(f"{len(errores)} problema(s) encontrados (las filas con error se omiten):")
        st.dataframe(
            pd.DataFrame(errores)[["fila", "campo", "problema"]],
            use_container_width=True, hide_index=True,
        )

    if not validas:
        st.warning("No hay filas válidas para importar. Corrige el archivo y vuelve a subirlo.")
        return

    # 4) Confirmar e importar -------------------------------------------
    st.markdown("**4. Importar**")
    if st.button(f"✅ Importar {len(validas)} {etiqueta}", type="primary", key=f"imp_{tipo}"):
        try:
            if tipo == "equipos":
                n = importador.importar_equipos(validas)
            else:
                n = importador.importar_ordenes(validas)
            st.success(f"✅ Se importaron {n} {etiqueta}. "
                       "Quita el archivo (✕) para terminar y evitar duplicados.")
        except Exception as e:
            st.error(f"Error al importar: {e}")


def main():
    # Alertas automáticas por correo (desatendido; deduplicado + cooldown).
    try:
        _auto = notificaciones.revisar_y_enviar_auto()
        if _auto.get("enviado"):
            st.toast(
                f"📧 {_auto['n']} alerta(s) crítica(s) enviada(s) a {_auto['destino']}",
                icon="⚠️",
            )
    except Exception as _e:  # nunca romper la app por el envío automático
        st.toast(f"No se pudo enviar alertas automáticas: {_e}", icon="⚠️")

    st.sidebar.title("🔧 Reporte y Análisis de Falla · Wärtsilä W46")
    seccion = st.sidebar.radio(
        "Navegación",
        ["📊 Panel", "📋 Equipos", "🔧 Órdenes de trabajo",
         "🔮 Predictivo", "📅 Plan mantenimiento", "📈 Reportes",
         "📄 Documentos", "📥 Importar", "📧 Correo", "🤖 Asistente IA"],
    )
    st.sidebar.divider()
    st.sidebar.caption(f"Fecha: {date.today().isoformat()}")

    if seccion == "📊 Panel":
        vista_panel()
    elif seccion == "📋 Equipos":
        vista_equipos()
    elif seccion == "🔧 Órdenes de trabajo":
        vista_ordenes()
    elif seccion == "🔮 Predictivo":
        vista_predictivo()
    elif seccion == "📅 Plan mantenimiento":
        vista_plan()
    elif seccion == "📈 Reportes":
        vista_reportes()
    elif seccion == "📄 Documentos":
        vista_documentos()
    elif seccion == "📥 Importar":
        vista_importar()
    elif seccion == "📧 Correo":
        vista_correo()
    else:
        vista_asistente()


if __name__ == "__main__":
    main()

# Danilo Mendoza

---

## Identidad

| Campo | Valor |
|---|---|
| Nombre completo | Danilo Mendoza |
| Handle GitHub | @manimendoza2406-mani |
| Correo de contacto | mani.mendoza2406@gmail.com |
| Repo personal del proyecto | https://github.com/luislootx/uthAgentes/tree/main/danilo_mendoza_agente |
| Fecha de registro | 2026-06-06 |

---

## Proyecto

| Campo | Valor |
|---|---|
| Nombre del agente | MotorVigia (asistente de mantenimiento) |
| Variante elegida | (1) Diagnóstico — análisis de fallas en motor de combustión Wärtsilä W46 (planta PAVANA III, motor U14 18V46) |
| Modelo LLM | Claude Code (la propia sesión como cerebro) |
| Canal de salida principal | correo (Canal A) + difusión MCP de la clase (Canal B, `enviar_mensaje destino=todos`) |
| PDFs base del RAG | Manual de fabricante Wärtsilä + extracto ISO 10816 (chunks en `data/manual_w46_chunks.json`) |
| Código del agente | `danilo_mendoza_agente/` (en este mismo repo) |

---

## Arquitectura (módulos propios)

El agente es modular (un módulo por responsabilidad) en `src/`:

1. `models.py` / `database.py` — modelo de datos y persistencia (equipos, lecturas, órdenes).
2. `importador.py` — importación masiva de lecturas desde CSV/Excel con dedup.
3. `anomalias.py` / `predictivo.py` — detección de anomalías, tendencia (regresión) y proyección de umbrales.
4. `rag_manual.py` — RAG (BM25/TF-IDF) sobre el manual del motor y normas.
5. `agente_ia.py` — orquestación del diagnóstico con IA.
6. `reportes.py` — generación de reportes (PDF/DOCX) con gráficos y logo.
7. `notificaciones.py` / `canal_mcp.py` — salida por correo (SMTP) y difusión MCP de la clase.

---

## Herramientas (tools) del agente

1. `app.py` — panel Streamlit: equipos, órdenes, alertas preventivas/predictivas, reportes de costos.
2. `vigilancia_alertas.py` — vigía: observa archivos nuevos de lecturas y dispara alarmas (watchdog).
3. `generar_lecturas.py` — genera lecturas de demo por semana (WXX) para simular escenarios.
4. `motovigia.py` — procesa lecturas, evalúa límites/críticos y prepara la alarma.
5. `enviar_alarma.py` — envío de la alarma por los canales configurados.

---

## Estado actual

- `2026-06-06` · Registrado en el repo. Agente **MotorVigia** punta a punta: importación de lecturas, detección predictiva/anomalías, RAG sobre manual W46, reportes PDF/DOCX y doble canal de alarma (correo + MCP). Listo para el demo del sábado. LLM = Claude Code.

---

## Mensajes para otros estudiantes / instructor

(vacío)

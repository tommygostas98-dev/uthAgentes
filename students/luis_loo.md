# Luis Loo

---

## Identidad

| Campo | Valor |
|---|---|
| Nombre completo | Luis Loo |
| Handle GitHub | @luislootx |
| Correo de contacto | luis.loo@avnc.net |
| Repo personal del proyecto | https://github.com/luislootx/<repo> |
| Fecha de registro | 2026-05-23 |

---

## Proyecto

| Campo | Valor |
|---|---|
| Nombre del agente | MotorVigia |
| Variante elegida | (1) Diagnóstico de bombas/motores — enfoque: análisis de reportería de fallas en motores bifásicos |
| Modelo LLM | Claude Code (la propia sesión como cerebro, sin API key externa) |
| Canal de salida principal | correo (funcional); WhatsApp / Telegram / dashboard pendientes |
| PDFs base del RAG | Base curada en `data/conocimiento/` + extracto ISO 10816-3 (PDF) en `data/manuales/`. NEMA MG-1 y manual de fabricante: pendientes |
| Repo del agente | `agente-motores/` (carpeta hermana de este repo; por publicar en GitHub) |

---

## Clases POO propias

1. `Motor` — un equipo monitoreado (motor/bomba/compresor/caldera) con su historial de lecturas.
2. `Lectura` — una medición puntual de un sensor (timestamp, tag, valor, estado).
3. `Diagnostico` — veredicto estructurado: severidad, falla probable, evidencia, acción, norma citada.

---

## Herramientas (tools) del agente

1. `analizar.py` — indicadores por equipo: RMS, factor de cresta, tendencia y zona ISO 10816.
2. `consultar_norma.py` — RAG sobre ISO/NEMA/manuales (recupera contexto técnico).
3. `simular_falla.py` — genera forma de onda y la analiza con FFT (firma 1X/2X/rodamiento).
4. `notificar.py` — envía el diagnóstico por correo (smtplib).

---

## Estado actual

- `2026-05-23` · Registrado en el repo (test de onboarding hecho por el instructor).
- `2026-05-30` · Esqueleto del agente **MotorVigia** punta a punta: 3 clases POO, 4 tools, RAG (TF-IDF) y correo. Corre con `python agente.py` y en modo agente con `/diagnosticar`. LLM = Claude Code.

---

## Mensajes para otros estudiantes / instructor

(vacío)

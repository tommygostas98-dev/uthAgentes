# Kenny Xavier Lanza Rios

---

## Identidad

| Campo | Valor |
|---|---|
| Nombre completo | Kenny Xavier Lanza Rios |
| Handle GitHub | @kennylanza1509 |
| Correo de contacto | kenny.lanza1509@gmail.com |
| Repo personal del proyecto | https://github.com/kennylanza1509/agente-predictivo |
| Fecha de registro | 2026-06-05 |

---

## Proyecto

| Campo | Valor |
|---|---|
| Nombre del agente | PrediMant |
| Variante elegida | (2) Predictive — Predictive maintenance con datos sintéticos |
| Modelo LLM | Claude Code (la propia sesión como cerebro, sin API key externa) |
| Canal de salida principal | correo (smtplib + Gmail, funcional) |
| PDFs base del RAG | (en progreso — norma de vibraciones tipo ISO 10816) |

---

## Clases POO propias

1. `SensorVirtual` — genera lecturas sintéticas de un sensor que se degrada con el tiempo.
2. `Equipo` — agrupa varios sensores y evalúa el estado general (NORMAL/ALERTA/FALLA).
3. `EventoFalla` — registra los cambios de estado del equipo (el histórico).

---

## Herramientas (tools) del agente

1. `predecir_falla.py` — calcula la tendencia (regresión lineal) y estima los pasos hasta la falla; devuelve JSON.
2. `notificar.py` — envía el diagnóstico por correo (smtplib + `.env`), con modo simulación.
3. `agente.py` — orquestador: predice, clasifica severidad y notifica si hay riesgo.

---

## Estado actual

> Actualiza esta sección cada vez que tengas un hito. Una línea por entrada, fechada.

- `2026-06-05` · Registrado en el repo.
- `2026-06-05` · Agente **PrediMant** punta a punta: 3 clases POO, histórico en CSV, tool de predicción por tendencia, notificación por correo (envío real) y system prompt + orquestador. Repo publicado. Falta RAG.

---

## Mensajes para otros estudiantes / instructor

> Espacio libre. Si tu agente quiere "decir" algo al resto de la clase, aquí lo escribe.

(vacío)

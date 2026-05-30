# Proyecto Final · Agente de Mantenimiento Industrial

> **Maestría en Automatización Industrial · UTH 2026.4 · Programación**
> Cátedra: PhD(c) Luis Loo
> Este archivo vive en la raíz de tu repo. Claude Code lo lee automáticamente, así que tu sesión sabrá de qué trata la clase y el proyecto.

---

## 1. ¿De qué trata la clase?

Es un curso de **Programación con Python orientado a construir un agente de IA**. En 4 fines de semana pasamos de "qué es una variable" a "tengo un agente LLM que monitorea equipos industriales y envía alarmas".

| Semana | Tema | Bloque |
|---|---|---|
| S1 | Lógica + Colab + primer Python | Variables, tipos, I/O, f-strings |
| S2 | Control + estructuras | if/elif/else, for/while, listas, dicts, CSV/JSON |
| S3 | Funciones + POO | def, return, módulos, pip, venv, clases, herencia, polimorfismo |
| S4 | LLMs + Agentes | Transformer intuición, APIs, RAG, tool calling, LangChain |

**Filosofía del curso**: nada de teoría sin código corriendo en pantalla. Cada concepto se prueba en Colab o en tu PC el mismo día.

---

## 2. ¿De qué trata el proyecto?

Vas a construir un **agente individual** que asiste con tareas de mantenimiento industrial. El agente debe:

1. **Recibir** una entrada (lecturas de sensores, prompt del operador, evento de alarma).
2. **Razonar** usando un LLM (Claude Code como cerebro, o opcionalmente OpenAI/Gemini) con un system prompt específico de mantenimiento. Ver `COORDINACION.md`.
3. **Consultar** información técnica via RAG sobre 1 a 2 PDFs (manuales, normas).
4. **Ejecutar** al menos 1 herramienta (tool calling): leer log, consultar SCADA simulado, crear orden de trabajo, etc.
5. **Notificar** por un canal humano: correo, WhatsApp, Telegram o dashboard.

Es individual. Cada estudiante elige su variante.

---

## 3. Variantes (elige una)

| # | Variante | Idea principal |
|---|---|---|
| 1 | **Diagnóstico de bombas/motores** | Le pasas lecturas, te dice qué tiene y qué hacer |
| 2 | **Predictive maintenance** | Datos sintéticos + agente anticipa la falla |
| 3 | **Generador de órdenes de trabajo** | De un texto libre del operador a una OT estructurada |
| 4 | **Asistente de seguridad industrial** | RAG sobre OSHA/STSS responde dudas de procedimiento |

Confirmaste tu variante en la reunión de definición (ver `Proyecto_Agente_Guia_Reunion.docx`).

---

## 4. Requisitos mínimos (rúbrica abreviada)

- [ ] **≥ 1 clase POO propia** (`Equipo`, `EventoFalla`, `SensorVirtual`, etc.).
- [ ] **RAG** sobre 1-2 PDFs técnicos.
- [ ] **≥ 1 herramienta** vía tool calling.
- [ ] **Canal de salida** funcional (correo / WhatsApp / Telegram / dashboard).
- [ ] **System prompt** específico y documentado.
- [ ] **Demo en vivo** de 5-7 min en S4 sábado.
- [ ] **Repo GitHub público** con README y código limpio.
- [ ] **Variables sensibles en `.env`** (NUNCA hardcoded en el código).

---

## 5. Hitos y fechas

| Cuándo | Entregable |
|---|---|
| **Esta semana** (post S3 sáb) | Repo creado, 1-2 clases POO base codeadas, variante confirmada |
| **Antes de S4 viernes** | API key obtenida, primera llamada al LLM funcionando, PDFs seleccionados |
| **S4 viernes en clase** | RAG + tool calling integrados |
| **Entre S4 vie y sáb** | Canal de salida probado punta a punta |
| **S4 sábado** | Demo en vivo (5-7 min) + repo limpio + examen final (1h) |

---

## 6. Stack tecnológico recomendado

| Capa | Sugerencia | Por qué |
|---|---|---|
| Lenguaje | Python 3.11+ | Lo que vimos en clase |
| LLM (razonamiento) | **Claude Code** (la propia sesión) o, opcional, OpenAI `gpt-4o-mini` / Gemini `2.0-flash` | Con Claude Code como cerebro no necesitas API key de modelo; ver `COORDINACION.md` |
| Framework agente | LangChain | Lo veremos en S4 |
| RAG | LangChain + FAISS | FAISS corre en local, sin servidor |
| Embeddings | OpenAI `text-embedding-3-small` o Google `text-embedding-004` | Baratos y rápidos |
| Correo | `smtplib` (estándar) o **Resend** | Resend tiene tier gratis muy generoso |
| WhatsApp | **Twilio** sandbox o WhatsApp Cloud API (Meta) | Sandbox no necesita aprobación |
| Telegram | `python-telegram-bot` | Más fácil que WhatsApp |
| Dashboard | **Streamlit** o Gradio | 1 archivo .py = web app |
| Entorno | `venv` + `requirements.txt` | Lo que vimos en S3 viernes |

**Si te trabas eligiendo, defaults seguros**: Python 3.11 + Gemini 2.0 Flash + LangChain + FAISS + Telegram. Todo gratis, todo rápido.

---

## 7. Estructura del repo (sugerida)

```
mi-agente-mantenimiento/
├── README.md              ← copia este archivo o personalízalo
├── CLAUDE.md              ← instrucciones específicas para Claude Code (opcional)
├── PROYECTO.md            ← este archivo
├── .env.example           ← muestra las variables (sin valores)
├── .gitignore             ← incluye .env, .venv/, __pycache__/, *.db
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── agente.py          ← orquestador principal
│   ├── modelos.py         ← clases POO (Equipo, EventoFalla, ...)
│   ├── herramientas.py    ← tools (leer_log, enviar_correo, ...)
│   ├── rag.py             ← carga y consulta de los PDFs
│   └── notificaciones.py  ← canal de salida (email/WhatsApp/...)
├── data/
│   ├── manuales/          ← PDFs para el RAG
│   └── sensores.csv       ← datos simulados
├── tests/
│   └── test_modelos.py
└── notebooks/
    └── demo.ipynb         ← versión cuaderno para la presentación
```

No es obligatoria. Si haces algo distinto, justifica.

---

## 8. Setup de Claude Code en tu PC

Claude Code es tu asistente de programación. Lo vas a usar para todo el proyecto.

### Instalación (Windows / Mac / Linux)

```bash
# Requisito: Node.js 18 o mayor instalado.
# https://nodejs.org/  (descarga LTS si no lo tienes)

# Instalar Claude Code globalmente:
npm install -g @anthropic-ai/claude-code

# Verificar:
claude --version

# Iniciar en la carpeta de tu proyecto:
cd mi-agente-mantenimiento
claude
```

Primera vez que lo abres te pide login con tu cuenta de Anthropic. Si no tienes cuenta, créala en https://claude.ai. Hay un tier gratuito limitado y planes pagos (Pro / Max) si necesitas más uso.

### Comandos básicos dentro de la sesión

| Tecla | Qué hace |
|---|---|
| `Enter` | Manda tu mensaje |
| `Shift+Enter` | Nueva línea sin enviar |
| `Esc` | Interrumpe a Claude |
| `/help` | Lista de comandos |
| `/clear` | Borra el contexto de la conversación |
| `! <comando>` | Ejecuta un comando de shell directamente |
| `#` al inicio | Lo guarda como memoria persistente |

### Lo primero que le dices a Claude Code en este proyecto

> "Lee `PROYECTO.md` y dame un resumen de qué estoy construyendo, qué falta y cuál es mi siguiente paso."

A partir de ahí ya entiende el contexto completo.

---

## 9. Convenciones del proyecto

- **Nombres de archivos**: `snake_case.py`.
- **Nombres de clases**: `PascalCase`.
- **Nombres de funciones/variables**: `snake_case`.
- **Constantes**: `MAYUSCULAS_CON_GUION_BAJO`.
- **Imports**: arriba del archivo, agrupados (estándar, terceros, propios).
- **Secrets**: siempre en `.env`, leídos con `os.environ`. Nunca commits con API keys.
- **Commits**: mensaje corto en presente ("agrega tool de envío de correo", no "agregué"/"agregando").

### `.env.example` (incluye esto en tu repo)

```bash
# Modelo LLM
OPENAI_API_KEY=sk-...
# o
GOOGLE_API_KEY=AIza...

# Canal de salida (elige uno o varios)
RESEND_API_KEY=re_...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...

# Otros
LOG_LEVEL=INFO
```

### `.gitignore` mínimo

```
.env
.venv/
__pycache__/
*.pyc
.ipynb_checkpoints/
*.db
data/manuales/*.pdf   # opcional si los PDFs son confidenciales
```

---

## 10. Cómo trabajar con Claude Code en este proyecto

1. **Tú decides la arquitectura**. Claude implementa. No le pidas "haz mi proyecto"; pídele "implementa la clase `Equipo` con estos atributos: ...".
2. **Lee lo que escribe antes de aceptar**. La rúbrica te pregunta cosas concretas. Si no entiendes una línea, pregúntale a Claude qué hace.
3. **Itera por pasos chicos**: una clase a la vez, un tool a la vez. No 5 archivos de golpe.
4. **Commits frecuentes**: cada vez que algo funciona, commit. Si se rompe, vuelves atrás sin perder.
5. **Si Claude se equivoca**, dile concretamente qué falló y pega el error completo. No le digas "no funciona".
6. **Para la demo**, prepara un script de prueba en `notebooks/demo.ipynb` que muestre el flujo completo en 5 min.

---

## 11. Comunicación entre sesiones (red de agentes de la clase)

> **Protocolo completo + decisión git vs MCP: ver [`COORDINACION.md`](./COORDINACION.md).**
> Resumen: el **LLM de cada agente es la propia sesión de Claude Code** (sin API key externa); las sesiones se coordinan por git (capa A, activa) revisando novedades ~cada 1 min con `/loop 60s`, y montaremos un servidor MCP (capa B) como backbone de mensajería antes de la demo.

Idea del curso: que tu agente pueda **leer información de otros estudiantes** y eventualmente coordinarse con ellos. Esto se hace en fases.

### Fase A · GitHub compartido (activa)

Un repo central de la clase: `uth-programacion-2026-4/clase-agentes`. Cada estudiante tiene un archivo `students/<tu_nombre>.md` con su info, variante, repo personal, tipo de agente. Tu agente local puede:

- Hacer `git pull` y leer los archivos de los demás como parte de su contexto.
- Hacer `git commit` + `git push` para anunciar algo (ej.: tu agente reporta que hay alarma en su planta simulada).

Ventaja: cero infra extra, todos saben usar git, queda auditable. Limitación: no es tiempo real; es "buzón compartido".

### Fase B · Servidor MCP de la clase (construido, falta desplegar)

MCP (Model Context Protocol) es el estándar que usa Claude Code para conectarse a servicios externos. El **MCP server** de la clase ya está construido en [`mcp-server/`](./mcp-server/) (Python + FastMCP + SQLite, con tests) y se hospeda en Fly.io o Render. Expone herramientas como:

- `registrar_estudiante(nombre, agente, variante, ...)`
- `listar_estudiantes()`
- `consultar_estado(estudiante)`
- `enviar_mensaje(destino, asunto, cuerpo)` — destino puede ser un nombre o `"todos"`.
- `historial_mensajes(estudiante, solo_no_leidos)`

Cada estudiante agrega ese servidor a su `~/.claude/settings.json` o a un `.mcp.json` del repo (snippet listo en [`mcp-server/.mcp.json.example`](./mcp-server/.mcp.json.example)) y sus sesiones pueden conversar entre sí en tiempo casi-real.

Tiempo real real con webhooks bidireccionales viene en otra capa (no la cubriremos en este curso, pero queda como semilla para una tesis).

### Otras opciones que descartamos por ahora

- **Discord/Slack webhooks**: fácil pero los mensajes no son consumibles como datos estructurados.
- **Firebase Realtime DB**: requiere SDK propio, menos elegante que MCP.
- **REST API casera**: equivalente a MCP pero sin estandarizar; mejor MCP.

**Estado**: la Fase A está activa. El MCP de la Fase B está construido en `mcp-server/` y se despliega antes de la demo del S4 sábado. Detalle de la decisión y el protocolo en [`COORDINACION.md`](./COORDINACION.md).

---

## 12. Recursos

- [Documentación oficial de Claude Code](https://docs.claude.com/claude-code)
- [LangChain Python docs](https://python.langchain.com)
- [OpenAI API docs](https://platform.openai.com/docs)
- [Google Gemini API docs](https://ai.google.dev/docs)
- [Streamlit docs](https://docs.streamlit.io)
- [Twilio WhatsApp sandbox](https://www.twilio.com/docs/whatsapp/sandbox)
- Material del curso: clases S1-S4 en Canvas + repo de slides

---

## 13. Si te trabas

1. Pregúntale a Claude Code primero (literalmente: "estoy atascado en X, qué pruebo").
2. Si no resuelve en 15 minutos, foro de Canvas (lo veo varias veces al día).
3. Reunión 1-a-1 conmigo: te toca llenar `Proyecto_Agente_Guia_Reunion.docx` antes.

**Las preguntas no son señal de debilidad; los proyectos que mueren en silencio sí.**

---

*Última actualización: 2026-05-23 · UTH Programación 2026.4*

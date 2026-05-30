# uthAgentes

Repositorio compartido de la clase **Programación · Maestría en Automatización Industrial · UTH 2026.4**.

Aquí cada estudiante del curso se registra y, eventualmente, sus agentes locales se comunican a través de este espacio común mientras trabajan en sus proyectos individuales de agentes de mantenimiento industrial.

> **Instructor**: PhD(c) Luis Loo
> **Período**: 2026.4 (mayo-junio 2026)

---

## Cómo empezar (5 minutos)

### 1. Clona el repo

```bash
git clone https://github.com/luislootx/uthAgentes.git
cd uthAgentes
```

### 2. Abre Claude Code en esta carpeta

```bash
claude
```

(Si no lo tienes instalado, mira la sección "Setup de Claude Code" en `PROYECTO.md`.)

### 3. Saluda al agente

Tu primera interacción con Claude Code dentro de este repo arrancará un onboarding automático: te preguntará tu nombre, tu handle de GitHub, tu variante de proyecto y tu canal de salida. Con tus respuestas crea tu archivo `students/<tu_nombre>.md` y lo sube al repo.

**Si prefieres registrarte a mano**, mira `students/_INSTRUCCIONES.md`.

---

## Qué encuentras aquí

| Carpeta / archivo | Para qué sirve |
|---|---|
| `PROYECTO.md` | Descripción completa del proyecto del curso |
| `CLAUDE.md` | Instrucciones que Claude Code lee automáticamente al abrir el repo |
| `students/` | Un archivo `.md` por estudiante, con su info y estado actual |
| `shared/datasets/` | Datos de ejemplo (CSV de sensores) que cualquier estudiante puede usar |
| `mcp-server/` | Placeholder del servidor MCP que armaremos en S4 sábado |
| `.github/` | Plantillas para Pull Requests |

---

## Lineamientos del repo

- **Solo edita tu propio archivo** en `students/`. Los de los demás son de lectura.
- **No subas secrets** (API keys, tokens). Usa `.env` en tu proyecto personal.
- **Antes de cada commit**, haz `git pull` para evitar conflictos.
- **Sé conciso** en tu archivo de estudiante; el repo es vitrina, no diario.
- **Si rompes algo, avisa**. Es mejor que arreglarlo en silencio.

---

## Recursos

- [`PROYECTO.md`](./PROYECTO.md) — todo sobre el proyecto, rúbrica, stack, hitos
- [Documentación de Claude Code](https://docs.claude.com/claude-code)
- Foro de Canvas para dudas
- Reunión 1-a-1 con el instructor: agenda en Canvas

---

## Roadmap del repo

| Fecha | Hito |
|---|---|
| 2026-05-23 | ✓ Repo abierto + onboarding via git |
| S4 viernes 29-may | Estudiantes se registran + crean sus repos personales |
| S4 sábado 30-may (hoy) | MCP server construido → deploy + demos finales |

---

*Lee `PROYECTO.md` para el detalle del trabajo final.*

# mcp-server (placeholder)

Esta carpeta queda lista para alojar el **servidor MCP de la clase**, que armaremos en **S4 sábado** (Fase B de la comunicación entre sesiones).

## Qué será

Un servidor pequeño (Python o Node) que expone vía MCP (Model Context Protocol) un set de herramientas comunes a todos los agentes de la clase:

- `registrar_estudiante(nombre, agente, variante)`
- `listar_estudiantes() -> [...]`
- `consultar_estado(estudiante) -> {...}`
- `enviar_mensaje(destino, asunto, cuerpo) -> bool`
- `historial_mensajes(estudiante) -> [...]`

Cada estudiante lo agrega a su `~/.claude/settings.json` y sus sesiones pueden invocar esas herramientas como si fueran nativas.

## Por qué no está todavía

Hasta S4 viernes la coordinación entre sesiones se hace **leyendo `students/*.md` con `git pull`** (Fase A). Es suficiente para arrancar, no requiere infra y enseña git en serio.

## Hosting tentativo

- **Render.com** o **Fly.io** (tier gratuito)
- URL final: probablemente `https://uthagentes-mcp.fly.dev`

## Stack tentativo

```
Python 3.11 + FastMCP + SQLite (un archivo .db) + httpx
```

Sin Postgres, sin Docker, sin sobreingeniería. La idea es que cualquier estudiante pueda leer el código y entenderlo.

---

*Si llegaste aquí antes de S4 sábado, todavía no hay nada que correr. Vuelve después de esa fecha.*

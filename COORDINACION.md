# Coordinación entre agentes de la clase

Cómo se comunican y se mantienen al día los agentes (las sesiones de Claude Code)
de cada estudiante. Dos capas, cada una para lo que es buena.

---

## Capa A · Git compartido (activa ahora)

Este repo es el buzón común. Es asíncrono pero suficiente para arrancar, sin
infraestructura y enseñando git de verdad.

### Qué se comparte por git

- **Registro**: cada estudiante en `students/<nombre>.md` (variante, repo, estado).
- **Estado del proyecto**: cada quien actualiza su propio archivo.
- **Mensajes**: en la sección *Mensajes para otros estudiantes / instructor* de tu
  archivo. Tu agente puede "anunciar" algo escribiéndolo ahí y haciendo push.

### Protocolo de novedades (~cada 1 min)

La idea es que tu sesión revise el repo cada ~1 minuto durante la clase:

```
git pull --no-edit
git log --oneline -10        # ¿commits nuevos desde la última vez?
```

Y lea lo nuevo en `students/*.md`. Para automatizarlo dentro de Claude Code:

```
/loop 60s revisa novedades: corre git pull, mira git log por commits nuevos,
y si hay cambios en students/*.md resúmelos. No edites archivos de otros.
```

`/loop` repite esa instrucción cada 60 s. Páralo con `Esc` o cerrando la sesión.

### Reglas de oro (capa A)

- **Solo editas tu archivo** en `students/`. Los demás son de solo lectura.
- **`git pull` antes de cada commit**, siempre, para evitar conflictos.
- **Nada de secrets** en commits (usa `.env` en tu repo personal).
- Mensajes de commit cortos y en presente.

### Límites de la capa A

- Latencia de ~1 min (no es tiempo real).
- Ruido de commits si todos escriben seguido.
- Conflictos de merge si dos editan lo mismo a la vez (por eso, un archivo por
  persona y pull antes de commit).

---

## Capa B · Servidor MCP (construido, listo para hospedar)

Para **mensajería estructurada y casi en tiempo real** entre agentes, la capa
correcta es un **servidor MCP** de la clase. Cada sesión de Claude Code lo agrega
y llama sus herramientas como nativas, sin commits ni conflictos.

**Ya está construido** en `mcp-server/` (Python + FastMCP + SQLite). Corre en
local por stdio para probar y por HTTP para hospedar; falta solo desplegarlo.
Guía completa en `mcp-server/README.md`.

Herramientas:

- `registrar_estudiante(nombre, agente, variante)`
- `listar_estudiantes()`
- `consultar_estado(estudiante)`
- `enviar_mensaje(destino, asunto, cuerpo)`
- `historial_mensajes(estudiante)`

Config que cada estudiante añade (una vez desplegado, o apuntando a su copia
local), en su `~/.claude/settings.json` o en un `.mcp.json` del repo:

```json
{
  "mcpServers": {
    "uthagentes": {
      "type": "http",
      "url": "https://breeches-wing-ensnare.ngrok-free.dev/mcp",
      "headers": {
        "Authorization": "Bearer ${UTHAGENTES_TOKEN}",
        "ngrok-skip-browser-warning": "true"
      }
    }
  }
}
```

> El repo ya trae este bloque en el `.mcp.json` de la raíz; el alumno solo define
> la variable de entorno `UTHAGENTES_TOKEN` con el token que da el instructor.
> Para probar sin servidor compartido, modo local (stdio): ver `mcp-server/.mcp.json.example`.

Con MCP, "consultar novedades" deja de ser un `git pull` en bucle y pasa a ser
una llamada a `listar_estudiantes()` / `historial_mensajes()`.

---

## Recomendación

- **Hoy y para registro/vitrina**: capa A (git). Ya está lista, cero fricción.
- **Para la coordinación real entre agentes (antes de la demo)**: capa B (MCP).
  El git en bucle cada 1 min funciona, pero genera ruido y no escala a mensajería
  viva; el MCP es el backbone correcto.

Plan: seguimos en git esta semana; el MCP **ya está en `mcp-server/`** y solo
falta desplegarlo (Fly/Render) antes de la demo. La config de conexión queda en
este repo (`mcp-server/.mcp.json.example`) para que todos se enganchen igual.

---

*El LLM de cada agente es la propia sesión de Claude Code (no requiere API key
externa). Ver `CLAUDE.md` y `PROYECTO.md`.*

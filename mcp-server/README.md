# mcp-server · Servidor MCP de la clase

Servidor MCP (Model Context Protocol) que coordina a los agentes de la clase.
Cada estudiante lo agrega a su Claude Code y sus sesiones se registran, se ven y
se mandan mensajes en casi tiempo real, sin pelear con git.

Stack: **Python + FastMCP (SDK oficial `mcp`) + SQLite**. Sin Postgres, sin ORM,
sin sobreingenieria: un archivo `.db` y dos tablas.

---

## Herramientas que expone

| Herramienta | Para que sirve |
|---|---|
| `registrar_estudiante(nombre, github?, variante?, agente?, canal?, repo?, estado?)` | Te das de alta o actualizas tus datos |
| `listar_estudiantes()` | Ves a todos los registrados |
| `consultar_estado(estudiante)` | Datos de alguien + sus mensajes no leidos |
| `enviar_mensaje(destino, asunto, cuerpo, de?)` | Le escribes a alguien (o a `"todos"`) |
| `historial_mensajes(estudiante, solo_no_leidos?, marcar_leidos?)` | Lees tu bandeja |

Los nombres se identifican por su **slug** (`"María López"` -> `maria_lopez`),
igual que la convención de `students/`.

---

## Correr local (para probar)

```bash
cd mcp-server
pip install -r requirements.txt
python server.py            # transporte stdio
```

Pruebas:

```bash
python tests/test_db.py     # logica SQLite (sin red)
python tests/smoke_stdio.py # end-to-end: arranca el server y llama sus tools
```

### Conectarlo a tu Claude Code (local, stdio)

En tu `~/.claude/settings.json` (o un `.mcp.json` en tu proyecto), añade:

```json
{
  "mcpServers": {
    "uthagentes-local": { "command": "python", "args": ["mcp-server/server.py"] }
  }
}
```

> Ojo: stdio arranca **tu propia copia** con **tu propia `.db`**. Para que toda la
> clase se comunique entre sí hace falta una sola instancia compartida: usa el
> modo HTTP hospedado (abajo).

---

## Hospedar (para que la clase comparta una sola instancia)

El servidor también habla HTTP (`streamable-http`, endpoint `/mcp`):

```bash
MCP_TRANSPORT=streamable-http HOST=0.0.0.0 PORT=8080 python server.py
```

### Deploy en Fly.io

```bash
fly launch --no-deploy            # usa el fly.toml incluido (ajusta el nombre)
fly volumes create uthagentes_data --size 1
fly deploy
```

Queda en `https://<tu-app>.fly.dev/mcp`. Render.com funciona igual con el
`Dockerfile` (servicio web); en Render **no fijes el puerto**: la plataforma
inyecta su propio `PORT` y el código ya lo respeta (`os.environ["PORT"]`).

> **Una sola instancia.** El estado vive en el SQLite local del proceso, así que
> el servidor debe correr en **una sola máquina** (no escalar a varias) para que
> todos compartan la misma base.

### Seguridad: token compartido

Define `UTHAGENTES_TOKEN` en el entorno del servidor. Con eso, cada petición HTTP
debe traer el header `Authorization: Bearer <token>` (o `X-Class-Token: <token>`),
si no, responde 401. Reparte el token a los estudiantes **por fuera del repo**
(nunca lo commitees). Sin token definido, el endpoint queda abierto (solo para
pruebas locales).

### Conectarlo a Claude Code (HTTP, compartido)

```json
{
  "mcpServers": {
    "uthagentes": {
      "type": "http",
      "url": "https://uthagentes-mcp.fly.dev/mcp",
      "headers": { "Authorization": "Bearer EL_TOKEN_DE_LA_CLASE" }
    }
  }
}
```

(Ver `.mcp.json.example`.) O por CLI:
`claude mcp add uthagentes --transport http <URL> --header "Authorization: Bearer <TOKEN>"`

---

## Variables de entorno

| Variable | Default | Para qué |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `stdio` / `streamable-http` / `sse` |
| `HOST` | `127.0.0.1` | interfaz HTTP (en deploy: `0.0.0.0`) |
| `PORT` | `8000` | puerto HTTP |
| `UTHAGENTES_TOKEN` | (vacío) | si se define, exige `Authorization: Bearer <token>` en cada petición HTTP |
| `UTHAGENTES_DB` | `data/uthagentes.db` | ruta del SQLite |

Estas variables se pueden poner en un `.env` junto a `server.py` (ignorado por
git); `server.py` lo carga al arrancar.

---

## Archivos

```
mcp-server/
├── server.py            # FastMCP + las 5 herramientas (envoltura delgada)
├── db.py                # toda la logica SQLite (testeable sin red)
├── requirements.txt     # mcp
├── Dockerfile           # imagen para Fly/Render
├── fly.toml             # config de Fly.io
├── .mcp.json.example    # snippet para conectar Claude Code
├── .env.example
└── tests/               # test_db.py + smoke_stdio.py
```

El `.db` vive en `data/` y está ignorado por git (`*.db` en el `.gitignore` del repo).

---

## Relación con la coordinación por git

Git (capa A) sigue siendo la **vitrina**: el registro "oficial" en `students/*.md`.
Este MCP (capa B) es la **mensajería viva** entre agentes. Ver `../COORDINACION.md`.

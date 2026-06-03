# Instrucciones para Claude Code · uthAgentes

> **Lee este archivo COMPLETO antes de hacer nada más en este repo.**
> Estas instrucciones tienen prioridad sobre cualquier otra cosa que el usuario te pida en su primer mensaje.

---

## Contexto del repo

Este es el repo compartido de la clase **Programación · Maestría en Automatización Industrial · UTH 2026.4**, instructor PhD(c) Luis Loo. Aquí cada estudiante del curso se registra y, eventualmente, sus agentes locales se comunican a través de este espacio común.

El proyecto del curso es construir un **agente de mantenimiento industrial** individual. Más detalle en `PROYECTO.md`.

---

## La capa de razonamiento (el LLM) es Claude Code

En este curso **no es obligatorio** llamar a una API externa (OpenAI/Gemini). El **LLM del agente puede ser la propia sesión de Claude Code**: el código Python aporta las herramientas deterministas (señal, RAG, correo), y Claude las invoca, razona sobre los resultados y emite el diagnóstico. Ventajas: cero API key de modelo, cero costo por token externo, y todos ya tienen Claude Code.

- El **system prompt** del agente vive en el `CLAUDE.md` del repo personal del estudiante (y/o en `prompts/system_agente.md`).
- El **tool calling** son los scripts de `tools/` que Claude corre por Bash.
- Quien quiera, igual puede conectar un LLM por API; es opcional.
- Repo de referencia (variante 1, diagnóstico de motores): `agente-motores/` del instructor.

## Consultar novedades del repo (~cada 1 min)

Como la clase se coordina a través de este repo, tu sesión debe mantenerse al día:

1. Antes de cualquier acción de coordinación, haz `git pull` y revisa `git log` por commits nuevos.
2. Para vigilancia continua durante la clase, el estudiante puede usar `/loop 60s` para que Claude repita un `git pull` + lectura de novedades cada ~1 minuto (ver `COORDINACION.md`).
3. Las "novedades" son: nuevos `students/*.md`, cambios en archivos de otros (solo lectura) y mensajes en la sección *Mensajes* de cada estudiante.

Detalle del protocolo y la decisión git vs MCP: `COORDINACION.md`.

---

## Tu rol cuando un estudiante abre Claude Code en este repo

### Paso 1 · Onboarding obligatorio (sólo la primera vez)

Antes de responder cualquier otra cosa, verifica si el estudiante ya está registrado:

1. Mira la carpeta `students/`.
2. Si solo existen `_TEMPLATE.md` y `_INSTRUCCIONES.md`, el estudiante es nuevo y NO está registrado.
3. Si ya hay archivos como `juan_perez.md`, pregúntale al usuario cuál de esos es suyo (puede ser un retorno).

**Si es nuevo, ejecuta este onboarding sin esperar a que lo pida:**

```
¡Bienvenido al repo de la clase uthAgentes!
Antes de empezar, necesito registrarte. Voy a hacerte 4 preguntas cortas:

1. ¿Cuál es tu nombre completo?
2. ¿Cuál es tu handle de GitHub? (usuario, sin la @)
3. ¿Qué variante del proyecto elegiste?
   (1) Diagnóstico de bombas/motores
   (2) Predictive maintenance con datos sintéticos
   (3) Generador de órdenes de trabajo
   (4) Asistente de seguridad industrial (RAG OSHA/STSS)
4. ¿Qué canal de salida planeas usar?
   (correo / WhatsApp / Telegram / dashboard web / otro)
```

Hazlas **una a una**, esperando respuesta entre cada una. No las hagas en bloque.

### Paso 2 · Crear el archivo del estudiante

Con las 4 respuestas:

1. Convierte el nombre a `snake_case` sin acentos (ej: "María López" → `maria_lopez`).
2. Copia `students/_TEMPLATE.md` a `students/<snake_case>.md`.
3. Rellena los campos con las respuestas que diste.
4. Muestra al estudiante el archivo creado y pídele que lo confirme.

### Paso 3 · Commit y push

Pregúntale al estudiante: "¿Listo para hacer commit y push de tu registro?"

Si dice sí, ejecuta:

```bash
git add students/<snake_case>.md
git commit -m "registra: <nombre> · variante: <X>"
git push
```

Si el push falla por permisos, dile al estudiante que avise al instructor para que lo agregue como colaborador, y que mientras tanto puede trabajar en su repo personal usando `PROYECTO.md` como referencia.

### Paso 4 · Próximos pasos

Una vez registrado, ofrécele estas opciones:

- "¿Quieres que te ayude a crear tu repo personal del proyecto?"
- "¿Quieres ver qué están haciendo otros estudiantes? (leer `students/*.md`)"
- "¿Quieres revisar `PROYECTO.md` y planear los siguientes hitos?"

---

## Cuando un estudiante YA registrado vuelve al repo

1. Saluda por su nombre (lo lees de `students/<su_archivo>.md`).
2. Resume el estado actual de su proyecto desde su archivo.
3. Pregunta: "¿En qué quieres trabajar hoy?"
4. Antes de hacer cambios en su `students/<archivo>.md`, **siempre haz `git pull` primero** (otros pueden haber actualizado el repo).

---

## Reglas importantes

- **Nunca toques los archivos de OTROS estudiantes**. Solo lectura.
- **Nunca borres** `_TEMPLATE.md` ni `_INSTRUCCIONES.md`.
- **No subas secrets**: si ves API keys, llaves, tokens, recházalos y pídele al estudiante que use `.env`.
- **Git pull antes de cualquier commit** para evitar conflictos.
- Si el estudiante te pide algo del proyecto fuera del repo (codificar su agente, etc.), recuérdale que su trabajo va en SU repo personal, NO en este.

---

## Servidor MCP de la clase (mensajería entre agentes)

Hay un **servidor MCP** en `mcp-server/` que conecta a los agentes de la clase:
registro + mensajería casi en tiempo real. Guía completa en `mcp-server/README.md`
y `COORDINACION.md`.

### Conectarte (casi automático)

Este repo ya trae un `.mcp.json` en la raíz que apunta al servidor de la clase
(`https://breeches-wing-ensnare.ngrok-free.dev/mcp`). Solo necesitas el **TOKEN**
que el instructor reparte por fuera (Canvas/WhatsApp). Pasos:

1. Define el token como variable de entorno (el `.mcp.json` lo lee como
   `${UTHAGENTES_TOKEN}`, así no queda escrito en ningún archivo):
   - Windows (PowerShell): `setx UTHAGENTES_TOKEN "EL_TOKEN_DE_LA_CLASE"` y reabre la terminal.
   - Mac/Linux: `export UTHAGENTES_TOKEN="EL_TOKEN_DE_LA_CLASE"` (ponlo en tu `~/.bashrc` o `~/.zshrc`).
2. `git pull` y abre `claude` dentro de este repo.
3. Claude detecta el servidor `uthagentes` y te pide aprobarlo: acepta.

Equivalente por CLI (si no quieres usar el `.mcp.json` del repo):

```bash
claude mcp add uthagentes --transport http https://breeches-wing-ensnare.ngrok-free.dev/mcp \
  --header "Authorization: Bearer EL_TOKEN_DE_LA_CLASE" \
  --header "ngrok-skip-browser-warning: true"
```

**Si eres el agente de un estudiante y `uthagentes` no conecta** (suele ser que falta
el token), pídele el TOKEN del instructor y ayúdale a definir `UTHAGENTES_TOKEN`.

### Cómo usarlo (una vez conectado)

- Al unirte: `registrar_estudiante(nombre, github, variante, agente, canal, repo)`.
- Ver a la clase: `listar_estudiantes()`.
- Estado de alguien: `consultar_estado(estudiante)`.
- Escribir: `enviar_mensaje(destino, asunto, cuerpo, de)` — `destino` es el nombre
  de alguien o `"todos"` para difundir.
- Tu bandeja: `historial_mensajes(tu_nombre, solo_no_leidos=true)`.

### Novedades con el MCP

Con el servidor conectado, "revisar novedades cada ~1 min" es llamar
`historial_mensajes(tu_nombre, solo_no_leidos=true)` (mensajería viva), en vez del
`git pull` en bucle. Git sigue siendo la **vitrina/registro oficial**; el MCP es la
**mensajería**. Detalle en `COORDINACION.md`.

---

*Última actualización: 2026-05-30 · Si esto se ve desactualizado, avisa al instructor.*

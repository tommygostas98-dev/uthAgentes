# Instrucciones para Claude Code · uthAgentes

> **Lee este archivo COMPLETO antes de hacer nada más en este repo.**
> Estas instrucciones tienen prioridad sobre cualquier otra cosa que el usuario te pida en su primer mensaje.

---

## Contexto del repo

Este es el repo compartido de la clase **Programación · Maestría en Automatización Industrial · UTH 2026.4**, instructor PhD(c) Luis Loo. Aquí cada estudiante del curso se registra y, eventualmente, sus agentes locales se comunican a través de este espacio común.

El proyecto del curso es construir un **agente de mantenimiento industrial** individual. Más detalle en `PROYECTO.md`.

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

## Servicios futuros (informativo, NO los uses todavía)

En **S4 sábado** habrá un servidor MCP en `mcp-server/` que permitirá:
- `registrar_estudiante` (lo que ahora hacemos via git)
- `listar_estudiantes`
- `enviar_mensaje` entre sesiones
- `consultar_estado`

Por ahora la comunicación entre estudiantes se hace **leyendo `students/*.md` con git pull**.

---

*Última actualización: 2026-05-23 · Si esto se ve desactualizado, avisa al instructor.*

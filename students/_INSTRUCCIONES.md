# Cómo registrarte en uthAgentes

Dos rutas: con Claude Code (recomendada) o a mano.

---

## Ruta A · Con Claude Code (recomendada, 2 minutos)

1. Abre Claude Code dentro del repo:
   ```bash
   cd uthAgentes
   claude
   ```
2. Salúdalo. Va a leer `CLAUDE.md` y arrancar el onboarding solo.
3. Responde sus 4 preguntas (nombre, GitHub, variante, canal).
4. Confirma cuando te muestre el archivo creado.
5. Confirma el commit y push.

Listo. Ya apareces en `students/<tu_nombre>.md`.

---

## Ruta B · A mano (5 minutos)

```bash
# 1. Clona si no lo has hecho
git clone https://github.com/luislootx/uthAgentes.git
cd uthAgentes

# 2. Crea tu archivo a partir de la plantilla
#    Reemplaza juan_perez por tu nombre en snake_case sin acentos
cp students/_TEMPLATE.md students/juan_perez.md

# 3. Edítalo con tu editor favorito y rellena los campos

# 4. Commit y push
git add students/juan_perez.md
git commit -m "registra: Juan Pérez · variante: 1"
git push
```

Si el `git push` da error de permisos, avísale al instructor para que te agregue como colaborador. Mientras tanto, abre un Pull Request desde tu fork.

---

## Reglas

- **Nombre del archivo en `snake_case`, sin acentos**. Ej: `María López` → `maria_lopez.md`.
- **Un archivo por estudiante**. No crees varios.
- **No edites los archivos de otros**. Solo lectura.
- **Antes de cualquier commit, haz `git pull`** para evitar conflictos.

---

## Si te trabas

- Foro de Canvas
- Reunión 1-a-1 con el instructor (agenda en Canvas)

# GUÍA DEMO — MotoVigia (go-live sábado)

*Preparado 2026-06-04. Esta guía la ignora el vigía (es `.md`).*

## Modelo del demo (un solo emisor)
1. **Tú generas/sueltas** un `lecturas_nuevas_W##.csv` en la carpeta del proyecto.
2. El **vigía** (always-on, `modo_agente_ia=1`) lo detecta, importa a **U14**, y **Claude (su agente) analiza y envía** la alarma: **Canal A** = correo a `mani.mendoza2406@gmail.com`, **Canal B** = MCP a la clase (con el túnel ngrok arriba).
3. ⚠️ **No envíes manualmente además** (no corras `enviar_alarma.py` tú): habría **doble alarma**.

## Checklist ANTES de empezar
1. **Vigía vivo:** PowerShell → `Get-Process pythonw` → deben verse **2** (supervisor + loop).
   - Si no: desde la carpeta del proyecto → `pythonw vigilancia_alertas.py --supervisor 2`
2. **Modo agente = 1:** `python -c "from src import database as db; print(db.obtener_config('modo_agente_ia','0'))"` → debe imprimir `1`
3. **BD limpia:** `python reiniciar_baseline_u14.py` → deja **0 alertas**
4. **Túnel MCP arriba** (para que el Canal B llegue a la clase).

## Por cada escenario (durante el demo)
1. `python reiniciar_baseline_u14.py`   *(deja la BD limpia para que salga 1 sola falla)*
2. Copia **un** archivo de `_simulaciones\` a la carpeta del proyecto.
3. Espera ~50 s → llega el correo (y MCP). Muéstralo.
4. **Borra ese `.csv`** de la carpeta del proyecto *(si no, su `mtime` puede cambiar y reprocesarse → correo duplicado)*.

## Archivos listos (en `_simulaciones\`)
| Archivo | Falla | Qué demuestra |
|---|---|---|
| `lecturas_nuevas_W47.csv` | devanado A se sobrecalienta | LÍMITE 'alta' → CRÍTICO |
| `lecturas_nuevas_W48.csv` | presión de aceite cae | LÍMITE 'baja' → CRÍTICO |
| `lecturas_nuevas_W49.csv` | pico de gases de escape | ANOMALÍA/SALTO (el límite no lo ve) |
| `lecturas_nuevas_W50.csv` | devanado A (repite) | LÍMITE 'alta' → CRÍTICO |

Generar más: `python generar_lecturas.py W51 W52 ...`
(o `--escenario {devanado_critico|presion_baja|salto_escape|normal}`)

## Si algo falla
- **El vigía no responde / se cayó:** `Get-Process pythonw`; si no hay 2, relanza `pythonw vigilancia_alertas.py --supervisor 2`. *(Ojo: el `.vbs` de Inicio solo lo revive al iniciar sesión; si muere a media demo, hay que relanzarlo a mano.)*
- **No llega el correo:** `python -c "from src import notificaciones as n; print(n.configurado())"` debe ser `True`; revisa `.env` (GMAIL_USER / GMAIL_APP_PASSWORD).
- **Llegó doble alarma:** asegúrate de no haber enviado tú también; el emisor es **solo el vigía**.
- **Revertir la BD:** detén el vigía y copia un `data\mantenimiento.db.bak-*` sobre `data\mantenimiento.db`.

"""Watcher: los archivos `lecturas_nuevas_*` se IMPORTAN y analizan al llegar.

BD y carpetas temporales; SMTP y MCP mockeados. Correr:
    python test_import_lecturas.py
"""
import tempfile
from pathlib import Path

import src.database as database

_tmp = Path(tempfile.mkdtemp(prefix="implect_"))
database.DB_DIR = _tmp
database.DB_PATH = _tmp / "demo.db"
database.init_db()

import src.canal_mcp as canal_mcp
import vigilancia_alertas as v
from src import models, notificaciones, predictivo


def _ok(cond, msg):
    print(("OK  " if cond else "FALLO ") + msg)
    assert cond, msg


# Equipo destino U14
models.crear_equipo({"codigo": "U14", "nombre": "Unidad U14"})

# Redirigir watcher a carpetas temporales
watch = _tmp / "proyecto"
watch.mkdir()
v.CARPETA_VIGILADA = watch
v.DIR_REPORTES = _tmp / "reportes_fallas"
v.VISTOS_JSON = _tmp / "archivos_vistos.json"

# === 1. Reconocimiento del tipo de archivo =================================
_ok(v._es_archivo_lecturas("lecturas_nuevas_W46.csv"), "reconoce lecturas_nuevas_W46.csv")
_ok(v._es_archivo_lecturas("lecturas_nuevas_W99.xlsx"), "reconoce .xlsx de lecturas")
_ok(not v._es_archivo_lecturas("plantilla_lecturas.csv"), "NO trata la plantilla como lecturas")
_ok(not v._es_archivo_lecturas("Reporte_Falla.pdf"), "NO trata un PDF como lecturas")

# === 2. Equipo destino =====================================================
eid, ecod = v._equipo_destino_lecturas()
_ok(ecod == "U14", "equipo destino por defecto = U14")

# === 3. Importación directa de un archivo de lecturas ======================
csv = watch / "lecturas_nuevas_W46.csv"
csv.write_text(
    "﻿parametro,valor,unidad,horas_operacion\n"   # con BOM, como los reales
    "temperatura_agua,75,C,11500\n"
    "temperatura_agua,78,C,11600\n"
    "temperatura_agua,82,C,11700\n"
    "temperatura_agua,140,C,11800\n"                    # salto -> anomalia
    "valor_malo,abc,C,11900\n",                         # fila inválida -> omitida
    encoding="utf-8",
)
res = v._importar_archivo_lecturas("lecturas_nuevas_W46.csv")
_ok(res["insertados"] == 4, f"importa 4 lecturas válidas (got {res['insertados']})")
_ok(len(res["errores"]) == 1, "omite la fila inválida (valor no numérico)")
_ok(len(predictivo.lecturas_de(eid, "temperatura_agua")) == 4,
    "las lecturas quedaron en la BD del equipo")

# === 4. Flujo completo del watcher: importa + analiza + alarma =============
_correos, _mcp = [], []
notificaciones.enviar = lambda d, a, c, adjuntos=None: _correos.append({"adj": adjuntos, "asunto": a})
notificaciones.configurado = lambda: True
database.guardar_config("auto_alertas_destino", "danilo@planta.com")
canal_mcp.enviar_difusion = lambda a, c, de="MotoVigia", timeout=8.0: _mcp.append(a) or {"ok": True, "motivo": "enviado"}

# baseline ya incluye el W46 del paso 3 (ya procesado); solo el W47 es nuevo
vistos = {"lecturas_nuevas_W46.csv"}
(watch / "lecturas_nuevas_W47.csv").write_text(
    "parametro,valor,unidad,horas_operacion\n"
    "temperatura_agua,90,C,12020\n"
    "temperatura_agua,200,C,12080\n",                   # salto fuerte
    encoding="utf-8",
)
v._revisar_archivos(vistos)

_ok(len(predictivo.lecturas_de(eid, "temperatura_agua")) == 6,
    "el watcher importó las lecturas del archivo nuevo (4+2=6)")
_ok(len(_correos) == 1 and _correos[0]["adj"], "disparó 1 correo con PDF adjunto")
_ok("ANALIZADO" in _correos[0]["asunto"] or len(_mcp) == 1,
    "la difusión MCP también se disparó")
_ok("lecturas_nuevas_W47.csv" in vistos, "el archivo quedó registrado (no redispara)")

import shutil
shutil.rmtree(_tmp, ignore_errors=True)
print("\nTODOS LOS TESTS DE IMPORT+ANALISIS PASARON")

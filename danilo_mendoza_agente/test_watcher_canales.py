"""Integración: watcher de archivos nuevos + canal A (correo) + canal B (MCP).

Usa BD y carpetas TEMPORALES; mockea el envío SMTP y la difusión MCP (no manda
correos ni toca la red salvo el chequeo de degradación del túnel). Correr:
    python test_watcher_canales.py
"""
import os
import tempfile
from pathlib import Path

import src.database as database

_tmp = Path(tempfile.mkdtemp(prefix="watcher_"))
database.DB_DIR = _tmp
database.DB_PATH = _tmp / "demo.db"
database.init_db()

import src.canal_mcp as canal_mcp
import vigilancia_alertas as v
from src import notificaciones


def _ok(cond, msg):
    print(("OK  " if cond else "FALLO ") + msg)
    assert cond, msg


# === 1. Canal B (MCP) degrada con gracia ===================================
_tok_guardado = os.environ.pop("UTHAGENTES_TOKEN", None)
_ok(canal_mcp.enviar_difusion("a", "b")["motivo"] == "sin_token",
    "canal B: sin token -> motivo sin_token (no lanza)")
_ok(canal_mcp.mcp_activo() is False, "canal B: mcp_activo() False sin token")
if _tok_guardado:
    os.environ["UTHAGENTES_TOKEN"] = _tok_guardado
    # Túnel real está caído (ERR_NGROK_3200): debe degradar, no lanzar.
    r = canal_mcp.enviar_difusion("ping", "test", timeout=8.0)
    _ok(r["ok"] is False and r["motivo"] in ("mcp_inactivo", "http_404", "sin_respuesta", "error"),
        f"canal B: tunel caido -> degrada (motivo={r['motivo']})")

# === 2. Watcher: redirigir carpetas a temporales ===========================
watch = _tmp / "proyecto"
watch.mkdir()
v.CARPETA_VIGILADA = watch
v.DIR_REPORTES = _tmp / "reportes_fallas"
v.VISTOS_JSON = _tmp / "archivos_vistos.json"

# Archivo preexistente (baseline -> NO debe disparar)
(watch / "viejo.csv").write_text("a,b\n1,2\n", encoding="utf-8")
_ok(v._archivos_actuales() == {"viejo.csv"}, "watcher: detecta archivos por extension")
(watch / "notas.py").write_text("# codigo, no debe contar\n", encoding="utf-8")
_ok(v._archivos_actuales() == {"viejo.csv"}, "watcher: ignora .py y otros no-datos")

# === 3. Mockear envíos y simular un archivo NUEVO ==========================
_correos = []
def _enviar_stub(dest, asunto, cuerpo, adjuntos=None):
    _correos.append({"dest": dest, "asunto": asunto, "adjuntos": adjuntos})
notificaciones.enviar = _enviar_stub
notificaciones.configurado = lambda: True
database.guardar_config("auto_alertas_destino", "jefe@planta.com")

_mcp_calls = []
def _difusion_stub(asunto, cuerpo, de="MotoVigia", timeout=8.0):
    _mcp_calls.append({"asunto": asunto, "de": de})
    return {"ok": True, "motivo": "enviado"}
canal_mcp.enviar_difusion = _difusion_stub

# baseline = {viejo.csv}; luego llega uno nuevo
vistos = v._archivos_actuales()
v._guardar_vistos(vistos)
(watch / "lecturas_scada.xlsx").write_bytes(b"PK\x03\x04 fake xlsx")

v._revisar_archivos(vistos)

_ok(len(_correos) == 1, "watcher: dispara 1 correo (canal A) al llegar archivo nuevo")
_ok(_correos[0]["dest"] == "jefe@planta.com", "canal A: usa el destino configurado")
_ok(_correos[0]["adjuntos"] and Path(_correos[0]["adjuntos"][0]).suffix == ".pdf",
    "canal A: adjunta el PDF de falla")
_ok(Path(_correos[0]["adjuntos"][0]).exists(), "watcher: el PDF de falla se guardó en disco")
_ok(len(_mcp_calls) == 1 and "archivo nuevo" in _mcp_calls[0]["asunto"],
    "watcher: dispara la difusión MCP (canal B)")
_ok("lecturas_scada.xlsx" in vistos, "watcher: el archivo nuevo queda registrado")

# Segundo barrido sin cambios: NO redispara
v._revisar_archivos(vistos)
_ok(len(_correos) == 1 and len(_mcp_calls) == 1,
    "watcher: no redispara si no hay archivos nuevos (sin duplicados)")

import shutil
shutil.rmtree(_tmp, ignore_errors=True)
print("\nTODOS LOS TESTS DE WATCHER+CANALES PASARON")

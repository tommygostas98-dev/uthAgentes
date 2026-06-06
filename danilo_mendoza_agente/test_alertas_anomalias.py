"""Integración: las anomalías de severidad ALTA disparan la alerta por correo.

Usa una BD temporal aislada y reemplaza el envío SMTP por un stub (no manda
correos de verdad). Correr:  python test_alertas_anomalias.py
"""
import os
import tempfile
from pathlib import Path

import src.database as database

# --- BD temporal aislada (no toca la base real) ----------------------------
_tmp = Path(tempfile.mkdtemp(prefix="alertas_anom_"))
database.DB_DIR = _tmp
database.DB_PATH = _tmp / "demo.db"
database.init_db()

from src import models, notificaciones, predictivo


def _ok(cond, msg):
    print(("OK  " if cond else "FALLO ") + msg)
    assert cond, msg


# --- Stub de envío: captura en vez de mandar -------------------------------
_enviados = []
def _enviar_stub(destinatario, asunto, cuerpo, adjuntos=None):
    _enviados.append({"destino": destinatario, "asunto": asunto, "cuerpo": cuerpo})
notificaciones.enviar = _enviar_stub
# Simula credenciales para que `configurado()` devuelva True.
os.environ["GMAIL_USER"] = "test@gmail.com"
os.environ["GMAIL_APP_PASSWORD"] = "xxxxxxxxxxxxxxxx"


def sembrar(con_anomalia: bool):
    eid = models.crear_equipo({"codigo": "U14", "nombre": "Motor 18V46"})
    base = [(11000 + i * 20, 88 + (0.1 if i % 2 else -0.1)) for i in range(10)]
    for h, v in base:
        predictivo.registrar_lectura(eid, "temp_aceite", v, "C", h)
    if con_anomalia:
        # Pico extremo -> outlier de severidad ALTA (score >> umbral).
        predictivo.registrar_lectura(eid, "temp_aceite", 145.0, "C", 11220)
    return eid


# === 1. Sin anomalía alta: no hay alerta crítica por anomalías =============
sembrar(con_anomalia=False)
criticas_base = notificaciones.alertas_criticas()
_ok(not any("ANOMALIA ALTA" in c for c in criticas_base),
    "sin pico: no hay líneas de ANOMALIA ALTA")
_ok("(sin anomalías de severidad alta)" in notificaciones.texto_alertas(),
    "sin pico: el cuerpo dice que no hay anomalías altas")

# === 2. Agregar la anomalía extrema ========================================
predictivo.registrar_lectura(
    [e["id"] for e in models.listar_equipos()][0], "temp_aceite", 145.0, "C", 11220)

altas = notificaciones.anomalias_altas()
_ok(len(altas) >= 1, "con pico: anomalias_altas() encuentra la anomalía")
_ok(altas[0]["severidad"] == "alta", "con pico: severidad alta")

criticas = notificaciones.alertas_criticas()
_ok(any("ANOMALIA ALTA" in c and "temp_aceite" in c for c in criticas),
    "con pico: alertas_criticas() incluye la anomalía alta")

cuerpo = notificaciones.texto_alertas()
_ok("ANOMALÍAS DETECTADAS" in cuerpo and "145" in cuerpo,
    "con pico: el cuerpo del correo lista la anomalía (145)")

# La firma de deduplicación cambia al aparecer la anomalía.
_ok(notificaciones._firma(criticas_base) != notificaciones._firma(criticas),
    "la firma cambia cuando aparece una anomalía -> dispararía reenvío")

# === 3. Envío automático real (con stub) ===================================
database.guardar_config("auto_alertas_activo", "1")
database.guardar_config("auto_alertas_destino", "jefe@planta.com")
database.guardar_config("auto_alertas_cooldown_horas", "9999")  # casi nunca reenvía por reloj

r1 = notificaciones.revisar_y_enviar_auto()
_ok(r1["enviado"] and r1["motivo"] == "enviado", "auto: envía cuando hay anomalía alta")
_ok(len(_enviados) == 1 and "ANOMALÍAS DETECTADAS" in _enviados[0]["cuerpo"],
    "auto: el correo enviado incluye la sección de anomalías")
_ok(_enviados[0]["destino"] == "jefe@planta.com", "auto: respeta el destino configurado")

# Segunda corrida sin cambios: deduplicado (no reenvía).
r2 = notificaciones.revisar_y_enviar_auto()
_ok(not r2["enviado"] and r2["motivo"] == "en_cooldown",
    "auto: no reenvía si el conjunto no cambió (dedup + cooldown)")
_ok(len(_enviados) == 1, "auto: sigue habiendo un solo envío")

import shutil
shutil.rmtree(_tmp, ignore_errors=True)
print("\nTODOS LOS TESTS DE ALERTAS+ANOMALIAS PASARON")

"""Envío de correos (reportes y alertas) vía Gmail SMTP.

Configuración por variables de entorno (.env):
    GMAIL_USER          = tu_cuenta@gmail.com   (cuenta que ENVÍA)
    GMAIL_APP_PASSWORD  = contraseña de aplicación de 16 caracteres
    EMAIL_DESTINO       = correo de destino por defecto (opcional)

Gmail ya no permite usar la contraseña normal por SMTP: hay que activar la
verificación en 2 pasos y generar una "Contraseña de aplicación".
"""

import hashlib
import os
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote

from . import anomalias, database, models, predictivo

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL


def _subtipo_mime(ruta: Path) -> tuple[str, str]:
    """(maintype, subtype) MIME a partir de la extensión del archivo."""
    return {
        ".pdf": ("application", "pdf"),
        ".docx": ("application",
                  "vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ".xlsx": ("application",
                  "vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ".csv": ("text", "csv"),
        ".png": ("image", "png"),
    }.get(ruta.suffix.lower(), ("application", "octet-stream"))


def configurado() -> bool:
    """Indica si hay credenciales de envío configuradas."""
    return bool(os.getenv("GMAIL_USER") and os.getenv("GMAIL_APP_PASSWORD"))


def destino_por_defecto() -> str:
    return os.getenv("EMAIL_DESTINO", "")


def enviar(destinatario: str, asunto: str, cuerpo: str,
           adjuntos: list[Path] | None = None) -> None:
    """Envía un correo. Lanza excepción si falla (credenciales, red, etc.)."""
    if not configurado():
        raise RuntimeError(
            "Faltan credenciales. Configura GMAIL_USER y GMAIL_APP_PASSWORD en .env."
        )
    remitente = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD")

    msg = EmailMessage()
    msg["From"] = remitente
    msg["To"] = destinatario
    msg["Subject"] = asunto
    msg.set_content(cuerpo)

    for ruta in (adjuntos or []):
        ruta = Path(ruta)
        if not ruta.exists():
            continue
        datos = ruta.read_bytes()
        subtype = _subtipo_mime(ruta)
        msg.add_attachment(datos, maintype=subtype[0], subtype=subtype[1],
                           filename=ruta.name)

    contexto = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=contexto) as servidor:
        servidor.login(remitente, password)
        servidor.send_message(msg)


# ---------------------------------------------------------------------------
# ENVÍO SIN CREDENCIALES (abre el correo del propio usuario)
# ---------------------------------------------------------------------------
# No requieren GMAIL_USER ni contraseña: en vez de enviar desde el servidor,
# preparan el mensaje y lo abren en el cliente de correo del usuario (Gmail,
# Outlook, etc.), donde ya está su sesión iniciada. El usuario solo da "Enviar".

def mailto_url(destinatario: str, asunto: str, cuerpo: str) -> str:
    """Enlace ``mailto:`` para abrir el correo del usuario con el mensaje listo.

    No admite adjuntos (el estándar mailto no los soporta). Ideal para alertas
    de solo texto. No usa credenciales.
    """
    params = []
    if asunto:
        params.append("subject=" + quote(asunto))
    if cuerpo:
        params.append("body=" + quote(cuerpo))
    destino = quote(destinatario or "")
    cola = ("?" + "&".join(params)) if params else ""
    return f"mailto:{destino}{cola}"


def cuenta_gmail() -> str:
    """Cuenta de Gmail con la que se abre la redacción (de .env)."""
    return os.getenv("GMAIL_CUENTA") or os.getenv("GMAIL_USER") or ""


def gmail_url(destinatario: str, asunto: str, cuerpo: str,
              cuenta: str | None = None) -> str:
    """Enlace que abre la **ventana de redacción de Gmail web** con el mensaje
    listo, en el navegador (usa la sesión ya iniciada del usuario).

    Si se indica ``cuenta`` (o está GMAIL_CUENTA en .env), fija esa cuenta con
    ``authuser`` para abrir Gmail con la sesión correcta aunque haya varias
    abiertas. No depende del cliente de correo del sistema ni usa credenciales.
    No admite adjuntos.
    """
    cuenta = cuenta if cuenta is not None else cuenta_gmail()
    params = [
        "view=cm",   # compose
        "fs=1",      # pantalla completa
        "to=" + quote(destinatario or ""),
        "su=" + quote(asunto or ""),
        "body=" + quote(cuerpo or ""),
    ]
    if cuenta:
        params.insert(0, "authuser=" + quote(cuenta))
    return "https://mail.google.com/mail/?" + "&".join(params)


def construir_eml(destinatario: str, asunto: str, cuerpo: str,
                  adjuntos: list[Path] | None = None,
                  remitente: str = "") -> bytes:
    """Genera un correo en formato ``.eml`` (RFC 822) descargable, con adjuntos.

    Al abrir el archivo, el cliente de correo del usuario muestra el mensaje con
    todo incluido (asunto, cuerpo y adjuntos), listo para enviar. No usa
    credenciales. ``remitente`` es opcional: si se omite, el cliente pone la
    cuenta del usuario automáticamente.
    """
    msg = EmailMessage()
    if remitente:
        msg["From"] = remitente
    if destinatario:
        msg["To"] = destinatario
    msg["Subject"] = asunto
    msg.set_content(cuerpo)

    for ruta in (adjuntos or []):
        ruta = Path(ruta)
        if not ruta.exists():
            continue
        datos = ruta.read_bytes()
        subtype = _subtipo_mime(ruta)
        msg.add_attachment(datos, maintype=subtype[0], subtype=subtype[1],
                           filename=ruta.name)
    return bytes(msg)


def _cuando_anomalia(a: dict) -> str:
    """Ubica una anomalía en el tiempo: fecha, horas de operación o nº de lectura."""
    if a.get("fecha"):
        return str(a["fecha"])[:16]
    if a.get("horas_operacion") is not None:
        return f"{a['horas_operacion']:.0f} h"
    return f"lectura #{a['indice'] + 1}"


def anomalias_altas() -> list[dict]:
    """Anomalías de severidad ALTA en todos los equipos, con su contexto
    (detección avanzada estadística, sin depender de límites definidos)."""
    altas = []
    for r in anomalias.resumen_global():
        for a in r["anomalias"]:
            if a["severidad"] == "alta":
                altas.append({
                    "equipo_codigo": r["equipo_codigo"],
                    "parametro": r["parametro"],
                    **a,
                })
    return altas


def texto_alertas() -> str:
    """Construye el cuerpo de texto con las alertas vigentes (preventivo + predictivo)."""
    lineas = ["RESUMEN DE ALERTAS DE MANTENIMIENTO", "=" * 40, ""]

    prev = models.equipos_con_preventivo_vencido()
    lineas.append(f"PREVENTIVO ({len(prev)} alerta(s)):")
    if prev:
        for a in prev:
            estado = "VENCIDO" if a["urgencia"] == "vencido" else "Por vencer"
            valor = f"{abs(a['restante']):.0f}"
            lineas.append(
                f"  - [{a['codigo']}] {a['nombre']}: {estado} "
                f"({valor} {a['unidad']}) · {a['detalle']}"
            )
    else:
        lineas.append("  (sin alertas)")
    lineas.append("")

    pred = predictivo.alertas_predictivas()
    lineas.append(f"PREDICTIVO ({len(pred)} alerta(s)):")
    if pred:
        for a in pred:
            lineas.append(f"  - [{a['equipo_codigo']}] {a['parametro']}: {a['mensaje']}")
    else:
        lineas.append("  (sin alertas)")
    lineas.append("")

    anom = anomalias_altas()
    lineas.append(f"ANOMALÍAS DETECTADAS · severidad alta ({len(anom)}):")
    if anom:
        for a in anom:
            lineas.append(
                f"  - [{a['equipo_codigo']}] {a['parametro']} @ {_cuando_anomalia(a)}: "
                f"{a['detalle']}"
            )
    else:
        lineas.append("  (sin anomalías de severidad alta)")
    lineas.append("")
    lineas.append("-- Reporte y Análisis de falla en motor de combustión Wärtsilä W46 --")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# ALERTAS AUTOMÁTICAS (envío desatendido con deduplicación + cooldown)
# ---------------------------------------------------------------------------
def alertas_criticas() -> list[str]:
    """Alertas que justifican un aviso inmediato: preventivo VENCIDO,
    predictivo en estado CRÍTICO y anomalías de severidad ALTA (detección
    avanzada). Cada elemento es una línea de texto; el conjunto alimenta la
    firma de deduplicación, así que un cambio en las anomalías reenvía solo."""
    items: list[str] = []
    for a in models.equipos_con_preventivo_vencido():
        if a["urgencia"] == "vencido":
            items.append(f"PREVENTIVO VENCIDO [{a['codigo']}] {a['nombre']}: {a['detalle']}")
    for a in predictivo.alertas_predictivas():
        if a["estado"] == "critico":
            items.append(
                f"PREDICTIVO CRITICO [{a['equipo_codigo']}] {a['parametro']}: {a['mensaje']}"
            )
    for a in anomalias_altas():
        items.append(
            f"ANOMALIA ALTA [{a['equipo_codigo']}] {a['parametro']} @ "
            f"{_cuando_anomalia(a)}: {a['detalle']}"
        )
    return items


def _firma(items: list[str]) -> str:
    """Huella estable del conjunto de alertas, para detectar cambios."""
    base = "\n".join(sorted(items))
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def revisar_y_enviar_auto() -> dict:
    """Envía las alertas críticas por correo SI procede, sin intervención.

    Para no spamear, solo envía cuando: el modo automático está activo, hay
    credenciales y destino, y existen alertas críticas. Reenvía cuando el
    conjunto de alertas CAMBIA o cuando pasó el cooldown desde el último envío.
    Si no hay alertas críticas, limpia la firma para que una reaparición vuelva
    a avisar. Devuelve {'enviado': bool, 'motivo': str, ...}.
    """
    if database.obtener_config("auto_alertas_activo", "0") != "1":
        return {"enviado": False, "motivo": "desactivado"}
    if not configurado():
        return {"enviado": False, "motivo": "sin_credenciales"}
    destino = database.obtener_config("auto_alertas_destino", "") or destino_por_defecto()
    if not destino:
        return {"enviado": False, "motivo": "sin_destino"}

    criticas = alertas_criticas()
    if not criticas:
        database.guardar_config("auto_alertas_firma", "")
        return {"enviado": False, "motivo": "sin_alertas_criticas"}

    firma = _firma(criticas)
    ultima_firma = database.obtener_config("auto_alertas_firma", "")
    ultimo_envio = database.obtener_config("auto_alertas_ultimo_envio", "")
    try:
        cooldown_h = float(database.obtener_config("auto_alertas_cooldown_horas", "6"))
    except (TypeError, ValueError):
        cooldown_h = 6.0

    cooldown_cumplido = True
    if ultimo_envio:
        try:
            transcurrido = datetime.now() - datetime.fromisoformat(ultimo_envio)
            cooldown_cumplido = transcurrido >= timedelta(hours=cooldown_h)
        except ValueError:
            cooldown_cumplido = True

    if firma == ultima_firma and not cooldown_cumplido:
        return {"enviado": False, "motivo": "en_cooldown", "n": len(criticas)}

    asunto = f"⚠️ {len(criticas)} alerta(s) CRÍTICA(S) de mantenimiento"
    enviar(destino, asunto, texto_alertas())
    database.guardar_config("auto_alertas_firma", firma)
    database.guardar_config(
        "auto_alertas_ultimo_envio", datetime.now().isoformat(timespec="seconds")
    )
    return {"enviado": True, "motivo": "enviado", "n": len(criticas), "destino": destino}

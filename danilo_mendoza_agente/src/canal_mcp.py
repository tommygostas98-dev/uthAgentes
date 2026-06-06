"""Canal B de alertas: difusión por el túnel MCP de la clase.

El servidor MCP de la clase (FastMCP, transporte streamable-http) corre tras un
túnel ngrok en la PC de Luis. Este módulo habla el protocolo MCP con un cliente
HTTP MÍNIMO (httpx), sin depender de la librería `mcp` (que no está instalada en
el Python del proyecto). Hace el handshake estándar:

    initialize  ->  notifications/initialized  ->  tools/call(enviar_mensaje)

Está pensado para degradar con gracia: si el túnel está caído (ERR_NGROK_3200),
sin token, o hay cualquier error de red, `enviar_difusion` devuelve
``{"ok": False, "motivo": ...}`` sin lanzar excepción. Así el vigía manda por
correo (canal A) aunque el MCP (canal B) no esté disponible — «cuando el MCP
esté activo».
"""

from __future__ import annotations

import json
import os

import httpx

URL = "https://breeches-wing-ensnare.ngrok-free.dev/mcp"
PROTOCOL = "2024-11-05"
_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "ngrok-skip-browser-warning": "true",
}


def token() -> str:
    """Token de la clase (variable de entorno de Usuario `UTHAGENTES_TOKEN`)."""
    return os.environ.get("UTHAGENTES_TOKEN", "")


def _extraer_json(resp: httpx.Response):
    """Devuelve el JSON-RPC de una respuesta, sea JSON directo o SSE."""
    ct = resp.headers.get("content-type", "")
    texto = resp.text or ""
    if "text/event-stream" in ct:
        partes = [ln[5:].strip() for ln in texto.splitlines() if ln.startswith("data:")]
        payload = "".join(partes)
        return json.loads(payload) if payload else None
    return resp.json() if texto.strip() else None


def _tunel_caido(resp: httpx.Response) -> bool:
    """True si la respuesta es una página de error de ngrok (túnel apagado)."""
    return bool(resp.headers.get("Ngrok-Error-Code"))


def enviar_difusion(asunto: str, cuerpo: str, de: str = "El Agente te informa de una alarma generada en la U14",
                    timeout: float = 8.0) -> dict:
    """Envía un mensaje de difusión ('todos') por el MCP de la clase.

    Devuelve {'ok': bool, 'motivo': str, ...}. Nunca lanza: ante túnel caído,
    falta de token o error de red, reporta el motivo y sigue.
    """
    tok = token()
    if not tok:
        return {"ok": False, "motivo": "sin_token"}

    headers = {**_HEADERS, "Authorization": f"Bearer {tok}"}
    try:
        with httpx.Client(timeout=timeout) as client:
            # 1) initialize
            init = {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL,
                    "capabilities": {},
                    "clientInfo": {"name": "motovigia-vigia", "version": "1.0"},
                },
            }
            r = client.post(URL, headers=headers, content=json.dumps(init))
            if _tunel_caido(r):
                return {"ok": False, "motivo": "mcp_inactivo", "detalle": r.headers.get("Ngrok-Error-Code")}
            if r.status_code != 200:
                return {"ok": False, "motivo": f"http_{r.status_code}"}
            sesion = r.headers.get("mcp-session-id")
            h2 = {**headers, "mcp-session-id": sesion} if sesion else headers

            # 2) notifications/initialized (handshake)
            client.post(URL, headers=h2,
                        content=json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))

            # 3) tools/call -> enviar_mensaje a 'todos'
            call = {
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {
                    "name": "enviar_mensaje",
                    "arguments": {"destino": "todos", "asunto": asunto, "cuerpo": cuerpo, "de": de},
                },
            }
            r = client.post(URL, headers=h2, content=json.dumps(call))
            data = _extraer_json(r)
            if not data:
                return {"ok": False, "motivo": "sin_respuesta"}
            if data.get("error"):
                return {"ok": False, "motivo": "error_tool", "detalle": data["error"]}
            resultado = data.get("result", {})
            if resultado.get("isError"):
                return {"ok": False, "motivo": "tool_isError", "detalle": resultado}
            return {"ok": True, "motivo": "enviado", "detalle": resultado}
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError):
        return {"ok": False, "motivo": "mcp_inactivo"}
    except Exception as e:  # nunca tumbar al vigía por el canal B
        return {"ok": False, "motivo": "error", "detalle": f"{type(e).__name__}: {e}"}


def mcp_activo(timeout: float = 5.0) -> bool:
    """Chequeo rápido: ¿responde el MCP (túnel arriba y token válido)?"""
    tok = token()
    if not tok:
        return False
    headers = {**_HEADERS, "Authorization": f"Bearer {tok}"}
    init = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                   "clientInfo": {"name": "motovigia-check", "version": "1.0"}},
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(URL, headers=headers, content=json.dumps(init))
            return r.status_code == 200 and not _tunel_caido(r)
    except Exception:
        return False

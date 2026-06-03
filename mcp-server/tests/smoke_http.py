"""Smoke test HTTP end-to-end: arranca el servidor en modo streamable-http con
token y verifica el camino de despliegue:
  1. sin token            -> 401 (el gate rechaza)
  2. con token equivocado -> 401
  3. con el token correcto -> habla MCP y sus 5 tools funcionan

Mirror de smoke_stdio.py para el transporte que realmente se hospeda.

    python tests/smoke_http.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import socket
import subprocess
import sys
import tempfile

import httpx

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ESPERADAS = {
    "registrar_estudiante",
    "listar_estudiantes",
    "consultar_estado",
    "enviar_mensaje",
    "historial_mensajes",
}
# Cuerpo MCP minimo; da igual su validez, el token se revisa ANTES de procesarlo.
_PING = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
_ACCEPT = {"Accept": "application/json, text/event-stream"}


def _puerto_libre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    try:
        return s.getsockname()[1]
    finally:
        s.close()


async def _esperar_puerto(port: int, intentos: int = 100) -> None:
    for _ in range(intentos):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return
        except OSError:
            await asyncio.sleep(0.2)
    raise RuntimeError(f"el servidor no abrio el puerto {port}")


async def _sesion_ok(url: str, token: str):
    """Abre una sesion MCP por HTTP con el token y ejercita las tools."""
    headers = {"Authorization": f"Bearer {token}"}
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            assert ESPERADAS <= tools, f"faltan herramientas: {ESPERADAS - tools}"
            await session.call_tool("registrar_estudiante", {"nombre": "Ana Perez", "variante": "2"})
            await session.call_tool("registrar_estudiante", {"nombre": "Beto Ruiz", "variante": "1"})
            await session.call_tool(
                "enviar_mensaje",
                {"destino": "Ana Perez", "asunto": "hola", "cuerpo": "prueba", "de": "Beto Ruiz"},
            )
            lst = await session.call_tool("listar_estudiantes", {})
            inbox = await session.call_tool("historial_mensajes", {"estudiante": "Ana Perez"})
            assert not lst.isError and not inbox.isError
            print("tools:", sorted(tools))
            print("listar_estudiantes ->", lst.structuredContent)
            print("historial Ana    ->", inbox.structuredContent)


async def main() -> int:
    port = _puerto_libre()
    token = "tok-smoke-http"
    url = f"http://127.0.0.1:{port}/mcp"
    fd, db_tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    env = {
        **os.environ,
        "MCP_TRANSPORT": "streamable-http",
        "HOST": "127.0.0.1",
        "PORT": str(port),
        "UTHAGENTES_TOKEN": token,
        "UTHAGENTES_DB": db_tmp,
    }
    proc = subprocess.Popen([sys.executable, str(RAIZ / "server.py")], env=env)
    try:
        await _esperar_puerto(port)

        # 1 y 2) El gate del token rechaza antes de tocar MCP.
        r = httpx.post(url, json=_PING, headers=_ACCEPT, timeout=10)
        assert r.status_code == 401, f"sin token esperaba 401, dio {r.status_code}"
        print("sin token -> 401 (OK)")
        r = httpx.post(url, json=_PING, headers={**_ACCEPT, "Authorization": "Bearer mal"}, timeout=10)
        assert r.status_code == 401, f"token malo esperaba 401, dio {r.status_code}"
        print("token equivocado -> 401 (OK)")

        # 3) Con el token correcto, MCP funciona end-to-end.
        await asyncio.wait_for(_sesion_ok(url, token), timeout=20)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    print("\nSMOKE HTTP OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

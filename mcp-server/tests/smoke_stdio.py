"""Smoke test end-to-end: arranca el servidor por stdio y llama sus herramientas
como lo haria Claude Code. Verifica que el servidor habla MCP de verdad.

    python tests/smoke_stdio.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ESPERADAS = {
    "registrar_estudiante",
    "listar_estudiantes",
    "consultar_estado",
    "enviar_mensaje",
    "historial_mensajes",
}


async def main() -> int:
    fd, db_tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(RAIZ / "server.py")],
        env={**os.environ, "UTHAGENTES_DB": db_tmp, "MCP_TRANSPORT": "stdio"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            print("tools:", sorted(tools))
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
            print("listar_estudiantes ->", lst.structuredContent)
            print("historial Ana    ->", inbox.structuredContent)
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

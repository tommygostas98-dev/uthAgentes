#!/usr/bin/env python
"""Servidor MCP de la clase uthAgentes.

Expone, via Model Context Protocol, las herramientas de coordinacion entre los
agentes (las sesiones de Claude Code) de los estudiantes. Cada estudiante agrega
este servidor a su Claude Code y puede registrarse, ver a los demas y mandarse
mensajes en casi tiempo real, sin pelear con git.

Ejecucion:
  python server.py                       # transporte stdio (local, para probar)
  MCP_TRANSPORT=streamable-http python server.py   # HTTP (para hospedar)

Variables de entorno:
  MCP_TRANSPORT  stdio (default) | streamable-http | sse
  HOST           interfaz para HTTP (default 127.0.0.1; en deploy usa 0.0.0.0)
  PORT           puerto para HTTP (default 8000)
  UTHAGENTES_DB  ruta del archivo SQLite (default data/uthagentes.db)
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

import db


def _cargar_env(ruta: str | None = None) -> None:
    """Carga el .env junto a este archivo (sin dependencias). No sobreescribe el
    entorno ya definido."""
    ruta = ruta or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(ruta, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                clave, _, valor = linea.partition("=")
                os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


_cargar_env()

INSTRUCCIONES = (
    "Red de coordinacion de la clase Programacion UTH 2026.4. Usa "
    "registrar_estudiante al unirte, listar_estudiantes para ver quien hay, "
    "enviar_mensaje para escribirle a alguien (o a 'todos'), e "
    "historial_mensajes para leer tu bandeja. Los nombres se identifican por su "
    "slug (ej. 'Maria Lopez' -> 'maria_lopez')."
)

mcp = FastMCP(
    "uthAgentes",
    instructions=INSTRUCCIONES,
    host=os.environ.get("HOST", "127.0.0.1"),
    port=int(os.environ.get("PORT", "8000")),
)

# Asegura el esquema al arrancar.
db.init_db()


@mcp.tool()
def registrar_estudiante(
    nombre: str,
    github: str = "",
    variante: str = "",
    agente: str = "",
    canal: str = "",
    repo: str = "",
    estado: str = "",
) -> dict:
    """Registra o actualiza a un estudiante en la red de la clase.

    nombre es obligatorio (no puede ser vacio ni una palabra reservada como
    'todos'); lo demas es opcional y solo se sobrescribe si se envia.
    variante: el numero de variante del proyecto como texto, "1" a "4".
    canal: correo/whatsapp/telegram/dashboard. Devuelve el registro guardado.
    """
    con = db.conectar()
    try:
        return db.registrar_estudiante(con, nombre, github, variante, agente, canal, repo, estado)
    finally:
        con.close()


@mcp.tool()
def listar_estudiantes() -> list[dict]:
    """Lista todos los estudiantes registrados, ordenados por nombre."""
    con = db.conectar()
    try:
        return db.listar_estudiantes(con)
    finally:
        con.close()


@mcp.tool()
def consultar_estado(estudiante: str) -> dict:
    """Devuelve el registro de un estudiante (por nombre o slug) y su numero de
    mensajes no leidos. Si no existe, devuelve un error."""
    con = db.conectar()
    try:
        est = db.consultar_estado(con, estudiante)
        return est if est is not None else {"error": f"no existe el estudiante {estudiante!r}"}
    finally:
        con.close()


@mcp.tool()
def enviar_mensaje(destino: str, asunto: str, cuerpo: str, de: str = "") -> dict:
    """Envia un mensaje a un estudiante (por nombre/slug) o a 'todos' (difusion).

    'de' es opcional (tu nombre/slug). El campo 'destino_existe' avisa si el
    destinatario no esta registrado (util para detectar typos); el mensaje se
    encola igual.
    """
    con = db.conectar()
    try:
        return db.enviar_mensaje(con, destino, asunto, cuerpo, de)
    finally:
        con.close()


@mcp.tool()
def historial_mensajes(
    estudiante: str, solo_no_leidos: bool = False, marcar_leidos: bool = True
) -> list[dict]:
    """Bandeja de un estudiante: sus mensajes directos mas las difusiones.

    Por defecto marca como leidos los directos devueltos. Usa solo_no_leidos=True
    para revisar novedades, o marcar_leidos=False para solo mirar sin marcar.
    """
    con = db.conectar()
    try:
        return db.historial_mensajes(con, estudiante, solo_no_leidos, marcar_leidos)
    finally:
        con.close()


def _app_http_con_token():
    """App HTTP (streamable-http) con verificacion opcional de token compartido.

    Si UTHAGENTES_TOKEN esta definido, exige en cada peticion el header
    'Authorization: Bearer <token>' (o 'X-Class-Token: <token>'). Si no esta
    definido, el endpoint queda ABIERTO (solo para pruebas locales).
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    token = os.environ.get("UTHAGENTES_TOKEN", "").strip()
    app = mcp.streamable_http_app()

    if not token:
        print("ADVERTENCIA: UTHAGENTES_TOKEN no definido; el endpoint HTTP queda ABIERTO.")
        return app

    class TokenMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            enviado = request.headers.get("authorization", "")
            if enviado.lower().startswith("bearer "):
                enviado = enviado[7:]
            enviado = enviado.strip() or request.headers.get("x-class-token", "").strip()
            if enviado != token:
                return JSONResponse({"error": "no autorizado"}, status_code=401)
            return await call_next(request)

    app.add_middleware(TokenMiddleware)
    print("Token compartido ACTIVO (Authorization: Bearer <token> o X-Class-Token).")
    return app


if __name__ == "__main__":
    transporte = os.environ.get("MCP_TRANSPORT", "stdio")
    if transporte == "stdio":
        mcp.run()
    elif transporte == "streamable-http":
        import uvicorn

        uvicorn.run(
            _app_http_con_token(),
            host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", "8000")),
        )
    else:
        mcp.run(transport=transporte)  # sse u otro

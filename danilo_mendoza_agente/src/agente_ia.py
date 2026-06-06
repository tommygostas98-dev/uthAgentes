"""Agente conversacional de mantenimiento basado en la API de Claude.

El agente recibe como contexto el inventario de equipos y las órdenes
abiertas, de modo que sus respuestas estén ancladas a la planta real.
"""

import os

from anthropic import Anthropic

from . import models, rag_manual

MODELO_POR_DEFECTO = "claude-sonnet-4-6"

INSTRUCCIONES_SISTEMA = """\
Eres un asistente experto en mantenimiento industrial que apoya a un equipo \
de planta. Tu trabajo es:
- Diagnosticar posibles causas de fallas en equipos (motores, bombas, \
compresores, reductores, sistemas eléctricos, hidráulicos y neumáticos).
- Sugerir procedimientos de mantenimiento preventivo y correctivo paso a paso.
- Recomendar repuestos, herramientas y precauciones de seguridad.
- Priorizar acciones según criticidad y riesgo.

Reglas:
- Responde en español, de forma clara y práctica, orientada a un técnico.
- SIEMPRE incluye precauciones de seguridad (LOTO/bloqueo y etiquetado, EPP) \
cuando propongas intervenciones físicas.
- Si el contexto incluye datos de los equipos de la planta, úsalos y \
refiérete a ellos por su código.
- Si no tienes suficiente información, indica qué datos faltan en lugar de \
inventar. No des un diagnóstico definitivo sin evidencia.
- Si se incluye contexto del MANUAL Wärtsilä 46, basa tu respuesta en esos \
fragmentos y CITA la página entre paréntesis, p. ej. «(manual pág. 52)». Si el \
manual no cubre la consulta, dilo en vez de inventar.
- Sé conciso: ve al grano con listas y pasos numerados.
"""


def _construir_contexto_planta() -> str:
    """Resume el estado de la planta para inyectarlo en la conversación."""
    equipos = models.listar_equipos()
    ordenes = models.listar_ordenes()
    abiertas = [o for o in ordenes if o["estado"] in ("abierta", "en_proceso")]

    if not equipos:
        return "No hay equipos registrados todavía en el sistema."

    lineas = ["=== INVENTARIO DE EQUIPOS ==="]
    for e in equipos:
        horas = e.get("horas_operacion") or 0
        lineas.append(
            f"- [{e['codigo']}] {e['nombre']} | tipo: {e['tipo'] or 'n/d'} | "
            f"ubicación: {e['ubicacion'] or 'n/d'} | estado: {e['estado']} | "
            f"fabricante/modelo: {e['fabricante'] or 'n/d'} {e['modelo'] or ''} | "
            f"horas operación: {horas:.0f} h"
        )

    lineas.append("\n=== ÓRDENES DE TRABAJO ABIERTAS ===")
    if abiertas:
        for o in abiertas:
            lineas.append(
                f"- OT#{o['id']} [{o['equipo_codigo']}] {o['tipo']} | "
                f"prioridad: {o['prioridad']} | {o['descripcion']}"
            )
    else:
        lineas.append("(ninguna)")

    return "\n".join(lineas)


def cliente_disponible() -> bool:
    """Indica si hay clave de API configurada."""
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def responder(
    mensajes: list[dict], usar_contexto: bool = True, usar_manual: bool = False
) -> str:
    """Envía la conversación a Claude y devuelve la respuesta en texto.

    `mensajes` es una lista [{"role": "user"|"assistant", "content": "..."}].
    Con `usar_manual=True` se recuperan fragmentos del manual Wärtsilä 46 (RAG)
    relevantes a la última pregunta y se inyectan como contexto citable.
    """
    if not cliente_disponible():
        return (
            "⚠️ No hay clave de API configurada. Copia `.env.example` a `.env` "
            "y agrega tu `ANTHROPIC_API_KEY` para activar el asistente."
        )

    cliente = Anthropic()  # toma ANTHROPIC_API_KEY del entorno
    modelo = os.getenv("ANTHROPIC_MODEL", MODELO_POR_DEFECTO)

    system = INSTRUCCIONES_SISTEMA
    if usar_contexto:
        system += "\n\n# Contexto actual de la planta\n" + _construir_contexto_planta()
    if usar_manual:
        pregunta = next(
            (m["content"] for m in reversed(mensajes) if m.get("role") == "user"), ""
        )
        contexto_manual, _paginas = rag_manual.contexto_para(pregunta)
        if contexto_manual:
            system += "\n\n" + contexto_manual

    respuesta = cliente.messages.create(
        model=modelo,
        max_tokens=1500,
        system=system,
        messages=mensajes,
    )
    return "".join(
        bloque.text for bloque in respuesta.content if bloque.type == "text"
    )

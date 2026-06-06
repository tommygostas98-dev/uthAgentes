"""Helper de envío de alarma para el AGENTE (Claude) — canal A (correo) + B (MCP).

Lo usa Claude cuando el vigía lo invoca para procesar un archivo: Claude redacta
el asunto y el cuerpo (con su diagnóstico) y los manda por los dos canales con:

    python enviar_alarma.py "ASUNTO" "CUERPO" [ruta_pdf_opcional]

El correo lleva la alarma del momento (el cuerpo que redactó el agente) y, ADJUNTO,
el REPORTE GERENCIAL en PDF de esa alarma (resumen ejecutivo), que este script
genera a partir del asunto+cuerpo y del estado crítico actual. El agente se
concentra en analizar y redactar; el envío y el PDF quedan robustos y uniformes.
"""
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

from src import canal_mcp, database, notificaciones, reportes  # noqa: E402

DIR_REPORTES = BASE / "reportes_fallas"


def _generar_pdf_gerencial(asunto: str, cuerpo: str) -> Path | None:
    """Genera y guarda el reporte gerencial (resumen ejecutivo) en PDF de esta
    alarma. Devuelve la ruta del PDF, o None si no se pudo generar."""
    try:
        lineas = notificaciones.alertas_criticas()
        anoms = notificaciones.anomalias_altas()
        fecha = datetime.now().isoformat(timespec="seconds")
        pdf = reportes.generar_pdf_gerencial(asunto, cuerpo, lineas, anoms, fecha=fecha)
        DIR_REPORTES.mkdir(exist_ok=True)
        ruta = DIR_REPORTES / f"gerencial_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        ruta.write_bytes(pdf)
        print(f"Reporte gerencial PDF: reportes_fallas/{ruta.name}")
        return ruta
    except Exception as e:
        print(f"Reporte gerencial NO generado: {type(e).__name__}: {e}")
        return None


def main() -> None:
    if len(sys.argv) < 3:
        print("uso: python enviar_alarma.py \"ASUNTO\" \"CUERPO\" [ruta_pdf]")
        sys.exit(2)
    asunto = sys.argv[1]
    cuerpo = sys.argv[2]
    pdf_extra = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3].strip() else None

    # Reporte gerencial en PDF de la alarma del momento (siempre se adjunta).
    adjuntos: list[Path] = []
    pdf_gerencial = _generar_pdf_gerencial(asunto, cuerpo)
    if pdf_gerencial:
        adjuntos.append(pdf_gerencial)
    if pdf_extra and Path(pdf_extra).exists():     # PDF adicional opcional
        adjuntos.append(Path(pdf_extra))

    # --- Canal A: correo (alarma del momento + reporte gerencial adjunto) ---
    destino = database.obtener_config("auto_alertas_destino", "") or notificaciones.destino_por_defecto()
    if notificaciones.configurado() and destino:
        try:
            notificaciones.enviar(destino, asunto, cuerpo, adjuntos=adjuntos or None)
            print(f"CANAL A (correo) -> {destino}"
                  + (f" con {len(adjuntos)} adjunto(s)" if adjuntos else ""))
        except Exception as e:
            print(f"CANAL A ERROR: {type(e).__name__}: {e}")
    else:
        print("CANAL A omitido (sin credenciales SMTP o sin destino)")

    # --- Canal B: difusión a los otros agentes (MCP) ---
    res = canal_mcp.enviar_difusion(asunto, cuerpo[:1500])
    print(f"CANAL B (otros agentes): {'enviado' if res.get('ok') else 'no enviado (' + str(res.get('motivo')) + ')'}")


if __name__ == "__main__":
    main()

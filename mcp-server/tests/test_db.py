"""Tests de la capa SQLite. Corre con `python tests/test_db.py` o con pytest."""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import db


def _con():
    fd, ruta = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    con = db.conectar(ruta)
    db.init_db(con)
    return con


def test_slug():
    assert db.slug("María López") == "maria_lopez"
    assert db.slug("Juan  Pérez-Gómez") == "juan_perez_gomez"
    assert db.slug("   ") == "anon"


def test_registrar_y_listar():
    c = _con()
    e = db.registrar_estudiante(c, "Ana Perez", variante="2", canal="telegram")
    assert e["slug"] == "ana_perez" and e["variante"] == "2"
    assert len(db.listar_estudiantes(c)) == 1


def test_update_preserva_campos_vacios():
    c = _con()
    db.registrar_estudiante(c, "Ana Perez", variante="2", canal="telegram")
    db.registrar_estudiante(c, "Ana Perez", agente="MotorBot")  # variante/canal vacios
    e = db.obtener_estudiante(c, "ana_perez")
    assert e["variante"] == "2" and e["canal"] == "telegram" and e["agente"] == "MotorBot"


def test_mensajes_directos_y_difusion():
    c = _con()
    db.registrar_estudiante(c, "Ana Perez")
    db.registrar_estudiante(c, "Beto Ruiz")
    db.enviar_mensaje(c, "Ana Perez", "hola", "cuerpo", de="Beto Ruiz")
    db.enviar_mensaje(c, "todos", "anuncio", "a la clase", de="Beto Ruiz")

    # Ana tiene 1 directo + 1 difusion sin ver.
    assert db.contar_no_leidos(c, "ana_perez") == 2
    inbox = db.historial_mensajes(c, "ana_perez")
    assert len(inbox) == 2  # directo + difusion
    # Tras leer, nada queda como no leido.
    assert db.contar_no_leidos(c, "ana_perez") == 0
    # Beto no recibe el directo de Ana, pero si la difusion.
    assert len(db.historial_mensajes(c, "beto_ruiz")) == 1


def test_solo_no_leidos():
    c = _con()
    db.registrar_estudiante(c, "Ana Perez")
    db.enviar_mensaje(c, "Ana Perez", "1", "a")
    db.historial_mensajes(c, "ana_perez")  # marca leido
    db.enviar_mensaje(c, "Ana Perez", "2", "b")
    nuevos = db.historial_mensajes(c, "ana_perez", solo_no_leidos=True, marcar_leidos=False)
    assert len(nuevos) == 1 and nuevos[0]["asunto"] == "2"


def test_enviar_a_desconocido():
    c = _con()
    r = db.enviar_mensaje(c, "fantasma", "x", "y")
    assert r["destino_existe"] is False
    r2 = db.enviar_mensaje(c, "todos", "x", "y")
    assert r2["destino"] == "todos" and r2["destino_existe"] is True


def test_consultar_estado():
    c = _con()
    assert db.consultar_estado(c, "nadie") is None
    db.registrar_estudiante(c, "Ana Perez")
    db.enviar_mensaje(c, "Ana Perez", "x", "y")
    est = db.consultar_estado(c, "ana_perez")
    assert est["mensajes_no_leidos"] == 1


def test_difusion_estado_por_lector():
    c = _con()
    db.registrar_estudiante(c, "Ana Perez")
    db.enviar_mensaje(c, "todos", "anuncio", "x")
    assert db.contar_no_leidos(c, "ana_perez") == 1  # difusion sin ver
    db.historial_mensajes(c, "ana_perez")  # marca vista (avanza el high-water mark)
    assert db.contar_no_leidos(c, "ana_perez") == 0
    nuevos = db.historial_mensajes(c, "ana_perez", solo_no_leidos=True, marcar_leidos=False)
    assert nuevos == []  # la difusion ya vista no reaparece eternamente


def test_marca_solo_lo_devuelto():
    c = _con()
    db.registrar_estudiante(c, "Ana Perez")
    db.enviar_mensaje(c, "Ana Perez", "1", "a")
    db.historial_mensajes(c, "ana_perez")  # lee y marca el #1
    db.enviar_mensaje(c, "Ana Perez", "2", "b")  # llega despues
    # El #2 (no devuelto en la lectura previa) NO quedo marcado.
    assert db.contar_no_leidos(c, "ana_perez") == 1


def test_rechaza_nombre_reservado_o_vacio():
    c = _con()
    for malo in ("todos", "Clase", "all", "   ", "###"):
        try:
            db.registrar_estudiante(c, malo)
        except ValueError:
            continue
        raise AssertionError(f"debio rechazar el nombre {malo!r}")
    assert len(db.listar_estudiantes(c)) == 0


def test_dm_a_palabra_reservada_es_difusion():
    c = _con()
    db.registrar_estudiante(c, "Ana Perez")
    r = db.enviar_mensaje(c, "todos", "x", "y")
    assert r["destino"] == "todos"
    assert db.obtener_estudiante(c, "todos") is None  # 'todos' no es un estudiante real


def test_caps_de_longitud():
    c = _con()
    db.registrar_estudiante(c, "Ana Perez")
    db.enviar_mensaje(c, "Ana Perez", "x" * 500, "y" * 9000)
    inbox = db.historial_mensajes(c, "ana_perez")
    assert len(inbox[0]["asunto"]) == db.MAX_ASUNTO
    assert len(inbox[0]["cuerpo"]) == db.MAX_CUERPO


def _run_all():
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fallos = 0
    for f in funcs:
        try:
            f()
            print(f"  OK   {f.__name__}")
        except Exception as e:  # noqa: BLE001
            fallos += 1
            print(f"  FAIL {f.__name__}: {e}")
    print(f"\n{len(funcs) - fallos}/{len(funcs)} tests pasaron.")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())

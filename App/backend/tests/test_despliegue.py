"""Arranque de Render: migraciones explícitas y worker con el ciclo de la API."""

import asyncio
import hashlib
from contextlib import asynccontextmanager

import pytest


def despliegue():
    from scripts import serve

    return serve


@pytest.mark.parametrize("terminacion", [b"\n", b"\r\n"])
def test_checksums_historicos_toleran_solo_saltos_de_linea(tmp_path, terminacion):
    serve = despliegue()
    sql = b"CREATE TABLE ejemplo (id int);\n-- Inmutable\n"
    archivo = tmp_path / "001_ejemplo.sql"
    archivo.write_bytes(sql)
    historico = hashlib.sha256(sql.replace(b"\n", terminacion)).hexdigest()[:16]
    assert serve.checksum_compatible(archivo, historico)
    archivo.write_bytes(sql.replace(b"id int", b"id text"))
    assert not serve.checksum_compatible(archivo, historico)


def test_arranque_no_migra_si_no_se_pide(monkeypatch):
    serve = despliegue()
    acciones = []
    monkeypatch.setattr(serve, "migrar", lambda: acciones.append("migracion"))
    monkeypatch.setattr(serve, "iniciar_servidor", lambda **kw: acciones.append(kw))
    assert serve.main([]) == 0
    assert acciones == [{"con_worker": True}]


def test_migra_antes_de_arrancar_y_no_continua_si_falla(monkeypatch):
    serve = despliegue()
    acciones = []

    def fallar():
        acciones.append("migracion")
        raise RuntimeError("migracion fallida")

    monkeypatch.setattr(serve, "migrar", fallar)
    monkeypatch.setattr(serve, "iniciar_servidor", lambda **kw: acciones.append("api"))
    with pytest.raises(RuntimeError, match="migracion fallida"):
        serve.main(["--migrar"])
    assert acciones == ["migracion"]


async def test_worker_comparte_ciclo_y_se_detiene_antes_de_cerrar_pool(monkeypatch):
    serve = despliegue()
    acciones = []
    iniciado = asyncio.Event()

    @asynccontextmanager
    async def ciclo_api(_):
        acciones.append("abrir_pool")
        yield
        acciones.append("cerrar_pool")

    async def worker():
        acciones.append("worker")
        iniciado.set()
        try:
            await asyncio.Event().wait()
        finally:
            acciones.append("detener_worker")

    monkeypatch.setattr(serve, "ciclo_api", ciclo_api)
    monkeypatch.setattr(serve, "procesar_continuamente", worker)
    async with serve.ciclo_servicio(object(), con_worker=True):
        await asyncio.wait_for(iniciado.wait(), timeout=1)
        acciones.append("servir")
    assert acciones == ["abrir_pool", "worker", "servir", "detener_worker", "cerrar_pool"]


async def test_sin_worker_no_procesa_la_cola(monkeypatch):
    serve = despliegue()

    @asynccontextmanager
    async def ciclo_api(_):
        yield

    async def worker():
        pytest.fail("No debe ejecutar el worker")

    monkeypatch.setattr(serve, "ciclo_api", ciclo_api)
    monkeypatch.setattr(serve, "procesar_continuamente", worker)
    async with serve.ciclo_servicio(object(), con_worker=False):
        pass


def test_arranque_no_registra_consultas_con_tokens(monkeypatch):
    serve = despliegue()
    capturado = {}
    monkeypatch.setattr(serve.uvicorn, "run", lambda app, **kw: capturado.update(kw))
    monkeypatch.setenv("PORT", "10000")
    serve.iniciar_servidor(con_worker=False)
    assert capturado["host"] == "0.0.0.0"
    assert capturado["port"] == 10000
    assert capturado["access_log"] is False
    assert capturado["reload"] is False


async def test_migracion_de_despliegue_es_idempotente_y_no_carga_seed(monkeypatch):
    serve = despliegue()
    from tests.soporte_bd import exigir_base_descartable

    exigir_base_descartable()
    # La prueba usa la base descartable explícita; no sobrescribe la URL de .env.
    from app.core.config import settings
    from scripts import migrate

    monkeypatch.setattr(migrate, "sembrar", lambda *a: pytest.fail("No cargar seed"))
    import psycopg

    with psycopg.connect(settings.database_url) as conn:
        antes = conn.execute("SELECT count(*) FROM usuario").fetchone()[0]
    serve.migrar()
    serve.migrar()
    with psycopg.connect(settings.database_url) as conn:
        assert conn.execute("SELECT count(*) FROM usuario").fetchone()[0] == antes


async def test_worker_continua_tras_un_fallo_transitorio(monkeypatch, caplog):
    from scripts import whatsapp_worker

    intentos = 0

    async def lote():
        nonlocal intentos
        intentos += 1
        if intentos == 1:
            raise RuntimeError("secreto-que-no-debe-aparecer")

    async def pausa(_):
        if intentos == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(whatsapp_worker, "procesar_lote", lote)
    monkeypatch.setattr(whatsapp_worker, "pausar", pausa)
    with pytest.raises(asyncio.CancelledError):
        await whatsapp_worker.procesar_continuamente()
    assert intentos == 2
    assert "secreto-que-no-debe-aparecer" not in caplog.text

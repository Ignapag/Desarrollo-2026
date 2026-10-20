"""Arranque de Render: migraciones explícitas y worker con el ciclo de la API."""

import asyncio
import hashlib
import json
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
    monkeypatch.setattr(serve, "cargar_demo_publica", lambda: False, raising=False)
    monkeypatch.setattr(serve.uvicorn, "run", lambda app, **kw: capturado.update(kw))
    monkeypatch.setenv("PORT", "10000")
    serve.iniciar_servidor(con_worker=False)
    assert capturado["host"] == "0.0.0.0"
    assert capturado["port"] == 10000
    assert capturado["access_log"] is False
    assert capturado["reload"] is False


@pytest.mark.parametrize("modo", ["real", "simulado"])
def test_arranque_demo_publica_carga_autorizacion_y_procesa_solo_su_canal(monkeypatch, modo):
    serve = despliegue()
    from app.core.config import settings

    monkeypatch.setattr(settings, "whatsapp_modo", "simulado")
    monkeypatch.setattr(settings, "chat_demo_habilitado", False)
    monkeypatch.setattr(settings, "chat_demo_bd_compartida_autorizada", False, raising=False)
    monkeypatch.setattr(settings, "gemini_modo", "simulado")
    monkeypatch.setattr(settings, "chat_demo_gemini_modo", None)

    class Base:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql, params):
            assert params == ("chat_demo_publico",)
            return self

        def fetchone(self):
            return (json.dumps({"habilitado": True, "gemini_modo": modo}),)

    monkeypatch.setattr(serve.psycopg, "connect", lambda *a, **kw: Base())
    monkeypatch.setattr(serve.uvicorn, "run", lambda *a, **kw: None)
    monkeypatch.setattr(serve.app.router, "lifespan_context", serve.app.router.lifespan_context)
    serve.iniciar_servidor(con_worker=True)
    assert settings.chat_demo_habilitado
    assert settings.chat_demo_bd_compartida_autorizada
    assert settings.chat_demo_gemini_modo == modo
    assert settings.gemini_modo == "simulado"
    opciones = serve.app.router.lifespan_context.keywords
    assert opciones["con_worker"]
    assert opciones["solo_demo"]


@pytest.mark.parametrize(
    "valor",
    [
        None,
        "false",
        "{}",
        '{"habilitado":"true"}',
        "no-json",
        '{"habilitado":true,"gemini_modo":[]}',
        '{"habilitado":true,"gemini_modo":{}}',
    ],
)
def test_sin_parametro_explicito_no_habilita_demo_publica(monkeypatch, valor):
    serve = despliegue()
    from app.core.config import settings

    monkeypatch.setattr(settings, "chat_demo_habilitado", False)

    class Base:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, *args):
            return self

        def fetchone(self):
            return None if valor is None else (valor,)

    monkeypatch.setattr(serve.psycopg, "connect", lambda *a, **kw: Base())
    assert not serve.cargar_demo_publica()
    assert not settings.chat_demo_habilitado


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


async def test_worker_externo_carga_perfil_antes_de_procesar(monkeypatch):
    from scripts import whatsapp_worker

    pasos = []

    async def abrir():
        pasos.append("pool")

    async def cerrar():
        pasos.append("cerrar")

    async def lote(**opciones):
        pasos.append(opciones)

    monkeypatch.setattr(whatsapp_worker, "cargar_demo_publica", lambda: pasos.append("perfil"))
    monkeypatch.setattr(whatsapp_worker, "abrir_pool", abrir)
    monkeypatch.setattr(whatsapp_worker, "cerrar_pool", cerrar)
    monkeypatch.setattr(whatsapp_worker, "procesar_lote", lote)
    await whatsapp_worker.ejecutar(una_vez=True, solo_demo=True)
    assert pasos == ["perfil", "pool", {"solo_demo": True}, "cerrar"]

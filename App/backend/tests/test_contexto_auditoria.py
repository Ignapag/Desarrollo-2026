"""El actor validado y el origen deben acompañar cada transacción, sin fugas."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.core import auditoria
from app.core.db import UnidadDeTrabajo, abrir_pool, cerrar_pool
from app.core.dependencias import UoW
from app.errores import NoAutenticado
from app.modules.usuarios.application.servicio_auth import ServicioAuth
from app.modules.usuarios.domain.entidades import ClaimsSesion, Rol
from app.modules.usuarios.infrastructure.repositorio_sql import RepositorioUsuariosSQL
from app.modules.usuarios.presentation.dependencias import (
    obtener_servicio_acceso,
    sesion_vigente,
)
from app.modules.whatsapp.presentation import procesamiento
from tests.soporte_bd import exigir_base_descartable


async def contexto(uow):
    return await uow.uno(
        """SELECT NULLIF(current_setting('monu.usuario_id', true), '') AS usuario_id,
                  NULLIF(current_setting('monu.ip', true), '') AS ip,
                  NULLIF(current_setting('monu.origen', true), '') AS origen,
                  NULLIF(current_setting('monu.identificador_operacion', true), '')
                    AS identificador_operacion"""
    )


async def test_contexto_instala_origen_y_limpia_actor_previo(uow):
    await uow.ejecutar("SELECT set_config('monu.usuario_id', '999', true)")
    await uow.configurar_auditoria(origen="http", ip="2001:db8::1")

    datos = await contexto(uow)
    assert datos["usuario_id"] is None
    assert datos["ip"] == "2001:db8::1"
    assert datos["origen"] == "http"
    assert UUID(datos["identificador_operacion"])


async def test_contexto_no_sobrevive_rollback(uow):
    await uow.configurar_auditoria(origen="http", ip="192.0.2.7")
    await uow.atribuir_actor(1)
    await uow.conn.rollback()

    assert await contexto(uow) == {
        "usuario_id": None, "ip": None, "origen": None,
        "identificador_operacion": None,
    }


async def test_contexto_no_sobrevive_commit(uow):
    await uow.configurar_auditoria(origen="http", ip="192.0.2.8")
    await uow.atribuir_actor(1)
    await uow.conn.commit()

    assert (await contexto(uow))["usuario_id"] is None
    assert (await contexto(uow))["ip"] is None


async def test_worker_no_hereda_actor_http_en_misma_conexion(uow):
    await uow.configurar_auditoria(origen="http", ip="192.0.2.8")
    await uow.atribuir_actor(1)
    worker = UnidadDeTrabajo(
        uow.conn, origen="whatsapp", identificador_operacion="mensaje-de-prueba",
    )

    assert await contexto(worker) == {
        "usuario_id": None, "ip": None, "origen": "whatsapp",
        "identificador_operacion": "mensaje-de-prueba",
    }


async def test_sesion_atribuye_solo_identidad_vigente(uow):
    fila = await uow.uno("SELECT id FROM usuario WHERE username='taramburu'")
    await uow.configurar_auditoria(origen="http")
    # Un rol antiguo en el JWT no puede convertirse en la identidad vigente.
    token = ClaimsSesion(fila["id"], Rol.DUENIO, "nombre-anterior")

    vigente = await sesion_vigente(token, obtener_servicio_acceso(uow), uow)

    assert vigente.rol == Rol.EMPLEADO
    assert vigente.username == "taramburu"
    assert (await contexto(uow))["usuario_id"] == str(fila["id"])


async def test_sesion_inactiva_no_atribuye_actor(uow):
    fila = await uow.uno("SELECT id FROM usuario WHERE username='taramburu'")
    await uow.ejecutar("UPDATE usuario SET estado='INACTIVO' WHERE id=%s", (fila["id"],))
    await uow.configurar_auditoria(origen="http")

    with pytest.raises(NoAutenticado):
        await sesion_vigente(
            ClaimsSesion(fila["id"], Rol.EMPLEADO, "taramburu"),
            obtener_servicio_acceso(uow), uow,
        )
    assert (await contexto(uow))["usuario_id"] is None


async def test_evento_negocio_hereda_contexto_transaccional(uow):
    fila = await uow.uno("SELECT id FROM usuario WHERE username='admin'")
    operacion = uuid4().hex
    await uow.configurar_auditoria(
        origen="http", ip="192.0.2.20", identificador_operacion=operacion,
    )
    await uow.atribuir_actor(fila["id"])
    await auditoria.registrar(
        uow, accion="PRUEBA_CONTEXTO", entidad="prueba", entidad_id=operacion,
    )

    evento = next(e for e in await auditoria.listar(uow, accion="PRUEBA_CONTEXTO")
                  if e["entidad_id"] == operacion)
    assert evento["usuario_id"] == fila["id"]
    assert evento["ip"] == "192.0.2.20"
    assert evento["origen"] == "http"
    assert evento["identificador_operacion"] == operacion


async def test_login_exitoso_atribuye_antes_de_modificar_usuario(uow):
    await uow.configurar_auditoria(origen="http", ip="192.0.2.30")
    servicio = ServicioAuth(uow, RepositorioUsuariosSQL(uow))

    sesion = await servicio.iniciar_sesion(username="taramburu", password="Monu2026!")

    assert (await contexto(uow))["usuario_id"] == str(sesion.usuario_id)
    eventos = await auditoria.listar(uow, accion="DATOS_MODIFICADOS", entidad="usuario")
    acceso = next(e for e in eventos if e["entidad_id"] == str(sesion.usuario_id)
                  and "ultimo_acceso" in e["datos"]["campos_modificados"])
    assert acceso["usuario_id"] == sesion.usuario_id
    assert acceso["ip"] == "192.0.2.30"


async def test_login_fallido_no_atribuye_usuario_encontrado(uow):
    await uow.configurar_auditoria(origen="http")
    servicio = ServicioAuth(uow, RepositorioUsuariosSQL(uow))

    with pytest.raises(NoAutenticado):
        await servicio.iniciar_sesion(username="taramburu", password="incorrecta")
    assert (await contexto(uow))["usuario_id"] is None


@pytest.mark.parametrize(
    "identificador,origen", [("wamid.prueba", "whatsapp"), ("web:hash-privado:uuid", "chat_demo")],
)
async def test_worker_atribuye_cambio_real_sin_usuario_ni_hash_sesion(
    uow, monkeypatch, identificador, origen,
):
    fila = await uow.uno("SELECT id FROM usuario WHERE username='taramburu'")
    await uow.configurar_auditoria(origen="http", ip="192.0.2.80")
    await uow.atribuir_actor(fila["id"])

    @asynccontextmanager
    async def conexion_local():
        yield uow.conn

    class Preparacion:
        def __init__(self, unidad):
            self.unidad = unidad

        async def preparar(self, _):
            await self.unidad.ejecutar(
                "UPDATE usuario SET ultimo_acceso=now() WHERE id=%s", (fila["id"],),
            )
            return None

    monkeypatch.setattr(procesamiento, "conexion", conexion_local)
    monkeypatch.setattr(procesamiento, "construir_servicio", Preparacion)
    await procesamiento.procesar_entrada(identificador)

    eventos = await auditoria.listar(uow, accion="DATOS_MODIFICADOS", entidad="usuario")
    cambio = next(e for e in eventos if e["entidad_id"] == str(fila["id"])
                  and "ultimo_acceso" in e["datos"]["campos_modificados"])
    assert cambio["origen"] == origen
    assert cambio["usuario_id"] is None
    assert cambio["ip"] is None
    assert UUID(cambio["identificador_operacion"])
    assert "hash-privado" not in cambio["identificador_operacion"]


@pytest_asyncio.fixture
async def api_contexto():
    exigir_base_descartable()
    aplicacion = FastAPI()

    @aplicacion.get("/contexto")
    @aplicacion.get("/api/chat-demo/contexto")
    async def leer_contexto(uow: UoW):
        return await contexto(uow)

    await abrir_pool()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=aplicacion), base_url="http://test",
        ) as cliente:
            yield cliente
    finally:
        await cerrar_pool()


async def test_requests_concurrentes_no_comparten_origen_ip_ni_identificador(api_contexto):
    normal, demo = await asyncio.gather(
        api_contexto.get("/contexto", headers={"x-forwarded-for": "192.0.2.41"}),
        api_contexto.get(
            "/api/chat-demo/contexto",
            headers={"x-forwarded-for": "192.0.2.42", "x-usuario-id": "1"},
        ),
    )

    assert normal.status_code == demo.status_code == 200
    normal, demo = normal.json(), demo.json()
    assert normal["origen"] == "http"
    assert demo["origen"] == "chat_demo"
    assert normal["ip"] == "192.0.2.41"
    assert demo["ip"] == "192.0.2.42"
    assert normal["usuario_id"] is demo["usuario_id"] is None
    assert normal["identificador_operacion"] != demo["identificador_operacion"]

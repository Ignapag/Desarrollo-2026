"""Doble solicitud HTTP sobre conexiones y commits independientes, base local."""

import asyncio
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import settings
from app.core.db import UnidadDeTrabajo
from app.core.dependencias import obtener_uow
from app.core.errores import manejador_error_dominio
from app.errores import ErrorDominio
from app.modules.whatsapp.domain.mensajes import hash_referencia
from tests.soporte_bd import conectar_o_omitir
from tests.test_whatsapp_bd import datos_prueba


@pytest.mark.asyncio
async def test_doble_click_concurrente_confirma_una_entrada_y_recupera_conexion_nueva(
    uow, monkeypatch
):
    from app.modules.whatsapp.presentation.router_demo import router

    monkeypatch.setattr(settings, "chat_demo_habilitado", True)
    monkeypatch.setattr(settings, "entorno", "desarrollo")
    monkeypatch.setattr(settings, "whatsapp_modo", "simulado")
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)

    async def unidad():
        conn = await conectar_o_omitir()
        async with conn:
            yield UnidadDeTrabajo(conn)

    app.dependency_overrides[obtener_uow] = unidad
    _, item = await datos_prueba(uow)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://prueba",
        headers={"X-Chat-Demo": "1"},
    ) as cliente:
        assert (await cliente.post("/api/chat-demo/sesion", json={})).status_code == 200
        token_hash = hash_referencia(cliente.cookies.get("monu_chat_demo"))
        try:
            cuerpo = {"solicitud_id": str(uuid4()), "borrador": {"items": [item]}}
            respuestas = await asyncio.gather(
                *[cliente.post("/api/chat-demo/borradores", json=cuerpo) for _ in range(2)]
            )
            assert [r.status_code for r in respuestas] == [202, 202]
            assert respuestas[0].json() == respuestas[1].json()
            historial = (await cliente.get("/api/chat-demo/conversacion")).json()
            assert len(historial["borradores"]) == len(historial["mensajes"]) == 1
            # La lectura proviene de otra conexión, posterior a ambos commits HTTP.
            conn = await conectar_o_omitir()
            async with conn:
                db = UnidadDeTrabajo(conn)
                assert (
                    await db.valor(
                        "SELECT count(*) FROM chat_demo_operacion WHERE sesion_hash=%s",
                        (token_hash,),
                    )
                    == 1
                )
        finally:
            conn = await conectar_o_omitir()
            async with conn:
                db = UnidadDeTrabajo(conn)
                sesion = await db.uno(
                    "SELECT * FROM chat_demo_sesion WHERE token_hash=%s",
                    (token_hash,),
                )
                # Sólo filas de esta prueba, sin worker ni pedidos operativos creados.
                await db.ejecutar(
                    "DELETE FROM chat_demo_operacion WHERE sesion_hash=%s", (token_hash,)
                )
                await db.ejecutar(
                    "DELETE FROM whatsapp_entrada WHERE telefono=%s", (sesion["telefono"],)
                )
                await db.ejecutar(
                    "DELETE FROM whatsapp_borrador WHERE telefono=%s", (sesion["telefono"],)
                )
                await db.ejecutar("DELETE FROM chat_demo_sesion WHERE token_hash=%s", (token_hash,))
                await db.ejecutar("DELETE FROM cliente WHERE id=%s", (sesion["cliente_id"],))

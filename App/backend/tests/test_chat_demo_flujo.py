"""Recorrido HTTP + worker + panel compartido en PostgreSQL, IA simulada explícita."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.errores import ReglaDeNegocio
from app.modules.pedidos.domain.entidades import EstadoPedido
from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos
from app.modules.whatsapp.infrastructure.proveedores import (
    GeminiInterpretador,
    SimuladoInterpretador,
)
from app.modules.whatsapp.presentation import procesamiento
from app.modules.whatsapp.presentation.dependencias import construir_servicio
from tests.test_chat_demo import chat as chat
from tests.test_chat_demo import enviar, iniciar
from tests.test_whatsapp_regresiones import empleado, item_con_tomate

__all__ = ["chat"]


@pytest.fixture
def worker_demo(uow, monkeypatch):
    @asynccontextmanager
    async def conexion():
        yield uow.conn

    monkeypatch.setattr(procesamiento, "conexion", conexion)
    monkeypatch.setattr(procesamiento, "interpretador", SimuladoInterpretador)
    return procesamiento


async def turno(chat, worker_demo, texto):
    entrada = await enviar(chat, texto)
    await worker_demo.procesar_entrada(entrada)
    return entrada


async def preparar(chat, uow, worker_demo, items):
    await iniciar(chat)
    cuerpo = {"solicitud_id": str(uuid4()), "borrador": {"items": items}}
    recibido = await chat.post("/api/chat-demo/borradores", json=cuerpo)
    assert recibido.status_code == 202, recibido.text
    await worker_demo.procesar_entrada(recibido.json()["id"])
    assert (await chat.get("/api/chat-demo/conversacion")).json()["borradores"][0][
        "pedido_id"
    ] is None
    await turno(chat, worker_demo, "retiro")
    await turno(chat, worker_demo, "transferencia")
    datos = (await chat.get("/api/chat-demo/conversacion")).json()
    return datos["borradores"][0]["pedido_id"]


@pytest.mark.asyncio
async def test_carrito_modificacion_cocina_revision_y_notificacion(
    chat, uow, worker_demo, monkeypatch
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "whatsapp_transferencia_datos", "DEMO: cuenta sin valor bancario")
    pedido_id = await preparar(chat, uow, worker_demo, [await item_con_tomate(uow)])
    assert pedido_id
    await turno(chat, worker_demo, "¿Le podés sacar el tomate?")
    assert (
        await uow.valor(
            "SELECT aclaraciones FROM pedido_item WHERE pedido_id=%s",
            (pedido_id,),
        )
        == "Sin Tomate"
    )
    pedidos = obtener_servicio_pedidos(uow)
    # Cocina recibe el mismo pedido persistido y sus aclaraciones vigentes.
    pedido = await pedidos.repo.detalle(pedido_id)
    assert pedido["items"][0]["aclaraciones"] == "Sin Tomate"
    with pytest.raises(ReglaDeNegocio):
        await pedidos.cambiar_estado(pedido_id, EstadoPedido.EN_PREPARACION, usuario_id=None)

    subida = await chat.post(
        "/api/chat-demo/comprobantes",
        content=b"%PDF-1.4\nDEMO\n%%EOF",
        headers={
            "Content-Type": "application/pdf",
            "X-Solicitud-Id": str(uuid4()),
        },
    )
    assert subida.status_code == 202
    await worker_demo.procesar_entrada(subida.json()["id"])
    comprobante = await uow.uno(
        "SELECT * FROM whatsapp_comprobante WHERE pedido_id=%s",
        (pedido_id,),
    )
    assert comprobante["estado"] == "PENDIENTE"
    assert await uow.valor("SELECT count(*) FROM pago WHERE pedido_id=%s", (pedido_id,)) == 0
    total = await uow.valor("SELECT total FROM pedido WHERE id=%s", (pedido_id,))
    servicio = construir_servicio(uow)
    personal = await empleado(uow)
    for _ in range(2):
        await servicio.revisar_comprobante(
            comprobante["id"],
            True,
            personal,
            "Revisión humana ficticia",
            total_verificado=total,
        )
    assert await uow.valor("SELECT count(*) FROM pago WHERE pedido_id=%s", (pedido_id,)) == 1
    await pedidos.cambiar_estado(pedido_id, EstadoPedido.EN_PREPARACION, usuario_id=personal)
    stock = await uow.valor(
        "SELECT count(*) FROM movimiento_stock WHERE pedido_id=%s", (pedido_id,)
    )
    assert stock > 0
    await turno(chat, worker_demo, "cantidad: 2")
    await turno(chat, worker_demo, "confirmar")
    assert await uow.valor("SELECT cantidad FROM pedido_item WHERE pedido_id=%s", (pedido_id,)) == 1
    assert (
        await uow.valor(
            "SELECT count(*) FROM whatsapp_cambio "
            "WHERE pedido_id=%s AND estado='PENDIENTE_EMPLEADO'",
            (pedido_id,),
        )
        == 1
    )
    while await worker_demo.enviar_uno():
        pass
    conversacion = (await chat.get("/api/chat-demo/conversacion")).json()
    assert conversacion["borradores"][0]["estado_pedido"] == "EN_PREPARACION"
    assert any(
        "prepar" in m["texto"].lower() for m in conversacion["mensajes"] if m["direccion"] == "bot"
    )
    assert all(
        m["estado"] == "SIMULADO" for m in conversacion["mensajes"] if m["direccion"] == "bot"
    )
    assert (
        await uow.valor("SELECT count(*) FROM movimiento_stock WHERE pedido_id=%s", (pedido_id,))
        == stock
    )


@pytest.mark.asyncio
async def test_ambiguedad_aclaracion_y_fallo_gemini_conservan_pedido(
    chat, uow, worker_demo, monkeypatch
):
    item = await item_con_tomate(uow)
    # Variantes distintas impiden que ServicioPedidos agrupe los dos ítems.
    variantes = await uow.valor(
        "SELECT variantes FROM producto WHERE id=%s", (item["producto_id"],)
    )
    segundo = {**item, "variante": variantes[1]["nombre"]}
    pedido_id = await preparar(chat, uow, worker_demo, [item, segundo])
    await turno(chat, worker_demo, "sin tomate")
    assert not await uow.valor(
        "SELECT EXISTS(SELECT 1 FROM pedido_item WHERE pedido_id=%s AND aclaraciones IS NOT NULL)",
        (pedido_id,),
    )
    await turno(chat, worker_demo, "producto 1")
    assert (
        await uow.valor(
            "SELECT count(*) FROM pedido_item WHERE pedido_id=%s AND aclaraciones='Sin Tomate'",
            (pedido_id,),
        )
        == 1
    )
    antes = await construir_servicio(uow).repo.pedido(pedido_id)
    monkeypatch.setattr(
        procesamiento, "interpretador", lambda: GeminiInterpretador("", "sin-clave")
    )
    fallo = await turno(chat, worker_demo, "cantidad: 2")
    respuesta = await uow.valor("SELECT respuesta FROM whatsapp_entrada WHERE id=%s", (fallo,))
    assert "empleado" in respuesta.lower()
    assert (await construir_servicio(uow).repo.pedido(pedido_id))["items"] == antes["items"]
    await turno(chat, worker_demo, "quiero hablar con una persona")
    atencion = await uow.uno("SELECT * FROM whatsapp_atencion WHERE estado='PENDIENTE'")
    assert atencion
    await construir_servicio(uow).responder_atencion(
        atencion["id"],
        await empleado(uow),
        "Te atendemos por este chat de demostración",
        str(uuid4()),
    )
    visible = (await chat.get("/api/chat-demo/conversacion")).json()["mensajes"]
    assert any("Te atendemos" in mensaje["texto"] for mensaje in visible)

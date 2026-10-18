"""Confirmación humana y snapshot canónico en una llamada, con BD local."""

from decimal import Decimal
from uuid import uuid4

import httpx
import psycopg
import pytest

from app.core.dependencias import obtener_uow
from app.errores import ReglaDeNegocio
from app.modules.pagos.application.servicio_conciliacion import ServicioConciliacion
from app.modules.pedidos.presentation.router import router as pedidos_router
from tests.test_pagos_privacidad import aplicacion, sesion
from tests.test_stock_consumo_bd import crear_pedido, escenario


@pytest.mark.asyncio
@pytest.mark.parametrize("tipo", ["transferencia", "efectivo"])
async def test_cobro_rapido_devuelve_pedido_y_habilita_cocina_sin_get(uow, tipo):
    cliente, producto, (ingrediente,) = await escenario(uow)
    pedido, _ = await crear_pedido(uow, cliente, producto)
    await uow.ejecutar(
        "UPDATE pedido SET subtotal=100,total=100,metodo_pago_acordado=%s WHERE id=%s",
        (tipo.upper(), pedido),
    )
    # El borrador no es autoridad sobre el ingreso conciliado desde el panel.
    await uow.ejecutar(
        "INSERT INTO whatsapp_borrador(referencia_hash,cliente_id,telefono,items,"
        "metodo_pago,estado_pago,pedido_id) "
        "VALUES(%s,%s,'5492215550000','[]','TRANSFERENCIA','PENDIENTE',%s)",
        (uuid4().hex, cliente, pedido),
    )
    actor = await uow.valor("SELECT id FROM usuario WHERE rol='ADMINISTRADOR' LIMIT 1")
    app = aplicacion()
    app.include_router(pedidos_router)
    app.dependency_overrides[obtener_uow] = lambda: uow
    body = {"pedido_id": pedido, "clave_operacion": str(uuid4())}
    body.update({"monto": "100"} if tipo == "transferencia" else {"monto_recibido": "100"})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url="http://test",
        cookies=sesion(actor, "ADMINISTRADOR"),
    ) as client:
        path = f"/api/pagos/{tipo}?incluir_pedido=true&confirmar_ingreso=true"
        paid = await client.post(path, json=body)
        assert paid.status_code == 201, paid.text
        snapshot = paid.json()["pedido"]
        assert Decimal(snapshot["neto_cobrado"]) == 100
        assert Decimal(snapshot["saldo_pendiente"]) == 0
        assert snapshot["estado"] == "PENDIENTE"
        repeat = await client.post(path, json=body)
        assert repeat.status_code == 201
        assert len(repeat.json()["pedido"]["pagos"]) == 1
        cooking = await client.patch(
            f"/api/pedidos/{pedido}/estado",
            json={
                "estado": "EN_PREPARACION",
                "version_esperada": snapshot["version"],
                "estado_esperado": snapshot["estado"],
            },
        )
    assert cooking.status_code == 200, cooking.text
    assert cooking.json()["estado"] == "EN_PREPARACION"
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,)) == 1
    )


@pytest.mark.asyncio
async def test_transferencia_sin_confirmacion_sigue_pendiente(uow):
    cliente, producto, _ = await escenario(uow)
    pedido, _ = await crear_pedido(uow, cliente, producto)
    await uow.ejecutar("UPDATE pedido SET subtotal=100,total=100 WHERE id=%s", (pedido,))
    actor = await uow.valor("SELECT id FROM usuario WHERE rol='ADMINISTRADOR' LIMIT 1")
    app = aplicacion()
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url="http://test",
        cookies=sesion(actor, "ADMINISTRADOR"),
    ) as client:
        result = await client.post(
            "/api/pagos/transferencia?incluir_pedido=true",
            json={"pedido_id": pedido, "monto": "100", "clave_operacion": str(uuid4())},
        )
    assert result.status_code == 201
    assert result.json()["estado"] == "PENDIENTE"
    assert Decimal(result.json()["pedido"]["neto_cobrado"]) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metodo,neto,permitido",
    [("TRANSFERENCIA", 0, False), ("TRANSFERENCIA", 100, True), ("EFECTIVO", 0, True)],
)
async def test_trigger_usa_metodo_vigente_y_dinero_real_sin_depender_del_borrador(
    uow, metodo, neto, permitido
):
    cliente, producto, _ = await escenario(uow)
    pedido, _ = await crear_pedido(uow, cliente, producto)
    await uow.ejecutar(
        "UPDATE pedido SET subtotal=100,total=100,metodo_pago_acordado=%s WHERE id=%s",
        (metodo, pedido),
    )
    await uow.ejecutar(
        "INSERT INTO whatsapp_borrador(referencia_hash,cliente_id,telefono,items,"
        "metodo_pago,estado_pago,pedido_id) "
        "VALUES(%s,%s,'5492215550000','[]','TRANSFERENCIA','APROBADO',%s)",
        (uuid4().hex, cliente, pedido),
    )
    if neto:
        await uow.ejecutar(
            "INSERT INTO pago(pedido_id,metodo_pago,monto,estado) "
            "VALUES(%s,'TRANSFERENCIA',%s,'CONCILIADO')",
            (pedido, neto),
        )
    if permitido:
        await uow.ejecutar("UPDATE pedido SET estado='EN_PREPARACION' WHERE id=%s", (pedido,))
    else:
        async with uow.conn.transaction():
            with pytest.raises(psycopg.errors.CheckViolation):
                async with uow.conn.transaction():
                    await uow.ejecutar(
                        "UPDATE pedido SET estado='EN_PREPARACION' WHERE id=%s", (pedido,)
                    )


@pytest.mark.asyncio
async def test_confirmacion_atomica_revierte_registro_si_no_se_puede_conciliar(uow, monkeypatch):
    cliente, producto, _ = await escenario(uow)
    pedido, _ = await crear_pedido(uow, cliente, producto)
    await uow.ejecutar("UPDATE pedido SET subtotal=100,total=100 WHERE id=%s", (pedido,))
    actor = await uow.valor("SELECT id FROM usuario WHERE rol='ADMINISTRADOR' LIMIT 1")

    async def fallar(*args, **kwargs):
        raise ReglaDeNegocio("No se pudo verificar el ingreso")

    monkeypatch.setattr(ServicioConciliacion, "conciliar_pago", fallar)

    async def transaccion_request():
        async with uow.conn.transaction():
            yield uow

    app = aplicacion()
    app.dependency_overrides[obtener_uow] = transaccion_request
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url="http://test",
        cookies=sesion(actor, "ADMINISTRADOR"),
    ) as client:
        result = await client.post(
            "/api/pagos/transferencia?confirmar_ingreso=true&incluir_pedido=true",
            json={"pedido_id": pedido, "monto": "100", "clave_operacion": str(uuid4())},
        )
    assert result.status_code == 409
    assert await uow.valor("SELECT count(*) FROM pago WHERE pedido_id=%s", (pedido,)) == 0


@pytest.mark.asyncio
async def test_conciliar_pendiente_y_devolver_devuelven_saldo_canonico(uow):
    cliente, producto, _ = await escenario(uow)
    pedido, _ = await crear_pedido(uow, cliente, producto)
    await uow.ejecutar("UPDATE pedido SET subtotal=100,total=100 WHERE id=%s", (pedido,))
    pago = await uow.valor(
        "INSERT INTO pago(pedido_id,metodo_pago,monto,estado) "
        "VALUES(%s,'TRANSFERENCIA',100,'PENDIENTE') RETURNING id",
        (pedido,),
    )
    actor = await uow.valor("SELECT id FROM usuario WHERE rol='ADMINISTRADOR' LIMIT 1")
    app = aplicacion()
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url="http://test",
        cookies=sesion(actor, "ADMINISTRADOR"),
    ) as client:
        paid = await client.post(f"/api/pagos/{pago}/conciliar?incluir_pedido=true", json={})
        assert paid.status_code == 200
        assert Decimal(paid.json()["pedido"]["saldo_pendiente"]) == 0
        refund = await client.post(
            "/api/pagos/devolucion?incluir_pedido=true",
            json={
                "pedido_id": pedido,
                "monto": "50",
                "metodo_pago": "TRANSFERENCIA",
                "motivo": "Devolución verificada",
                "clave_operacion": str(uuid4()),
            },
        )
    assert refund.status_code == 201, refund.text
    assert Decimal(refund.json()["pedido"]["neto_cobrado"]) == 50
    assert Decimal(refund.json()["pedido"]["saldo_pendiente"]) == 50

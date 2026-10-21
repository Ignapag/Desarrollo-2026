"""Edicion conjunta: una propuesta y un total final, sin estados intermedios."""

from decimal import Decimal
from uuid import uuid4

import pytest
from psycopg.errors import LockNotAvailable

from app.core.db import UnidadDeTrabajo
from app.errores import DatosInvalidos, ReglaDeNegocio
from app.modules.pedidos.domain.entidades import EstadoPedido
from app.modules.pedidos.infrastructure.repositorio_sql import RepositorioPedidosSQL
from app.modules.stock.application.servicio_stock import StockInsuficiente
from tests.soporte_bd import conectar_o_omitir
from tests.test_edicion_items_bd import crear


async def direccion_nueva(uow, *, costo=25):
    localidad = f"Compuesta {uuid4().hex}"
    await uow.ejecutar(
        "INSERT INTO zona_cobertura(nombre,costo_envio,poligono,centro_lat,centro_lng) "
        "VALUES(%s,%s,'[]',0,0)", (localidad, costo),
    )
    return {"calle": "52", "numero": "32", "localidad": localidad}


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmado", [False, True])
async def test_cotiza_sin_escribir_y_aplica_items_entrega_pago_en_una_version(uow, confirmado):
    servicio, pedido, producto, ingrediente = await crear(uow)
    if confirmado:
        pedido = await servicio.cambiar_estado(
            pedido["id"], EstadoPedido.CONFIRMADO, usuario_id=None,
        )
    original = pedido["items"][0]
    direccion = await direccion_nueva(uow)
    items = [{"id": original["id"], "cantidad": 1}, {"producto_id": producto, "cantidad": 1}]
    cambios = {"tipo_entrega": "DELIVERY", "direccion_nueva": direccion,
               "metodo_pago_acordado": "TRANSFERENCIA"}
    direcciones = await uow.valor("SELECT count(*) FROM direccion")
    cotizacion = await servicio.cotizar_edicion(pedido["id"], items=items, cambios=cambios)
    assert cotizacion["total"] == 225
    assert cotizacion["subtotal"] == 200
    assert cotizacion["costo_envio"] == 25
    assert cotizacion["direccion_nueva"] == direccion
    assert await uow.valor("SELECT count(*) FROM direccion") == direcciones
    assert (await servicio.detalle(pedido["id"])) == pedido
    editado = await servicio.editar_edicion(
        pedido["id"], items=items, cambios=cambios, version_esperada=pedido["version"],
        total_esperado=cotizacion["total"],
    )
    assert editado["version"] == pedido["version"] + 1
    assert editado["total"] == 225
    assert editado["tipo_entrega"] == "DELIVERY"
    assert editado["metodo_pago_acordado"] == "TRANSFERENCIA"
    assert editado["items"][0]["id"] == original["id"]
    assert editado["items"][0]["receta_snapshot"] == original["receta_snapshot"]
    assert len(editado["historial"]) == len(pedido["historial"]) + 1
    assert set(editado["historial"][-1]["cambios"]) >= {"items", "tipo_entrega", "total"}
    assert await uow.valor(
        "SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,),
    ) == (8 if confirmado else 10)


@pytest.mark.asyncio
async def test_reduccion_items_mas_envio_valida_neto_final_no_subtotal_intermedio(uow):
    servicio, pedido, _, _ = await crear(uow)
    pedido = await servicio.editar_items(
        pedido["id"], items=[{"id": pedido["items"][0]["id"], "cantidad": 2}],
        version_esperada=pedido["version"],
    )
    await uow.ejecutar(
        "INSERT INTO pago(pedido_id,tipo,metodo_pago,monto,estado) "
        "VALUES(%s,'COBRO','EFECTIVO',120,'CONCILIADO')", (pedido["id"],),
    )
    direccion = await direccion_nueva(uow)
    items = [{"id": pedido["items"][0]["id"], "cantidad": 1}]
    cambios = {"tipo_entrega": "DELIVERY", "direccion_nueva": direccion}
    cotizacion = await servicio.cotizar_edicion(pedido["id"], items=items, cambios=cambios)
    assert cotizacion["total"] == 125
    editado = await servicio.editar_edicion(
        pedido["id"], items=items, cambios=cambios, version_esperada=pedido["version"],
        total_esperado=cotizacion["total"],
    )
    assert editado["total"] == 125
    assert editado["neto_cobrado"] == 120


@pytest.mark.asyncio
async def test_agregar_items_mas_retiro_no_valida_total_intermedio_sin_envio(uow):
    servicio, pedido, _, _ = await crear(uow)
    direccion = await direccion_nueva(uow)
    pedido = await servicio.editar_operacion(
        pedido["id"], cambios={"tipo_entrega": "DELIVERY", "direccion_nueva": direccion},
        usuario_id=None, motivo="Delivery", version_esperada=pedido["version"],
    )
    await uow.ejecutar(
        "INSERT INTO pago(pedido_id,tipo,metodo_pago,monto,estado) "
        "VALUES(%s,'COBRO','EFECTIVO',125,'CONCILIADO')", (pedido["id"],),
    )
    items = [{"id": pedido["items"][0]["id"], "cantidad": 2}]
    cotizacion = await servicio.cotizar_edicion(
        pedido["id"], items=items, cambios={"tipo_entrega": "RETIRO"},
    )
    editado = await servicio.editar_edicion(
        pedido["id"], items=items, cambios={"tipo_entrega": "RETIRO"},
        version_esperada=pedido["version"], total_esperado=cotizacion["total"],
    )
    assert editado["total"] == 200
    assert editado["costo_envio"] == 0
    assert editado["direccion_id"] is None
    assert editado["version"] == pedido["version"] + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("caso", ["neto", "version", "precio", "zona", "stock", "cocina"])
async def test_rechaza_antes_de_mutar_items_direccion_stock_historial(uow, caso):
    servicio, pedido, producto, ingrediente = await crear(uow, saldo=Decimal("2"))
    pedido = await servicio.cambiar_estado(pedido["id"], EstadoPedido.CONFIRMADO, usuario_id=None)
    direccion = await direccion_nueva(uow)
    items = [{"id": pedido["items"][0]["id"], "cantidad": 1},
             {"producto_id": producto, "cantidad": 1}]
    cambios = {"tipo_entrega": "DELIVERY", "direccion_nueva": direccion}
    cotizacion = await servicio.cotizar_edicion(pedido["id"], items=items, cambios=cambios)
    version = pedido["version"]
    if caso == "neto":
        await uow.ejecutar(
            "INSERT INTO pago(pedido_id,tipo,metodo_pago,monto,estado) "
            "VALUES(%s,'COBRO','EFECTIVO',300,'CONCILIADO')", (pedido["id"],),
        )
    elif caso == "version":
        version -= 1
    elif caso == "precio":
        await uow.ejecutar("UPDATE producto SET precio_base=150 WHERE id=%s", (producto,))
    elif caso == "zona":
        await uow.ejecutar("UPDATE zona_cobertura SET costo_envio=50 WHERE nombre=%s",
                          (direccion["localidad"],))
    elif caso == "stock":
        await uow.ejecutar("UPDATE ingrediente SET cantidad_actual=0 WHERE id=%s", (ingrediente,))
    elif caso == "cocina":
        await uow.ejecutar("UPDATE pedido SET preparacion_en=now() WHERE id=%s", (pedido["id"],))
    antes = await servicio.detalle(pedido["id"])
    saldo = await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,))
    direcciones = await uow.valor("SELECT count(*) FROM direccion")
    with pytest.raises((ReglaDeNegocio, StockInsuficiente)):
        await servicio.editar_edicion(
            pedido["id"], items=items, cambios=cambios, version_esperada=version,
            total_esperado=cotizacion["total"],
        )
    assert await servicio.detalle(pedido["id"]) == antes
    assert await uow.valor("SELECT count(*) FROM direccion") == direcciones
    assert await uow.valor(
        "SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,),
    ) == saldo


@pytest.mark.asyncio
async def test_campos_ajenos_no_se_ignoran(uow):
    servicio, pedido, _, _ = await crear(uow)
    with pytest.raises(DatosInvalidos):
        await servicio.cotizar_edicion(
            pedido["id"], items=[{"id": pedido["items"][0]["id"], "cantidad": 1}],
            cambios={"total": 1},
        )


@pytest.mark.asyncio
async def test_error_tras_escritura_propaga_y_revierte_toda_la_edicion(uow, monkeypatch):
    servicio, pedido, _, ingrediente = await crear(uow)
    pedido = await servicio.cambiar_estado(pedido["id"], EstadoPedido.CONFIRMADO, usuario_id=None)
    direccion = await direccion_nueva(uow)
    direcciones = await uow.valor("SELECT count(*) FROM direccion")
    movimientos = await uow.valor(
        "SELECT count(*) FROM movimiento_stock WHERE pedido_id=%s", (pedido["id"],),
    )
    guardar = servicio.repo.guardar_edicion

    async def guardar_y_fallar(*args, **kwargs):
        await guardar(*args, **kwargs)
        raise ReglaDeNegocio("Fallo posterior a escritura")

    monkeypatch.setattr(servicio.repo, "guardar_edicion", guardar_y_fallar)
    with pytest.raises(ReglaDeNegocio, match="Fallo posterior"):
        async with uow.conn.transaction():
            await servicio.editar_edicion(
                pedido["id"], items=[{"id": pedido["items"][0]["id"], "cantidad": 2}],
                cambios={"tipo_entrega": "DELIVERY", "direccion_nueva": direccion},
                version_esperada=pedido["version"], total_esperado=Decimal("225"),
            )
    assert await servicio.detalle(pedido["id"]) == pedido
    assert await uow.valor("SELECT count(*) FROM direccion") == direcciones
    assert await uow.valor(
        "SELECT count(*) FROM movimiento_stock WHERE pedido_id=%s", (pedido["id"],),
    ) == movimientos
    assert await uow.valor(
        "SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,),
    ) == 9


@pytest.mark.asyncio
@pytest.mark.parametrize("cambio", ["tarifa", "direccion"])
async def test_cotizacion_bloquea_tarifa_y_desactivacion_hasta_fin_transaccion(cambio):
    primera = await conectar_o_omitir()
    segunda = await conectar_o_omitir()
    unidad = UnidadDeTrabajo(primera)
    otra = UnidadDeTrabajo(segunda)
    cliente = zona = None
    try:
        async with primera.transaction():
            cliente = await unidad.valor(
                "INSERT INTO cliente(telefono_whatsapp) VALUES('5492210000000') RETURNING id"
            )
            zona = await unidad.valor(
                "INSERT INTO zona_cobertura(nombre,costo_envio,poligono,centro_lat,centro_lng) "
                "VALUES(%s,25,'[]',0,0) RETURNING id", (f"Bloqueo {uuid4().hex}",),
            )
            direccion = await unidad.valor(
                "INSERT INTO direccion(cliente_id,calle,numero,localidad,zona_id) "
                "VALUES(%s,'52','32','Prueba',%s) RETURNING id", (cliente, zona),
            )
        assert await RepositorioPedidosSQL(unidad).costo_direccion(direccion) == 25
        with pytest.raises(LockNotAvailable):
            async with segunda.transaction():
                await otra.ejecutar("SET LOCAL lock_timeout='100ms'")
                if cambio == "tarifa":
                    await otra.ejecutar(
                        "UPDATE zona_cobertura SET costo_envio=50 WHERE id=%s", (zona,),
                    )
                else:
                    await otra.ejecutar(
                        "UPDATE direccion SET activa=false WHERE id=%s", (direccion,),
                    )
    finally:
        await primera.rollback()
        await segunda.rollback()
        if cliente is not None:
            await unidad.ejecutar("DELETE FROM cliente WHERE id=%s", (cliente,))
        if zona is not None:
            await unidad.ejecutar("DELETE FROM zona_cobertura WHERE id=%s", (zona,))
        await primera.commit()
        await primera.close()
        await segunda.close()

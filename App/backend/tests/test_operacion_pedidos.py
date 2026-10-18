"""Regresiones de la autoridad operativa de pedidos sobre PostgreSQL local."""

import asyncio
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from app.core.config import settings
from app.core.db import UnidadDeTrabajo
from app.errores import ReglaDeNegocio
from app.modules.pedidos.application.servicio_pedidos import ItemNuevoPedido
from app.modules.pedidos.domain.entidades import EstadoPedido as E
from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos
from tests.test_stock_consumo_bd import crear_pedido, escenario

pytest_plugins = ("tests.test_stock_consumo_bd",)


@pytest.mark.asyncio
async def test_cancelar_confirmado_devuelve_reserva_sin_duplicar(uow):
    cliente, producto, (ingrediente,) = await escenario(uow, saldo=Decimal("10"))
    pedido, _ = await crear_pedido(uow, cliente, producto)
    servicio = obtener_servicio_pedidos(uow)
    await servicio.cambiar_estado(pedido, E.CONFIRMADO, usuario_id=None)
    await servicio.cambiar_estado(pedido, E.CANCELADO, usuario_id=None)
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,)) == 10
    )


@pytest.mark.asyncio
async def test_preparar_directo_registra_fecha_confirmacion(uow):
    cliente, producto, _ = await escenario(uow)
    pedido, _ = await crear_pedido(uow, cliente, producto)
    await obtener_servicio_pedidos(uow).cambiar_estado(pedido, E.EN_PREPARACION, usuario_id=None)
    assert await uow.valor("SELECT confirmado_en FROM pedido WHERE id=%s", (pedido,)) is not None


@pytest.mark.asyncio
async def test_delivery_no_sale_sin_envio_asignado_y_salida_real(uow):
    cliente, producto, _ = await escenario(uow)
    pedido, _ = await crear_pedido(uow, cliente, producto)
    await uow.ejecutar("UPDATE pedido SET estado='LISTO' WHERE id=%s", (pedido,))
    with pytest.raises(ReglaDeNegocio):
        await obtener_servicio_pedidos(uow).cambiar_estado(pedido, E.EN_CAMINO, usuario_id=None)


@pytest.mark.asyncio
async def test_activos_no_desaparecen_tras_200_cerrados(uow):
    cliente, producto, _ = await escenario(uow)
    pedido, _ = await crear_pedido(uow, cliente, producto)
    await uow.ejecutar(
        "INSERT INTO pedido(cliente_id,tipo_entrega,estado) "
        "SELECT %s,'RETIRO','ENTREGADO' FROM generate_series(1,201)",
        (cliente,),
    )
    filas = await obtener_servicio_pedidos(uow).listar(cliente_id=cliente)
    assert pedido in {fila["id"] for fila in filas}
    activos = await obtener_servicio_pedidos(uow).listar(cliente_id=cliente, activos=True)
    assert [fila["id"] for fila in activos] == [pedido]
    assert await obtener_servicio_pedidos(uow).listar(cliente_id=cliente, q="inexistente") == []


@pytest.mark.asyncio
async def test_retiro_listo_entrega_y_corrige_click_sin_duplicar_stock(uow):
    cliente, producto, (ingrediente,) = await escenario(uow, saldo=Decimal("10"))
    pedido, _ = await crear_pedido(uow, cliente, producto)
    servicio = obtener_servicio_pedidos(uow)
    await servicio.cambiar_estado(pedido, E.EN_PREPARACION, usuario_id=None)
    await servicio.cambiar_estado(pedido, E.LISTO, usuario_id=None)
    await servicio.cambiar_estado(pedido, E.ENTREGADO, usuario_id=None)
    recuperado = await servicio.cambiar_estado(
        pedido,
        E.LISTO,
        usuario_id=None,
        motivo="Click equivocado",
        version_esperada=4,
        rol="ADMINISTRADOR",
        correccion=True,
        tratamiento_stock="CONSERVAR",
    )
    assert recuperado["id"] == pedido
    assert recuperado["historial"][-1]["observacion"] == "Click equivocado"
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,)) == 9
    )


@pytest.mark.asyncio
async def test_edicion_operativa_version_motivo_y_canon_pago_preserva_ledger(uow):
    cliente, producto, _ = await escenario(uow)
    pedido, _ = await crear_pedido(uow, cliente, producto)
    servicio = obtener_servicio_pedidos(uow)
    resultado = await servicio.editar_operacion(
        pedido,
        cambios={"observaciones": "Sin timbre", "metodo_pago_acordado": "TRANSFERENCIA"},
        usuario_id=None,
        motivo="Cliente solicita",
        version_esperada=1,
    )
    assert resultado["version"] == 2
    assert resultado["metodo_pago_acordado"] == "TRANSFERENCIA"
    assert resultado["historial"][-1]["cambios"]["observaciones"]["nuevo"] == "Sin timbre"
    with pytest.raises(ReglaDeNegocio):
        await servicio.editar_operacion(
            pedido,
            cambios={"observaciones": "viejo"},
            usuario_id=None,
            motivo="Respuesta atrasada",
            version_esperada=1,
        )


@pytest.mark.asyncio
async def test_transferencia_canonica_sin_cobro_no_prepara_aunque_borrador_diga_aprobado(uow):
    cliente, producto, _ = await escenario(uow)
    pedido, _ = await crear_pedido(uow, cliente, producto)
    await uow.ejecutar(
        "UPDATE pedido SET metodo_pago_acordado='TRANSFERENCIA',total=100 " "WHERE id=%s", (pedido,)
    )
    with pytest.raises(ReglaDeNegocio):
        await obtener_servicio_pedidos(uow).cambiar_estado(
            pedido, E.EN_PREPARACION, usuario_id=None
        )


@pytest.mark.asyncio
async def test_recuperar_cancelado_reconsume_explicito_y_empleado_no_puede(uow):
    cliente, producto, (ingrediente,) = await escenario(uow, saldo=Decimal("10"))
    pedido, _ = await crear_pedido(uow, cliente, producto)
    servicio = obtener_servicio_pedidos(uow)
    await servicio.cambiar_estado(pedido, E.CONFIRMADO, usuario_id=None)
    await servicio.cambiar_estado(pedido, E.CANCELADO, usuario_id=None)
    with pytest.raises(ReglaDeNegocio):
        await servicio.cambiar_estado(
            pedido,
            E.EN_PREPARACION,
            usuario_id=None,
            correccion=True,
            motivo="Recuperar",
            version_esperada=3,
            rol="EMPLEADO",
            tratamiento_stock="RECONSUMIR",
        )
    recuperado = await servicio.cambiar_estado(
        pedido,
        E.EN_PREPARACION,
        usuario_id=None,
        correccion=True,
        motivo="Recuperar",
        version_esperada=3,
        rol="DUENIO",
        tratamiento_stock="RECONSUMIR",
    )
    assert recuperado["version"] == 4
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,)) == 9
    )


@pytest.mark.asyncio
async def test_cancelar_cocinado_declara_merma_y_reapertura_no_reutiliza_insumos(uow):
    cliente, producto, (ingrediente,) = await escenario(uow, saldo=Decimal("10"))
    pedido, _ = await crear_pedido(uow, cliente, producto)
    servicio = obtener_servicio_pedidos(uow)
    await servicio.cambiar_estado(pedido, E.EN_PREPARACION, usuario_id=None)
    with pytest.raises(ReglaDeNegocio, match="MERMA"):
        await servicio.cambiar_estado(
            pedido,
            E.CANCELADO,
            usuario_id=None,
            correccion=True,
            rol="EMPLEADO",
            motivo="Quemado",
            version_esperada=2,
        )
    cancelado = await servicio.cambiar_estado(
        pedido,
        E.CANCELADO,
        usuario_id=None,
        correccion=True,
        rol="EMPLEADO",
        motivo="Quemado",
        version_esperada=2,
        tratamiento_stock="MERMA",
    )
    assert cancelado["historial"][-1]["tratamiento_stock"] == "MERMA"
    await servicio.cambiar_estado(
        pedido,
        E.EN_PREPARACION,
        usuario_id=None,
        correccion=True,
        rol="DUENIO",
        motivo="Volver a cocinar",
        version_esperada=3,
        tratamiento_stock="RECONSUMIR",
    )
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,)) == 8
    )


@pytest.mark.asyncio
async def test_listo_repetido_legitimo_notifica_amigable_y_reintento_no_duplica(uow):
    cliente, producto, _ = await escenario(uow, saldo=Decimal("10"))
    pedido, _ = await crear_pedido(uow, cliente, producto)
    await uow.ejecutar(
        "INSERT INTO whatsapp_borrador(referencia_hash,cliente_id,telefono,items,"
        "pedido_id) VALUES(%s,%s,'5492215550000','[]',%s)",
        (uuid4().hex, cliente, pedido),
    )
    servicio = obtener_servicio_pedidos(uow)
    await servicio.cambiar_estado(pedido, E.EN_PREPARACION, usuario_id=None)
    await servicio.cambiar_estado(pedido, E.LISTO, usuario_id=None, version_esperada=2)
    await servicio.cambiar_estado(
        pedido,
        E.EN_PREPARACION,
        usuario_id=None,
        correccion=True,
        motivo="Falta coccion",
        version_esperada=3,
        rol="EMPLEADO",
    )
    await servicio.cambiar_estado(pedido, E.LISTO, usuario_id=None, version_esperada=4)
    with pytest.raises(ReglaDeNegocio):
        await servicio.cambiar_estado(pedido, E.LISTO, usuario_id=None, version_esperada=4)
    eventos = await uow.todos(
        "SELECT clave,texto FROM whatsapp_salida WHERE clave LIKE %s", (f"estado:{pedido}:v%",)
    )
    assert len(eventos) == 4
    assert all("🍔" in e["texto"] for e in eventos)
    assert sum("listo para retirar" in e["texto"] for e in eventos) == 2


@pytest.mark.asyncio
async def test_cambio_modalidad_recalcula_y_bloquea_reduccion_bajo_neto_acreditado(uow):
    cliente, producto, _ = await escenario(uow)
    pedido, _ = await crear_pedido(uow, cliente, producto)
    zona = await uow.valor(
        "INSERT INTO zona_cobertura(nombre,costo_envio,poligono,"
        "centro_lat,centro_lng) VALUES(%s,25,'[]',0,0) "
        "RETURNING id",
        (f"Zona {uuid4().hex}",),
    )
    direccion = await uow.valor(
        "INSERT INTO direccion(cliente_id,calle,numero,localidad,zona_id) "
        "VALUES(%s,'Calle','1','Localidad',%s) RETURNING id",
        (cliente, zona),
    )
    await uow.ejecutar("UPDATE pedido SET subtotal=100,total=100 WHERE id=%s", (pedido,))
    servicio = obtener_servicio_pedidos(uow)
    delivery = await servicio.editar_operacion(
        pedido,
        cambios={"tipo_entrega": "DELIVERY", "direccion_id": direccion},
        usuario_id=None,
        motivo="Cambiar entrega",
        version_esperada=1,
    )
    assert delivery["total"] == 125
    nuevo = await servicio.crear(
        cliente_id=cliente,
        tipo_entrega="DELIVERY",
        direccion_id=direccion,
        direccion_nueva=None,
        observaciones=None,
        items=[ItemNuevoPedido(producto, 1)],
    )
    assert nuevo["costo_envio"] == 25
    assert nuevo["total"] == 125
    await uow.ejecutar(
        "INSERT INTO pago(pedido_id,metodo_pago,monto,estado) "
        "VALUES(%s,'EFECTIVO',125,'CONCILIADO')",
        (pedido,),
    )
    with pytest.raises(ReglaDeNegocio, match="reintegro"):
        await servicio.editar_operacion(
            pedido,
            cambios={"tipo_entrega": "RETIRO"},
            usuario_id=None,
            motivo="Retirar",
            version_esperada=2,
        )
    actual = await servicio.detalle(pedido)
    assert actual["total"] == 125
    assert len(actual["pagos"]) == 1


@pytest.mark.asyncio
async def test_dos_ediciones_concurrentes_solo_una_version_prevalece(escenario_concurrente):
    _, _, pedido, _ = escenario_concurrente

    async def editar(texto):
        conn = await psycopg.AsyncConnection.connect(
            settings.database_url, row_factory=psycopg.rows.dict_row, connect_timeout=2
        )
        try:
            async with conn.transaction():
                await obtener_servicio_pedidos(UnidadDeTrabajo(conn)).editar_operacion(
                    pedido,
                    cambios={"observaciones": texto},
                    usuario_id=None,
                    motivo="Cliente solicita",
                    version_esperada=1,
                )
            return "aplicado"
        except ReglaDeNegocio:
            return "conflicto"
        finally:
            await conn.close()

    resultados = await asyncio.wait_for(asyncio.gather(editar("Cambio A"), editar("Cambio B")), 10)
    assert sorted(resultados) == ["aplicado", "conflicto"]


@pytest.mark.asyncio
async def test_envio_fallido_mantiene_asignacion_hasta_regreso_real(uow):
    cliente, producto, _ = await escenario(uow)
    pedido, _ = await crear_pedido(uow, cliente, producto)
    repartidor = await uow.valor("SELECT usuario_id FROM repartidor LIMIT 1")
    viaje = await uow.valor(
        "INSERT INTO viaje(repartidor_id,estado,salida_en) "
        "VALUES(%s,'EN_RUTA',now()) RETURNING id",
        (repartidor,),
    )
    await uow.ejecutar(
        "INSERT INTO envio(pedido_id,viaje_id,estado) VALUES(%s,%s,'FALLIDO')", (pedido, viaje)
    )
    await uow.ejecutar("UPDATE pedido SET estado='EN_CAMINO' WHERE id=%s", (pedido,))
    with pytest.raises(ReglaDeNegocio, match="asignacion"):
        await obtener_servicio_pedidos(uow).cambiar_estado(
            pedido,
            E.LISTO,
            usuario_id=None,
            correccion=True,
            motivo="No entregado",
            version_esperada=1,
            rol="EMPLEADO",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("carrera", ["asignacion_edicion", "reintegro_preparacion"])
async def test_indicadores_se_releen_despues_de_esperar_bloqueo(escenario_concurrente, carrera):
    _, _, pedido, _ = escenario_concurrente
    primera = await psycopg.AsyncConnection.connect(
        settings.database_url, row_factory=psycopg.rows.dict_row, connect_timeout=2
    )
    segunda = await psycopg.AsyncConnection.connect(
        settings.database_url, row_factory=psycopg.rows.dict_row, connect_timeout=2
    )
    unidad = UnidadDeTrabajo(primera)
    viaje = repartidor = direccion = None
    intento = None
    try:
        if carrera == "asignacion_edicion":
            cliente = await unidad.valor("SELECT cliente_id FROM pedido WHERE id=%s", (pedido,))
            zona = await unidad.valor("SELECT id FROM zona_cobertura WHERE activa LIMIT 1")
            direccion = await unidad.valor(
                "INSERT INTO direccion(cliente_id,calle,numero,"
                "localidad,zona_id) VALUES(%s,'Prueba','1','Local',%s) RETURNING id",
                (cliente, zona),
            )
            repartidor = await unidad.valor(
                "INSERT INTO usuario(nombre,apellido,username,"
                "password_hash,rol) VALUES('Prueba','Carrera',%s,'x','REPARTIDOR') RETURNING id",
                (f"carrera_{uuid4().hex}",),
            )
            await unidad.ejecutar("INSERT INTO repartidor(usuario_id) VALUES(%s)", (repartidor,))
            await unidad.ejecutar(
                "UPDATE pedido SET estado='LISTO',tipo_entrega='DELIVERY',"
                "direccion_id=%s WHERE id=%s",
                (direccion, pedido),
            )
        else:
            await unidad.ejecutar(
                "UPDATE pedido SET metodo_pago_acordado='TRANSFERENCIA',"
                "subtotal=100,total=100 WHERE id=%s",
                (pedido,),
            )
            await unidad.ejecutar(
                "INSERT INTO pago(pedido_id,metodo_pago,monto,estado) "
                "VALUES(%s,'TRANSFERENCIA',100,'CONCILIADO')",
                (pedido,),
            )
        await primera.commit()
        await unidad.valor("SELECT id FROM pedido WHERE id=%s FOR UPDATE", (pedido,))

        async def operar_esperando():
            servicio = obtener_servicio_pedidos(UnidadDeTrabajo(segunda))
            try:
                if carrera == "asignacion_edicion":
                    await servicio.editar_operacion(
                        pedido,
                        cambios={"tipo_entrega": "RETIRO"},
                        usuario_id=None,
                        motivo="Cambio durante asignacion",
                        version_esperada=1,
                        rol="EMPLEADO",
                    )
                else:
                    await servicio.cambiar_estado(pedido, E.EN_PREPARACION, usuario_id=None)
                return "aceptado"
            except ReglaDeNegocio as exc:
                return exc.mensaje
            finally:
                await segunda.rollback()

        intento = asyncio.create_task(operar_esperando())
        limite = asyncio.get_running_loop().time() + 5
        while True:
            # Confirma que la operacion real esta esperando precisamente nuestro
            # bloqueo, sin depender de sleeps para adivinar el intercalado.
            await unidad.valor("SELECT pg_stat_clear_snapshot()")
            espera = await unidad.valor(
                "SELECT wait_event_type='Lock' AND "
                "%s=ANY(pg_blocking_pids(pid)) FROM pg_stat_activity WHERE pid=%s",
                (primera.info.backend_pid, segunda.info.backend_pid),
            )
            if espera:
                break
            assert not intento.done(), "La segunda operacion no espero el bloqueo"
            assert asyncio.get_running_loop().time() < limite, "No se observo espera por Lock"
            await asyncio.sleep(0.01)
        if carrera == "asignacion_edicion":
            viaje = await unidad.valor(
                "INSERT INTO viaje(repartidor_id) VALUES(%s) " "RETURNING id", (repartidor,)
            )
            await unidad.ejecutar(
                "INSERT INTO envio(pedido_id,viaje_id,estado) " "VALUES(%s,%s,'ASIGNADO')",
                (pedido, viaje),
            )
        else:
            await unidad.ejecutar(
                "INSERT INTO pago(pedido_id,tipo,metodo_pago,monto,estado) "
                "VALUES(%s,'DEVOLUCION','TRANSFERENCIA',100,'CONCILIADO')",
                (pedido,),
            )
        # Igual que asignacion/pagos: el productor confirma su relacion sin
        # actualizar pedido. El lector debe obtener un nuevo snapshot al seguir.
        await primera.commit()
        resultado = await asyncio.wait_for(intento, 5)
        if carrera == "asignacion_edicion":
            assert "desasignacion" in resultado
        else:
            assert "transferencia" in resultado.lower()
        assert resultado != "aceptado"
    finally:
        await primera.rollback()
        if intento is not None and not intento.done():
            intento.cancel()
            await asyncio.gather(intento, return_exceptions=True)
        await segunda.rollback()
        await segunda.close()
        await unidad.ejecutar("DELETE FROM pago WHERE pedido_id=%s", (pedido,))
        await unidad.ejecutar("DELETE FROM envio WHERE pedido_id=%s", (pedido,))
        if viaje is not None:
            await unidad.ejecutar("DELETE FROM viaje WHERE id=%s", (viaje,))
        if repartidor is not None:
            await unidad.ejecutar("DELETE FROM repartidor WHERE usuario_id=%s", (repartidor,))
            await unidad.ejecutar("DELETE FROM usuario WHERE id=%s", (repartidor,))
        if direccion is not None:
            await unidad.ejecutar(
                "UPDATE pedido SET tipo_entrega='RETIRO',direccion_id=NULL " "WHERE id=%s",
                (pedido,),
            )
            await unidad.ejecutar("DELETE FROM direccion WHERE id=%s", (direccion,))
        await primera.commit()
        await primera.close()

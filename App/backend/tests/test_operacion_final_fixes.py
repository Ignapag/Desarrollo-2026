"""Regresiones de los dos hallazgos finales sobre caja y recuperación logística."""

import asyncio
from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.core.db import UnidadDeTrabajo
from app.errores import ReglaDeNegocio
from app.modules.pagos.application.servicio_caja import ServicioCaja
from app.modules.pagos.application.servicio_conciliacion import ServicioConciliacion
from app.modules.pagos.domain.entidades import TurnoCierre
from app.modules.pagos.infrastructure.repositorio_caja_sql import RepositorioCajaSQL
from app.modules.pagos.infrastructure.repositorio_sql import RepositorioPagosSQL
from app.modules.pagos.presentation.dependencias import (
    obtener_servicio_caja,
    obtener_servicio_conciliacion,
)
from tests.soporte_bd import conectar_o_omitir
from tests.test_caja_seguridad import datos_caja as datos_caja_fixture
from tests.test_delivery_seguridad import api as api_fixture
from tests.test_delivery_seguridad import autenticar, crear_viaje_propio
from tests.test_stock_consumo_bd import escenario

datos_caja = datos_caja_fixture
api = api_fixture


async def historico(uow, *, total=100):
    cliente = await uow.valor(
        "INSERT INTO cliente(nombre,telefono_whatsapp) VALUES('Legado',%s) RETURNING id",
        (uuid4().hex,),
    )
    pedido = await uow.valor(
        "INSERT INTO pedido(cliente_id,tipo_entrega,subtotal,total) "
        "VALUES(%s,'RETIRO',100,100) RETURNING id",
        (cliente,),
    )
    cierre = await uow.valor(
        "INSERT INTO cierre_caja(fecha,turno,total_billeteras,total_general,estado) "
        "VALUES('1900-01-01','MEDIODIA',%s,%s,'PENDIENTE_APROBACION') RETURNING id",
        (total, total),
    )
    pago = await uow.valor(
        "INSERT INTO pago(pedido_id,cierre_caja_id,metodo_pago,monto,estado,registrado_en) "
        "VALUES(%s,%s,'TRANSFERENCIA',100,'PENDIENTE','1900-01-01 12:00:00+00') RETURNING id",
        (pedido, cierre),
    )
    return cierre, pago


@pytest.mark.parametrize("recorrido", ["regenerar", "aprobar", "ya_aprobado"])
async def test_pendiente_historico_no_se_pierde_tras_aprobar_y_conciliar(uow, recorrido):
    cierre_id, pago_id = await historico(uow, total=100 if recorrido == "regenerar" else 0)
    actor = await uow.valor("SELECT id FROM usuario WHERE rol='DUENIO' LIMIT 1")
    caja = ServicioCaja(uow, RepositorioCajaSQL(uow))
    if recorrido == "regenerar":
        regenerado = await caja.generar_resumen_cierre(date(1900, 1, 1), TurnoCierre.MEDIODIA)
        assert regenerado.total_general == 0
    if recorrido == "ya_aprobado":
        await uow.ejecutar(
            "UPDATE cierre_caja SET estado='APROBADO',aprobado_por=%s,aprobado_en=now() "
            "WHERE id=%s",
            (actor, cierre_id),
        )
    else:
        await caja.aprobar_y_bloquear_cierre(cierre_id, actor)
    aprobado = await caja.obtener_cierre(cierre_id)
    conciliado = await obtener_servicio_conciliacion(uow).conciliar_pago(
        pago_id,
        conciliar_por=actor,
    )
    siguiente = await caja.generar_resumen_cierre(date(2080, 1, 1), TurnoCierre.MEDIODIA)
    assert siguiente.total_general == 100
    assert conciliado.cierre_caja_id is None
    assert await caja.obtener_cierre(cierre_id) == aprobado
    assert (
        await uow.valor("SELECT cierre_caja_id FROM pago WHERE id=%s", (pago_id,)) == siguiente.id
    )
    auditoria = await uow.todos(
        "SELECT datos FROM auditoria WHERE accion='PAGO_DESVINCULADO_CIERRE' AND entidad_id=%s",
        (str(pago_id),),
    )
    assert len(auditoria) == 1
    assert auditoria[0]["datos"]["cierre_anterior_id"] == cierre_id


async def test_aprobado_que_contabilizo_pendientes_exige_revision_contable(uow):
    cierre_id, pago_id = await historico(uow)
    actor = await uow.valor("SELECT id FROM usuario WHERE rol='DUENIO' LIMIT 1")
    await uow.ejecutar(
        "UPDATE cierre_caja SET estado='APROBADO',aprobado_por=%s,aprobado_en=now() " "WHERE id=%s",
        (actor, cierre_id),
    )
    caja = ServicioCaja(uow, RepositorioCajaSQL(uow))
    aprobado = await caja.obtener_cierre(cierre_id)
    pago = await RepositorioPagosSQL(uow).obtener_pago_por_id(pago_id)
    with pytest.raises(ReglaDeNegocio, match="revisión contable"):
        await obtener_servicio_conciliacion(uow).conciliar_pago(pago_id, conciliar_por=actor)
    assert await caja.obtener_cierre(cierre_id) == aprobado
    assert await RepositorioPagosSQL(uow).obtener_pago_por_id(pago_id) == pago
    assert not await uow.valor(
        "SELECT count(*) FROM auditoria WHERE entidad='pago' AND entidad_id=%s",
        (str(pago_id),),
    )


@pytest.mark.parametrize("primera", ["aprobacion", "conciliacion"])
async def test_carrera_aprobacion_conciliacion_libera_pendiente_sin_cambiar_corte(
    datos_caja,
    monkeypatch,
    primera,
):
    _, pago_id, actor, fecha = datos_caja
    a, b = await conectar_o_omitir(), await conectar_o_omitir()
    ua, ub = UnidadDeTrabajo(a), UnidadDeTrabajo(b)
    pausa, continuar = asyncio.Event(), asyncio.Event()
    tareas = []
    try:
        cierre_id = await ua.valor(
            "INSERT INTO cierre_caja(fecha,turno,estado) "
            "VALUES(%s,'MEDIODIA','PENDIENTE_APROBACION') RETURNING id",
            (fecha,),
        )
        await ua.ejecutar("UPDATE pago SET cierre_caja_id=%s WHERE id=%s", (cierre_id, pago_id))
        await a.commit()
        repo_caja = RepositorioCajaSQL(ua if primera == "aprobacion" else ub)
        repo_pago = RepositorioPagosSQL(ua if primera == "conciliacion" else ub)
        objeto, metodo = (
            (repo_caja, "aprobar_cierre")
            if primera == "aprobacion"
            else (repo_pago, "conciliar_pago")
        )
        original = getattr(objeto, metodo)

        async def detener(*args, **kwargs):
            pausa.set()
            await continuar.wait()
            return await original(*args, **kwargs)

        monkeypatch.setattr(objeto, metodo, detener)

        async def operar(tipo, conn):
            try:
                if tipo == "aprobacion":
                    resultado = await ServicioCaja(
                        repo_caja.uow, repo_caja
                    ).aprobar_y_bloquear_cierre(
                        cierre_id,
                        actor,
                    )
                else:
                    resultado = await ServicioConciliacion(
                        repo_pago.uow,
                        repo_pago,
                        obtener_servicio_caja(repo_pago.uow),
                    ).conciliar_pago(pago_id, conciliar_por=actor)
                await conn.commit()
                return resultado
            except BaseException:
                await conn.rollback()
                raise

        pid_b = await ub.valor("SELECT pg_backend_pid()")
        tareas.append(asyncio.create_task(operar(primera, a)))
        await asyncio.wait_for(pausa.wait(), 10)
        otra = "conciliacion" if primera == "aprobacion" else "aprobacion"
        tareas.append(asyncio.create_task(operar(otra, b)))
        bloqueada = False
        for _ in range(300):
            bloqueada = bool(await ua.valor("SELECT cardinality(pg_blocking_pids(%s))", (pid_b,)))
            if bloqueada or tareas[1].done():
                break
            await asyncio.sleep(0.01)
        assert bloqueada, "Ambos comandos deben compartir la exclusión del turno"
        continuar.set()
        await asyncio.wait_for(asyncio.gather(*tareas), 10)
        caja = ServicioCaja(ua, RepositorioCajaSQL(ua))
        aprobado = await caja.obtener_cierre(cierre_id)
        siguiente = await caja.generar_resumen_cierre(
            fecha + timedelta(days=1), TurnoCierre.MEDIODIA
        )
        assert aprobado.es_aprobado and aprobado.total_general == 0
        assert siguiente.total_general == 100
        assert await caja.obtener_cierre(cierre_id) == aprobado
        await a.commit()
    finally:
        continuar.set()
        if tareas:
            await asyncio.wait_for(asyncio.gather(*tareas, return_exceptions=True), 10)
        await a.close()
        await b.close()


async def test_lotes_con_pedidos_distintos_y_turnos_invertidos_no_interbloquean(monkeypatch):
    a, b = await conectar_o_omitir(), await conectar_o_omitir()
    ua, ub = UnidadDeTrabajo(a), UnidadDeTrabajo(b)
    fecha = date(2180, 1, 1) + timedelta(days=uuid4().int % 10000)
    pausa, continuar = asyncio.Event(), asyncio.Event()
    tareas, pedidos, pagos, cierres = [], [], [], []
    cliente = None
    try:
        cliente = await ua.valor(
            "INSERT INTO cliente(nombre,telefono_whatsapp) VALUES('Lotes',%s) RETURNING id",
            (uuid4().hex,),
        )
        for dia in range(2):
            cierres.append(
                await ua.valor(
                    "INSERT INTO cierre_caja(fecha,turno,estado) "
                    "VALUES(%s,'MEDIODIA','PENDIENTE_APROBACION') RETURNING id",
                    (fecha + timedelta(days=dia),),
                )
            )
        # El primer pago del lote A pertenece al segundo turno. El lote B
        # presenta el orden opuesto y no comparte pedidos que oculten la carrera.
        for indice_cierre in (1, 0, 0, 1):
            pedido = await ua.valor(
                "INSERT INTO pedido(cliente_id,tipo_entrega,subtotal,total) "
                "VALUES(%s,'RETIRO',100,100) RETURNING id",
                (cliente,),
            )
            pedidos.append(pedido)
            pagos.append(
                await ua.valor(
                    "INSERT INTO pago(pedido_id,cierre_caja_id,metodo_pago,monto,estado) "
                    "VALUES(%s,%s,'TRANSFERENCIA',100,'PENDIENTE') RETURNING id",
                    (pedido, cierres[indice_cierre]),
                )
            )
        await a.commit()
        caja_a = RepositorioCajaSQL(ua)
        lock_original = caja_a.bloquear_turno
        adquiridos = []

        async def detener_primer_turno(fecha_caja, turno):
            await lock_original(fecha_caja, turno)
            adquiridos.append(fecha_caja)
            if len(adquiridos) == 1:
                pausa.set()
                await continuar.wait()

        monkeypatch.setattr(caja_a, "bloquear_turno", detener_primer_turno)
        servicio_a = ServicioConciliacion(ua, RepositorioPagosSQL(ua), ServicioCaja(ua, caja_a))

        async def conciliar(servicio, ids, conn):
            try:
                resultado = await servicio.conciliar_lote(ids)
                await conn.commit()
                return resultado
            except BaseException:
                await conn.rollback()
                raise

        pid_b = await ub.valor("SELECT pg_backend_pid()")
        tareas.append(asyncio.create_task(conciliar(servicio_a, pagos[:2], a)))
        await asyncio.wait_for(pausa.wait(), 10)
        tareas.append(
            asyncio.create_task(
                conciliar(
                    obtener_servicio_conciliacion(ub),
                    pagos[2:],
                    b,
                )
            )
        )
        bloqueada = False
        for _ in range(300):
            bloqueada = bool(await ua.valor("SELECT cardinality(pg_blocking_pids(%s))", (pid_b,)))
            if bloqueada or tareas[1].done():
                break
            await asyncio.sleep(0.01)
        assert bloqueada
        assert adquiridos == [fecha], "Ambos lotes deben empezar por el mismo turno"
        continuar.set()
        resultados = await asyncio.wait_for(asyncio.gather(*tareas), 10)
        assert all(r["total_procesados"] == 2 and not r["fallidos"] for r in resultados)
        assert (
            await ua.valor(
                "SELECT count(*) FROM pago WHERE id=ANY(%s) "
                "AND estado='CONCILIADO' AND cierre_caja_id IS NULL",
                (pagos,),
            )
            == 4
        )
        siguiente = await ServicioCaja(ua, RepositorioCajaSQL(ua)).generar_resumen_cierre(
            fecha + timedelta(days=1),
            TurnoCierre.NOCHE,
        )
        cierres.append(siguiente.id)
        assert siguiente.total_general == 400
        await a.commit()
    finally:
        continuar.set()
        if tareas:
            await asyncio.wait_for(asyncio.gather(*tareas, return_exceptions=True), 10)
        await a.rollback()
        await b.rollback()
        if cliente is not None:
            await ua.ejecutar(
                "DELETE FROM auditoria WHERE (entidad='pago' AND entidad_id=ANY(%s)) "
                "OR (entidad='cierre_caja' AND entidad_id=ANY(%s))",
                ([str(p) for p in pagos], [str(c) for c in cierres]),
            )
            await ua.ejecutar("DELETE FROM pago WHERE pedido_id=ANY(%s)", (pedidos,))
            await ua.ejecutar("DELETE FROM pedido WHERE id=ANY(%s)", (pedidos,))
            await ua.ejecutar("DELETE FROM cierre_caja WHERE id=ANY(%s)", (cierres,))
            await ua.ejecutar("DELETE FROM cliente WHERE id=%s", (cliente,))
            await a.commit()
        await a.close()
        await b.close()


@pytest.mark.parametrize("cantidad", [1, 2])
async def test_http_recuperacion_general_exige_comando_logistico(uow, api, cantidad):
    servicio, rider, viaje, pedidos, envios = await crear_viaje_propio(uow, cantidad=cantidad)
    pedido_id = pedidos[0]
    _, producto, (ingrediente,) = await escenario(uow)
    await uow.ejecutar(
        "INSERT INTO pedido_item(pedido_id,producto_id,nombre_producto,cantidad,"
        "precio_unitario,subtotal) VALUES(%s,%s,'Hamburguesa',1,100,100)",
        (pedido_id, producto),
    )
    await servicio.pedidos.stock.procesar(
        pedido_id,
        await servicio.pedidos.repo.items_para_stock(pedido_id),
    )
    await uow.ejecutar(
        "INSERT INTO pago(pedido_id,metodo_pago,monto,estado,conciliado_en) "
        "VALUES(%s,'EFECTIVO',100,'CONCILIADO',now())",
        (pedido_id,),
    )
    await servicio.iniciar_viaje(viaje, usuario_id=rider, rol="REPARTIDOR")
    await servicio.registrar_entrega(envios[0], usuario_id=rider, rol="REPARTIDOR")
    antes = await servicio.pedidos.detalle(pedido_id)
    pagos = await uow.todos("SELECT * FROM pago WHERE pedido_id=%s ORDER BY id", (pedido_id,))
    stock = await uow.todos(
        "SELECT * FROM movimiento_stock WHERE pedido_id=%s ORDER BY id", (pedido_id,)
    )
    assert len(pagos) == len(stock) == 1
    saldo_stock = await uow.valor(
        "SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,)
    )
    autenticar(api, rider, "ADMINISTRADOR")
    respuesta = await api.patch(
        f"/api/pedidos/{pedido_id}/estado",
        json={
            "estado": "LISTO",
            "motivo": "Error de entrega",
            "correccion": True,
            "version_esperada": antes["version"],
            "tratamiento_stock": "CONSERVAR",
        },
    )
    assert respuesta.status_code == 409, respuesta.text
    for extra in ({"origen": "DELIVERY"}, {"regreso_confirmado": True}):
        invalida = await api.patch(
            f"/api/pedidos/{pedido_id}/estado",
            json={
                "estado": "LISTO",
                "motivo": "Error de entrega",
                "correccion": True,
                "version_esperada": antes["version"],
                "tratamiento_stock": "CONSERVAR",
                **extra,
            },
        )
        assert invalida.status_code == 422
    assert await servicio.pedidos.detalle(pedido_id) == antes
    corregido = await api.post(
        f"/api/delivery/envios/{envios[0]}/corregir-entrega",
        json={
            "motivo": "Paquete recibido en local",
            "version_esperada": antes["version"],
            "regreso_confirmado": True,
        },
    )
    assert corregido.status_code == 200, corregido.text
    despues = await servicio.pedidos.detalle(pedido_id)
    assert (despues["id"], despues["numero"]) == (antes["id"], antes["numero"])
    assert despues["estado"] == "LISTO" and despues["version"] == antes["version"] + 1
    assert despues["historial"][:-1] == antes["historial"]
    assert despues["historial"][-1]["origen"] == "DELIVERY"
    assert despues["historial"][-1]["tratamiento_stock"] == "CONSERVAR"
    assert (
        await uow.todos("SELECT * FROM pago WHERE pedido_id=%s ORDER BY id", (pedido_id,)) == pagos
    )
    assert (
        await uow.todos(
            "SELECT * FROM movimiento_stock WHERE pedido_id=%s ORDER BY id", (pedido_id,)
        )
        == stock
    )
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,))
        == saldo_stock
    )
    assert despues["neto_cobrado"] == antes["neto_cobrado"] == 100
    assert despues["items"] == antes["items"]
    assert pedido_id in {p.pedido_id for p in await servicio.repo.pedidos_para_despachar()}
    assert await uow.valor("SELECT viaje_id FROM envio WHERE id=%s", (envios[0],)) is None
    if cantidad == 2:
        assert await uow.valor("SELECT estado FROM envio WHERE id=%s", (envios[1],)) == "EN_CAMINO"
        assert await uow.valor("SELECT viaje_id FROM envio WHERE id=%s", (envios[1],)) == viaje


async def test_recuperacion_delivery_finalizado_con_reconsumo_sigue_disponible(uow, api):
    servicio, rider, viaje, pedidos, envios = await crear_viaje_propio(uow)
    pedido_id = pedidos[0]
    _, producto, (ingrediente,) = await escenario(uow)
    await uow.ejecutar(
        "INSERT INTO pedido_item(pedido_id,producto_id,nombre_producto,cantidad,"
        "precio_unitario,subtotal) VALUES(%s,%s,'Hamburguesa',1,100,100)",
        (pedido_id, producto),
    )
    await servicio.pedidos.stock.procesar(
        pedido_id,
        await servicio.pedidos.repo.items_para_stock(pedido_id),
    )
    await servicio.iniciar_viaje(viaje, usuario_id=rider, rol="REPARTIDOR")
    await servicio.registrar_entrega(envios[0], usuario_id=rider, rol="REPARTIDOR")
    antes = await servicio.pedidos.detalle(pedido_id)
    autenticar(api, rider, "ADMINISTRADOR")
    respuesta = await api.patch(
        f"/api/pedidos/{pedido_id}/estado",
        json={
            "estado": "EN_PREPARACION",
            "motivo": "Nueva preparación autorizada",
            "correccion": True,
            "version_esperada": antes["version"],
            "tratamiento_stock": "RECONSUMIR",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["id"] == pedido_id
    assert respuesta.json()["numero"] == antes["numero"]
    assert respuesta.json()["estado"] == "EN_PREPARACION"
    assert respuesta.json()["historial"][-1]["tratamiento_stock"] == "RECONSUMIR"
    assert (
        await uow.valor(
            "SELECT count(*) FROM movimiento_stock WHERE pedido_id=%s",
            (pedido_id,),
        )
        == 2
    )
    assert (
        await uow.valor(
            "SELECT cantidad_actual FROM ingrediente WHERE id=%s",
            (ingrediente,),
        )
        == 0
    )

"""Regresiones financieras con PostgreSQL local, sin proveedor externo."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from app.core.db import UnidadDeTrabajo
from app.core.dependencias import obtener_uow
from app.errores import DatosInvalidos, ReglaDeNegocio
from app.modules.pagos.application.servicio_conciliacion import ServicioConciliacion
from app.modules.pagos.application.servicio_pagos import ServicioPagos
from app.modules.pagos.domain.entidades import calcular_estado_financiero
from app.modules.pagos.infrastructure.cliente_billetera import ClienteMercadoPago
from app.modules.pagos.infrastructure.repositorio_caja_sql import RepositorioCajaSQL
from app.modules.pagos.infrastructure.repositorio_sql import RepositorioPagosSQL
from app.modules.pagos.presentation.dependencias import (
    obtener_servicio_caja,
    obtener_servicio_conciliacion,
)
from tests.soporte_bd import conectar_o_omitir
from tests.test_pagos_privacidad import aplicacion, sesion


@pytest_asyncio.fixture
async def pedido(uow):
    cliente_id = await uow.valor(
        "INSERT INTO cliente (nombre, telefono_whatsapp) VALUES ('Prueba pagos', %s) RETURNING id",
        (uuid4().hex,),
    )
    return await uow.valor(
        "INSERT INTO pedido (cliente_id, tipo_entrega, canal, estado, subtotal, total) "
        "VALUES (%s, 'RETIRO', 'MOSTRADOR', 'PENDIENTE', 100, 100) RETURNING id",
        (cliente_id,),
    )


async def insertar_pago(uow, pedido_id, estado, monto=100):
    return await uow.valor(
        "INSERT INTO pago (pedido_id,tipo,metodo_pago,monto,propina,estado) "
        "VALUES (%s,'COBRO','TRANSFERENCIA',%s,0,%s) RETURNING id",
        (pedido_id, monto, estado),
    )


async def test_pendiente_no_es_dinero_en_saldo_dominio_ni_sql(uow, pedido):
    await insertar_pago(uow, pedido, "PENDIENTE")
    repo = RepositorioPagosSQL(uow)
    assert await repo.total_pagado_por_pedido(pedido) == 0
    estado = calcular_estado_financiero(
        pedido,
        1,
        "PENDIENTE",
        Decimal(100),
        await repo.listar_pagos_por_pedido(pedido),
    )
    assert estado.total_pagado == 0 and estado.saldo_pendiente == 100
    assert not estado.esta_saldado


async def test_pendiente_no_habilita_devolucion(uow, pedido):
    await insertar_pago(uow, pedido, "PENDIENTE")
    servicio = obtener_servicio_conciliacion(uow)
    with pytest.raises(DatosInvalidos, match="neto abonado"):
        await servicio.registrar_devolucion(pedido, Decimal(100), "Reintegro solicitado")


async def test_caja_muestra_pendientes_sin_sumarlos_ni_vincularlos(uow, pedido):
    pago_id = await insertar_pago(uow, pedido, "PENDIENTE")
    repo = RepositorioCajaSQL(uow)
    ahora = datetime.now(UTC)
    totales = await repo.consolidar_totales_turno(ahora - timedelta(minutes=1), ahora)
    assert totales["total_general"] == 0
    assert totales["cantidad_pagos"] == 0
    assert totales["pagos_pendientes_conciliacion"] == 1
    assert await repo.desglose_por_metodo(ahora - timedelta(minutes=1), ahora) == []
    cierre_id = await uow.valor(
        "INSERT INTO cierre_caja (fecha,turno) VALUES ('2026-01-01','MEDIODIA') RETURNING id"
    )
    corte = await repo.capturar_pagos_cierre(cierre_id, ahora)
    assert await repo.vincular_pagos_al_cierre(cierre_id, corte.pago_ids) == 0
    assert await uow.valor("SELECT cierre_caja_id FROM pago WHERE id=%s", (pago_id,)) is None


async def test_cobro_y_conciliacion_no_avanzan_estado_fisico(uow, pedido):
    repo = RepositorioPagosSQL(uow)
    await ServicioPagos(uow, repo).registrar_pago_efectivo(pedido, Decimal(100))
    assert await uow.valor("SELECT estado FROM pedido WHERE id=%s", (pedido,)) == "PENDIENTE"


async def test_conciliar_transferencia_no_avanza_cocina(uow, pedido):
    pago_id = await insertar_pago(uow, pedido, "PENDIENTE")
    await obtener_servicio_conciliacion(uow).conciliar_pago(pago_id)
    assert await uow.valor("SELECT estado FROM pedido WHERE id=%s", (pedido,)) == "PENDIENTE"


async def test_webhook_publico_no_acredita_pago_falso(uow, pedido):
    pago_id = await insertar_pago(uow, pedido, "PENDIENTE")
    await uow.ejecutar("UPDATE pago SET referencia_externa=%s WHERE id=%s", ("sim_falso", pago_id))
    app = aplicacion()
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        respuesta = await client.post("/api/pagos/webhook/mercadopago?id=sim_falso")
    assert respuesta.status_code in (404, 410)
    assert await uow.valor("SELECT estado FROM pago WHERE id=%s", (pago_id,)) == "PENDIENTE"


async def test_adapter_desactivado_no_simula_aprobacion():
    with pytest.raises(ReglaDeNegocio, match="deshabilitad"):
        await ClienteMercadoPago(access_token="").consultar_pago("sim_falso")


async def test_conciliar_no_sobreacredita_pedido(uow, pedido):
    await insertar_pago(uow, pedido, "CONCILIADO", 80)
    pago_id = await insertar_pago(uow, pedido, "PENDIENTE", 30)
    with pytest.raises(ReglaDeNegocio, match="saldo"):
        await obtener_servicio_conciliacion(uow).conciliar_pago(pago_id)


async def test_reintento_devolucion_no_duplica_y_rechaza_clave_reutilizada(uow, pedido):
    await insertar_pago(uow, pedido, "CONCILIADO")
    servicio = obtener_servicio_conciliacion(uow)
    clave = str(uuid4())
    primera = await servicio.registrar_devolucion(
        pedido,
        Decimal(30),
        "Reintegro parcial",
        clave_operacion=clave,
    )
    repetida = await servicio.registrar_devolucion(
        pedido,
        Decimal(30),
        "Reintegro parcial",
        clave_operacion=clave,
    )
    assert primera.id == repetida.id
    assert await servicio.repo.total_pagado_por_pedido(pedido) == 70
    with pytest.raises(ReglaDeNegocio, match="clave"):
        await servicio.registrar_devolucion(
            pedido,
            Decimal(40),
            "Reintegro parcial",
            clave_operacion=clave,
        )


async def test_transferencia_es_pendiente_y_requiere_conciliacion_humana(uow, pedido):
    repo = RepositorioPagosSQL(uow)
    servicio = ServicioPagos(uow, repo)
    clave = str(uuid4())
    pago = await servicio.registrar_transferencia(
        pedido,
        Decimal(100),
        comprobante="Banco #123",
        clave_operacion=clave,
    )
    repetido = await servicio.registrar_transferencia(
        pedido,
        Decimal(100),
        comprobante="Banco #123",
        clave_operacion=clave,
    )
    assert pago.id == repetido.id and pago.estado == "PENDIENTE"
    assert await repo.total_pagado_por_pedido(pedido) == 0
    conciliacion = ServicioConciliacion(uow, repo, obtener_servicio_caja(uow))
    await conciliacion.conciliar_pago(pago.id, comprobante="Banco #123")
    assert await repo.total_pagado_por_pedido(pedido) == 100


async def test_reintento_efectivo_reproduce_vuelto_sin_segundo_cobro(uow, pedido):
    servicio = ServicioPagos(uow, RepositorioPagosSQL(uow))
    clave = str(uuid4())
    original = await servicio.registrar_pago_efectivo(pedido, Decimal(150), clave_operacion=clave)
    repetida = await servicio.registrar_pago_efectivo(pedido, Decimal(150), clave_operacion=clave)
    assert original == repetida
    assert repetida.detalle.vuelto == 50


@pytest_asyncio.fixture
async def pedido_confirmado():
    """Datos confirmados visibles a conexiones independientes; limpieza solo de estos IDs."""
    conn = await conectar_o_omitir()
    uow = UnidadDeTrabajo(conn)
    cliente_id = await uow.valor(
        "INSERT INTO cliente (nombre,telefono_whatsapp) VALUES ('Carrera pagos',%s) RETURNING id",
        (uuid4().hex,),
    )
    pedido_id = await uow.valor(
        "INSERT INTO pedido (cliente_id,tipo_entrega,subtotal,total) "
        "VALUES (%s,'RETIRO',100,100) RETURNING id",
        (cliente_id,),
    )
    await conn.commit()
    try:
        yield pedido_id
    finally:
        await conn.rollback()
        await uow.ejecutar(
            "DELETE FROM auditoria WHERE entidad='pago' AND entidad_id IN "
            "(SELECT id::text FROM pago WHERE pedido_id=%s)",
            (pedido_id,),
        )
        await uow.ejecutar("DELETE FROM pago WHERE pedido_id=%s", (pedido_id,))
        await uow.ejecutar("DELETE FROM pedido WHERE id=%s", (pedido_id,))
        await uow.ejecutar("DELETE FROM cliente WHERE id=%s", (cliente_id,))
        await conn.commit()
        await conn.close()


async def ejecutar_conexion(accion):
    conn = await conectar_o_omitir()
    try:
        resultado = await accion(UnidadDeTrabajo(conn))
        await conn.commit()
        return resultado
    except (DatosInvalidos, ReglaDeNegocio) as exc:
        await conn.rollback()
        return exc
    finally:
        await conn.close()


@pytest.mark.parametrize("operacion", ["cobro", "devolucion", "conciliacion"])
async def test_dos_operaciones_reales_concurrentes_no_superan_fondos(pedido_confirmado, operacion):
    pedido_id = pedido_confirmado
    if operacion == "devolucion":
        await ejecutar_conexion(lambda uow: insertar_pago(uow, pedido_id, "CONCILIADO"))
    if operacion == "conciliacion":
        pagos = [
            await ejecutar_conexion(
                lambda uow: insertar_pago(uow, pedido_id, "PENDIENTE", 80),
            )
            for _ in range(2)
        ]

    inicio = asyncio.Event()

    async def operacion_concurrente(indice):
        await inicio.wait()

        async def ejecutar(uow):
            repo = RepositorioPagosSQL(uow)
            if operacion == "cobro":
                return await ServicioPagos(uow, repo).registrar_pago_efectivo(
                    pedido_id,
                    Decimal(80),
                    monto_a_pagar=Decimal(80),
                    clave_operacion=str(uuid4()),
                )
            conciliacion = ServicioConciliacion(uow, repo, obtener_servicio_caja(uow))
            if operacion == "devolucion":
                return await conciliacion.registrar_devolucion(
                    pedido_id,
                    Decimal(80),
                    "Reintegro simultáneo",
                    clave_operacion=str(uuid4()),
                )
            return await conciliacion.conciliar_pago(pagos[indice])

        return await ejecutar_conexion(ejecutar)

    tareas = [asyncio.create_task(operacion_concurrente(i)) for i in range(2)]
    inicio.set()
    resultados = await asyncio.wait_for(asyncio.gather(*tareas), timeout=15)
    assert sum(isinstance(r, DatosInvalidos | ReglaDeNegocio) for r in resultados) == 1
    neto = await ejecutar_conexion(
        lambda uow: RepositorioPagosSQL(uow).total_pagado_por_pedido(pedido_id),
    )
    assert neto == (20 if operacion == "devolucion" else 80)


async def test_doble_click_concurrente_parcial_usa_la_misma_operacion(pedido_confirmado):
    clave = str(uuid4())

    async def ejecutar(uow):
        return await ServicioPagos(uow, RepositorioPagosSQL(uow)).registrar_pago_efectivo(
            pedido_confirmado,
            Decimal(35),
            monto_a_pagar=Decimal(30),
            clave_operacion=clave,
        )

    a, b = await asyncio.wait_for(
        asyncio.gather(
            ejecutar_conexion(ejecutar),
            ejecutar_conexion(ejecutar),
        ),
        timeout=15,
    )
    assert a.pago.id == b.pago.id
    assert a.detalle == b.detalle
    assert (
        await ejecutar_conexion(
            lambda uow: RepositorioPagosSQL(uow).total_pagado_por_pedido(pedido_confirmado),
        )
        == 30
    )


@pytest.mark.parametrize(
    "operacion", ["efectivo", "transferencia", "devolucion", "conciliar", "anular"]
)
async def test_http_actor_financiero_es_la_sesion_aunque_body_indique_otro(uow, pedido, operacion):
    actor = await uow.valor("SELECT id FROM usuario WHERE rol='EMPLEADO' LIMIT 1")
    otro = await uow.valor("SELECT id FROM usuario WHERE rol='DUENIO' LIMIT 1")
    clave = str(uuid4())
    cuerpo = {"pedido_id": pedido, "clave_operacion": clave, "registrado_por": otro}
    ruta = "/" + operacion
    if operacion == "efectivo":
        cuerpo["monto_recibido"] = "100"
    elif operacion == "transferencia":
        cuerpo.pop("registrado_por")
        cuerpo.update(monto="100", comprobante="Recibo banco")
    elif operacion == "devolucion":
        await insertar_pago(uow, pedido, "CONCILIADO")
        cuerpo.update(monto="30", motivo="Reintegro verificado")
    else:
        pago_id = await insertar_pago(uow, pedido, "PENDIENTE")
        ruta = f"/{pago_id}/{operacion}"
        cuerpo = (
            {"conciliar_por": otro, "comprobante": "Recibo banco"}
            if operacion == "conciliar"
            else {"anulado_por": otro, "motivo": "Transferencia no recibida"}
        )
    app = aplicacion()
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url="http://test",
        cookies=sesion(actor, "EMPLEADO"),
    ) as cliente:
        respuesta = await cliente.post("/api/pagos" + ruta, json=cuerpo)
    assert respuesta.status_code in (200, 201), respuesta.text
    pago = respuesta.json().get("pago", respuesta.json())
    responsable = await uow.valor(
        "SELECT usuario_id FROM auditoria WHERE entidad='pago' AND entidad_id=%s "
        "ORDER BY id DESC LIMIT 1",
        (str(pago["id"]),),
    )
    assert responsable == actor
    if operacion in ("efectivo", "transferencia", "devolucion"):
        assert pago["registrado_por"] == actor


@pytest.mark.parametrize(
    "cambio",
    [
        {"monto_a_pagar": Decimal(40)},
        {"registrado_por": 2},
        {"pedido_id": 999999},
    ],
)
async def test_clave_efectivo_no_puede_reusarse_con_otro_payload(uow, pedido, cambio):
    servicio = ServicioPagos(uow, RepositorioPagosSQL(uow))
    solicitud = dict(
        pedido_id=pedido,
        monto_recibido=Decimal(50),
        monto_a_pagar=Decimal(30),
        clave_operacion=str(uuid4()),
    )
    await servicio.registrar_pago_efectivo(**solicitud)
    with pytest.raises(ReglaDeNegocio, match="clave"):
        await servicio.registrar_pago_efectivo(**(solicitud | cambio))


@pytest.mark.parametrize("monto", ["1.001", "1000000000000", "NaN", "Infinity"])
async def test_http_efectivo_no_redondea_importes_silenciosamente(uow, pedido, monto):
    actor = await uow.valor("SELECT id FROM usuario WHERE rol='EMPLEADO' LIMIT 1")
    app = aplicacion()
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url="http://test",
        cookies=sesion(actor, "EMPLEADO"),
    ) as cliente:
        respuesta = await cliente.post(
            "/api/pagos/efectivo",
            json={
                "pedido_id": pedido,
                "monto_recibido": monto,
                "clave_operacion": str(uuid4()),
            },
        )
    assert respuesta.status_code == 422
    assert await uow.valor("SELECT count(*) FROM pago WHERE pedido_id=%s", (pedido,)) == 0

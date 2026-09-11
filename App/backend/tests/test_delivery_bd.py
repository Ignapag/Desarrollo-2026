"""Pruebas de asignacion contra la base real (tarea 11 del cronograma).

Recorren el flujo completo: pedidos listos -> agrupacion -> asignacion de
repartidor -> salida del viaje -> entrega -> repartidor liberado.

Cada prueba corre en una transaccion que se revierte, asi que **no ensucian
la base compartida del grupo**.

    pytest tests/test_delivery_bd.py -v
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import psycopg
import pytest
import pytest_asyncio

from app.core.config import settings
from app.core.db import UnidadDeTrabajo
from app.modules.delivery.application.servicio_delivery import ServicioDelivery
from app.modules.delivery.infrastructure.repositorio_sql import RepositorioDeliverySQL

# Coordenadas reales de la zona de reparto
ENSENADA_CENTRO = (-34.860, -57.907)
ENSENADA_CERCA = (-34.8620, -57.9090)   # ~300 m del centro
ENSENADA_LEJOS = (-34.8840, -57.9350)   # ~3,5 km del centro


@pytest_asyncio.fixture
async def uow() -> AsyncIterator[UnidadDeTrabajo]:
    """Unidad de trabajo sobre una transaccion que siempre se revierte."""
    try:
        conn = await psycopg.AsyncConnection.connect(
            settings.database_url, row_factory=psycopg.rows.dict_row, connect_timeout=10
        )
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Base no accesible: {exc.__class__.__name__}")

    await conn.set_autocommit(False)
    try:
        yield UnidadDeTrabajo(conn)
    finally:
        await conn.rollback()
        await conn.close()


@pytest_asyncio.fixture
async def servicio(uow: UnidadDeTrabajo) -> ServicioDelivery:
    return ServicioDelivery(uow, RepositorioDeliverySQL(uow))


# ------------------------------------------------------------------ ayudas

async def crear_cliente(uow: UnidadDeTrabajo, sufijo: str) -> int:
    fila = await uow.uno(
        """
        INSERT INTO usuario (nombre, apellido, username, password_hash, rol)
        VALUES ('Cliente', %s, %s, 'x', 'CLIENTE') RETURNING id
        """,
        (sufijo, f"cli_prueba_{sufijo}"),
    )
    cliente_id = fila["id"]
    await uow.ejecutar(
        "INSERT INTO cliente (usuario_id, telefono_whatsapp) VALUES (%s, '5492210000000')",
        (cliente_id,),
    )
    return cliente_id


async def crear_pedido_listo(
    uow: UnidadDeTrabajo,
    sufijo: str,
    coordenadas: tuple[float, float],
    zona_nombre: str = "Ensenada",
) -> int:
    """Cliente + direccion con coordenadas + pedido en estado LISTO."""
    cliente_id = await crear_cliente(uow, sufijo)
    zona_id = await uow.valor("SELECT id FROM zona_cobertura WHERE nombre = %s", (zona_nombre,))

    lat, lng = coordenadas
    direccion_id = await uow.valor(
        """
        INSERT INTO direccion (cliente_id, calle, numero, lat, lng, zona_id)
        VALUES (%s, 'Calle Falsa', '123', %s, %s, %s) RETURNING id
        """,
        (cliente_id, lat, lng, zona_id),
    )
    return await uow.valor(
        """
        INSERT INTO pedido (cliente_id, tipo_entrega, direccion_id, estado)
        VALUES (%s, 'DELIVERY', %s, 'LISTO') RETURNING id
        """,
        (cliente_id, direccion_id),
    )


async def liberar_repartidores(uow: UnidadDeTrabajo) -> None:
    """Deja a todos los repartidores disponibles y sin viajes abiertos."""
    await uow.ejecutar(
        "UPDATE viaje SET estado = 'FINALIZADO'"
        " WHERE estado IN ('PLANIFICADO','EN_RUTA')"
    )
    await uow.ejecutar("UPDATE repartidor SET estado = 'DISPONIBLE'")


# ------------------------------------------------------- lectura de datos

@pytest.mark.asyncio
async def test_detecta_los_pedidos_listos_con_su_zona(uow, servicio):
    await liberar_repartidores(uow)
    pedido_id = await crear_pedido_listo(uow, "z1", ENSENADA_CENTRO)

    pedidos = await servicio.repo.pedidos_para_despachar()

    encontrado = next((p for p in pedidos if p.pedido_id == pedido_id), None)
    assert encontrado is not None
    assert encontrado.zona_nombre == "Ensenada"
    assert encontrado.tiene_ubicacion


@pytest.mark.asyncio
async def test_ignora_pedidos_que_no_estan_listos(uow, servicio):
    pedido_id = await crear_pedido_listo(uow, "z2", ENSENADA_CENTRO)
    await uow.ejecutar("UPDATE pedido SET estado = 'EN_PREPARACION' WHERE id = %s", (pedido_id,))

    pedidos = await servicio.repo.pedidos_para_despachar()

    assert all(p.pedido_id != pedido_id for p in pedidos)


@pytest.mark.asyncio
async def test_los_repartidores_del_seed_estan_disponibles(uow, servicio):
    await liberar_repartidores(uow)
    repartidores = await servicio.repo.repartidores_disponibles()
    assert len(repartidores) >= 2


# --------------------------------------------------- asignacion completa

@pytest.mark.asyncio
async def test_dos_pedidos_cercanos_salen_en_un_solo_viaje(uow, servicio):
    await liberar_repartidores(uow)
    uno = await crear_pedido_listo(uow, "c1", ENSENADA_CENTRO)
    dos = await crear_pedido_listo(uow, "c2", ENSENADA_CERCA)

    resultado = await servicio.planificar_y_asignar()

    viaje = next(v for v in resultado.viajes if uno in v.pedidos)
    assert sorted(viaje.pedidos) == sorted([uno, dos])


@pytest.mark.asyncio
async def test_dos_pedidos_lejanos_salen_en_viajes_distintos(uow, servicio):
    await liberar_repartidores(uow)
    cerca = await crear_pedido_listo(uow, "l1", ENSENADA_CENTRO)
    lejos = await crear_pedido_listo(uow, "l2", ENSENADA_LEJOS)

    resultado = await servicio.planificar_y_asignar()

    viaje_cerca = next(v for v in resultado.viajes if cerca in v.pedidos)
    viaje_lejos = next(v for v in resultado.viajes if lejos in v.pedidos)
    assert viaje_cerca.viaje_id != viaje_lejos.viaje_id


@pytest.mark.asyncio
async def test_la_asignacion_deja_el_envio_y_el_repartidor_en_estado(uow, servicio):
    await liberar_repartidores(uow)
    pedido_id = await crear_pedido_listo(uow, "e1", ENSENADA_CENTRO)

    resultado = await servicio.planificar_y_asignar()
    viaje = next(v for v in resultado.viajes if pedido_id in v.pedidos)

    estado_envio = await uow.valor(
        "SELECT estado FROM envio WHERE pedido_id = %s", (pedido_id,)
    )
    estado_repartidor = await uow.valor(
        "SELECT estado FROM repartidor WHERE usuario_id = %s", (viaje.repartidor_id,)
    )
    assert estado_envio == "ASIGNADO"
    assert estado_repartidor == "EN_RUTA"


@pytest.mark.asyncio
async def test_un_repartidor_ocupado_no_recibe_otro_viaje(uow, servicio):
    await liberar_repartidores(uow)
    disponibles = len(await servicio.repo.repartidores_disponibles())

    # Un pedido por cada repartidor, todos lejanos entre si
    for i in range(disponibles + 1):
        await crear_pedido_listo(
            uow, f"o{i}", (-34.860 - i * 0.02, -57.907 - i * 0.02)
        )

    resultado = await servicio.planificar_y_asignar()

    repartidores_usados = [v.repartidor_id for v in resultado.viajes]
    assert len(repartidores_usados) == len(set(repartidores_usados))
    assert len(resultado.sin_asignar) >= 1, "deberia sobrar al menos un pedido sin repartidor"


@pytest.mark.asyncio
async def test_previsualizar_no_escribe_nada(uow, servicio):
    await liberar_repartidores(uow)
    await crear_pedido_listo(uow, "p1", ENSENADA_CENTRO)

    viajes_antes = await uow.valor("SELECT count(*) FROM viaje")
    await servicio.previsualizar()
    viajes_despues = await uow.valor("SELECT count(*) FROM viaje")

    assert viajes_antes == viajes_despues


@pytest.mark.asyncio
async def test_no_reasigna_un_pedido_ya_asignado(uow, servicio):
    await liberar_repartidores(uow)
    pedido_id = await crear_pedido_listo(uow, "r1", ENSENADA_CENTRO)
    await servicio.planificar_y_asignar()

    await liberar_repartidores(uow)
    segunda = await servicio.planificar_y_asignar()

    asignados = [p for v in segunda.viajes for p in v.pedidos]
    assert pedido_id not in asignados


# ------------------------------------------------------ ciclo de entrega

@pytest.mark.asyncio
async def test_iniciar_viaje_pone_los_pedidos_en_camino(uow, servicio):
    await liberar_repartidores(uow)
    pedido_id = await crear_pedido_listo(uow, "i1", ENSENADA_CENTRO)
    resultado = await servicio.planificar_y_asignar()
    viaje = next(v for v in resultado.viajes if pedido_id in v.pedidos)

    await servicio.iniciar_viaje(viaje.viaje_id)

    assert await uow.valor("SELECT estado FROM pedido WHERE id = %s", (pedido_id,)) == "EN_CAMINO"
    assert await uow.valor("SELECT estado FROM viaje WHERE id = %s", (viaje.viaje_id,)) == "EN_RUTA"


@pytest.mark.asyncio
async def test_iniciar_dos_veces_el_mismo_viaje_falla(uow, servicio):
    from app.core.errores import ReglaDeNegocio

    await liberar_repartidores(uow)
    await crear_pedido_listo(uow, "i2", ENSENADA_CENTRO)
    resultado = await servicio.planificar_y_asignar()
    viaje_id = resultado.viajes[0].viaje_id

    await servicio.iniciar_viaje(viaje_id)
    with pytest.raises(ReglaDeNegocio):
        await servicio.iniciar_viaje(viaje_id)


@pytest.mark.asyncio
async def test_cada_cambio_de_estado_queda_en_el_historial(uow, servicio):
    """El alcance exige timestamp de cada cambio y quien lo hizo."""
    await liberar_repartidores(uow)
    pedido_id = await crear_pedido_listo(uow, "h1", ENSENADA_CENTRO)
    resultado = await servicio.planificar_y_asignar()
    viaje = next(v for v in resultado.viajes if pedido_id in v.pedidos)

    await servicio.iniciar_viaje(viaje.viaje_id)

    estados = await uow.todos(
        "SELECT estado_nuevo FROM pedido_estado_historial WHERE pedido_id = %s ORDER BY id",
        (pedido_id,),
    )
    assert [e["estado_nuevo"] for e in estados] == ["EN_CAMINO"]


@pytest.mark.asyncio
async def test_entregar_el_ultimo_pedido_cierra_el_viaje_y_libera_al_repartidor(uow, servicio):
    await liberar_repartidores(uow)
    pedido_id = await crear_pedido_listo(uow, "t1", ENSENADA_CENTRO)
    resultado = await servicio.planificar_y_asignar()
    viaje = next(v for v in resultado.viajes if pedido_id in v.pedidos)
    await servicio.iniciar_viaje(viaje.viaje_id)

    envio_id = await uow.valor("SELECT id FROM envio WHERE pedido_id = %s", (pedido_id,))
    entrega = await servicio.registrar_entrega(envio_id)

    assert entrega["viaje_finalizado"] is True
    assert await uow.valor("SELECT estado FROM pedido WHERE id = %s", (pedido_id,)) == "ENTREGADO"
    estado_viaje = await uow.valor(
        "SELECT estado FROM viaje WHERE id = %s", (viaje.viaje_id,)
    )
    assert estado_viaje == "FINALIZADO"
    assert (
        await uow.valor(
            "SELECT estado FROM repartidor WHERE usuario_id = %s", (viaje.repartidor_id,)
        )
        == "DISPONIBLE"
    )


@pytest.mark.asyncio
async def test_con_dos_pedidos_el_viaje_sigue_abierto_tras_la_primera_entrega(uow, servicio):
    await liberar_repartidores(uow)
    uno = await crear_pedido_listo(uow, "d1", ENSENADA_CENTRO)
    await crear_pedido_listo(uow, "d2", ENSENADA_CERCA)
    resultado = await servicio.planificar_y_asignar()
    viaje = next(v for v in resultado.viajes if uno in v.pedidos)
    await servicio.iniciar_viaje(viaje.viaje_id)

    envio_id = await uow.valor("SELECT id FROM envio WHERE pedido_id = %s", (uno,))
    entrega = await servicio.registrar_entrega(envio_id)

    assert entrega["viaje_finalizado"] is False
    assert await uow.valor("SELECT estado FROM viaje WHERE id = %s", (viaje.viaje_id,)) == "EN_RUTA"


@pytest.mark.asyncio
async def test_no_se_puede_entregar_dos_veces(uow, servicio):
    from app.core.errores import ReglaDeNegocio

    await liberar_repartidores(uow)
    pedido_id = await crear_pedido_listo(uow, "dd", ENSENADA_CENTRO)
    resultado = await servicio.planificar_y_asignar()
    await servicio.iniciar_viaje(resultado.viajes[0].viaje_id)

    envio_id = await uow.valor("SELECT id FROM envio WHERE pedido_id = %s", (pedido_id,))
    await servicio.registrar_entrega(envio_id)
    with pytest.raises(ReglaDeNegocio):
        await servicio.registrar_entrega(envio_id)


@pytest.mark.asyncio
async def test_la_asignacion_queda_auditada(uow, servicio):
    """RNF-09: las acciones criticas se registran con usuario y timestamp."""
    await liberar_repartidores(uow)
    await crear_pedido_listo(uow, "a1", ENSENADA_CENTRO)

    antes = await uow.valor("SELECT count(*) FROM auditoria WHERE accion = 'VIAJE_ASIGNADO'")
    await servicio.planificar_y_asignar()
    despues = await uow.valor("SELECT count(*) FROM auditoria WHERE accion = 'VIAJE_ASIGNADO'")

    assert despues > antes


@pytest.mark.asyncio
async def test_el_repartidor_ve_su_viaje_con_el_contacto_del_cliente(uow, servicio):
    await liberar_repartidores(uow)
    pedido_id = await crear_pedido_listo(uow, "v1", ENSENADA_CENTRO)
    resultado = await servicio.planificar_y_asignar()
    viaje = next(v for v in resultado.viajes if pedido_id in v.pedidos)

    detalle = await servicio.viaje_del_repartidor(viaje.repartidor_id)

    assert detalle is not None
    assert detalle["id"] == viaje.viaje_id
    assert detalle["envios"][0]["telefono_cliente"]
    assert detalle["envios"][0]["calle"]


@pytest.mark.asyncio
async def test_la_distancia_de_python_coincide_con_la_de_postgres(uow):
    """Las dos implementaciones de haversine tienen que dar lo mismo."""
    from app.modules.delivery.domain.entidades import distancia_km

    lat1, lng1 = ENSENADA_CENTRO
    lat2, lng2 = ENSENADA_LEJOS

    en_sql = float(
        await uow.valor("SELECT distancia_km(%s, %s, %s, %s)", (lat1, lng1, lat2, lng2))
    )
    en_python = distancia_km(lat1, lng1, lat2, lng2)

    assert abs(en_sql - en_python) < 0.01

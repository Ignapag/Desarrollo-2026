"""Pruebas del modulo de Notificaciones contra la base real.

Igual criterio que test_usuarios_bd.py: transaccion que se revierte, se
saltea si no hay base accesible.

Los eventos BIENVENIDA, PEDIDO_CONFIRMADO, EN_CAMINO y ENTREGADO ya tienen
plantilla activa cargada por App/db/seed.sql; se usan tal cual, como hace
test_delivery_bd.py con los repartidores del seed.

    pytest tests/test_notificaciones_bd.py -v
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import psycopg
import pytest
import pytest_asyncio

from app.core.config import settings
from app.core.db import UnidadDeTrabajo
from app.core.errores import NoEncontrado, ReglaDeNegocio
from app.modules.notificaciones.application.servicio_notificaciones import ServicioNotificaciones
from app.modules.notificaciones.domain.entidades import EventoNotificacion
from app.modules.notificaciones.infrastructure.enviadores import EnviadorSimulado
from app.modules.notificaciones.infrastructure.repositorio_sql import RepositorioNotificacionesSQL


@pytest_asyncio.fixture
async def uow() -> AsyncIterator[UnidadDeTrabajo]:
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
async def servicio(uow: UnidadDeTrabajo) -> ServicioNotificaciones:
    return ServicioNotificaciones(uow, RepositorioNotificacionesSQL(uow), EnviadorSimulado())


class EnviadorQueSiempreFalla:
    async def enviar(self, destinatario: str, cuerpo: str) -> None:
        raise RuntimeError("canal caido (simulado para la prueba)")


# --------------------------------------------------------- encolado (CU_BOT_*)


@pytest.mark.asyncio
async def test_notificar_bienvenida_usa_la_plantilla_del_seed(uow, servicio):
    telefono = "5492210000000"
    notificacion_id = await servicio.notificar(
        EventoNotificacion.BIENVENIDA,
        destinatario=telefono,
        variables={"url_menu": "https://monuburger.example"},
    )

    assert notificacion_id is not None
    fila = await uow.uno("SELECT * FROM notificacion WHERE id = %s", (notificacion_id,))
    assert fila["estado"] == "PENDIENTE"
    assert fila["destinatario"] == telefono
    assert "https://monuburger.example" in fila["cuerpo_renderizado"]


@pytest.mark.asyncio
async def test_notificar_evento_de_pedido_sin_pedido_id_falla(uow, servicio):
    with pytest.raises(ReglaDeNegocio):
        await servicio.notificar(
            EventoNotificacion.PEDIDO_CONFIRMADO, destinatario="5492210000000"
        )


@pytest.mark.asyncio
async def test_notificar_sin_destinatario_no_encola_y_no_falla(uow, servicio):
    resultado = await servicio.notificar(EventoNotificacion.BIENVENIDA, destinatario="")
    assert resultado is None


@pytest.mark.asyncio
async def test_notificar_evento_sin_plantilla_activa_devuelve_none(uow, servicio):
    # ALERTA_STOCK no tiene plantilla cargada en el seed.
    resultado = await servicio.notificar(
        EventoNotificacion.ALERTA_STOCK, destinatario="5492210000000"
    )
    assert resultado is None


# --------------------------------------------------------- envio (procesar)


@pytest.mark.asyncio
async def test_procesar_pendientes_marca_enviada(uow, servicio):
    notificacion_id = await servicio.notificar(
        EventoNotificacion.BIENVENIDA, destinatario="5492210000000", variables={"url_menu": "x"}
    )

    resultado = await servicio.procesar_pendientes()

    assert resultado["enviadas"] >= 1
    fila = await uow.uno("SELECT estado FROM notificacion WHERE id = %s", (notificacion_id,))
    assert fila["estado"] == "ENVIADA"


@pytest.mark.asyncio
async def test_procesar_pendientes_marca_fallida_si_el_enviador_revienta(uow):
    repo = RepositorioNotificacionesSQL(uow)
    servicio_con_fallo = ServicioNotificaciones(uow, repo, EnviadorQueSiempreFalla())
    notificacion_id = await servicio_con_fallo.notificar(
        EventoNotificacion.BIENVENIDA, destinatario="5492210000000", variables={"url_menu": "x"}
    )

    resultado = await servicio_con_fallo.procesar_pendientes()

    assert resultado["fallidas"] >= 1
    fila = await uow.uno("SELECT estado, error FROM notificacion WHERE id = %s", (notificacion_id,))
    assert fila["estado"] == "FALLIDA"
    assert fila["error"]


# --------------------------------------------------------- plantillas (CRUD)


@pytest.mark.asyncio
async def test_registrar_plantilla_y_encontrarla(uow, servicio):
    clave = "CIERRE_CAJA"  # sin plantilla en el seed, libre para la prueba
    nombre_unico = f"Prueba {uuid.uuid4().hex[:8]}"

    creada = await servicio.registrar_plantilla(
        clave=clave, nombre=nombre_unico, cuerpo="Cierre del turno: {{total_neto}}",
        activa=True, ejecutor_id=None,
    )

    assert creada["clave"] == clave
    encontradas = await servicio.buscar_plantillas(nombre=nombre_unico)
    assert len(encontradas) == 1


@pytest.mark.asyncio
async def test_registrar_plantilla_con_evento_invalido_falla(uow, servicio):
    with pytest.raises(ReglaDeNegocio):
        await servicio.registrar_plantilla(
            clave="EVENTO_QUE_NO_EXISTE", nombre="X", cuerpo="Y", activa=True, ejecutor_id=None
        )


@pytest.mark.asyncio
async def test_desactivar_plantilla_dos_veces_falla(uow, servicio):
    creada = await servicio.registrar_plantilla(
        clave="CIERRE_CAJA", nombre=f"Prueba {uuid.uuid4().hex[:8]}", cuerpo="X",
        activa=True, ejecutor_id=None,
    )
    await servicio.desactivar_plantilla(creada["id"], ejecutor_id=None)

    with pytest.raises(ReglaDeNegocio):
        await servicio.desactivar_plantilla(creada["id"], ejecutor_id=None)


@pytest.mark.asyncio
async def test_modificar_plantilla_inexistente_falla(uow, servicio):
    with pytest.raises(NoEncontrado):
        await servicio.modificar_plantilla(
            -1, nombre="X", cuerpo="Y", activa=True, ejecutor_id=None
        )

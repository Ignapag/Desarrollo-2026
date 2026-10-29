"""Pedidos finalizados del día argentino, con límites reales en PostgreSQL local."""

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos
from app.modules.pedidos.presentation.router import router
from app.modules.usuarios.domain.entidades import ClaimsSesion, Rol
from app.modules.usuarios.presentation.dependencias import sesion_vigente
from tests.test_stock_consumo_bd import escenario


@pytest.mark.asyncio
async def test_finalizados_hoy_respeta_cierre_dia_argentino_estado_y_cliente(uow):
    cliente, _, _ = await escenario(uow)
    otro_cliente, _, _ = await escenario(uow)
    inicio = await uow.valor(
        "SELECT date_trunc('day', now() AT TIME ZONE 'America/Argentina/Buenos_Aires') "
        "AT TIME ZONE 'America/Argentina/Buenos_Aires'"
    )

    async def insertar(estado, cierre, *, titular=cliente, entrega_anterior=None):
        return await uow.valor(
            "INSERT INTO pedido(cliente_id,tipo_entrega,estado,creado_en,"
            "entregado_en,cancelado_en) "
            "VALUES (%s,'RETIRO',%s,%s,%s,%s) RETURNING id",
            (titular, estado, inicio - timedelta(days=2),
             cierre if estado == 'ENTREGADO' else entrega_anterior,
             cierre if estado == 'CANCELADO' else None),
        )

    entregado = await insertar('ENTREGADO', inicio)
    cancelado = await insertar('CANCELADO', inicio + timedelta(days=1, microseconds=-1),
                               entrega_anterior=inicio - timedelta(days=1))
    await insertar('ENTREGADO', inicio - timedelta(microseconds=1))
    await insertar('ENTREGADO', inicio + timedelta(days=1))
    await insertar('LISTO', inicio, entrega_anterior=inicio)
    await insertar('ENTREGADO', inicio, titular=otro_cliente)
    servicio = obtener_servicio_pedidos(uow)
    filas = await servicio.listar(cliente_id=cliente, finalizados_hoy=True)
    assert [fila['id'] for fila in filas] == [cancelado, entregado]
    assert await servicio.listar(cliente_id=cliente, finalizados_hoy=True, q='inexistente') == []
    sin_filtro = await servicio.listar(cliente_id=cliente)
    assert len(sin_filtro) == 5


@pytest.mark.parametrize('rol', [Rol.EMPLEADO, Rol.CLIENTE, Rol.REPARTIDOR])
def test_filtro_http_conserva_el_alcance_de_la_sesion(rol):
    recibidos = {}

    class Servicio:
        async def cliente_para_usuario(self, usuario_id):
            assert usuario_id == 7
            return 11

        async def listar(self, **filtros):
            recibidos.update(filtros)
            return []

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[sesion_vigente] = lambda: ClaimsSesion(
        7, rol, 'prueba', frozenset({'pedidos.ver'})
    )
    app.dependency_overrides[obtener_servicio_pedidos] = Servicio
    with TestClient(app) as api:
        respuesta = api.get('/api/pedidos?finalizados_hoy=true')
    assert respuesta.status_code == 200
    assert respuesta.json() == []
    assert recibidos['finalizados_hoy'] is True
    assert recibidos['cliente_id'] == (11 if rol == Rol.CLIENTE else None)
    assert recibidos['repartidor_id'] == (7 if rol == Rol.REPARTIDOR else None)

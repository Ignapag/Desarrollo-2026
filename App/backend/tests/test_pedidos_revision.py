"""La lectura liviana detecta cambios sin hidratar el listado completo."""

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.pedidos.infrastructure.repositorio_sql import RepositorioPedidosSQL
from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos
from app.modules.pedidos.presentation.router import router
from app.modules.usuarios.domain.entidades import ClaimsSesion, Rol
from app.modules.usuarios.presentation.dependencias import sesion_vigente
from tests.test_stock_consumo_bd import crear_pedido, escenario


@pytest.mark.asyncio
async def test_revision_estable_y_sensible_a_estado_y_pago(uow):
    cliente, producto, _ = await escenario(uow)
    pedido, _ = await crear_pedido(uow, cliente, producto)
    repo = RepositorioPedidosSQL(uow)
    inicial = await repo.revision(cliente_id=cliente, activos=True)
    assert inicial == await repo.revision(cliente_id=cliente, activos=True)
    await uow.ejecutar("UPDATE pedido SET observaciones='Sin timbre' WHERE id=%s", (pedido,))
    editado = await repo.revision(cliente_id=cliente, activos=True)
    assert editado != inicial
    await uow.ejecutar(
        "INSERT INTO pago(pedido_id,tipo,metodo_pago,monto,estado) "
        "VALUES(%s,'COBRO','EFECTIVO',%s,'CONCILIADO')",
        (pedido, Decimal('100')),
    )
    pagado = await repo.revision(cliente_id=cliente, activos=True)
    assert pagado != editado
    await uow.ejecutar("UPDATE pago SET estado='ANULADO' WHERE pedido_id=%s", (pedido,))
    assert pagado != await repo.revision(cliente_id=cliente, activos=True)
    vacio = await repo.revision(cliente_id=cliente, q='no existe')
    await uow.ejecutar("UPDATE pedido SET estado='CANCELADO' WHERE id=%s", (pedido,))
    assert vacio == await repo.revision(cliente_id=cliente, activos=True)


@pytest.mark.asyncio
async def test_revision_no_carga_relaciones_y_solo_hace_una_consulta(uow):
    cliente, producto, _ = await escenario(uow)
    await crear_pedido(uow, cliente, producto)

    class Contador:
        consultas = 0

        async def todos(self, sql, parametros):
            self.consultas += 1
            return await uow.todos(sql, parametros)

    contador = Contador()
    repo = RepositorioPedidosSQL(contador)
    assert isinstance(await repo.revision(cliente_id=cliente, activos=True), str)
    assert contador.consultas == 1


@pytest.mark.asyncio
async def test_revision_de_servicio_detecta_asignacion_y_cierre_sin_ver_otros_clientes(uow):
    cliente, producto, _ = await escenario(uow)
    pedido, _ = await crear_pedido(uow, cliente, producto)
    servicio = obtener_servicio_pedidos(uow)
    inicial = await servicio.revision(cliente_id=cliente)
    otro_cliente, otro_producto, _ = await escenario(uow)
    await crear_pedido(uow, otro_cliente, otro_producto)
    assert inicial == await servicio.revision(cliente_id=cliente)
    repartidor = await uow.valor('SELECT usuario_id FROM repartidor LIMIT 1')
    viaje = await uow.valor(
        "INSERT INTO viaje(repartidor_id) VALUES(%s) RETURNING id", (repartidor,),
    )
    await uow.ejecutar(
        "INSERT INTO envio(pedido_id,viaje_id,estado,orden_en_viaje) VALUES(%s,%s,'ASIGNADO',1)",
        (pedido, viaje),
    )
    asignado = await servicio.revision(cliente_id=cliente)
    assert asignado != inicial
    await uow.ejecutar("UPDATE viaje SET estado='EN_RUTA',salida_en=now() WHERE id=%s", (viaje,))
    assert asignado != await servicio.revision(cliente_id=cliente)


@pytest.mark.parametrize('rol', [Rol.EMPLEADO, Rol.CLIENTE, Rol.REPARTIDOR])
def test_revision_http_es_privada_y_conserva_el_alcance_de_cada_rol(rol):
    filtros = {}

    class Servicio:
        async def cliente_para_usuario(self, usuario_id):
            assert usuario_id == 7
            return 11

        async def revision(self, **recibidos):
            filtros.update(recibidos)
            return 'misma-revision'

    sesion = {'permisos': frozenset({'pedidos.ver', 'pagos.ver'})}
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[obtener_servicio_pedidos] = Servicio
    app.dependency_overrides[sesion_vigente] = lambda: ClaimsSesion(
        7, rol, 'prueba', sesion['permisos'],
    )
    with TestClient(app) as api:
        respuesta = api.get('/api/pedidos/revision')
        assert respuesta.status_code == 200
        assert respuesta.headers['cache-control'] == 'private, no-store'
        valor = respuesta.json()['revision']
        assert len(valor) == 64
        assert api.get('/api/pedidos/revision').json()['revision'] == valor
        sesion['permisos'] = frozenset({'pedidos.ver'})
        assert api.get('/api/pedidos/revision').json()['revision'] != valor
    assert filtros['cliente_id'] == (11 if rol == Rol.CLIENTE else None)
    assert filtros['repartidor_id'] == (7 if rol == Rol.REPARTIDOR else None)

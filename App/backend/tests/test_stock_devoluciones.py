"""Devoluciones previas a cocina: cantidades persistidas, guardas e idempotencia."""

from decimal import Decimal

import pytest
import pytest_asyncio

from app.errores import DatosInvalidos, NoEncontrado, ReglaDeNegocio
from app.modules.stock.application.servicio_stock import ServicioStock
from app.modules.stock.domain.entidades import ItemConsumoStock
from app.modules.stock.infrastructure.repositorio_sql import RepositorioStockSQL
from tests.test_stock_consumo_bd import crear_pedido, escenario


class RepositorioDevolucion:
    def __init__(self):
        self.item = {"estado": "CONFIRMADO", "cantidad": 2, "ingrediente_id": 30,
                     "cantidad_requerida": Decimal("0.5"), "aclaraciones": None}
        self.saldo = Decimal("3")
        self.neto = Decimal("1")
        self.movimientos = []
        self.bloqueado = False

    async def bloquear_pedido(self, pedido_id):
        self.bloqueado = True
        return pedido_id == 7

    async def ingrediente_item_para_devolucion(self, pedido_id, item_id, nombre):
        assert self.bloqueado
        return self.item if item_id == 12 and nombre == "tomate" else None

    async def devolucion_existente(self, pedido_id, motivo):
        return any(m["motivo"] == motivo for m in self.movimientos)

    async def consumo_neto_ingrediente(self, pedido_id, ingrediente_id):
        return self.neto

    async def devolver(self, ingrediente_id, cantidad, pedido_id, usuario_id, motivo):
        self.saldo += cantidad
        self.neto -= cantidad
        self.movimientos.append({"ingrediente_id": ingrediente_id, "cantidad": cantidad,
                                 "usuario_id": usuario_id, "motivo": motivo})


@pytest.mark.asyncio
async def test_devuelve_cantidad_de_receta_por_cantidad_persistida_una_sola_vez():
    repo = RepositorioDevolucion()
    servicio = ServicioStock(repo)
    await servicio.devolver_ingrediente_antes_preparacion(7, 12, " Tomate ", usuario_id=5)
    await servicio.devolver_ingrediente_antes_preparacion(7, 12, "tomate", usuario_id=5)
    assert repo.saldo == Decimal("4")
    assert repo.movimientos == [{"ingrediente_id": 30, "cantidad": Decimal("1"),
                                "usuario_id": 5, "motivo": "WHATSAPP_RETIRO:12:30"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("estado", ["EN_PREPARACION", "LISTO", "CANCELADO", "ENTREGADO"])
async def test_no_devuelve_ingrediente_despues_del_inicio_de_preparacion(estado):
    repo = RepositorioDevolucion()
    repo.item["estado"] = estado
    with pytest.raises(ReglaDeNegocio):
        await ServicioStock(repo).devolver_ingrediente_antes_preparacion(7, 12, "tomate")
    assert repo.movimientos == []
    assert repo.saldo == Decimal("3")


@pytest.mark.asyncio
@pytest.mark.parametrize("neto", [Decimal("0"), Decimal("0.5")])
async def test_no_devuelve_mas_que_el_consumo_neto_disponible(neto):
    repo = RepositorioDevolucion()
    repo.neto = neto
    with pytest.raises(ReglaDeNegocio):
        await ServicioStock(repo).devolver_ingrediente_antes_preparacion(7, 12, "tomate")
    assert repo.movimientos == []


@pytest.mark.asyncio
async def test_no_devuelve_ingrediente_ya_omitido_al_consumir():
    repo = RepositorioDevolucion()
    repo.item["aclaraciones"] = "Sin Tomate, Sin Lechuga"
    await ServicioStock(repo).devolver_ingrediente_antes_preparacion(7, 12, "tomate")
    assert repo.movimientos == []


@pytest.mark.asyncio
async def test_valida_pedido_item_y_que_ingrediente_se_puede_retirar():
    repo = RepositorioDevolucion()
    servicio = ServicioStock(repo)
    for pedido_id, item_id, nombre in [(0, 12, "tomate"), (7, True, "tomate"),
                                       (7, 12, "Carne")]:
        with pytest.raises(DatosInvalidos):
            await servicio.devolver_ingrediente_antes_preparacion(pedido_id, item_id, nombre)
    with pytest.raises(NoEncontrado):
        await servicio.devolver_ingrediente_antes_preparacion(8, 12, "tomate")
    with pytest.raises(NoEncontrado):
        await servicio.devolver_ingrediente_antes_preparacion(7, 13, "tomate")
    assert repo.movimientos == []


@pytest_asyncio.fixture
async def devolucion_sql(uow):
    cliente_id, producto_id, (ingrediente_id,) = await escenario(uow, saldo=Decimal("5"))
    # Nombre propio, distinto del seed; el dominio compara sin distinguir mayusculas.
    await uow.ejecutar("UPDATE ingrediente SET nombre = 'tOmAtE', umbral_minimo = 4 "
                       "WHERE id = %s", (ingrediente_id,))
    await uow.ejecutar("UPDATE producto_ingrediente SET cantidad_requerida = 0.5 "
                       "WHERE producto_id = %s", (producto_id,))
    pedido_id, item_id = await crear_pedido(uow, cliente_id, producto_id)
    await uow.ejecutar("UPDATE pedido_item SET cantidad = 4, subtotal = 400 WHERE id = %s",
                       (item_id,))
    repo = RepositorioStockSQL(uow)
    servicio = ServicioStock(repo)
    await servicio.procesar_consumo(pedido_id, [ItemConsumoStock(producto_id, 4)])
    await uow.ejecutar("UPDATE pedido SET estado = 'CONFIRMADO' WHERE id = %s", (pedido_id,))
    usuario_id = await uow.valor("SELECT usuario_id FROM cliente WHERE id=%s", (cliente_id,))
    return servicio, repo, pedido_id, item_id, ingrediente_id, usuario_id


@pytest.mark.asyncio
async def test_sql_devolucion_idempotente_y_alerta_resuelta(uow, devolucion_sql):
    servicio, _, pedido_id, item_id, ingrediente_id, usuario_id = devolucion_sql
    assert await uow.valor("SELECT estado FROM alerta_stock WHERE ingrediente_id = %s",
                           (ingrediente_id,)) == "ACTIVA"
    await servicio.devolver_ingrediente_antes_preparacion(pedido_id, item_id, "tomate", usuario_id)
    await servicio.devolver_ingrediente_antes_preparacion(pedido_id, item_id, "tomate", usuario_id)
    assert await uow.uno("SELECT cantidad_actual, umbral_minimo FROM ingrediente WHERE id = %s",
                          (ingrediente_id,)) == {"cantidad_actual": Decimal("5"),
                                                 "umbral_minimo": Decimal("4")}
    movimientos = await uow.todos(
        "SELECT tipo, cantidad, saldo_resultante, usuario_id FROM movimiento_stock "
        "WHERE pedido_id = %s ORDER BY id", (pedido_id,),
    )
    assert movimientos == [
        {"tipo": "CONSUMO", "cantidad": Decimal("2"), "saldo_resultante": Decimal("3"),
         "usuario_id": None},
        {"tipo": "DEVOLUCION", "cantidad": Decimal("2"), "saldo_resultante": Decimal("5"),
         "usuario_id": usuario_id},
    ]
    assert await uow.valor("SELECT estado FROM alerta_stock WHERE ingrediente_id = %s",
                           (ingrediente_id,)) == "RESUELTA"
    assert await uow.valor("SELECT cantidad_requerida FROM producto_ingrediente "
                           "WHERE ingrediente_id = %s", (ingrediente_id,)) == Decimal("0.5")


@pytest.mark.asyncio
async def test_sql_preparacion_y_consumo_neto_se_revalidan(uow, devolucion_sql):
    servicio, _, pedido_id, item_id, ingrediente_id, _ = devolucion_sql
    await uow.ejecutar("UPDATE pedido SET estado = 'EN_PREPARACION' WHERE id = %s", (pedido_id,))
    with pytest.raises(ReglaDeNegocio):
        await servicio.devolver_ingrediente_antes_preparacion(pedido_id, item_id, "tomate")
    await uow.ejecutar("UPDATE pedido SET estado = 'CONFIRMADO' WHERE id = %s", (pedido_id,))
    # Una devolucion manual previa tambien reduce lo que puede devolver el bot.
    await uow.ejecutar(
        "INSERT INTO movimiento_stock (ingrediente_id,tipo,cantidad,saldo_resultante,pedido_id) "
        "VALUES (%s, 'DEVOLUCION', 1, 4, %s)", (ingrediente_id, pedido_id),
    )
    with pytest.raises(ReglaDeNegocio):
        await servicio.devolver_ingrediente_antes_preparacion(pedido_id, item_id, "tomate")
    assert await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id = %s",
                           (ingrediente_id,)) == Decimal("3")


@pytest.mark.asyncio
async def test_sql_error_posterior_revierte_saldo_movimiento_y_alerta(uow, devolucion_sql):
    servicio, repo, pedido_id, item_id, ingrediente_id, _ = devolucion_sql
    devolver_real = repo.devolver

    async def devolver_y_fallar(*args):
        await devolver_real(*args)
        raise RuntimeError("fallo posterior a devolver")

    repo.devolver = devolver_y_fallar
    with pytest.raises(RuntimeError, match="fallo posterior"):
        async with uow.conn.transaction():
            await servicio.devolver_ingrediente_antes_preparacion(pedido_id, item_id, "tomate")
    assert await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id = %s",
                           (ingrediente_id,)) == Decimal("3")
    assert await uow.valor("SELECT count(*) FROM movimiento_stock WHERE pedido_id = %s "
                           "AND tipo = 'DEVOLUCION'", (pedido_id,)) == 0
    assert await uow.valor("SELECT estado FROM alerta_stock WHERE ingrediente_id = %s",
                           (ingrediente_id,)) == "ACTIVA"

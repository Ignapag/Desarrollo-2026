"""Extras estructurados: cotización, presentación y preservación al editar el chat."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.errores import DatosInvalidos
from app.modules.whatsapp.application import edicion_conversacional
from app.modules.whatsapp.application.edicion_conversacional import resolver_items
from app.modules.whatsapp.application.edicion_multiple import _items_simples
from app.modules.whatsapp.application.servicio_bot import ServicioBot
from app.modules.whatsapp.domain.textos import mensaje_web, resumen_pedido

EXTRA = {"ingrediente_id": 8, "nombre": "Queso cheddar", "unidad_medida": "UNIDAD",
         "cantidad_requerida": "1", "precio": "700", "max_por_item": 3, "cantidad": 2}


def test_mensaje_inicial_suma_recargos_y_muestra_porciones_por_hamburguesa():
    datos = {"items": [{"producto_id": 1, "cantidad": 2, "extras_snapshot": [EXTRA]}]}
    productos = [{"id": 1, "nombre": "Cheese", "precio_base": "10000"}]
    texto = mensaje_web(datos, productos, datetime.now(UTC))
    assert "2 × Cheese — $ 22.800" in texto
    assert "  Extra: 2 × Queso cheddar — $ 1.400 por hamburguesa" in texto.splitlines()
    assert "cada porción" not in texto and "UNIDAD" not in texto


def test_resumen_operativo_muestra_extras_y_total_congelados():
    texto = resumen_pedido({"items": [{"cantidad": 1, "nombre_producto": "Cheese",
                                       "extras": [EXTRA]}],
                            "total": Decimal("11400"), "tipo_entrega": "RETIRO"})
    assert "  Extra: 2 × Queso cheddar — $ 1.400 por hamburguesa" in texto.splitlines()
    assert "cada porción" not in texto
    assert "$ 11.400" in texto


class PedidosMemoria:
    def __init__(self):
        self.repo = self

    async def productos(self, ids):
        return [{"id": 1, "nombre": "Cheese", "precio_base": "10000",
                 "disponible": True, "variantes": []}]

    async def cotizar_extras_item(self, item):
        return {"extras": [{"ingrediente_id": 8, "cantidad": 2}],
                "extras_snapshot": [EXTRA], "costo_opciones": Decimal("1400"),
                "receta_snapshot": []}

    async def validar_disponibilidad_items(self, items):
        pass


class BorradoresMemoria:
    async def crear_borrador(self, referencia_hash, cliente_id, datos):
        self.guardado = datos
        return {"expira_en": datetime.now(UTC)}


async def test_borrador_guarda_snapshot_valorado_por_servidor_sin_aceptarlo_del_cliente():
    repo = BorradoresMemoria()
    bot = ServicioBot(repo, PedidosMemoria())
    respuesta = await bot.crear_borrador(None, {
        "items": [{"producto_id": 1, "cantidad": 2,
                   "extras": [{"ingrediente_id": 8, "cantidad": 2}]}],
        "contacto": {"nombre": "Ana", "apellido": "Pérez", "telefono": "5492215551234"},
    })
    assert repo.guardado["items"][0]["extras_snapshot"] == [EXTRA]
    assert "$ 22.800" in respuesta["mensaje"]


@pytest.mark.parametrize("accion,argumentos", [
    ("cantidad", {"cantidad": 3}),
    ("personalizar", {"aclaraciones": "Sin Tomate"}),
])
async def test_edicion_chat_conserva_extras_en_formato_entrada(accion, argumentos):
    bot = SimpleNamespace(_foto_operacion=lambda pedido: {"version": 1})
    pedido = {"items": [{"id": 1, "producto_id": 1, "cantidad": 1,
                          "aclaraciones": None, "extras": [EXTRA]}]}
    resultado = await resolver_items(bot, {}, {}, pedido,
                                    {"accion": accion, "argumentos": argumentos})
    assert resultado[0][0]["extras"] == [{"ingrediente_id": 8, "cantidad": 2}]


def test_edicion_multiple_conserva_extras_entre_operaciones():
    items = _items_simples([{"id": 1, "producto_id": 1, "cantidad": 1, "extras": [EXTRA]}])
    assert items[0]["extras"] == [{"ingrediente_id": 8, "cantidad": 2}]


async def test_cambio_variante_conserva_extras_para_revalidarlos(monkeypatch):
    async def catalogo(bot):
        return [{"id": 1, "nombre": "Cheese", "variantes": [
            {"nombre": "Simple"}, {"nombre": "Doble"}]}]

    monkeypatch.setattr(edicion_conversacional, "catalogo", catalogo)
    bot = SimpleNamespace(_foto_operacion=lambda pedido: {"version": 1})
    pedido = {"items": [{"id": 1, "producto_id": 1, "cantidad": 1,
                          "variante": "Simple", "aclaraciones": None, "extras": [EXTRA]}]}
    resultado = await resolver_items(bot, {}, {}, pedido, {
        "accion": "cambiar_variante", "argumentos": {"variante": "Doble"}})
    assert resultado[0][0]["variante"] == "Doble"
    assert resultado[0][0]["extras"] == [{"ingrediente_id": 8, "cantidad": 2}]


async def test_borrador_rechaza_snapshot_o_importes_manipulados():
    repo = BorradoresMemoria()
    bot = ServicioBot(repo, PedidosMemoria())
    with pytest.raises(DatosInvalidos):
        await bot.crear_borrador(None, {"items": [{"producto_id": 1, "cantidad": 1,
                                                   "extras_snapshot": [EXTRA]}]})
    assert not hasattr(repo, "guardado")


async def test_falta_stock_conjunto_no_persiste_borrador():
    class SinStock(PedidosMemoria):
        async def validar_disponibilidad_items(self, items):
            raise DatosInvalidos("Stock insuficiente")

    repo = BorradoresMemoria()
    with pytest.raises(DatosInvalidos, match="Stock insuficiente"):
        await ServicioBot(repo, SinStock()).crear_borrador(None, {
            "items": [{"producto_id": 1, "cantidad": 2,
                       "extras": [{"ingrediente_id": 8, "cantidad": 2}]}],
        })
    assert not hasattr(repo, "guardado")


async def test_revision_legacy_no_quita_ingrediente_que_conserva_extra():
    class PedidoConExtra:
        async def pedido(self, pedido_id):
            return {"id": 1, "total": Decimal("11400"), "estado": "CONFIRMADO",
                    "pagado": Decimal("0"), "stock_consumido": False,
                    "tipo_entrega": "RETIRO", "version": 1,
                    "items": [{"id": 1, "producto_id": 1, "cantidad": 1,
                               "nombre_producto": "Cheese", "precio_unitario": Decimal("10000"),
                               "costo_opciones": Decimal("1400"),
                               "aclaraciones": None, "extras": [EXTRA]}]}

        async def ingredientes(self, producto_id):
            return [{"nombre": "Queso cheddar", "es_base": False}]

        async def aplicar_item(self, *args):
            pass

        async def historial(self, *args):
            pass

    bot = ServicioBot(PedidoConExtra(), PedidosMemoria())
    b = {"pedido_id": 1, "version": 1, "metodo_pago": "EFECTIVO"}
    respuesta = await bot._operar(b, "", {
        "accion": "quitar_ingrediente", "argumentos": {"ingrediente": "queso cheddar"},
    }, empleado_id=1)
    assert "extra" in respuesta.lower() and "sin cambios" in respuesta.lower()
    assert b["version"] == 1


async def test_recorrido_extras_hasta_cocina_y_reintentos_sin_doble_consumo(uow):
    from app.modules.pedidos.domain.entidades import EstadoPedido
    from app.modules.whatsapp.presentation.dependencias import construir_servicio
    from tests.test_stock_consumo_bd import escenario
    from tests.test_whatsapp_bd import pedido_borrador

    cliente_id, producto_id, (ingrediente_id,) = await escenario(uow, saldo=Decimal("10"))
    await uow.ejecutar(
        "INSERT INTO producto_opcion(producto_id,ingrediente_id,tipo,costo_adicional,"
        "cantidad_requerida,max_por_item) VALUES (%s,%s,'AGREGADO',700,0.250,3)",
        (producto_id, ingrediente_id),
    )
    servicio = construir_servicio(uow)
    pedidos_antes = await uow.valor("SELECT count(*) FROM pedido")
    borrador = await servicio.crear_borrador(cliente_id, {
        "telefono": "5492215550183", "tipo_entrega": "RETIRO", "metodo_pago": "EFECTIVO",
        "items": [{"producto_id": producto_id, "cantidad": 2,
                   "extras": [{"ingrediente_id": ingrediente_id, "cantidad": 2}]}],
    })
    for mensaje_id in ("extras-inicio", "extras-inicio", "extras-reenvio"):
        await servicio.recibir(mensaje_id, "5492215550183", borrador["mensaje"])
        respuesta = await servicio.procesar(mensaje_id, {"accion": "consulta"})
        assert "2 × Ingrediente consumo" in respuesta
    pedido_id = await pedido_borrador(uow, borrador)
    assert await uow.valor("SELECT count(*) FROM pedido") == pedidos_antes + 1
    item = (await servicio.repo.pedido(pedido_id))["items"][0]
    assert item["extras"][0]["cantidad"] == 2
    assert item["costo_opciones"] == Decimal("1400")
    await servicio.recibir("extras-cantidad", "5492215550183", "cantidad 3 producto 1")
    propuesta = await servicio.procesar("extras-cantidad", {
        "accion": "cantidad", "argumentos": {"cantidad": 3, "item_indice": 1},
    })
    assert "confirmar" in propuesta.lower()
    for _ in range(2):
        await servicio.recibir("extras-confirmacion", "5492215550183", "confirmar")
        await servicio.procesar("extras-confirmacion", {"accion": "confirmar"})
    item_editado = (await servicio.repo.pedido(pedido_id))["items"][0]
    assert item_editado["cantidad"] == 3 and item_editado["extras"] == item["extras"]
    await servicio.pedidos.cambiar_estado(pedido_id, EstadoPedido.CONFIRMADO, usuario_id=None)
    await servicio.pedidos.cambiar_estado(pedido_id, EstadoPedido.EN_PREPARACION, usuario_id=None)
    cocina = (await servicio.pedidos.listar(cliente_id=cliente_id))[0]
    assert cocina["items"][0]["extras"][0]["cantidad_requerida"] == "0.250"
    assert await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s",
                           (ingrediente_id,)) == Decimal("5.5")
    assert await uow.valor(
        "SELECT count(*) FROM movimiento_stock WHERE pedido_id=%s AND tipo='CONSUMO'",
        (pedido_id,),
    ) == 1

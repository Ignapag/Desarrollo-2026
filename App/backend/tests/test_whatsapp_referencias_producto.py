"""Referencias comerciales del intérprete, sin red ni base de datos."""

from copy import deepcopy

import pytest

from app.modules.whatsapp.application.edicion_conversacional import resolver_items
from app.modules.whatsapp.application.servicio_bot import ServicioBot


def producto(id=99, nombre='Nagui burger', descripcion='Triple tasty de Nagi'):
    return {'id': id, 'nombre': nombre, 'descripcion': descripcion, 'variantes': []}


async def resolver(referencia, productos):
    class Productos:
        async def listar(self, **kwargs): return productos

    bot = ServicioBot(None, None, productos=Productos())
    b = {'contexto_chat': {}, 'version': 1}
    pedido = {'version': 1, 'items': [{
        'id': 1, 'producto_id': 99, 'cantidad': 1, 'variante': None, 'aclaraciones': None,
    }]}
    original = deepcopy(pedido)
    resultado = await resolver_items(bot, b, {'id': 'ficticio'}, pedido, {
        'accion': 'agregar_producto', 'argumentos': {
            'producto': referencia, 'cantidad': 1, 'aclaraciones': 'Sin lechuga',
        },
    })
    assert pedido == original
    return resultado, b, original


@pytest.mark.parametrize('referencia', ['triple tasty', 'TRÍPLE   TASTY'])
async def test_descripcion_inequivoca_agrega_otro_item_y_conserva_personalizacion(referencia):
    resultado, _, original = await resolver(referencia, [producto()])
    assert not isinstance(resultado, str)
    items, accion, argumentos = resultado
    assert accion == 'agregar_producto'
    assert argumentos['producto'] == 'Nagui burger'
    assert items == [*original['items'], {
        'producto_id': 99, 'cantidad': 1, 'variante': None, 'aclaraciones': 'Sin lechuga',
    }]


async def test_descripcion_compartida_pide_elegir_solo_candidatos_y_conserva_solicitud():
    resultado, b, _ = await resolver('triple tasty', [
        producto(), producto(100, 'Otra burger', 'Nuestra triple tasty'),
        producto(101, 'Cheese', 'Carne y cheddar'),
    ])
    assert isinstance(resultado, str)
    assert 'Nagui burger' in resultado and 'Otra burger' in resultado and 'Cheese' not in resultado
    assert b['contexto_chat']['catalogo_opciones'] == [99, 100]
    assert b['contexto_chat']['edicion']['argumentos'] == {
        'producto': 'triple tasty', 'cantidad': 1, 'aclaraciones': 'Sin lechuga',
    }


async def test_nombre_exacto_prevalece_sobre_descripcion_de_otro_producto():
    resultado, _, _ = await resolver('triple tasty', [
        producto(), producto(100, 'Triple Tasty', 'Otra receta'),
    ])
    assert not isinstance(resultado, str)
    assert resultado[0][-1]['producto_id'] == 100


async def test_nombres_ambiguos_no_se_desambiguan_por_descripcion_de_un_tercero():
    resultado, b, _ = await resolver('triple tasty', [
        producto(), producto(100, 'Triple Tasty Simple', ''),
        producto(101, 'Triple Tasty Doble', ''),
    ])
    assert isinstance(resultado, str)
    assert b['contexto_chat']['catalogo_opciones'] == [100, 101]


@pytest.mark.parametrize('referencia,descripcion', [
    ('tasty', 'Triple tasty de Nagi'),
    ('sin lechuga', 'Burger sin lechuga'),
    ('triple tas', 'Triple tasty de Nagi'),
    ('trip tasty', 'Triple tasty de Nagi'),
    ('triple tasty', None),
    ('triple tasty', {'texto': 'Triple tasty de Nagi'}),
])
async def test_referencia_generica_incompleta_o_descripcion_invalida_no_se_autoselecciona(
    referencia, descripcion,
):
    resultado, b, _ = await resolver(referencia, [producto(descripcion=descripcion)])
    assert isinstance(resultado, str)
    assert b['contexto_chat']['pregunta'] == 'producto'

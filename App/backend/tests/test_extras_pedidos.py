"""Extras con precio de venta, porción real y composición congelada."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.errores import DatosInvalidos
from app.modules.pedidos.presentation.esquemas import ItemPedidoEntrada


def test_entrada_extras_rechaza_cantidades_manipuladas_y_precios():
    for extra in (
        {"ingrediente_id": 1, "cantidad": True},
        {"ingrediente_id": 1, "cantidad": 1.5},
        {"ingrediente_id": 1, "cantidad": -1},
        {"ingrediente_id": 1, "cantidad": 1, "precio": 0},
    ):
        with pytest.raises(ValidationError):
            ItemPedidoEntrada(producto_id=1, cantidad=1, extras=[extra])
    assert (
        ItemPedidoEntrada(producto_id=1, cantidad=1, extras=[{"ingrediente_id": 1, "cantidad": 2}])
        .extras[0]
        .cantidad
        == 2
    )


@pytest.mark.asyncio
async def test_cotizacion_congela_porcion_real_y_precio_sin_tomar_costos():
    from app.modules.pedidos.application.extras import cotizar_extras

    receta = [{"ingrediente_id": 1, "cantidad_requerida": "25", "es_base": True}]
    opciones = [
        {
            "ingrediente_id": 1,
            "nombre": "Tomate",
            "unidad_medida": "GR",
            "cantidad_requerida": "15",
            "precio": "300",
            "max_por_item": 3,
        }
    ]
    resultado = cotizar_extras([{"ingrediente_id": 1, "cantidad": 2}], receta, opciones)
    assert resultado["costo_opciones"] == Decimal("600")
    assert resultado["receta_snapshot"][0]["cantidad_requerida"] == "55"
    assert resultado["extras_snapshot"][0]["unidad_medida"] == "GR"
    assert receta[0]["cantidad_requerida"] == "25"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extras,aclaraciones",
    [
        ([{"ingrediente_id": 2, "cantidad": 1}], None),
        ([{"ingrediente_id": 1, "cantidad": 4}], None),
        ([{"ingrediente_id": 1, "cantidad": 1}] * 2, None),
        ([{"ingrediente_id": 1, "cantidad": 1}], "Sin Tomate"),
    ],
)
async def test_cotizacion_rechaza_fuera_receta_limites_duplicados_y_contradiccion(
    extras, aclaraciones
):
    from app.modules.pedidos.application.extras import cotizar_extras

    with pytest.raises(DatosInvalidos):
        cotizar_extras(
            extras,
            [{"ingrediente_id": 1, "cantidad_requerida": "25"}],
            [
                {
                    "ingrediente_id": 1,
                    "nombre": "Tomate",
                    "unidad_medida": "GR",
                    "cantidad_requerida": "15",
                    "precio": "300",
                    "max_por_item": 3,
                }
            ],
            aclaraciones,
        )

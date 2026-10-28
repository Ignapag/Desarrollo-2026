"""Los errores de dominio llegan como JSON aunque sus detalles traigan Decimal."""

from decimal import Decimal

import httpx
from fastapi import FastAPI

from app.core.errores import manejador_error_dominio
from app.errores import ErrorDominio
from app.modules.stock.application.servicio_stock import StockInsuficiente


async def test_stock_insuficiente_con_cantidades_decimales_responde_409():
    app = FastAPI()
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)

    @app.patch("/pedido")
    async def confirmar():
        raise StockInsuficiente("Stock insuficiente para el pedido", {"ingredientes": [{
            "ingrediente_id": 7,
            "nombre": "Tomate",
            "cantidad_requerida": Decimal("0.150"),
            "cantidad_disponible": Decimal("0.000"),
        }]})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as cliente:
        respuesta = await cliente.patch("/pedido")

    assert respuesta.status_code == 409
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "stock_insuficiente"
    assert cuerpo["mensaje"] == "Stock insuficiente para el pedido"
    faltante = cuerpo["detalles"]["ingredientes"][0]
    assert faltante["nombre"] == "Tomate"
    assert faltante["cantidad_requerida"] == 0.15

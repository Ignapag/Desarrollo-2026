"""Composición pública de WhatsApp; proveedores fuera de la transacción."""

from typing import Annotated

from fastapi import Depends

from app.core.config import settings
from app.core.dependencias import UoW
from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos
from app.modules.productos.presentation.dependencias import obtener_servicio_productos
from app.modules.stock.presentation.dependencias import obtener_servicio_stock
from app.modules.whatsapp.application.servicio_bot import ServicioBot
from app.modules.whatsapp.infrastructure.proveedores import (
    GeminiInterpretador,
    SimuladoInterpretador,
    SimuladoTransporte,
    WhatsAppCloud,
)
from app.modules.whatsapp.infrastructure.repositorio_sql import RepositorioBotSQL


def construir_servicio(uow: UoW) -> ServicioBot:
    return ServicioBot(
        RepositorioBotSQL(uow),
        obtener_servicio_pedidos(uow),
        settings.whatsapp_numero_negocio,
        settings.whatsapp_transferencia_datos,
        stock=obtener_servicio_stock(uow),
        productos=obtener_servicio_productos(uow),
    )


ServicioBotDep = Annotated[ServicioBot, Depends(construir_servicio)]


def interpretador(modo=None):
    if (modo or settings.gemini_modo) == "real":
        return GeminiInterpretador(
            settings.gemini_api_key, settings.gemini_modelo,
            timeout=settings.gemini_timeout,
            modelos_alternativos=settings.gemini_modelos_alternativos,
            max_intentos=settings.gemini_max_intentos,
        )
    return SimuladoInterpretador()


def transporte():
    if settings.whatsapp_modo == "real":
        return WhatsAppCloud(
            settings.whatsapp_token,
            settings.whatsapp_phone_number_id,
            settings.whatsapp_graph_version,
            destinatarios_prueba_sin_9=settings.whatsapp_destinatarios_prueba_sin_9,
        )
    return SimuladoTransporte()

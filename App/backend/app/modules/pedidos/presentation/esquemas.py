"""Contratos HTTP de pedidos."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.pedidos.domain.entidades import EstadoPedido


class ItemPedidoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    producto_id: int = Field(gt=0)
    cantidad: int = Field(gt=0, le=50)
    variante: str | None = Field(default=None, min_length=1, max_length=60)
    aclaraciones: str | None = Field(default=None, max_length=500)


class DireccionPedidoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calle: str = Field(min_length=1, max_length=160)
    numero: str = Field(default="S/N", min_length=1, max_length=30)
    localidad: str = Field(min_length=1, max_length=100)
    referencia: str | None = Field(default=None, max_length=300)


class PedidoCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cliente_id: int | None = Field(default=None, gt=0)
    tipo_entrega: Literal["DELIVERY", "RETIRO"] = "RETIRO"
    direccion_id: int | None = Field(default=None, gt=0)
    direccion_nueva: DireccionPedidoEntrada | None = None
    observaciones: str | None = Field(default=None, max_length=500)
    items: list[ItemPedidoEntrada] = Field(min_length=1)


class CambiarEstadoEntrada(BaseModel):
    estado: EstadoPedido


class ItemPedidoSalida(BaseModel):
    id: int
    producto_id: int
    nombre_producto: str
    cantidad: int
    precio_unitario: Decimal
    costo_opciones: Decimal
    subtotal: Decimal
    aclaraciones: str | None


class PedidoSalida(BaseModel):
    id: int
    numero: int
    cliente_id: int
    cliente: str
    tipo_entrega: str
    direccion_id: int | None
    estado: EstadoPedido
    subtotal: Decimal
    costo_envio: Decimal
    total: Decimal
    observaciones: str | None
    creado_en: datetime
    items: list[ItemPedidoSalida]

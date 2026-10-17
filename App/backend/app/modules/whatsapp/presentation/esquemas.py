"""Entrada estricta; no se admiten precios ni identificadores de otro cliente."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.pedidos.presentation.esquemas import DireccionPedidoEntrada, ItemPedidoEntrada


class BorradorEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    telefono: str = Field(pattern=r"^[0-9]{11,15}$")
    tipo_entrega: Literal["RETIRO", "DELIVERY"] | None = None
    metodo_pago: Literal["EFECTIVO", "TRANSFERENCIA"] | None = None
    direccion_nueva: DireccionPedidoEntrada | None = None
    items: list[ItemPedidoEntrada] = Field(min_length=1, max_length=50)


class MensajeSimulado(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=200)
    telefono: str = Field(pattern=r"^[0-9]{11,15}$")
    texto: str = Field(default="", max_length=4096)
    media_id: str | None = Field(default=None, min_length=1, max_length=200)


class RevisionEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aprobar: bool
    motivo: str = Field(min_length=1, max_length=500)
    total_verificado: Decimal | None = Field(default=None, ge=0)
    resolucion_financiera: Literal["COBRO_PENDIENTE"] | None = None


class RespuestaAtencionEntrada(BaseModel):
    """Respuesta del personal; ``solicitud_id`` evita duplicarla ante reintentos."""

    model_config = ConfigDict(extra="forbid")
    texto: str = Field(min_length=1, max_length=1000)
    solicitud_id: UUID


class ResolucionAtencionEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolucion: str = Field(min_length=1, max_length=500)

"""Contratos HTTP de pedidos."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.pedidos.domain.entidades import EstadoPedido
from app.modules.usuarios.domain.entidades import ClaimsSesion, Rol


class ItemPedidoEntrada(BaseModel):
    """Línea solicitada al crear un pedido: producto, cantidad, variante y aclaraciones."""

    model_config = ConfigDict(extra="forbid")

    producto_id: int = Field(gt=0)
    cantidad: int = Field(gt=0, le=50)
    variante: str | None = Field(default=None, min_length=1, max_length=60)
    aclaraciones: str | None = Field(default=None, max_length=500)


class DireccionPedidoEntrada(BaseModel):
    """Dirección de entrega nueva informada al crear o editar un pedido."""

    model_config = ConfigDict(extra="forbid")

    calle: str = Field(min_length=1, max_length=160)
    numero: str = Field(default="S/N", min_length=1, max_length=30)
    localidad: str = Field(min_length=1, max_length=100)
    referencia: str | None = Field(default=None, max_length=300)


class PedidoCrear(BaseModel):
    """Datos para crear un pedido de retiro o delivery."""

    model_config = ConfigDict(extra="forbid")

    cliente_id: int | None = Field(default=None, gt=0)
    tipo_entrega: Literal["DELIVERY", "RETIRO"] = "RETIRO"
    direccion_id: int | None = Field(default=None, gt=0)
    direccion_nueva: DireccionPedidoEntrada | None = None
    observaciones: str | None = Field(default=None, max_length=500)
    items: list[ItemPedidoEntrada] = Field(min_length=1)
    metodo_pago_acordado: Literal["EFECTIVO", "TRANSFERENCIA"] = "EFECTIVO"


class CambiarEstadoEntrada(BaseModel):
    """Solicitud de cambio de estado, con datos de control para correcciones."""

    model_config = ConfigDict(extra="forbid")
    estado: EstadoPedido
    motivo: str | None = Field(default=None, min_length=1, max_length=500)
    version_esperada: int | None = Field(default=None, gt=0)
    estado_esperado: EstadoPedido | None = None
    correccion: bool = False
    tratamiento_stock: Literal["CONSERVAR", "RECONSUMIR", "MERMA"] | None = None


class EditarOperacionEntrada(BaseModel):
    """Cambios operativos de un pedido (modalidad, dirección, pago acordado, notas)."""

    model_config = ConfigDict(extra="forbid")
    motivo: str = Field(min_length=1, max_length=500)
    version_esperada: int = Field(gt=0)
    tipo_entrega: Literal["DELIVERY", "RETIRO"] | None = None
    direccion_id: int | None = Field(default=None, gt=0)
    direccion_nueva: DireccionPedidoEntrada | None = None
    metodo_pago_acordado: Literal["EFECTIVO", "TRANSFERENCIA"] | None = None
    observaciones: str | None = Field(default=None, max_length=500)


class ItemPedidoSalida(BaseModel):
    """Línea del pedido con su precio congelado y subtotal."""

    id: int
    producto_id: int
    nombre_producto: str
    cantidad: int
    precio_unitario: Decimal
    costo_opciones: Decimal
    subtotal: Decimal
    aclaraciones: str | None
    variante: str | None = None


class PedidoSalida(BaseModel):
    """Pedido completo con ítems, historial, pagos y saldo para el panel o el cliente."""

    @classmethod
    def para_sesion(cls, fila: dict, sesion: ClaimsSesion) -> "PedidoSalida":
        """Arma la salida ocultando los pagos a quien no tenga permiso para verlos."""
        salida = cls(**fila)
        if sesion.rol != Rol.CLIENTE and not sesion.puede("pagos.ver"):
            salida.pagos = []
        return salida

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
    version: int = 1
    metodo_pago_acordado: str = "EFECTIVO"
    telefono: str | None = None
    direccion: dict | None = None
    envio: dict | None = None
    historial: list[dict] = Field(default_factory=list)
    pagos: list[dict] = Field(default_factory=list)
    neto_cobrado: Decimal = Decimal("0")
    saldo_pendiente: Decimal = Decimal("0")
    confirmado_en: datetime | None = None
    preparacion_en: datetime | None = None
    listo_en: datetime | None = None
    entregado_en: datetime | None = None
    cancelado_en: datetime | None = None

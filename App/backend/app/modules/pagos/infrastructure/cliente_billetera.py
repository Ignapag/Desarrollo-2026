"""Tipos históricos y adaptador deshabilitado de Mercado Pago, sin acceso externo."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.errores import ReglaDeNegocio


@dataclass(slots=True, frozen=True)
class PreferenciaCobro:
    """Datos generados para que el cliente abone a través de la billetera virtual."""

    preference_id: str
    init_point: str
    qr_data: str
    monto: Decimal
    referencia_externa: str


@dataclass(slots=True, frozen=True)
class DetallePagoExterno:
    """Información del pago obtenida desde la API de la billetera."""

    payment_id: str
    status: str  # approved, rejected, in_process, etc.
    status_detail: str | None
    monto: Decimal
    referencia_externa: str


class ClienteMercadoPago:
    """Compatibilidad histórica: la integración está deshabilitada en todos los entornos."""

    def __init__(self, access_token: str | None = None) -> None:
        pass

    @property
    def esta_configurado(self) -> bool:
        return False

    async def crear_preferencia(self, **kwargs) -> PreferenciaCobro:
        raise ReglaDeNegocio("La integración con Mercado Pago está deshabilitada")

    async def consultar_pago(self, payment_id: str) -> DetallePagoExterno:
        raise ReglaDeNegocio("La integración con Mercado Pago está deshabilitada")

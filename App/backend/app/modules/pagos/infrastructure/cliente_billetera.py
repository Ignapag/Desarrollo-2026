"""Adaptador de infraestructura para integración con billeteras virtuales (Mercado Pago).

Sigue Clean Architecture: desacopla las llamadas a las APIs externas y permite
funcionar tanto en modo real (con credenciales) como en modo simulación/sandbox
para entornos locales y de pruebas automatizadas.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal

from app.core.config import settings

log = logging.getLogger("monuburger.pagos")


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
    """Cliente para la API de Mercado Pago y generación de cobros QR / Checkout."""

    def __init__(self, access_token: str | None = None) -> None:
        self.access_token = access_token or settings.mp_access_token

    @property
    def esta_configurado(self) -> bool:
        return bool(self.access_token)

    async def crear_preferencia(
        self,
        pedido_id: int,
        numero_pedido: int,
        monto: Decimal,
        descripcion: str,
        payer_email: str | None = None,
    ) -> PreferenciaCobro:
        """Crea una preferencia de pago en Mercado Pago o genera un enlace simulado."""
        referencia = f"pedido_{pedido_id}_{int(time.time())}"

        if self.esta_configurado:
            try:
                import httpx

                url = "https://api.mercadopago.com/checkout/preferences"
                headers = {
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "items": [
                        {
                            "title": descripcion,
                            "quantity": 1,
                            "unit_price": float(monto),
                            "currency_id": "ARS",
                        }
                    ],
                    "external_reference": referencia,
                    "notification_url": settings.mp_url_notificacion,
                    "back_urls": {
                        "success": settings.mp_url_retorno,
                        "pending": settings.mp_url_retorno,
                        "failure": settings.mp_url_retorno,
                    },
                    "auto_return": "approved",
                }
                if payer_email:
                    payload["payer"] = {"email": payer_email}

                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()

                pref_id = data["id"]
                init_point = data.get("init_point", "")
                # Genera payload de QR basado en el init_point
                qr_data = data.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code", init_point)

                return PreferenciaCobro(
                    preference_id=pref_id,
                    init_point=init_point,
                    qr_data=qr_data,
                    monto=monto,
                    referencia_externa=referencia,
                )
            except Exception as exc:
                log.warning("Fallo al conectar con la API de Mercado Pago (%s). Usando simulación.", exc)

        # Modo simulación / desarrollo local
        pref_id = f"pref_{referencia}"
        init_point = f"https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id={pref_id}"
        qr_data = f"00020101021243650016com.mercadopago{pref_id}5204000053030325802AR"

        return PreferenciaCobro(
            preference_id=pref_id,
            init_point=init_point,
            qr_data=qr_data,
            monto=monto,
            referencia_externa=referencia,
        )

    async def consultar_pago(self, payment_id: str) -> DetallePagoExterno:
        """Consulta el estado del pago ante Mercado Pago a partir del payment_id."""
        if self.esta_configurado and not payment_id.startswith("sim_"):
            try:
                import httpx

                url = f"https://api.mercadopago.com/v1/payments/{payment_id}"
                headers = {"Authorization": f"Bearer {self.access_token}"}
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()

                return DetallePagoExterno(
                    payment_id=str(data["id"]),
                    status=data["status"],
                    status_detail=data.get("status_detail"),
                    monto=Decimal(str(data["transaction_amount"])),
                    referencia_externa=data.get("external_reference", ""),
                )
            except Exception as exc:
                log.warning("Fallo al consultar pago en Mercado Pago (%s). Usando simulación.", exc)

        # Modo simulación / pruebas
        if payment_id.startswith("rechazado_"):
            return DetallePagoExterno(
                payment_id=payment_id,
                status="rejected",
                status_detail="cc_rejected_insufficient_amount",
                monto=Decimal("0.00"),
                referencia_externa="",
            )

        return DetallePagoExterno(
            payment_id=payment_id,
            status="approved",
            status_detail="accredited",
            monto=Decimal("0.00"),
            referencia_externa="",
        )

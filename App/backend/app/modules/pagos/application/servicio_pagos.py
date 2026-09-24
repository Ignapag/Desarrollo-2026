"""Casos de uso del módulo de pagos."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.core.db import UnidadDeTrabajo
from app.core.errores import NoEncontrado, ReglaDeNegocio
from app.modules.pagos.domain.entidades import (
    EstadoPago,
    MetodoPago,
    Pago,
    ResultadoCobroEfectivo,
    TipoPago,
    calcular_cobro_efectivo,
)
from app.modules.pagos.infrastructure.repositorio_sql import RepositorioPagosSQL


class ServicioPagos:
    """Orquesta los casos de uso relacionados a cobros y validaciones de pago."""

    def __init__(self, uow: UnidadDeTrabajo, repo: RepositorioPagosSQL) -> None:
        self.uow = uow
        self.repo = repo

    async def registrar_pago_efectivo(
        self,
        pedido_id: int,
        monto_recibido: Decimal,
        monto_a_pagar: Decimal | None = None,
        propina: Decimal = Decimal("0.00"),
        conciliar_inmediato: bool = True,
        registrado_por: int | None = None,
    ) -> ResultadoCobroEfectivo:
        """Registra el cobro en efectivo de un pedido y calcula el vuelto.

        - Valida la existencia del pedido y que no esté cancelado.
        - Verifica el saldo pendiente.
        - Si conciliar_inmediato es True (ej. cobro en mostrador), se asienta como CONCILIADO.
        - Si el saldo queda cubierto y el pedido estaba PENDIENTE, se pasa a CONFIRMADO.
        """
        pedido = await self.repo.obtener_pedido(pedido_id)
        if pedido is None:
            raise NoEncontrado(f"Pedido {pedido_id} no encontrado")

        if pedido["estado"] == "CANCELADO":
            raise ReglaDeNegocio(f"El pedido #{pedido['numero']} está cancelado y no admite pagos")

        total_pedido = Decimal(str(pedido["total"]))
        total_pagado = await self.repo.total_pagado_por_pedido(pedido_id)

        # Regla pura de dominio
        detalle = calcular_cobro_efectivo(
            total_pedido=total_pedido,
            total_ya_pagado=total_pagado,
            monto_recibido=monto_recibido,
            monto_a_pagar=monto_a_pagar,
            propina=propina,
        )

        ahora = datetime.now(timezone.utc)
        estado = EstadoPago.CONCILIADO if conciliar_inmediato else EstadoPago.PENDIENTE
        conciliado_en = ahora if conciliar_inmediato else None

        pago = await self.repo.registrar_pago(
            pedido_id=pedido_id,
            tipo=TipoPago.COBRO,
            metodo_pago=MetodoPago.EFECTIVO,
            monto=detalle.monto_cobrado,
            propina=detalle.propina,
            estado=estado,
            referencia_externa=None,
            registrado_por=registrado_por,
            conciliado_en=conciliado_en,
            motivo=None,
        )

        # Si el saldo quedó cubierto en su totalidad y el pedido estaba pendiente de confirmación
        if detalle.saldo_restante == Decimal("0.00") and pedido["estado"] == "PENDIENTE":
            await self.repo.actualizar_estado_pedido(pedido_id, "CONFIRMADO")

        return ResultadoCobroEfectivo(pago=pago, detalle=detalle)

    async def obtener_pago(self, pago_id: int) -> Pago:
        """Recupera un pago específico o lanza NoEncontrado."""
        pago = await self.repo.obtener_pago_por_id(pago_id)
        if pago is None:
            raise NoEncontrado(f"Pago {pago_id} no encontrado")
        return pago

    async def listar_pagos_por_pedido(self, pedido_id: int) -> list[Pago]:
        """Devuelve todos los pagos imputados a un pedido."""
        pedido = await self.repo.obtener_pedido(pedido_id)
        if pedido is None:
            raise NoEncontrado(f"Pedido {pedido_id} no encontrado")
        return await self.repo.listar_pagos_por_pedido(pedido_id)

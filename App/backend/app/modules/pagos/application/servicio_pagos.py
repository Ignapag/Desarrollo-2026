"""Casos de uso del módulo de pagos y validación de cobros."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.core import auditoria
from app.core.db import UnidadDeTrabajo
from app.core.errores import NoEncontrado, ReglaDeNegocio
from app.modules.pagos.domain.entidades import (
    AccionesPagos,
    EstadoFinancieroPedido,
    EstadoPago,
    MetodoPago,
    Pago,
    ResultadoCobroEfectivo,
    TipoPago,
    calcular_cobro_efectivo,
    calcular_estado_financiero,
)
from app.modules.pagos.infrastructure.repositorio_sql import RepositorioPagosSQL


class ServicioPagos:
    """Orquesta los casos de uso relacionados a cobros, validaciones y balance financiero."""

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
        ip_cliente: str | None = None,
    ) -> ResultadoCobroEfectivo:
        """Registra el cobro en efectivo de un pedido y calcula el vuelto.

        Mecanismos de protección y validación:
        - Bloqueo pesimista (FOR UPDATE) sobre el pedido para evitar concurrencia y pagos duplicados.
        - Validación estricta de estado (no cancelado, no saldado previamente).
        - Validación de montos e importes recibidos contra saldo pendiente.
        - Si el saldo queda totalmente cubierto y el pedido estaba PENDIENTE, pasa a CONFIRMADO
          dejando trazabilidad en pedido_estado_historial.
        - Asienta la operación en la bitácora de auditoría (RNF-09).
        """
        # Bloqueo pesimista: cualquier otra transacción concurrente espera a que esta termine
        pedido = await self.repo.obtener_pedido_para_actualizar(pedido_id)
        if pedido is None:
            raise NoEncontrado(f"Pedido {pedido_id} no encontrado")

        if pedido["estado"] == "CANCELADO":
            raise ReglaDeNegocio(f"El pedido #{pedido['numero']} está cancelado y no admite pagos")

        total_pedido = Decimal(str(pedido["total"]))
        total_pagado = await self.repo.total_pagado_por_pedido(pedido_id)

        # Regla pura de dominio (valida que no esté saldado, importes positivos y vuelto)
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

        # Transición de estado del pedido con trazabilidad en historial
        if detalle.saldo_restante == Decimal("0.00") and pedido["estado"] == "PENDIENTE":
            await self.repo.cambiar_estado_pedido(
                pedido_id=pedido_id,
                estado="CONFIRMADO",
                usuario_id=registrado_por,
                observacion=f"Cobro total en efectivo acreditado (Pago #{pago.id})",
            )

        # Registro en auditoría
        await auditoria.registrar(
            self.uow,
            accion=AccionesPagos.PAGO_REGISTRADO,
            entidad="pago",
            entidad_id=pago.id,
            usuario_id=registrado_por,
            ip=ip_cliente,
            datos={
                "pedido_id": pedido_id,
                "numero_pedido": pedido["numero"],
                "metodo_pago": MetodoPago.EFECTIVO.value,
                "monto_cobrado": str(detalle.monto_cobrado),
                "propina": str(detalle.propina),
                "vuelto": str(detalle.vuelto),
                "saldo_restante": str(detalle.saldo_restante),
                "estado_pago": estado.value,
            },
        )

        return ResultadoCobroEfectivo(pago=pago, detalle=detalle)

    async def obtener_estado_financiero(self, pedido_id: int) -> EstadoFinancieroPedido:
        """Calcula el estado financiero y balance de pagos completo de un pedido."""
        pedido = await self.repo.obtener_pedido(pedido_id)
        if pedido is None:
            raise NoEncontrado(f"Pedido {pedido_id} no encontrado")

        pagos = await self.repo.listar_pagos_por_pedido(pedido_id)
        total_pedido = Decimal(str(pedido["total"]))

        return calcular_estado_financiero(
            pedido_id=pedido_id,
            numero=pedido["numero"],
            estado_pedido=pedido["estado"],
            total_pedido=total_pedido,
            pagos=pagos,
        )

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

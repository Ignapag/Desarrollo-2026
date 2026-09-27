"""Casos de uso del módulo de pagos, cobro digital y validación financiera."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from app.core import auditoria
from app.core.db import UnidadDeTrabajo
from app.core.errores import DatosInvalidos, NoEncontrado, ReglaDeNegocio
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
from app.modules.pagos.infrastructure.cliente_billetera import (
    ClienteMercadoPago,
    PreferenciaCobro,
)
from app.modules.pagos.infrastructure.repositorio_sql import RepositorioPagosSQL


@dataclass(slots=True, frozen=True)
class ResultadoInicioBilletera:
    pago: Pago
    preferencia: PreferenciaCobro


class ServicioPagos:
    """Orquesta los casos de uso relacionados a cobros, validaciones y balance financiero."""

    def __init__(
        self,
        uow: UnidadDeTrabajo,
        repo: RepositorioPagosSQL,
        cliente_mp: ClienteMercadoPago | None = None,
    ) -> None:
        self.uow = uow
        self.repo = repo
        self.cliente_mp = cliente_mp or ClienteMercadoPago()

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
        """Registra el cobro en efectivo de un pedido y calcula el vuelto."""
        pedido = await self.repo.obtener_pedido_para_actualizar(pedido_id)
        if pedido is None:
            raise NoEncontrado(f"Pedido {pedido_id} no encontrado")

        if pedido["estado"] == "CANCELADO":
            raise ReglaDeNegocio(f"El pedido #{pedido['numero']} está cancelado y no admite pagos")

        total_pedido = Decimal(str(pedido["total"]))
        total_pagado = await self.repo.total_pagado_por_pedido(pedido_id)

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

        if detalle.saldo_restante == Decimal("0.00") and pedido["estado"] == "PENDIENTE":
            await self.repo.cambiar_estado_pedido(
                pedido_id=pedido_id,
                estado="CONFIRMADO",
                usuario_id=registrado_por,
                observacion=f"Cobro total en efectivo acreditado (Pago #{pago.id})",
            )

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

    async def iniciar_cobro_digital(
        self,
        pedido_id: int,
        metodo_pago: MetodoPago = MetodoPago.MERCADO_PAGO,
        monto_a_pagar: Decimal | None = None,
        propina: Decimal = Decimal("0.00"),
        payer_email: str | None = None,
        registrado_por: int | None = None,
        ip_cliente: str | None = None,
    ) -> ResultadoInicioBilletera:
        """Genera la orden de cobro digital (preferencia de pago / QR dinámico).

        Crea el pago en estado PENDIENTE asociado a la preferencia_id.
        """
        if metodo_pago == MetodoPago.EFECTIVO:
            raise DatosInvalidos("Para cobro en efectivo debe utilizar el endpoint correspondiente")

        pedido = await self.repo.obtener_pedido_para_actualizar(pedido_id)
        if pedido is None:
            raise NoEncontrado(f"Pedido {pedido_id} no encontrado")

        if pedido["estado"] == "CANCELADO":
            raise ReglaDeNegocio(f"El pedido #{pedido['numero']} está cancelado y no admite pagos")

        total_pedido = Decimal(str(pedido["total"]))
        total_pagado = await self.repo.total_pagado_por_pedido(pedido_id)
        saldo_pendiente = max(Decimal("0.00"), total_pedido - total_pagado)

        if saldo_pendiente == Decimal("0.00"):
            raise ReglaDeNegocio(f"El pedido #{pedido['numero']} ya se encuentra saldado en su totalidad")

        monto_cobrar = monto_a_pagar if monto_a_pagar is not None else saldo_pendiente
        if monto_cobrar <= Decimal("0.00"):
            raise DatosInvalidos("El monto a cobrar debe ser mayor a cero")
        if monto_cobrar > saldo_pendiente:
            raise DatosInvalidos(f"El monto a cobrar (${monto_cobrar}) supera el saldo pendiente (${saldo_pendiente})")
        if propina < Decimal("0.00"):
            raise DatosInvalidos("La propina no puede ser negativa")

        monto_total_transaccion = monto_cobrar + propina
        descripcion = f"Monu Burger - Pedido #{pedido['numero']}"

        # Llamada al cliente de billetera virtual (Mercado Pago)
        preferencia = await self.cliente_mp.crear_preferencia(
            pedido_id=pedido_id,
            numero_pedido=pedido["numero"],
            monto=monto_total_transaccion,
            descripcion=descripcion,
            payer_email=payer_email,
        )

        pago = await self.repo.registrar_pago(
            pedido_id=pedido_id,
            tipo=TipoPago.COBRO,
            metodo_pago=metodo_pago,
            monto=monto_cobrar,
            propina=propina,
            estado=EstadoPago.PENDIENTE,
            referencia_externa=preferencia.preference_id,
            registrado_por=registrado_por,
            conciliado_en=None,
            motivo=None,
        )

        await auditoria.registrar(
            self.uow,
            accion="COBRO_DIGITAL_INICIADO",
            entidad="pago",
            entidad_id=pago.id,
            usuario_id=registrado_por,
            ip=ip_cliente,
            datos={
                "pedido_id": pedido_id,
                "metodo_pago": metodo_pago.value,
                "preference_id": preferencia.preference_id,
                "monto": str(monto_cobrar),
                "propina": str(propina),
            },
        )

        return ResultadoInicioBilletera(pago=pago, preferencia=preferencia)

    async def procesar_webhook_mercadopago(
        self,
        payment_id: str,
        topic: str | None = None,
        ip_cliente: str | None = None,
    ) -> dict:
        """Procesa las notificaciones de Mercado Pago (IPN / Webhooks) de forma idempotente."""
        # Consultar estado real del pago en la API de Mercado Pago
        info = await self.cliente_mp.consultar_pago(payment_id)

        # Buscar el pago pendiente por su referencia externa (preference_id o payment_id)
        pago = await self.repo.obtener_pago_por_referencia(info.referencia_externa)
        if pago is None:
            # Si no se encontró por external_reference, buscar por el payment_id directamente
            pago = await self.repo.obtener_pago_por_referencia(payment_id)

        if pago is None:
            # Webhook de un pago no registrado en este sistema
            return {
                "estado": "ignorado",
                "motivo": "No se encontró un pago pendiente asociado a la referencia externa",
            }

        # Idempotencia: si ya está conciliado, responder OK sin re-procesar
        if pago.estado == EstadoPago.CONCILIADO:
            return {"estado": "ya_conciliado", "pago_id": pago.id}

        ahora = datetime.now(timezone.utc)

        if info.status == "approved":
            pago_actualizado = await self.repo.actualizar_pago_por_referencia(
                referencia_externa=pago.referencia_externa or payment_id,
                nuevo_estado=EstadoPago.CONCILIADO,
                conciliado_en=ahora,
                nueva_referencia=info.payment_id,
            )

            # Verificar si se completa el total del pedido
            pedido = await self.repo.obtener_pedido_para_actualizar(pago.pedido_id)
            if pedido and pedido["estado"] == "PENDIENTE":
                total_pagado = await self.repo.total_pagado_por_pedido(pago.pedido_id)
                if total_pagado >= Decimal(str(pedido["total"])):
                    await self.repo.cambiar_estado_pedido(
                        pedido_id=pago.pedido_id,
                        estado="CONFIRMADO",
                        usuario_id=pago.registrado_por,
                        observacion=f"Pago digital aprobado (MP #{info.payment_id})",
                    )

            await auditoria.registrar(
                self.uow,
                accion=AccionesPagos.PAGO_CONCILIADO,
                entidad="pago",
                entidad_id=pago.id,
                usuario_id=None,
                ip=ip_cliente,
                datos={
                    "payment_id": info.payment_id,
                    "pedido_id": pago.pedido_id,
                    "monto": str(pago.monto),
                    "estado": "CONCILIADO",
                },
            )
            return {"estado": "aprobado", "pago_id": pago.id, "payment_id": info.payment_id}

        elif info.status in ("rejected", "cancelled"):
            await self.repo.actualizar_pago_por_referencia(
                referencia_externa=pago.referencia_externa or payment_id,
                nuevo_estado=EstadoPago.ANULADO,
                motivo=f"Rechazado por billetera: {info.status_detail or info.status}",
            )
            await auditoria.registrar(
                self.uow,
                accion=AccionesPagos.PAGO_ANULADO,
                entidad="pago",
                entidad_id=pago.id,
                usuario_id=None,
                ip=ip_cliente,
                datos={"payment_id": info.payment_id, "motivo": info.status_detail},
            )
            return {"estado": "rechazado", "pago_id": pago.id, "payment_id": info.payment_id}

        return {"estado": "en_proceso", "pago_id": pago.id, "status_mp": info.status}

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

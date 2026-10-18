"""Casos de uso del módulo de pagos, cobro digital y validación financiera."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal

from app.core import auditoria
from app.core.db import UnidadDeTrabajo
from app.errores import DatosInvalidos, NoEncontrado, ReglaDeNegocio
from app.modules.pagos.application.operaciones import recuperar_operacion, solicitud_operacion
from app.modules.pagos.domain.entidades import (
    AccionesPagos,
    DetalleCobroEfectivo,
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
        self.cliente_mp = cliente_mp if cliente_mp is not None else ClienteMercadoPago()

    async def registrar_pago_efectivo(
        self,
        pedido_id: int,
        monto_recibido: Decimal,
        monto_a_pagar: Decimal | None = None,
        propina: Decimal = Decimal("0.00"),
        conciliar_inmediato: bool = True,
        registrado_por: int | None = None,
        ip_cliente: str | None = None,
        clave_operacion: str | None = None,
    ) -> ResultadoCobroEfectivo:
        """Registra el cobro en efectivo de un pedido y calcula el vuelto."""
        solicitud = solicitud_operacion(
            tipo="COBRO",
            metodo="EFECTIVO",
            pedido_id=pedido_id,
            monto_recibido=monto_recibido,
            monto_a_pagar=monto_a_pagar,
            propina=propina,
            conciliar_inmediato=conciliar_inmediato,
            actor=registrado_por,
        )
        existente = await recuperar_operacion(self.repo, clave_operacion, solicitud)
        if existente:
            pago, datos = existente
            return ResultadoCobroEfectivo(
                pago=pago,
                detalle=DetalleCobroEfectivo(
                    **{campo: Decimal(valor) for campo, valor in datos["detalle"].items()}
                ),
            )
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

        ahora = datetime.now(UTC)
        estado = EstadoPago.CONCILIADO if conciliar_inmediato else EstadoPago.PENDIENTE
        conciliado_en = ahora if conciliar_inmediato else None

        if not conciliar_inmediato:
            detalle = replace(detalle, saldo_restante=total_pedido - total_pagado)
        metadatos = {
            "solicitud": solicitud,
            "detalle": {campo: str(valor) for campo, valor in asdict(detalle).items()},
        }
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
            clave_operacion=clave_operacion,
            datos_operacion=metadatos,
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

    async def registrar_transferencia(
        self,
        pedido_id: int,
        monto: Decimal,
        comprobante: str | None = None,
        registrado_por: int | None = None,
        ip_cliente: str | None = None,
        clave_operacion: str | None = None,
    ) -> Pago:
        """Registra una transferencia para revisión humana, sin acreditar por el adjunto."""
        solicitud = solicitud_operacion(
            tipo="COBRO",
            metodo="TRANSFERENCIA",
            pedido_id=pedido_id,
            monto=monto,
            comprobante=comprobante,
            actor=registrado_por,
        )
        existente = await recuperar_operacion(self.repo, clave_operacion, solicitud)
        if existente:
            return existente[0]
        pedido = await self.repo.obtener_pedido_para_actualizar(pedido_id)
        if pedido is None:
            raise NoEncontrado(f"Pedido {pedido_id} no encontrado")
        if pedido["estado"] == "CANCELADO":
            raise ReglaDeNegocio("El pedido cancelado no admite cobros")
        saldo = Decimal(str(pedido["total"])) - await self.repo.total_pagado_por_pedido(pedido_id)
        if monto <= 0 or monto > saldo:
            raise DatosInvalidos("El monto debe ser positivo y no superar el saldo pendiente")
        pago = await self.repo.registrar_pago(
            pedido_id=pedido_id,
            tipo=TipoPago.COBRO,
            metodo_pago=MetodoPago.TRANSFERENCIA,
            monto=monto,
            propina=Decimal("0.00"),
            estado=EstadoPago.PENDIENTE,
            referencia_externa=comprobante,
            registrado_por=registrado_por,
            clave_operacion=clave_operacion,
            datos_operacion={"solicitud": solicitud},
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
                "monto": str(monto),
                "estado": "PENDIENTE",
                "comprobante": comprobante,
            },
        )
        return pago

    async def iniciar_cobro_digital(
        self,
        pedido_id: int,
        metodo_pago: MetodoPago = MetodoPago.MERCADO_PAGO,
        monto_a_pagar: Decimal | None = None,
        propina: Decimal = Decimal("0.00"),
        payer_email: str | None = None,
        registrado_por: int | None = None,
        ip_cliente: str | None = None,
        *,
        cliente_usuario_id: int | None = None,
    ) -> ResultadoInicioBilletera:
        """La integración histórica permanece deshabilitada."""
        raise ReglaDeNegocio("La integración con Mercado Pago está deshabilitada")

    async def procesar_webhook_mercadopago(
        self,
        payment_id: str,
        topic: str | None = None,
        ip_cliente: str | None = None,
    ) -> dict:
        """Ningún webhook puede acreditar dinero."""
        raise ReglaDeNegocio("La integración con Mercado Pago está deshabilitada")

    async def _validar_acceso_pedido(
        self,
        pedido_id: int,
        cliente_usuario_id: int | None,
    ) -> None:
        """None corresponde a una operación interna autorizada en presentación."""
        if cliente_usuario_id is not None and not await self.repo.pedido_pertenece_a_usuario(
            pedido_id,
            cliente_usuario_id,
        ):
            raise NoEncontrado(f"Pedido {pedido_id} no encontrado")

    async def obtener_estado_financiero(
        self,
        pedido_id: int,
        *,
        cliente_usuario_id: int | None = None,
    ) -> EstadoFinancieroPedido:
        """Calcula el estado financiero y balance de pagos completo de un pedido."""
        await self._validar_acceso_pedido(pedido_id, cliente_usuario_id)
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

    async def obtener_pago(
        self,
        pago_id: int,
        *,
        cliente_usuario_id: int | None = None,
    ) -> Pago:
        """Recupera un pago específico o lanza NoEncontrado."""
        pago = await self.repo.obtener_pago_por_id(pago_id)
        if pago is None or (
            cliente_usuario_id is not None
            and not await self.repo.pedido_pertenece_a_usuario(pago.pedido_id, cliente_usuario_id)
        ):
            raise NoEncontrado(f"Pago {pago_id} no encontrado")
        return pago

    async def listar_pagos_por_pedido(
        self,
        pedido_id: int,
        *,
        cliente_usuario_id: int | None = None,
    ) -> list[Pago]:
        """Devuelve todos los pagos imputados a un pedido."""
        await self._validar_acceso_pedido(pedido_id, cliente_usuario_id)
        pedido = await self.repo.obtener_pedido(pedido_id)
        if pedido is None:
            raise NoEncontrado(f"Pedido {pedido_id} no encontrado")
        return await self.repo.listar_pagos_por_pedido(pedido_id)

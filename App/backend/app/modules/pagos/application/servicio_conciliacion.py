"""Casos de uso para conciliación de pagos, gestión de devoluciones y anulaciones."""

from __future__ import annotations

from decimal import Decimal

from app.core import auditoria
from app.core.db import UnidadDeTrabajo
from app.errores import DatosInvalidos, ErrorDominio, NoEncontrado, ReglaDeNegocio
from app.modules.pagos.application.operaciones import recuperar_operacion, solicitud_operacion
from app.modules.pagos.domain.entidades import (
    AccionesPagos,
    EstadoPago,
    MetodoPago,
    Pago,
    TipoPago,
)
from app.modules.pagos.infrastructure.repositorio_sql import RepositorioPagosSQL


class ServicioConciliacion:
    """Orquesta la conciliación de cobros pendientes, registro de egresos/devoluciones
    y anulaciones.
    """

    def __init__(self, uow: UnidadDeTrabajo, repo: RepositorioPagosSQL) -> None:
        self.uow = uow
        self.repo = repo

    async def conciliar_pago(
        self,
        pago_id: int,
        conciliar_por: int | None = None,
        comprobante: str | None = None,
        ip_cliente: str | None = None,
    ) -> Pago:
        """Marca un pago individual como CONCILIADO tras verificar la acreditación real."""
        pago = await self.repo.obtener_pago_por_id(pago_id)
        if pago is None:
            raise NoEncontrado(f"Pago #{pago_id} no encontrado")

        # Todas las operaciones financieras se serializan sobre el pedido antes del pago.
        pedido = await self.repo.obtener_pedido_para_actualizar(pago.pedido_id)
        pago = await self.repo.obtener_pago_por_id(pago_id)

        if pago.es_conciliado:
            return pago

        if pago.estado == EstadoPago.ANULADO:
            raise ReglaDeNegocio(f"No se puede conciliar el pago #{pago_id} porque está anulado")

        neto = await self.repo.total_pagado_por_pedido(pago.pedido_id)
        if pago.tipo == TipoPago.COBRO and pago.monto > Decimal(str(pedido["total"])) - neto:
            raise ReglaDeNegocio("El cobro supera el saldo pendiente del pedido")
        if pago.tipo == TipoPago.DEVOLUCION and pago.monto > neto:
            raise ReglaDeNegocio("La devolución supera el saldo neto acreditado")

        pago_conciliado = await self.repo.conciliar_pago(pago_id, comprobante)
        if pago_conciliado is None:
            raise ReglaDeNegocio(f"No se pudo conciliar el pago #{pago_id}")

        await auditoria.registrar(
            self.uow,
            accion=AccionesPagos.PAGO_CONCILIADO,
            entidad="pago",
            entidad_id=pago_id,
            usuario_id=conciliar_por,
            ip=ip_cliente,
            datos={
                "pago_id": pago_id,
                "pedido_id": pago.pedido_id,
                "monto": str(pago.monto),
                "comprobante": comprobante,
            },
        )

        return pago_conciliado

    async def conciliar_lote(
        self,
        pago_ids: list[int],
        conciliar_por: int | None = None,
        ip_cliente: str | None = None,
    ) -> dict:
        """Concilia en lote múltiples pagos pendientes (ej. arqueo de repartidores
        o extracto bancario).
        """
        conciliados: list[int] = []
        fallidos: list[dict] = []

        pago_ids = sorted(set(pago_ids))
        await self.repo.bloquear_pedidos_de_pagos(pago_ids)
        for pid in pago_ids:
            try:
                await self.conciliar_pago(
                    pago_id=pid,
                    conciliar_por=conciliar_por,
                    ip_cliente=ip_cliente,
                )
                conciliados.append(pid)
            except ErrorDominio as exc:
                fallidos.append({"pago_id": pid, "error": str(exc)})

        return {
            "conciliados": conciliados,
            "fallidos": fallidos,
            "total_procesados": len(conciliados),
        }

    async def registrar_devolucion(
        self,
        pedido_id: int,
        monto: Decimal,
        motivo: str,
        metodo_pago: MetodoPago = MetodoPago.EFECTIVO,
        registrado_por: int | None = None,
        ip_cliente: str | None = None,
        clave_operacion: str | None = None,
    ) -> Pago:
        """Registra un egreso/devolución sobre un pedido (C-11, RF-06, RF-08).

        - Valida que el motivo esté explicitado.
        - Verifica que el monto a devolver no exceda el importe neto efectivamente pagado.
        - Asienta el registro con tipo DEVOLUCION y estado CONCILIADO.
        - Registra la trazabilidad en auditoría.
        """
        if not motivo or not motivo.strip():
            raise DatosInvalidos("El motivo de la devolución es obligatorio")

        if monto <= Decimal("0.00"):
            raise DatosInvalidos("El monto de la devolución debe ser mayor a cero")

        if metodo_pago not in (MetodoPago.EFECTIVO, MetodoPago.TRANSFERENCIA):
            raise DatosInvalidos("La devolución debe ser en efectivo o transferencia")
        solicitud = solicitud_operacion(
            tipo="DEVOLUCION",
            metodo=metodo_pago.value,
            pedido_id=pedido_id,
            monto=monto,
            motivo=motivo.strip(),
            actor=registrado_por,
        )
        existente = await recuperar_operacion(self.repo, clave_operacion, solicitud)
        if existente:
            return existente[0]

        pedido = await self.repo.obtener_pedido_para_actualizar(pedido_id)
        if pedido is None:
            raise NoEncontrado(f"Pedido #{pedido_id} no encontrado")

        total_neto_pagado = await self.repo.total_pagado_por_pedido(pedido_id)
        if monto > total_neto_pagado:
            raise DatosInvalidos(
                f"El monto a devolver (${monto}) supera el total neto abonado "
                f"en el pedido (${total_neto_pagado})"
            )

        devolucion = await self.repo.registrar_pago(
            pedido_id=pedido_id,
            tipo=TipoPago.DEVOLUCION,
            metodo_pago=metodo_pago,
            monto=monto,
            propina=Decimal("0.00"),
            estado=EstadoPago.CONCILIADO,
            referencia_externa=None,
            registrado_por=registrado_por,
            conciliado_en=None,
            motivo=motivo.strip(),
            clave_operacion=clave_operacion,
            datos_operacion={"solicitud": solicitud},
        )

        await auditoria.registrar(
            self.uow,
            accion=AccionesPagos.DEVOLUCION_REGISTRADA,
            entidad="pago",
            entidad_id=devolucion.id,
            usuario_id=registrado_por,
            ip=ip_cliente,
            datos={
                "pago_id": devolucion.id,
                "pedido_id": pedido_id,
                "monto_devuelto": str(monto),
                "motivo": motivo.strip(),
            },
        )

        return devolucion

    async def anular_pago(
        self,
        pago_id: int,
        motivo: str,
        anulado_por: int | None = None,
        ip_cliente: str | None = None,
    ) -> Pago:
        """Anula un pago pendiente que no llegó a acreditarse o fue cargado por error."""
        if not motivo or not motivo.strip():
            raise DatosInvalidos("El motivo de anulación es obligatorio")

        pago = await self.repo.obtener_pago_por_id(pago_id)
        if pago is None:
            raise NoEncontrado(f"Pago #{pago_id} no encontrado")

        await self.repo.obtener_pedido_para_actualizar(pago.pedido_id)
        pago = await self.repo.obtener_pago_por_id(pago_id)

        if pago.es_conciliado:
            raise ReglaDeNegocio(
                f"No se puede anular el pago #{pago_id} porque ya está conciliado. "
                "Para reintegrar dinero debe registrarse una devolución."
            )

        if pago.estado == EstadoPago.ANULADO:
            raise ReglaDeNegocio(f"El pago #{pago_id} ya se encuentra anulado")

        pago_anulado = await self.repo.anular_pago(pago_id, motivo.strip())
        if pago_anulado is None:
            raise ReglaDeNegocio(f"No se pudo anular el pago #{pago_id}")

        await auditoria.registrar(
            self.uow,
            accion=AccionesPagos.PAGO_ANULADO,
            entidad="pago",
            entidad_id=pago_id,
            usuario_id=anulado_por,
            ip=ip_cliente,
            datos={
                "pago_id": pago_id,
                "pedido_id": pago.pedido_id,
                "motivo": motivo.strip(),
            },
        )

        return pago_anulado

    async def listar_pendientes_conciliacion(self) -> list[Pago]:
        """Obtiene la lista de pagos que aguardan conciliación."""
        return await self.repo.listar_pagos_pendientes_conciliacion()

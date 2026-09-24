"""Servicio de aplicación para consolidación de ingresos y arqueo de caja."""

from __future__ import annotations

from datetime import date, datetime

from app.core import auditoria
from app.core.db import UnidadDeTrabajo
from app.core.errores import NoEncontrado, ReglaDeNegocio
from app.modules.pagos.domain.entidades import (
    AccionesPagos,
    CierreCaja,
    ConsolidadoTurno,
    EstadoCierre,
    TurnoCierre,
    determinar_turno_y_ventana,
    ventana_para_turno,
)
from app.modules.pagos.infrastructure.repositorio_caja_sql import RepositorioCajaSQL


class ServicioCaja:
    """Orquesta la consolidación de ingresos por turno y cierres de caja."""

    def __init__(self, uow: UnidadDeTrabajo, repo: RepositorioCajaSQL) -> None:
        self.uow = uow
        self.repo = repo

    async def consolidar_turno(
        self,
        fecha: date | None = None,
        turno: TurnoCierre | None = None,
        momento_referencia: datetime | None = None,
    ) -> ConsolidadoTurno:
        """Consolida los ingresos y egresos de un turno específico o del turno activo actual."""
        if fecha is not None and turno is not None:
            fecha_caja = fecha
            turno_caja = turno
            desde, hasta = ventana_para_turno(fecha_caja, turno_caja)
        else:
            turno_caja, fecha_caja, desde, hasta = determinar_turno_y_ventana(momento_referencia)

        totales = await self.repo.consolidar_totales_turno(desde, hasta)
        desglose = await self.repo.desglose_por_metodo(desde, hasta)

        return ConsolidadoTurno(
            fecha=fecha_caja,
            turno=turno_caja,
            desde=desde,
            hasta=hasta,
            total_efectivo=totales["total_efectivo"],
            total_billeteras=totales["total_billeteras"],
            total_devoluciones=totales["total_devoluciones"],
            total_general=totales["total_general"],
            total_propinas=totales["total_propinas"],
            cantidad_pedidos=totales["cantidad_pedidos"],
            cantidad_pagos=totales["cantidad_pagos"],
            pagos_pendientes_conciliacion=totales["pagos_pendientes_conciliacion"],
            desglose_metodos=desglose,
        )

    async def generar_resumen_cierre(
        self,
        fecha: date | None = None,
        turno: TurnoCierre | None = None,
        generado_por: int | None = None,
        observaciones: str | None = None,
        momento_referencia: datetime | None = None,
        ip_cliente: str | None = None,
    ) -> CierreCaja:
        """Genera el cierre de caja del turno, totalizando operaciones y vinculando los pagos.

        - Determina la ventana contable (automática o por parámetros).
        - Verifica que el cierre no haya sido ya APROBADO.
        - Persiste el registro con estado PENDIENTE_APROBACION.
        - Asocia en lote todos los pagos del turno con el ID del cierre generado.
        - Registra la acción en la bitácora de auditoría.
        """
        if fecha is not None and turno is not None:
            fecha_caja = fecha
            turno_caja = turno
            desde, hasta = ventana_para_turno(fecha_caja, turno_caja)
        else:
            turno_caja, fecha_caja, desde, hasta = determinar_turno_y_ventana(momento_referencia)

        # Regla de negocio: si el turno ya fue aprobado, es inalterable
        existente = await self.repo.obtener_cierre_por_fecha_turno(fecha_caja, turno_caja)
        if existente and existente.es_aprobado:
            raise ReglaDeNegocio(
                f"El cierre de caja del turno {turno_caja.value} para el día {fecha_caja} ya fue aprobado y no puede reabrirse"
            )

        totales = await self.repo.consolidar_totales_turno(desde, hasta)

        cierre = await self.repo.crear_o_actualizar_cierre(
            fecha=fecha_caja,
            turno=turno_caja,
            total_efectivo=totales["total_efectivo"],
            total_billeteras=totales["total_billeteras"],
            total_devoluciones=totales["total_devoluciones"],
            total_general=totales["total_general"],
            cantidad_pedidos=totales["cantidad_pedidos"],
            generado_por=generado_por,
            observaciones=observaciones,
        )

        # Vinculación atómica en lote de los pagos del período al cierre_caja_id
        await self.repo.vincular_pagos_al_cierre(cierre.id, desde, hasta)

        await auditoria.registrar(
            self.uow,
            accion=AccionesPagos.CIERRE_GENERADO,
            entidad="cierre_caja",
            entidad_id=cierre.id,
            usuario_id=generado_por,
            ip=ip_cliente,
            datos={
                "fecha": str(cierre.fecha),
                "turno": cierre.turno.value,
                "total_general": str(cierre.total_general),
                "total_efectivo": str(cierre.total_efectivo),
                "total_billeteras": str(cierre.total_billeteras),
                "cantidad_pedidos": cierre.cantidad_pedidos,
                "estado": cierre.estado.value,
            },
        )

        return cierre

    async def obtener_cierre(self, cierre_id: int) -> CierreCaja:
        """Recupera un cierre por su identificador primario."""
        cierre = await self.repo.obtener_cierre_por_id(cierre_id)
        if cierre is None:
            raise NoEncontrado(f"Cierre de caja #{cierre_id} no encontrado")
        return cierre

    async def listar_cierres(
        self,
        desde_fecha: date | None = None,
        hasta_fecha: date | None = None,
        estado: EstadoCierre | None = None,
    ) -> list[CierreCaja]:
        """Obtiene la lista de cierres registrados con filtros opcionales."""
        return await self.repo.listar_cierres(
            desde_fecha=desde_fecha,
            hasta_fecha=hasta_fecha,
            estado=estado,
        )

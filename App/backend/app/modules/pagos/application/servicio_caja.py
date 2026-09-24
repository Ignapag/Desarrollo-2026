"""Servicio de aplicación para consolidación de ingresos y arqueo de caja."""

from __future__ import annotations

from datetime import date, datetime

from app.core.db import UnidadDeTrabajo
from app.core.errores import NoEncontrado
from app.modules.pagos.domain.entidades import (
    CierreCaja,
    ConsolidadoTurno,
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

    async def verificar_cierre_existente(
        self, fecha: date, turno: TurnoCierre
    ) -> CierreCaja | None:
        """Verifica si el turno ya fue cerrado formalmente."""
        return await self.repo.obtener_cierre_por_fecha_turno(fecha, turno)

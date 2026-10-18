"""Servicio de aplicación para consolidación de ingresos y arqueo de caja."""

from __future__ import annotations

from datetime import date, datetime

from app.core import auditoria
from app.core.db import UnidadDeTrabajo
from app.errores import NoEncontrado, ReglaDeNegocio
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

    async def desvincular_no_conciliados(
        self,
        cierre: CierreCaja,
        actor: int | None,
        ip: str | None = None,
    ) -> None:
        """Retira pertenencias históricas que nunca representaron dinero recibido.

        Requiere el lock del turno. Un aprobado solo admite retirar pendientes
        cuando su snapshot ya coincide con los conciliados; no se reparan aquí
        cierres históricos que contabilizaron fondos todavía inexistentes.
        """
        if cierre.es_aprobado:
            corte = await self.repo.capturar_cierre_vinculado(cierre.id)
            if not self._coinciden_totales(cierre, corte.totales):
                raise ReglaDeNegocio(
                    "El cierre aprobado histórico tiene totales inconsistentes; "
                    "requiere revisión contable antes de conciliar sus pendientes"
                )
        for pago_id in await self.repo.desvincular_no_conciliados(cierre.id):
            await auditoria.registrar(
                self.uow,
                accion="PAGO_DESVINCULADO_CIERRE",
                entidad="pago",
                entidad_id=pago_id,
                usuario_id=actor,
                ip=ip,
                datos={
                    "cierre_anterior_id": cierre.id,
                    "cierre_nuevo_id": None,
                    "estado_cierre": cierre.estado.value,
                    "motivo": "Movimiento no conciliado excluido del snapshot de caja",
                },
            )

    @staticmethod
    def _coinciden_totales(cierre: CierreCaja, totales: dict) -> bool:
        return all(
            totales[campo] == getattr(cierre, campo)
            for campo in (
                "total_efectivo",
                "total_billeteras",
                "total_devoluciones",
                "total_general",
                "cantidad_pedidos",
            )
        )

    async def bloquear_cierres_de_pagos(self, pago_ids: list[int]) -> None:
        await self.repo.bloquear_cierres_de_pagos(pago_ids)

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

        corte = await self.repo.capturar_turno(desde, hasta)
        totales = corte.totales

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
            desglose_metodos=corte.desglose,
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
        - Captura conciliados sin otro cierre hasta el fin del turno, incluidos anteriores.
        - Totaliza y vincula exactamente ese conjunto de pagos, bloqueado por ID.
        - Registra la acción en la bitácora de auditoría.
        """
        if fecha is not None and turno is not None:
            fecha_caja = fecha
            turno_caja = turno
            _, hasta = ventana_para_turno(fecha_caja, turno_caja)
        else:
            turno_caja, fecha_caja, _, hasta = determinar_turno_y_ventana(momento_referencia)

        await self.repo.bloquear_turno(fecha_caja, turno_caja)
        # Regla de negocio: si el turno ya fue aprobado, es inalterable
        existente = await self.repo.obtener_cierre_por_fecha_turno(fecha_caja, turno_caja)
        if existente and existente.es_aprobado:
            raise ReglaDeNegocio(
                f"El cierre de caja del turno {turno_caja.value} para el día {fecha_caja} "
                "ya fue aprobado y no puede reabrirse"
            )

        if existente:
            await self.desvincular_no_conciliados(existente, generado_por, ip_cliente)
        corte = await self.repo.capturar_pagos_cierre(existente.id if existente else None, hasta)
        totales = corte.totales

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

        # Totales y vínculos siempre provienen del mismo conjunto, bloqueado en la captura.
        vinculados = await self.repo.vincular_pagos_al_cierre(cierre.id, corte.pago_ids)
        if vinculados != len(corte.pago_ids):
            raise ReglaDeNegocio("El conjunto de pagos del cierre cambió durante la generación")

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
                "cantidad_pagos": len(corte.pago_ids),
                "criterio_corte": "CONCILIADO sin otro cierre hasta fin de turno, con arrastre",
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

    async def aprobar_y_bloquear_cierre(
        self,
        cierre_id: int,
        aprobado_por: int,
        observaciones: str | None = None,
        ip_cliente: str | None = None,
    ) -> CierreCaja:
        """Aprueba formalmente un cierre de caja, haciéndolo inalterable (regla del alcance).

        - Valida que el cierre exista.
        - Verifica que no haya sido ya aprobado previamente.
        - Asienta el estado APROBADO, timestamp de aprobación y usuario responsable.
        - Registra la acción crítica en auditoría (RNF-09).
        """
        cierre_actual = await self.repo.obtener_cierre_por_id(cierre_id)
        if cierre_actual is None:
            raise NoEncontrado(f"Cierre de caja #{cierre_id} no encontrado")

        await self.repo.bloquear_turno(cierre_actual.fecha, cierre_actual.turno)
        cierre_actual = await self.repo.obtener_cierre_por_id(cierre_id)

        if cierre_actual.es_aprobado:
            raise ReglaDeNegocio(
                f"El cierre de caja #{cierre_id} ya fue aprobado previamente y es inalterable"
            )

        await self.desvincular_no_conciliados(cierre_actual, aprobado_por, ip_cliente)
        corte = await self.repo.capturar_cierre_vinculado(cierre_id)
        if not self._coinciden_totales(cierre_actual, corte.totales):
            raise ReglaDeNegocio("Los totales del cierre no coinciden con sus pagos vinculados")

        cierre_aprobado = await self.repo.aprobar_cierre(
            cierre_id=cierre_id,
            aprobado_por=aprobado_por,
            observaciones=observaciones,
        )
        if cierre_aprobado is None:
            raise ReglaDeNegocio(f"No se pudo aprobar el cierre de caja #{cierre_id}")

        await auditoria.registrar(
            self.uow,
            accion=AccionesPagos.CIERRE_APROBADO,
            entidad="cierre_caja",
            entidad_id=cierre_id,
            usuario_id=aprobado_por,
            ip=ip_cliente,
            datos={
                "cierre_id": cierre_id,
                "fecha": str(cierre_aprobado.fecha),
                "turno": cierre_aprobado.turno.value,
                "total_general": str(cierre_aprobado.total_general),
                "aprobado_por": aprobado_por,
                "observaciones": observaciones,
            },
        )

        return cierre_aprobado

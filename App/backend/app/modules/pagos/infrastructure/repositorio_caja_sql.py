"""Repositorio de acceso a datos para consolidación y cierre de caja."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.core.db import UnidadDeTrabajo
from app.errores import ReglaDeNegocio
from app.modules.pagos.domain.entidades import (
    CierreCaja,
    CorteCaja,
    EstadoCierre,
    TotalesMetodoPago,
    TurnoCierre,
    calcular_corte_caja,
)
from app.modules.pagos.infrastructure.repositorio_sql import _mapear_pago


def _mapear_cierre(fila: dict) -> CierreCaja:
    return CierreCaja(
        id=fila["id"],
        fecha=fila["fecha"],
        turno=TurnoCierre(fila["turno"]),
        abierto_en=fila["abierto_en"],
        cerrado_en=fila.get("cerrado_en"),
        total_efectivo=Decimal(str(fila["total_efectivo"])),
        total_billeteras=Decimal(str(fila["total_billeteras"])),
        total_devoluciones=Decimal(str(fila["total_devoluciones"])),
        total_general=Decimal(str(fila["total_general"])),
        cantidad_pedidos=int(fila["cantidad_pedidos"]),
        estado=EstadoCierre(fila["estado"]),
        generado_por=fila.get("generado_por"),
        aprobado_por=fila.get("aprobado_por"),
        aprobado_en=fila.get("aprobado_en"),
        observaciones=fila.get("observaciones"),
    )


class RepositorioCajaSQL:
    def __init__(self, uow: UnidadDeTrabajo) -> None:
        self.uow = uow

    async def bloquear_turno(self, fecha: date, turno: TurnoCierre) -> None:
        """Generación y aprobación del mismo turno preceden a cualquier lock de pago."""
        await self.uow.ejecutar(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"caja:{fecha.isoformat()}:{turno.value}",),
        )

    async def capturar_turno(self, desde: datetime, hasta: datetime) -> CorteCaja:
        filas = await self.uow.todos(
            "SELECT id,pedido_id,cierre_caja_id,tipo,metodo_pago,monto,propina,estado,"
            "referencia_externa,registrado_por,registrado_en,conciliado_en,motivo "
            "FROM pago WHERE COALESCE(conciliado_en, registrado_en) >= %s "
            "AND COALESCE(conciliado_en, registrado_en) <= %s AND estado <> 'ANULADO' "
            "ORDER BY id",
            (desde, hasta),
        )
        return calcular_corte_caja([_mapear_pago(f) for f in filas])

    async def capturar_pagos_cierre(self, cierre_id: int | None, hasta: datetime) -> CorteCaja:
        """Corte fijo con arrastre de conciliados anteriores que aún no tienen cierre.

        Bloquea solo los movimientos capturados, por ID ascendente. Otro turno
        que compita por ellos espera y reevalúa su pertenencia tras el commit.
        Los pagos o acreditaciones posteriores al SELECT esperan al siguiente corte.
        Los conciliados ya vinculados se conservan aunque su acreditación haya
        ocurrido después del fin del turno, como permitía el circuito histórico.
        """
        filas = await self.uow.todos(
            "SELECT id,pedido_id,cierre_caja_id,tipo,metodo_pago,monto,propina,estado,"
            "referencia_externa,registrado_por,registrado_en,conciliado_en,motivo "
            "FROM pago WHERE estado='CONCILIADO' "
            "AND (cierre_caja_id=%s OR (cierre_caja_id IS NULL "
            "AND COALESCE(conciliado_en, registrado_en) <= %s)) ORDER BY id FOR UPDATE",
            (cierre_id, hasta),
        )
        return calcular_corte_caja([_mapear_pago(f) for f in filas])

    async def capturar_cierre_vinculado(self, cierre_id: int) -> CorteCaja:
        filas = await self.uow.todos(
            "SELECT id,pedido_id,cierre_caja_id,tipo,metodo_pago,monto,propina,estado,"
            "referencia_externa,registrado_por,registrado_en,conciliado_en,motivo "
            "FROM pago WHERE cierre_caja_id=%s ORDER BY id",
            (cierre_id,),
        )
        return calcular_corte_caja([_mapear_pago(f) for f in filas])

    async def parametro(self, clave: str, por_defecto: str) -> str:
        """Lee un parámetro de configuración desde la base de datos."""
        valor = await self.uow.valor("SELECT valor FROM parametro WHERE clave = %s", (clave,))
        return valor if valor is not None else por_defecto

    async def consolidar_totales_turno(self, desde: datetime, hasta: datetime) -> dict:
        return (await self.capturar_turno(desde, hasta)).totales

    async def desglose_por_metodo(
        self,
        desde: datetime,
        hasta: datetime,
    ) -> list[TotalesMetodoPago]:
        return (await self.capturar_turno(desde, hasta)).desglose

    async def obtener_cierre_por_fecha_turno(
        self, fecha: date, turno: TurnoCierre
    ) -> CierreCaja | None:
        """Busca si ya existe un registro de cierre formal para la fecha y turno."""
        sql = """
            SELECT id, fecha, turno, abierto_en, cerrado_en, total_efectivo,
                   total_billeteras, total_devoluciones, total_general,
                   cantidad_pedidos, estado, generado_por, aprobado_por,
                   aprobado_en, observaciones
            FROM cierre_caja
            WHERE fecha = %s AND turno = %s
        """
        fila = await self.uow.uno(sql, (fecha, turno.value))
        return _mapear_cierre(fila) if fila else None

    async def crear_o_actualizar_cierre(
        self,
        fecha: date,
        turno: TurnoCierre,
        total_efectivo: Decimal,
        total_billeteras: Decimal,
        total_devoluciones: Decimal,
        total_general: Decimal,
        cantidad_pedidos: int,
        generado_por: int | None = None,
        observaciones: str | None = None,
    ) -> CierreCaja:
        """Inserta o recalcula el resumen del cierre de caja en estado PENDIENTE_APROBACION.

        Si ya existía un cierre aprobado, no permite modificación alguna.
        """
        sql = """
            INSERT INTO cierre_caja (
                fecha, turno, cerrado_en, total_efectivo, total_billeteras,
                total_devoluciones, total_general, cantidad_pedidos,
                estado, generado_por, observaciones
            )
            VALUES (%s, %s, now(), %s, %s, %s, %s, %s, 'PENDIENTE_APROBACION', %s, %s)
            ON CONFLICT (fecha, turno) DO UPDATE
            SET cerrado_en = now(),
                total_efectivo = EXCLUDED.total_efectivo,
                total_billeteras = EXCLUDED.total_billeteras,
                total_devoluciones = EXCLUDED.total_devoluciones,
                total_general = EXCLUDED.total_general,
                cantidad_pedidos = EXCLUDED.cantidad_pedidos,
                estado = 'PENDIENTE_APROBACION',
                generado_por = COALESCE(EXCLUDED.generado_por, cierre_caja.generado_por),
                observaciones = COALESCE(EXCLUDED.observaciones, cierre_caja.observaciones)
            WHERE cierre_caja.estado <> 'APROBADO'
            RETURNING id, fecha, turno, abierto_en, cerrado_en, total_efectivo,
                      total_billeteras, total_devoluciones, total_general,
                      cantidad_pedidos, estado, generado_por, aprobado_por,
                      aprobado_en, observaciones
        """
        fila = await self.uow.uno(
            sql,
            (
                fecha,
                turno.value,
                total_efectivo,
                total_billeteras,
                total_devoluciones,
                total_general,
                cantidad_pedidos,
                generado_por,
                observaciones,
            ),
        )
        if fila is None:
            raise ReglaDeNegocio(
                f"El cierre de caja para {fecha} turno {turno.value} "
                "ya fue APROBADO y es inalterable"
            )
        return _mapear_cierre(fila)

    async def vincular_pagos_al_cierre(self, cierre_id: int, pago_ids: list[int]) -> int:
        return await self.uow.ejecutar(
            "UPDATE pago SET cierre_caja_id=%s WHERE id=ANY(%s) "
            "AND estado='CONCILIADO' AND (cierre_caja_id IS NULL OR cierre_caja_id=%s)",
            (cierre_id, pago_ids, cierre_id),
        )

    async def obtener_cierre_por_id(self, cierre_id: int) -> CierreCaja | None:
        """Recupera un cierre por su ID primario."""
        sql = """
            SELECT id, fecha, turno, abierto_en, cerrado_en, total_efectivo,
                   total_billeteras, total_devoluciones, total_general,
                   cantidad_pedidos, estado, generado_por, aprobado_por,
                   aprobado_en, observaciones
            FROM cierre_caja
            WHERE id = %s
        """
        fila = await self.uow.uno(sql, (cierre_id,))
        return _mapear_cierre(fila) if fila else None

    async def listar_cierres(
        self,
        desde_fecha: date | None = None,
        hasta_fecha: date | None = None,
        estado: EstadoCierre | None = None,
    ) -> list[CierreCaja]:
        """Lista el historial de cierres ordenados cronológicamente."""
        sql = """
            SELECT id, fecha, turno, abierto_en, cerrado_en, total_efectivo,
                   total_billeteras, total_devoluciones, total_general,
                   cantidad_pedidos, estado, generado_por, aprobado_por,
                   aprobado_en, observaciones
            FROM cierre_caja
            WHERE (%s::date IS NULL OR fecha >= %s)
              AND (%s::date IS NULL OR fecha <= %s)
              AND (%s::text IS NULL OR estado = %s)
            ORDER BY fecha DESC, turno DESC
        """
        filas = await self.uow.todos(
            sql,
            (
                desde_fecha,
                desde_fecha,
                hasta_fecha,
                hasta_fecha,
                estado.value if estado else None,
                estado.value if estado else None,
            ),
        )
        return [_mapear_cierre(f) for f in filas]

    async def aprobar_cierre(
        self,
        cierre_id: int,
        aprobado_por: int,
        observaciones: str | None = None,
    ) -> CierreCaja | None:
        """Aprueba formalmente un cierre de caja, fijando timestamp y responsable.

        Una vez aprobado, el trigger protege_cierre_aprobado bloquea cualquier
        modificación posterior garantizando inalterabilidad.
        """
        sql = """
            UPDATE cierre_caja
            SET estado = 'APROBADO',
                aprobado_por = %s,
                aprobado_en = now(),
                observaciones = COALESCE(%s, observaciones)
            WHERE id = %s AND estado <> 'APROBADO'
            RETURNING id, fecha, turno, abierto_en, cerrado_en, total_efectivo,
                      total_billeteras, total_devoluciones, total_general,
                      cantidad_pedidos, estado, generado_por, aprobado_por,
                      aprobado_en, observaciones
        """
        fila = await self.uow.uno(sql, (aprobado_por, observaciones, cierre_id))
        return _mapear_cierre(fila) if fila else None

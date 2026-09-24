"""Repositorio de acceso a datos para consolidación y cierre de caja."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.core.db import UnidadDeTrabajo
from app.modules.pagos.domain.entidades import (
    CierreCaja,
    EstadoCierre,
    MetodoPago,
    TotalesMetodoPago,
    TurnoCierre,
)


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

    async def parametro(self, clave: str, por_defecto: str) -> str:
        """Lee un parámetro de configuración desde la base de datos."""
        valor = await self.uow.valor(
            "SELECT valor FROM parametro WHERE clave = %s", (clave,)
        )
        return valor if valor is not None else por_defecto

    async def consolidar_totales_turno(self, desde: datetime, hasta: datetime) -> dict:
        """Calcula los totales agrupados por tipo y método en la ventana de tiempo dada."""
        sql = """
            SELECT
                COALESCE(SUM(CASE WHEN tipo = 'COBRO' AND metodo_pago = 'EFECTIVO' THEN monto ELSE 0 END), 0) AS total_efectivo,
                COALESCE(SUM(CASE WHEN tipo = 'COBRO' AND metodo_pago <> 'EFECTIVO' THEN monto ELSE 0 END), 0) AS total_billeteras,
                COALESCE(SUM(CASE WHEN tipo = 'DEVOLUCION' THEN monto ELSE 0 END), 0) AS total_devoluciones,
                COALESCE(SUM(CASE WHEN tipo = 'COBRO' THEN monto ELSE -monto END), 0) AS total_general,
                COALESCE(SUM(propina), 0) AS total_propinas,
                COUNT(DISTINCT pedido_id) FILTER (WHERE tipo = 'COBRO') AS cantidad_pedidos,
                COUNT(id) AS cantidad_pagos,
                COUNT(id) FILTER (WHERE estado = 'PENDIENTE') AS pagos_pendientes_conciliacion
            FROM pago
            WHERE registrado_en >= %s
              AND registrado_en <= %s
              AND estado <> 'ANULADO'
        """
        fila = await self.uow.uno(sql, (desde, hasta))
        if fila is None:
            return {
                "total_efectivo": Decimal("0.00"),
                "total_billeteras": Decimal("0.00"),
                "total_devoluciones": Decimal("0.00"),
                "total_general": Decimal("0.00"),
                "total_propinas": Decimal("0.00"),
                "cantidad_pedidos": 0,
                "cantidad_pagos": 0,
                "pagos_pendientes_conciliacion": 0,
            }
        return {
            "total_efectivo": Decimal(str(fila["total_efectivo"])),
            "total_billeteras": Decimal(str(fila["total_billeteras"])),
            "total_devoluciones": Decimal(str(fila["total_devoluciones"])),
            "total_general": Decimal(str(fila["total_general"])),
            "total_propinas": Decimal(str(fila["total_propinas"])),
            "cantidad_pedidos": int(fila["cantidad_pedidos"]),
            "cantidad_pagos": int(fila["cantidad_pagos"]),
            "pagos_pendientes_conciliacion": int(fila["pagos_pendientes_conciliacion"]),
        }

    async def desglose_por_metodo(self, desde: datetime, hasta: datetime) -> list[TotalesMetodoPago]:
        """Obtiene el monto y cantidad acumulada para cada método de pago."""
        sql = """
            SELECT
                metodo_pago,
                COALESCE(SUM(CASE WHEN tipo = 'COBRO' THEN monto ELSE -monto END), 0) AS total,
                COUNT(id) AS cantidad
            FROM pago
            WHERE registrado_en >= %s
              AND registrado_en <= %s
              AND estado <> 'ANULADO'
            GROUP BY metodo_pago
            ORDER BY total DESC
        """
        filas = await self.uow.todos(sql, (desde, hasta))
        return [
            TotalesMetodoPago(
                metodo_pago=MetodoPago(f["metodo_pago"]),
                total=Decimal(str(f["total"])),
                cantidad=int(f["cantidad"]),
            )
            for f in filas
        ]

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

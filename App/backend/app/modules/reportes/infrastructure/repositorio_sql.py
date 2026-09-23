"""Agregaciones SQL de pedidos y pagos; nunca une items con pagos."""

from __future__ import annotations

from datetime import date

from app.core.db import UnidadDeTrabajo
from app.modules.reportes.domain.reglas import ESTADOS_VENTA, ZONA_NEGOCIO


class RepositorioReportesSQL:
    def __init__(self, uow: UnidadDeTrabajo) -> None:
        self.uow = uow

    async def resumen_pedidos(self) -> dict:
        return await self.uow.uno(
            """
            WITH ahora AS (
                SELECT now() AS actualizado_en,
                       (now() AT TIME ZONE %s)::date AS hoy
            )
            SELECT a.actualizado_en,
                   count(p.id) FILTER (
                       WHERE (p.confirmado_en AT TIME ZONE %s)::date = a.hoy
                   ) AS pedidos_dia,
                   count(p.id) FILTER (
                       WHERE date_trunc('week', p.confirmado_en AT TIME ZONE %s)
                             = date_trunc('week', a.hoy::timestamp)
                   ) AS pedidos_semana,
                   count(p.id) FILTER (
                       WHERE date_trunc('month', p.confirmado_en AT TIME ZONE %s)
                             = date_trunc('month', a.hoy::timestamp)
                   ) AS pedidos_mes
            FROM ahora a
            LEFT JOIN pedido p ON p.estado = ANY(%s)
                              AND p.confirmado_en IS NOT NULL
            GROUP BY a.actualizado_en, a.hoy
            """,
            (ZONA_NEGOCIO, ZONA_NEGOCIO, ZONA_NEGOCIO, ZONA_NEGOCIO, list(ESTADOS_VENTA)),
        )

    async def ventas(
        self,
        desde: date,
        hasta: date,
        agrupacion_sql: str,
        categoria_id: int | None,
        producto_id: int | None,
        *,
        incluir_montos: bool,
    ) -> list[dict]:
        # Ambas variantes son SQL fijo; el Administrador ni siquiera consulta montos.
        monto = ", SUM(pi.subtotal) AS monto_total" if incluir_montos else ""
        return await self.uow.todos(
            """
            SELECT date_trunc(%s, p.confirmado_en AT TIME ZONE %s)::date AS periodo,
                   pr.id AS producto_id, pr.nombre AS producto,
                   c.nombre AS categoria, SUM(pi.cantidad) AS cantidad_vendida,
                   COUNT(DISTINCT p.id) AS cantidad_pedidos
            """
            + monto
            + """
            FROM pedido_item pi
            JOIN pedido p ON p.id = pi.pedido_id
            JOIN producto pr ON pr.id = pi.producto_id
            JOIN categoria c ON c.id = pr.categoria_id
            WHERE p.estado = ANY(%s) AND p.confirmado_en IS NOT NULL
              AND (p.confirmado_en AT TIME ZONE %s)::date >= %s
              AND (p.confirmado_en AT TIME ZONE %s)::date <= %s
              AND (%s IS NULL OR c.id = %s)
              AND (%s IS NULL OR pr.id = %s)
            GROUP BY periodo, pr.id, pr.nombre, c.nombre
            """,
            (
                agrupacion_sql,
                ZONA_NEGOCIO,
                list(ESTADOS_VENTA),
                ZONA_NEGOCIO,
                desde,
                ZONA_NEGOCIO,
                hasta,
                categoria_id,
                categoria_id,
                producto_id,
                producto_id,
            ),
        )

    async def pagos_por_metodo(self, desde: date, hasta: date) -> list[dict]:
        return await self.uow.todos(
            """
            SELECT metodo_pago,
                   SUM(CASE WHEN tipo = 'COBRO' THEN monto
                            ELSE -monto END) AS ingreso_neto
            FROM pago
            WHERE estado = 'CONCILIADO' AND conciliado_en IS NOT NULL
              AND (conciliado_en AT TIME ZONE %s)::date >= %s
              AND (conciliado_en AT TIME ZONE %s)::date <= %s
            GROUP BY metodo_pago
            ORDER BY metodo_pago
            """,
            (ZONA_NEGOCIO, desde, ZONA_NEGOCIO, hasta),
        )

    async def rentabilidad(
        self,
        desde: date,
        hasta: date,
        categoria_id: int | None,
        producto_id: int | None,
    ) -> list[dict]:
        return await self.uow.todos(
            """
            SELECT pr.id AS producto_id, pr.nombre AS producto,
                   SUM(pi.cantidad) AS unidades_vendidas,
                   SUM(pi.subtotal) AS ingreso_estimado,
                   SUM(pi.cantidad) * pc.costo_insumos AS costo_estimado
            FROM pedido_item pi
            JOIN pedido p ON p.id = pi.pedido_id
            JOIN producto pr ON pr.id = pi.producto_id
            JOIN producto_costo pc ON pc.producto_id = pr.id
            WHERE p.estado = ANY(%s) AND p.confirmado_en IS NOT NULL
              AND (p.confirmado_en AT TIME ZONE %s)::date >= %s
              AND (p.confirmado_en AT TIME ZONE %s)::date <= %s
              AND (%s IS NULL OR pr.categoria_id = %s)
              AND (%s IS NULL OR pr.id = %s)
            GROUP BY pr.id, pr.nombre, pc.costo_insumos
            ORDER BY pr.nombre, pr.id
            """,
            (
                list(ESTADOS_VENTA),
                ZONA_NEGOCIO,
                desde,
                ZONA_NEGOCIO,
                hasta,
                categoria_id,
                categoria_id,
                producto_id,
                producto_id,
            ),
        )

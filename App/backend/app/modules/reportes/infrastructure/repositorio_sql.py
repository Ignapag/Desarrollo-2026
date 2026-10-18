"""Agregaciones SQL de pedidos y pagos; nunca une items con pagos."""

from __future__ import annotations

from datetime import date

from app.core.db import UnidadDeTrabajo
from app.modules.reportes.domain.reglas import ESTADOS_VENTA, ZONA_NEGOCIO


class RepositorioReportesSQL:
    def __init__(self, uow: UnidadDeTrabajo) -> None:
        self.uow = uow

    async def clientes(self, *, q: str | None, limite: int, desplazamiento: int) -> dict:
        # La última actividad usa el índice de pedidos por cliente. Los conteos y
        # las zonas se agregan sólo para los clientes de la página solicitada.
        filas = await self.uow.todos(
            """
            WITH candidatos AS MATERIALIZED (
                SELECT c.id,
                       COALESCE(NULLIF(concat_ws(' ', u.nombre, u.apellido), ''),
                                c.nombre) AS nombre,
                       c.telefono_whatsapp AS telefono,
                       ultimo.creado_en AS ultimo_pedido_en
                FROM cliente c
                LEFT JOIN usuario u ON u.id = c.usuario_id
                LEFT JOIN LATERAL (
                    SELECT p.creado_en FROM pedido p WHERE p.cliente_id = c.id
                    ORDER BY p.creado_en DESC LIMIT 1
                ) ultimo ON true
                WHERE (%s::text IS NULL OR
                       concat_ws(' ', c.nombre, u.nombre, u.apellido,
                                 c.telefono_whatsapp) ILIKE '%%' || %s || '%%')
            ), pagina AS MATERIALIZED (
                SELECT * FROM candidatos
                ORDER BY ultimo_pedido_en DESC NULLS LAST, id DESC
                LIMIT %s OFFSET %s
            )
            SELECT totales.total, c.id, c.nombre, c.telefono,
                   resumen.pedidos_count, resumen.primer_pedido_en,
                   c.ultimo_pedido_en, zona.zona_frecuente
            FROM (SELECT count(*) AS total FROM candidatos) totales
            LEFT JOIN pagina c ON true
            LEFT JOIN LATERAL (
                SELECT count(*) AS pedidos_count, min(p.creado_en) AS primer_pedido_en
                FROM pedido p WHERE p.cliente_id = c.id
            ) resumen ON c.id IS NOT NULL
            LEFT JOIN LATERAL (
                SELECT CASE WHEN p.tipo_entrega = 'RETIRO' THEN 'Retiro en local'
                            ELSE COALESCE(ze.nombre, zd.nombre, NULLIF(btrim(d.localidad), ''))
                       END AS zona_frecuente
                FROM pedido p
                LEFT JOIN direccion d ON d.id = p.direccion_id
                LEFT JOIN zona_cobertura zd ON zd.id = d.zona_id
                LEFT JOIN envio e ON e.pedido_id = p.id
                LEFT JOIN zona_cobertura ze ON ze.id = e.zona_id
                WHERE p.cliente_id = c.id
                GROUP BY zona_frecuente
                HAVING CASE WHEN p.tipo_entrega = 'RETIRO' THEN 'Retiro en local'
                            ELSE COALESCE(ze.nombre, zd.nombre, NULLIF(btrim(d.localidad), ''))
                       END IS NOT NULL
                ORDER BY count(*) DESC, max(p.creado_en) DESC, zona_frecuente
                LIMIT 1
            ) zona ON c.id IS NOT NULL
            ORDER BY c.ultimo_pedido_en DESC NULLS LAST, c.id DESC
            """,
            (q, q, limite, desplazamiento),
        )
        total = filas[0]["total"]
        clientes = [
            {clave: valor for clave, valor in fila.items() if clave != "total"}
            for fila in filas
            if fila["id"] is not None
        ]
        return {
            "clientes": clientes,
            "total": total,
            "limite": limite,
            "desplazamiento": desplazamiento,
        }

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
        sql_sin_montos = """
            SELECT date_trunc(%s, p.confirmado_en AT TIME ZONE %s)::date AS periodo,
                   pr.id AS producto_id, pr.nombre AS producto,
                   c.nombre AS categoria, SUM(pi.cantidad) AS cantidad_vendida,
                   COUNT(DISTINCT p.id) AS cantidad_pedidos
            FROM pedido_item pi
            JOIN pedido p ON p.id = pi.pedido_id
            JOIN producto pr ON pr.id = pi.producto_id
            JOIN categoria c ON c.id = pr.categoria_id
            WHERE p.estado = ANY(%s) AND p.confirmado_en IS NOT NULL
              AND (p.confirmado_en AT TIME ZONE %s)::date >= %s
              AND (p.confirmado_en AT TIME ZONE %s)::date <= %s
              AND (%s::bigint IS NULL OR c.id = %s)
              AND (%s::bigint IS NULL OR pr.id = %s)
            GROUP BY periodo, pr.id, pr.nombre, c.nombre
        """
        sql_con_montos = """
            SELECT date_trunc(%s, p.confirmado_en AT TIME ZONE %s)::date AS periodo,
                   pr.id AS producto_id, pr.nombre AS producto,
                   c.nombre AS categoria, SUM(pi.cantidad) AS cantidad_vendida,
                   COUNT(DISTINCT p.id) AS cantidad_pedidos,
                   SUM(pi.subtotal) AS monto_total
            FROM pedido_item pi
            JOIN pedido p ON p.id = pi.pedido_id
            JOIN producto pr ON pr.id = pi.producto_id
            JOIN categoria c ON c.id = pr.categoria_id
            WHERE p.estado = ANY(%s) AND p.confirmado_en IS NOT NULL
              AND (p.confirmado_en AT TIME ZONE %s)::date >= %s
              AND (p.confirmado_en AT TIME ZONE %s)::date <= %s
              AND (%s::bigint IS NULL OR c.id = %s)
              AND (%s::bigint IS NULL OR pr.id = %s)
            GROUP BY periodo, pr.id, pr.nombre, c.nombre
        """
        return await self.uow.todos(
            sql_con_montos if incluir_montos else sql_sin_montos,
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
              AND (%s::bigint IS NULL OR pr.categoria_id = %s)
              AND (%s::bigint IS NULL OR pr.id = %s)
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

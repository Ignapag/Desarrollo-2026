"""Consultas de stock sobre las tablas existentes, sin ORM."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.db import UnidadDeTrabajo
from app.modules.stock.domain.entidades import DatosIngrediente, nivel_stock


class RepositorioStockSQL:
    def __init__(self, uow: UnidadDeTrabajo) -> None:
        self.uow = uow

    async def listar(
        self,
        *,
        nombre: str | None,
        responsable_id: int | None,
        activo: bool | None,
        nivel: str | None,
    ) -> list[dict]:
        return await self.uow.todos(
            """
            SELECT id, nombre, unidad_medida, cantidad_actual, umbral_minimo,
                   costo_unitario, dias_reposicion, responsable_id, responsable,
                   fecha_ultima_reposicion, activo, nivel,
                   EXISTS (
                       SELECT 1 FROM alerta_stock a
                       WHERE a.ingrediente_id = inventario.id AND a.estado = 'ACTIVA'
                   ) AS indicador_alerta
            FROM (
                SELECT i.*,
                       u.nombre || ' ' || u.apellido AS responsable,
                       CASE WHEN i.cantidad_actual = 0 THEN 'SIN_STOCK'
                            WHEN i.cantidad_actual <= i.umbral_minimo THEN 'BAJO_UMBRAL'
                            ELSE 'NORMAL' END AS nivel
                FROM ingrediente i
                LEFT JOIN usuario u ON u.id = i.responsable_id
            ) inventario
            WHERE (%s IS NULL OR nombre ILIKE '%%' || %s || '%%')
              AND (%s IS NULL OR responsable_id = %s)
              AND (%s IS NULL OR activo = %s)
              AND (%s IS NULL OR nivel = %s)
            ORDER BY nombre
            """,
            (nombre, nombre, responsable_id, responsable_id, activo, activo, nivel, nivel),
        )

    async def ingrediente(self, ingrediente_id: int, *, bloquear: bool = False) -> dict | None:
        return await self.uow.uno(
            "SELECT * FROM ingrediente WHERE id = %s" + (" FOR UPDATE" if bloquear else ""),
            (ingrediente_id,),
        )

    async def existe_nombre(self, nombre: str, *, excepto_id: int | None = None) -> bool:
        return bool(
            await self.uow.valor(
                "SELECT EXISTS (SELECT 1 FROM ingrediente "
                "WHERE lower(nombre) = lower(%s) AND (%s IS NULL OR id <> %s))",
                (nombre, excepto_id, excepto_id),
            )
        )

    async def responsable_valido(self, responsable_id: int) -> bool:
        return bool(
            await self.uow.valor(
                "SELECT EXISTS (SELECT 1 FROM usuario WHERE id = %s AND estado = 'ACTIVO')",
                (responsable_id,),
            )
        )

    async def asociado_a_producto_activo(self, ingrediente_id: int) -> bool:
        return bool(
            await self.uow.valor(
                """
                SELECT EXISTS (
                    SELECT 1 FROM producto_ingrediente pi
                    JOIN producto p ON p.id = pi.producto_id
                    WHERE pi.ingrediente_id = %s AND p.activo
                )
                """,
                (ingrediente_id,),
            )
        )

    async def crear(self, datos: DatosIngrediente) -> dict:
        fila = await self.uow.uno(
            """
            INSERT INTO ingrediente
                (nombre, unidad_medida, cantidad_actual, umbral_minimo, costo_unitario,
                 dias_reposicion, responsable_id, activo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
            """,
            (
                datos.nombre,
                datos.unidad_medida,
                datos.cantidad_actual,
                datos.umbral_minimo,
                datos.costo_unitario,
                list(datos.dias_reposicion),
                datos.responsable_id,
                datos.activo,
            ),
        )
        await self._sincronizar_alerta(fila)
        return fila

    async def modificar(self, ingrediente_id: int, datos: DatosIngrediente) -> dict:
        fila = await self.uow.uno(
            """
            UPDATE ingrediente SET nombre = %s, unidad_medida = %s, umbral_minimo = %s,
                   costo_unitario = %s, dias_reposicion = %s, responsable_id = %s,
                   activo = %s
            WHERE id = %s RETURNING *
            """,
            (
                datos.nombre,
                datos.unidad_medida,
                datos.umbral_minimo,
                datos.costo_unitario,
                list(datos.dias_reposicion),
                datos.responsable_id,
                datos.activo,
                ingrediente_id,
            ),
        )
        await self._sincronizar_alerta(fila)
        return fila

    async def reponer(
        self, ingrediente_id: int, cantidad: Decimal, *, usuario_id: int | None, origen: str
    ) -> dict:
        fila = await self.uow.uno(
            """
            UPDATE ingrediente
            SET cantidad_actual = cantidad_actual + %s,
                fecha_ultima_reposicion = now()
            WHERE id = %s RETURNING *
            """,
            (cantidad, ingrediente_id),
        )
        saldo_anterior = fila["cantidad_actual"] - cantidad
        movimiento = await self.uow.uno(
            """
            INSERT INTO movimiento_stock
                (ingrediente_id, tipo, cantidad, saldo_resultante, usuario_id, motivo)
            VALUES (%s, 'REPOSICION', %s, %s, %s, %s)
            RETURNING id, creado_en
            """,
            (ingrediente_id, cantidad, fila["cantidad_actual"], usuario_id, origen),
        )
        await self._sincronizar_alerta(fila, usuario_id=usuario_id)
        return {
            "ingrediente_id": ingrediente_id,
            "saldo_anterior": saldo_anterior,
            "cantidad": cantidad,
            "saldo_resultante": fila["cantidad_actual"],
            "fecha_ultima_reposicion": fila["fecha_ultima_reposicion"],
            "movimiento_id": movimiento["id"],
            "creado_en": movimiento["creado_en"],
        }

    async def historial(
        self,
        *,
        ingrediente_id: int | None,
        desde: date | None,
        hasta: date | None,
        tipo: str | None,
    ) -> list[dict]:
        return await self.uow.todos(
            """
            SELECT m.id, m.ingrediente_id, m.creado_en, m.tipo, m.cantidad,
                   CASE WHEN m.tipo IN ('CONSUMO', 'MERMA')
                        THEN m.saldo_resultante + m.cantidad
                        ELSE m.saldo_resultante - m.cantidad END AS saldo_anterior,
                   m.saldo_resultante, m.usuario_id,
                   COALESCE(u.nombre || ' ' || u.apellido, m.motivo) AS usuario_origen,
                   m.pedido_id, m.motivo
            FROM movimiento_stock m
            LEFT JOIN usuario u ON u.id = m.usuario_id
            WHERE (%s IS NULL OR m.ingrediente_id = %s)
              AND (%s IS NULL OR m.creado_en >= %s)
              AND (%s IS NULL OR m.creado_en < %s + INTERVAL '1 day')
              AND (%s IS NULL OR m.tipo = %s)
            ORDER BY m.creado_en DESC, m.id DESC
            """,
            (ingrediente_id, ingrediente_id, desde, desde, hasta, hasta, tipo, tipo),
        )

    async def _sincronizar_alerta(
        self, ingrediente: dict, *, usuario_id: int | None = None
    ) -> None:
        nivel_stock_actual = nivel_stock(
            ingrediente["cantidad_actual"], ingrediente["umbral_minimo"]
        )
        if not ingrediente["activo"] or nivel_stock_actual == "NORMAL":
            await self.uow.ejecutar(
                """
                UPDATE alerta_stock
                SET estado = 'RESUELTA', resuelta_en = now(), resuelta_por = %s
                WHERE ingrediente_id = %s AND estado = 'ACTIVA'
                """,
                (usuario_id, ingrediente["id"]),
            )
            return
        nivel = "AGOTADO" if nivel_stock_actual == "SIN_STOCK" else "BAJO"
        await self.uow.ejecutar(
            """
            INSERT INTO alerta_stock (ingrediente_id, nivel, cantidad_al_generar)
            VALUES (%s, %s, %s)
            ON CONFLICT (ingrediente_id) WHERE estado = 'ACTIVA'
            DO UPDATE SET nivel = EXCLUDED.nivel,
                          cantidad_al_generar = EXCLUDED.cantidad_al_generar
            """,
            (ingrediente["id"], nivel, ingrediente["cantidad_actual"]),
        )

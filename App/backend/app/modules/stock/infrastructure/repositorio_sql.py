"""Consultas de stock sobre las tablas existentes, sin ORM."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.db import UnidadDeTrabajo
from app.modules.stock.domain.entidades import DatosIngrediente, nivel_stock

# Proyeccion de IngredienteSalida; listado, alta y modificacion la comparten.
_CONSULTA_INVENTARIO = """
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
"""


class RepositorioStockSQL:
    """Acceso SQL a ingredientes, movimientos de stock y alertas."""

    def __init__(self, uow: UnidadDeTrabajo) -> None:
        """Recibe la unidad de trabajo cuya transacción comparten las consultas."""
        self.uow = uow

    async def reservas_antes_preparacion(self, pedido_id: int) -> list[dict] | None:
        """Devuelve el consumo neto por ingrediente si el pedido no llegó a cocina.

        Devuelve ``None`` cuando el pedido ya está en preparación o más avanzado.
        """
        pedido = await self.uow.uno(
            "SELECT estado, preparacion_en FROM pedido WHERE id=%s", (pedido_id,)
        )
        if pedido["estado"] not in {"PENDIENTE", "CONFIRMADO"} or pedido["preparacion_en"]:
            return None
        return await self.uow.todos(
            "SELECT ingrediente_id, sum(CASE WHEN tipo='CONSUMO' THEN cantidad "
            "WHEN tipo='DEVOLUCION' THEN -cantidad ELSE 0 END) AS cantidad "
            "FROM movimiento_stock WHERE pedido_id=%s GROUP BY ingrediente_id "
            "ORDER BY ingrediente_id",
            (pedido_id,),
        )

    async def bloquear_pedido(self, pedido_id: int) -> bool:
        """Bloquea la fila del pedido (FOR UPDATE); devuelve ``False`` si no existe."""
        return bool(
            await self.uow.uno("SELECT id FROM pedido WHERE id = %s FOR UPDATE", (pedido_id,))
        )

    async def consumo_existente(self, pedido_id: int) -> bool:
        """Indica si el pedido ya registró algún consumo de stock."""
        return bool(
            await self.uow.valor(
                "SELECT EXISTS (SELECT 1 FROM movimiento_stock "
                "WHERE pedido_id = %s AND tipo = 'CONSUMO')",
                (pedido_id,),
            )
        )

    async def pedido_tiene_opciones(self, pedido_id: int) -> bool:
        """Indica si algún ítem del pedido tiene opciones estructuradas."""
        return bool(
            await self.uow.valor(
                "SELECT EXISTS (SELECT 1 FROM pedido_item_opcion o "
                "JOIN pedido_item i ON i.id = o.pedido_item_id WHERE i.pedido_id = %s)",
                (pedido_id,),
            )
        )

    async def item_para_ajuste(self, pedido_id: int, item_id: int) -> dict | None:
        """Bloquea y devuelve un ítem del pedido con el estado del pedido."""
        return await self.uow.uno(
            "SELECT p.estado, p.preparacion_en, i.producto_id, i.cantidad, i.aclaraciones, "
            "i.receta_snapshot "
            "FROM pedido p JOIN pedido_item i ON i.pedido_id = p.id "
            "WHERE p.id = %s AND i.id = %s FOR UPDATE OF i",
            (pedido_id, item_id),
        )

    async def ajuste_existente(self, pedido_id: int, motivo: str) -> bool:
        """Indica si ya existe un movimiento del pedido con ese motivo (idempotencia)."""
        return bool(
            await self.uow.valor(
                "SELECT EXISTS (SELECT 1 FROM movimiento_stock "
                "WHERE pedido_id = %s AND motivo = %s)",
                (pedido_id, motivo),
            )
        )

    async def ingrediente_item_para_devolucion(
        self, pedido_id: int, item_id: int, nombre: str
    ) -> dict | None:
        """Busca un ingrediente de la receta del ítem por nombre y lo bloquea.

        Usa la receta congelada del ítem o, si no existe, la receta vigente del producto.
        """
        return await self.uow.uno(
            """
            SELECT p.estado, p.preparacion_en, i.cantidad, i.aclaraciones,
                   ing.id AS ingrediente_id, receta.cantidad_requerida
            FROM pedido p
            JOIN pedido_item i ON i.pedido_id = p.id
            CROSS JOIN LATERAL (
                SELECT (r->>'ingrediente_id')::bigint AS ingrediente_id,
                       (r->>'cantidad_requerida')::numeric AS cantidad_requerida
                FROM jsonb_array_elements(i.receta_snapshot) r
                UNION ALL
                SELECT pi.ingrediente_id, pi.cantidad_requerida
                FROM producto_ingrediente pi
                WHERE i.receta_snapshot IS NULL AND pi.producto_id = i.producto_id
            ) receta
            JOIN ingrediente ing ON ing.id = receta.ingrediente_id
            WHERE p.id = %s AND i.id = %s AND lower(ing.nombre) = %s
            FOR UPDATE OF i, ing
            """,
            (pedido_id, item_id, nombre),
        )

    async def devolucion_existente(self, pedido_id: int, motivo: str) -> bool:
        """Indica si ya se registró una devolución del pedido con ese motivo."""
        return bool(
            await self.uow.valor(
                "SELECT EXISTS (SELECT 1 FROM movimiento_stock WHERE pedido_id = %s "
                "AND tipo = 'DEVOLUCION' AND motivo = %s)",
                (pedido_id, motivo),
            )
        )

    async def consumo_neto_ingrediente(self, pedido_id: int, ingrediente_id: int) -> Decimal:
        """Devuelve lo consumido neto de un ingrediente por el pedido (consumos menos devoluciones).
        """
        return await self.uow.valor(
            """
            SELECT COALESCE(sum(CASE WHEN tipo = 'CONSUMO' THEN cantidad
                                    WHEN tipo = 'DEVOLUCION' THEN -cantidad ELSE 0 END), 0)
            FROM movimiento_stock WHERE pedido_id = %s AND ingrediente_id = %s
            """,
            (pedido_id, ingrediente_id),
        )

    async def devolver(
        self,
        ingrediente_id: int,
        cantidad: Decimal,
        pedido_id: int,
        usuario_id: int | None,
        motivo: str,
    ) -> None:
        """Suma la cantidad al ingrediente, registra el movimiento DEVOLUCION y actualiza alertas.
        """
        fila = await self.uow.uno(
            "UPDATE ingrediente SET cantidad_actual = cantidad_actual + %s "
            "WHERE id = %s RETURNING *",
            (cantidad, ingrediente_id),
        )
        await self.uow.ejecutar(
            "INSERT INTO movimiento_stock "
            "(ingrediente_id, tipo, cantidad, saldo_resultante, pedido_id, usuario_id, motivo) "
            "VALUES (%s, 'DEVOLUCION', %s, %s, %s, %s, %s)",
            (ingrediente_id, cantidad, fila["cantidad_actual"], pedido_id, usuario_id, motivo),
        )
        await self._sincronizar_alerta(fila, usuario_id=usuario_id)

    async def recetas(self, producto_ids: list[int]) -> list[dict]:
        """Devuelve la receta vigente de cada producto (fila con ingrediente nulo si no tiene)."""
        return await self.uow.todos(
            """
            SELECT p.id AS producto_id, pi.ingrediente_id, pi.cantidad_requerida
            FROM producto p
            LEFT JOIN producto_ingrediente pi ON pi.producto_id = p.id
            WHERE p.id = ANY(%s)
            ORDER BY p.id, pi.ingrediente_id
            """,
            (producto_ids,),
        )

    async def bloquear_ingredientes(self, ingrediente_ids: list[int]) -> list[dict]:
        # Una consulta por ID garantiza el orden de adquisicion de bloqueos.
        filas = []
        for ingrediente_id in ingrediente_ids:
            fila = await self.uow.uno(
                "SELECT id, nombre, cantidad_actual, umbral_minimo, activo "
                "FROM ingrediente WHERE id = %s FOR UPDATE",
                (ingrediente_id,),
            )
            if fila is not None:
                filas.append(fila)
        return filas

    async def consumir(
        self,
        ingrediente_id: int,
        cantidad: Decimal,
        pedido_id: int,
        *,
        motivo: str | None = None,
        usuario_id: int | None = None,
    ) -> dict | None:
        """Descuenta la cantidad si alcanza y registra el movimiento CONSUMO.

        Devuelve ``None`` si el stock no alcanzaba en el momento del UPDATE.
        """
        # El UPDATE condicional evita dejar el stock en negativo ante carreras.
        fila = await self.uow.uno(
            """
            UPDATE ingrediente
            SET cantidad_actual = cantidad_actual - %s
            WHERE id = %s AND cantidad_actual >= %s
            RETURNING *
            """,
            (cantidad, ingrediente_id, cantidad),
        )
        if fila is None:
            return None
        movimiento = await self.uow.uno(
            """
            INSERT INTO movimiento_stock
                (ingrediente_id, tipo, cantidad, saldo_resultante, pedido_id, motivo, usuario_id)
            VALUES (%s, 'CONSUMO', %s, %s, %s, %s, %s)
            RETURNING id, creado_en
            """,
            (ingrediente_id, cantidad, fila["cantidad_actual"], pedido_id, motivo, usuario_id),
        )
        await self._sincronizar_alerta(fila, usuario_id=usuario_id)
        return {
            "ingrediente_id": ingrediente_id,
            "cantidad": cantidad,
            "saldo_resultante": fila["cantidad_actual"],
            "pedido_id": pedido_id,
            "movimiento_id": movimiento["id"],
            "creado_en": movimiento["creado_en"],
        }

    async def listar(
        self,
        *,
        nombre: str | None,
        responsable_id: int | None,
        activo: bool | None,
        nivel: str | None,
    ) -> list[dict]:
        """Lista el inventario con su nivel y alerta, aplicando filtros opcionales."""
        return await self.uow.todos(
            _CONSULTA_INVENTARIO
            + """
            WHERE (%s::text IS NULL OR nombre ILIKE '%%' || %s || '%%')
              AND (%s::bigint IS NULL OR responsable_id = %s)
              AND (%s::boolean IS NULL OR activo = %s)
              AND (%s::text IS NULL OR nivel = %s)
            ORDER BY nombre
            """,
            (nombre, nombre, responsable_id, responsable_id, activo, activo, nivel, nivel),
        )

    async def ingrediente(self, ingrediente_id: int, *, bloquear: bool = False) -> dict | None:
        """Devuelve la fila de un ingrediente; con ``bloquear`` la toma FOR UPDATE."""
        if bloquear:
            return await self.uow.uno(
                "SELECT * FROM ingrediente WHERE id = %s FOR UPDATE",
                (ingrediente_id,),
            )
        return await self.uow.uno(
            "SELECT * FROM ingrediente WHERE id = %s",
            (ingrediente_id,),
        )

    async def existe_nombre(self, nombre: str, *, excepto_id: int | None = None) -> bool:
        """Indica si otro ingrediente ya usa ese nombre (sin distinguir mayúsculas)."""
        return bool(
            await self.uow.valor(
                "SELECT EXISTS (SELECT 1 FROM ingrediente "
                "WHERE lower(nombre) = lower(%s) AND (%s::bigint IS NULL OR id <> %s))",
                (nombre, excepto_id, excepto_id),
            )
        )

    async def responsable_valido(self, responsable_id: int) -> bool:
        """Indica si el usuario responsable existe y está activo."""
        return bool(
            await self.uow.valor(
                "SELECT EXISTS (SELECT 1 FROM usuario WHERE id = %s AND estado = 'ACTIVO')",
                (responsable_id,),
            )
        )

    async def asociado_a_producto_activo(self, ingrediente_id: int) -> bool:
        """Indica si el ingrediente forma parte de la receta de algún producto activo."""
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
        """Inserta un ingrediente, sincroniza su alerta y lo devuelve con el formato del listado."""
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
        return await self._fila_inventario(fila["id"])

    async def modificar(self, ingrediente_id: int, datos: DatosIngrediente) -> dict:
        """Actualiza los datos descriptivos del ingrediente y sincroniza su alerta."""
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
        return await self._fila_inventario(ingrediente_id)

    async def _fila_inventario(self, ingrediente_id: int) -> dict:
        """Misma proyeccion que el listado, leida despues de sincronizar la alerta."""
        return await self.uow.uno(
            _CONSULTA_INVENTARIO + " WHERE id = %s", (ingrediente_id,)
        )

    async def reponer(
        self, ingrediente_id: int, cantidad: Decimal, *, usuario_id: int | None, origen: str
    ) -> dict:
        """Suma la reposición al ingrediente, registra el movimiento y actualiza alertas."""
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
        """Lista movimientos de stock con el saldo anterior reconstruido y filtros opcionales."""
        # Consumos y mermas restaron stock; el resto lo sumó.
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
            WHERE (%s::bigint IS NULL OR m.ingrediente_id = %s)
              AND (%s::date IS NULL OR m.creado_en >= %s::date)
              AND (%s::date IS NULL OR m.creado_en < %s::date + INTERVAL '1 day')
              AND (%s::text IS NULL OR m.tipo = %s)
            ORDER BY m.creado_en DESC, m.id DESC
            """,
            (ingrediente_id, ingrediente_id, desde, desde, hasta, hasta, tipo, tipo),
        )

    async def _sincronizar_alerta(
        self, ingrediente: dict, *, usuario_id: int | None = None
    ) -> None:
        """Mantiene la alerta de stock acorde al nivel actual del ingrediente.

        Si el stock es normal o el ingrediente está inactivo, resuelve la alerta activa; si no, la
        crea o actualiza su nivel (BAJO o AGOTADO).
        """
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

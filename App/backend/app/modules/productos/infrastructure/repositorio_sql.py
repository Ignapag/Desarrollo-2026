"""Repositorio SQL parametrizado del catalogo."""

from app.core.db import UnidadDeTrabajo
from app.modules.productos.domain.entidades import DatosProducto


class RepositorioProductosSQL:
    def __init__(self, uow: UnidadDeTrabajo) -> None:
        self.uow = uow

    async def listar(self, *, solo_activos: bool) -> list[dict]:
        return await self.uow.todos(
            """
            SELECT p.id, p.categoria_id, c.nombre AS categoria, p.nombre,
                   p.descripcion, p.precio_base, p.imagen_url, p.variantes, p.activo,
                   pd.disponible
            FROM producto p
            JOIN categoria c ON c.id = p.categoria_id
            JOIN producto_disponible pd ON pd.producto_id = p.id
            WHERE (%s::boolean = FALSE OR (p.activo AND c.activa))
            ORDER BY c.orden, p.orden, p.nombre
            """,
            (solo_activos,),
        )

    async def categoria_existe(self, categoria_id: int) -> bool:
        return bool(
            await self.uow.valor(
                "SELECT EXISTS (SELECT 1 FROM categoria WHERE id = %s AND activa)",
                (categoria_id,),
            )
        )

    async def nombre_existe(self, categoria_id: int, nombre: str) -> bool:
        return bool(
            await self.uow.valor(
                """
                SELECT EXISTS (
                    SELECT 1 FROM producto
                    WHERE categoria_id = %s AND lower(nombre) = lower(%s)
                )
                """,
                (categoria_id, nombre),
            )
        )

    async def ingredientes_validos(self, ids: list[int]) -> bool:
        cantidad = await self.uow.valor(
            "SELECT count(*) FROM ingrediente WHERE id = ANY(%s) AND activo", (ids,)
        )
        return cantidad == len(ids)

    async def crear(self, datos: DatosProducto) -> dict:
        fila = await self.uow.uno(
            """
            INSERT INTO producto
                (categoria_id, nombre, descripcion, precio_base, imagen_url, activo, orden)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                datos.categoria_id,
                datos.nombre,
                datos.descripcion,
                datos.precio_base,
                datos.imagen_url,
                datos.activo,
                datos.orden,
            ),
        )
        producto_id = fila["id"]
        for ingrediente in datos.ingredientes:
            await self.uow.ejecutar(
                """
                INSERT INTO producto_ingrediente
                    (producto_id, ingrediente_id, cantidad_requerida, es_base)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    producto_id,
                    ingrediente.ingrediente_id,
                    ingrediente.cantidad_requerida,
                    ingrediente.es_base,
                ),
            )
        return await self.uow.uno(
            """
            SELECT p.id, p.categoria_id, c.nombre AS categoria, p.nombre,
                   p.descripcion, p.precio_base, p.imagen_url, p.variantes, p.activo,
                   pd.disponible
            FROM producto p
            JOIN categoria c ON c.id = p.categoria_id
            JOIN producto_disponible pd ON pd.producto_id = p.id
            WHERE p.id = %s
            """,
            (producto_id,),
        )

    async def cambiar_estado(self, producto_id: int, activo: bool) -> dict | None:
        fila = await self.uow.uno(
            """
            UPDATE producto SET activo = %s, actualizado_en = now()
            WHERE id = %s RETURNING id
            """,
            (activo, producto_id),
        )
        if fila is None:
            return None
        return await self.uow.uno(
            """
            SELECT p.id, p.categoria_id, c.nombre AS categoria, p.nombre,
                   p.descripcion, p.precio_base, p.imagen_url, p.variantes, p.activo,
                   pd.disponible
            FROM producto p
            JOIN categoria c ON c.id = p.categoria_id
            JOIN producto_disponible pd ON pd.producto_id = p.id
            WHERE p.id = %s
            """,
            (producto_id,),
        )

"""Repositorio SQL parametrizado del catalogo."""

from psycopg.types.json import Jsonb

from app.core.db import UnidadDeTrabajo
from app.errores import ReglaDeNegocio
from app.modules.productos.domain.entidades import CambioReceta, DatosProducto


class RepositorioProductosSQL:
    def __init__(self, uow: UnidadDeTrabajo) -> None:
        self.uow = uow

    async def listar(self, *, solo_activos: bool) -> list[dict]:
        return await self.uow.todos(
            """
            SELECT p.id, p.categoria_id, c.nombre AS categoria, p.nombre,
                   p.descripcion, p.precio_base, p.imagen_url,
                   COALESCE((SELECT jsonb_agg(v || jsonb_build_object(
                       'disponible', variante_producto_disponible(p.id, v->>'nombre')) ORDER BY n)
                       FROM jsonb_array_elements(p.variantes) WITH ORDINALITY x(v,n)),
                       '[]'::jsonb) AS variantes, p.activo,
                   pd.disponible,
                   ARRAY(SELECT i.nombre FROM producto_ingrediente pi
                         JOIN ingrediente i ON i.id=pi.ingrediente_id
                         WHERE pi.producto_id=p.id ORDER BY lower(i.nombre),i.id)
                   AS ingredientes_receta
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
                (categoria_id, nombre, descripcion, precio_base, imagen_url,
                 activo, orden, variantes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
                Jsonb([{"nombre": v.nombre, "precio": str(v.precio)} for v in datos.variantes]),
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
        await self._guardar_variantes(producto_id, datos.variantes)
        return await self.uow.uno(
            """
            SELECT p.id, p.categoria_id, c.nombre AS categoria, p.nombre,
                   p.descripcion, p.precio_base, p.imagen_url,
                   COALESCE((SELECT jsonb_agg(v || jsonb_build_object(
                       'disponible', variante_producto_disponible(p.id, v->>'nombre')) ORDER BY n)
                       FROM jsonb_array_elements(p.variantes) WITH ORDINALITY x(v,n)),
                       '[]'::jsonb) AS variantes, p.activo,
                   pd.disponible,
                   ARRAY(SELECT i.nombre FROM producto_ingrediente pi
                         JOIN ingrediente i ON i.id=pi.ingrediente_id
                         WHERE pi.producto_id=p.id ORDER BY lower(i.nombre),i.id)
                   AS ingredientes_receta
            FROM producto p
            JOIN categoria c ON c.id = p.categoria_id
            JOIN producto_disponible pd ON pd.producto_id = p.id
            WHERE p.id = %s
            """,
            (producto_id,),
        )

    async def _guardar_variantes(self, producto_id: int, variantes) -> None:
        for variante in variantes:
            for item in variante.ingredientes:
                await self.uow.ejecutar(
                    """
                    INSERT INTO producto_variante_ingrediente
                        (producto_id, variante, ingrediente_id, cantidad_requerida, es_base)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        producto_id,
                        variante.nombre,
                        item.ingrediente_id,
                        item.cantidad_requerida,
                        item.es_base,
                    ),
                )

    async def obtener_receta(self, producto_id: int, *, bloquear: bool = False) -> dict | None:
        if bloquear:
            producto = await self.uow.uno(
                "SELECT id, actualizado_en, variantes FROM producto WHERE id=%s FOR UPDATE",
                (producto_id,),
            )
        else:
            producto = await self.uow.uno(
                "SELECT id, actualizado_en, variantes FROM producto WHERE id=%s FOR SHARE",
                (producto_id,),
            )
        if producto is None:
            return None
        ingredientes = await self._leer_ingredientes(producto_id, None)
        variantes = []
        for variante in producto["variantes"]:
            nombre = variante["nombre"]
            configurada = await self.uow.valor(
                """SELECT EXISTS(SELECT 1 FROM producto_variante_ingrediente
                   WHERE producto_id=%s AND lower(btrim(variante))=lower(btrim(%s)))""",
                (producto_id, nombre),
            )
            variantes.append(
                {
                    "nombre": nombre,
                    "precio": variante["precio"],
                    "ingredientes": await self._leer_ingredientes(producto_id, nombre),
                    "receta_configurada": configurada,
                }
            )
        return {
            "producto_id": producto_id,
            "actualizado_en": producto["actualizado_en"],
            "ingredientes": ingredientes,
            "variantes": variantes,
        }

    async def _leer_ingredientes(self, producto_id: int, variante: str | None) -> list[dict]:
        return await self.uow.todos(
            """SELECT r.ingrediente_id, i.nombre, i.unidad_medida,
                      r.cantidad_requerida, r.es_base
               FROM receta_producto(%s, %s) r JOIN ingrediente i ON i.id=r.ingrediente_id
               ORDER BY lower(i.nombre), i.id""",
            (producto_id, variante),
        )

    async def guardar_receta(self, producto_id: int, datos: CambioReceta) -> dict:
        # El servicio mantiene FOR UPDATE sobre producto durante toda la UoW.
        fila = await self.uow.uno(
            """UPDATE producto SET actualizado_en=clock_timestamp()
               WHERE id=%s AND actualizado_en=%s RETURNING id""",
            (producto_id, datos.actualizado_en_esperado),
        )
        if fila is None:
            raise ReglaDeNegocio("La receta fue modificada; recargala antes de guardar")
        await self.uow.ejecutar(
            "DELETE FROM producto_variante_ingrediente WHERE producto_id=%s", (producto_id,)
        )
        await self.uow.ejecutar(
            "DELETE FROM producto_ingrediente WHERE producto_id=%s", (producto_id,)
        )
        for item in datos.ingredientes:
            await self.uow.ejecutar(
                """INSERT INTO producto_ingrediente
                   (producto_id,ingrediente_id,cantidad_requerida,es_base) VALUES (%s,%s,%s,%s)""",
                (producto_id, item.ingrediente_id, item.cantidad_requerida, item.es_base),
            )
        await self._guardar_variantes(producto_id, datos.variantes)
        return await self.obtener_receta(producto_id)

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
                   p.descripcion, p.precio_base, p.imagen_url,
                   COALESCE((SELECT jsonb_agg(v || jsonb_build_object(
                       'disponible', variante_producto_disponible(p.id, v->>'nombre')) ORDER BY n)
                       FROM jsonb_array_elements(p.variantes) WITH ORDINALITY x(v,n)),
                       '[]'::jsonb) AS variantes, p.activo,
                   pd.disponible,
                   ARRAY(SELECT i.nombre FROM producto_ingrediente pi
                         JOIN ingrediente i ON i.id=pi.ingrediente_id
                         WHERE pi.producto_id=p.id ORDER BY lower(i.nombre),i.id)
                   AS ingredientes_receta
            FROM producto p
            JOIN categoria c ON c.id = p.categoria_id
            JOIN producto_disponible pd ON pd.producto_id = p.id
            WHERE p.id = %s
            """,
            (producto_id,),
        )

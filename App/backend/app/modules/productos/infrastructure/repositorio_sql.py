"""Repositorio SQL parametrizado del catalogo."""

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from app.core.db import UnidadDeTrabajo
from app.errores import ReglaDeNegocio
from app.modules.productos.domain.entidades import CambioProducto, CambioReceta, DatosProducto


class RepositorioProductosSQL:
    """Acceso SQL al catálogo: productos, recetas, variantes y disponibilidad."""

    def __init__(self, uow: UnidadDeTrabajo) -> None:
        """Recibe la unidad de trabajo cuya transacción comparten las consultas."""
        self.uow = uow

    async def listar(self, *, solo_activos: bool) -> list[dict]:
        """Lista productos con categoría, variantes, disponibilidad e ingredientes de receta.

        Con ``solo_activos`` excluye productos inactivos o de categorías inactivas.
        """
        productos = await self.uow.todos(
            """
            SELECT p.id, p.categoria_id, c.nombre AS categoria, p.nombre,
                   p.descripcion, p.precio_base, p.imagen_url,
                   COALESCE((SELECT jsonb_agg(v || jsonb_build_object(
                       'disponible', variante_producto_disponible(p.id, v->>'nombre'),
                       'max_unidades', variante_producto_max_unidades(p.id, v->>'nombre'))
                       ORDER BY n)
                       FROM jsonb_array_elements(p.variantes) WITH ORDINALITY x(v,n)),
                       '[]'::jsonb) AS variantes, p.activo,
                   pd.disponible, producto_max_unidades(p.id) AS max_unidades,
                   ARRAY(SELECT i.nombre FROM producto_ingrediente pi
                         JOIN ingrediente i ON i.id=pi.ingrediente_id
                         WHERE pi.producto_id=p.id AND pi.eliminado_en IS NULL
                         ORDER BY lower(i.nombre),i.id)
                   AS ingredientes_receta
            FROM producto p
            JOIN categoria c ON c.id = p.categoria_id
            JOIN producto_disponible pd ON pd.producto_id = p.id
            WHERE (%s::boolean = FALSE OR (p.activo AND c.activa))
            ORDER BY c.orden, p.orden, p.nombre
            """,
            (solo_activos,),
        )
        opciones = await self.uow.todos(
            """SELECT o.producto_id,o.ingrediente_id,i.nombre,i.unidad_medida,
                      o.cantidad_requerida,o.costo_adicional AS precio,o.max_por_item,
                      ARRAY(SELECT v->>'nombre' FROM producto p2,
                            jsonb_array_elements(p2.variantes) v
                            WHERE p2.id=o.producto_id AND EXISTS (
                                SELECT 1 FROM receta_producto(p2.id,v->>'nombre') r
                                WHERE r.ingrediente_id=o.ingrediente_id)) AS variantes
               FROM producto_opcion o JOIN ingrediente i ON i.id=o.ingrediente_id
               JOIN producto p ON p.id=o.producto_id JOIN categoria c ON c.id=p.categoria_id
               WHERE o.tipo='AGREGADO' AND o.activo AND i.activo
                 AND o.costo_adicional>0 AND o.cantidad_requerida>0
                 AND lower(c.nombre)<>'dips extra'
                 AND EXISTS(SELECT 1 FROM receta_producto(p.id,NULL) r
                            WHERE r.ingrediente_id=o.ingrediente_id)
               ORDER BY lower(i.nombre),i.id"""
        )
        for producto in productos:
            producto["extras_disponibles"] = [
                {k: v for k, v in opcion.items() if k != "producto_id"}
                for opcion in opciones
                if opcion["producto_id"] == producto["id"]
            ]
        return productos

    async def categoria_existe(self, categoria_id: int) -> bool:
        """Valida y fija la categoría mientras un alta comprueba su nombre único."""
        return bool(
            await self.uow.valor(
                "SELECT id FROM categoria WHERE id = %s AND activa FOR UPDATE",
                (categoria_id,),
            )
        )

    async def nombre_existe(self, categoria_id: int, nombre: str) -> bool:
        """Busca el nombre en la categoría sin distinguir mayúsculas."""
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
        """Indica si todos los ingredientes indicados existen y están activos."""
        cantidad = await self.uow.valor(
            "SELECT count(*) FROM ingrediente WHERE id = ANY(%s) AND activo", (ids,)
        )
        return cantidad == len(ids)

    async def categoria_edicion(self, categoria_id: int) -> dict | None:
        """Serializa ediciones de nombres dentro de una categoría y fija su estado."""
        return await self.uow.uno(
            "SELECT id,nombre,activa FROM categoria WHERE id=%s FOR UPDATE", (categoria_id,)
        )

    async def nombre_en_uso(self, categoria_id: int, nombre: str, excepto_id: int) -> bool:
        """Excluye el producto editado de la validación de unicidad del nombre."""
        return bool(
            await self.uow.valor(
                "SELECT EXISTS(SELECT 1 FROM producto WHERE categoria_id=%s "
                "AND lower(nombre)=lower(%s) AND id<>%s)",
                (categoria_id, nombre, excepto_id),
            )
        )

    async def ingredientes_edicion(self, ids: list[int]) -> list[dict]:
        """Fija el estado de los ingredientes mientras se valida y guarda la receta."""
        return await self.uow.todos(
            "SELECT id,activo FROM ingrediente WHERE id=ANY(%s) ORDER BY id FOR SHARE", (ids,)
        )

    async def crear(self, datos: DatosProducto) -> dict:
        """Inserta el producto con su receta base y de variantes, y lo devuelve completo."""
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
        # Receta base: una fila por ingrediente.
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
        await self._guardar_extras(producto_id, datos.extras)
        return await self.uow.uno(
            """
            SELECT p.id, p.categoria_id, c.nombre AS categoria, p.nombre,
                   p.descripcion, p.precio_base, p.imagen_url,
                   COALESCE((SELECT jsonb_agg(v || jsonb_build_object(
                       'disponible', variante_producto_disponible(p.id, v->>'nombre'),
                       'max_unidades', variante_producto_max_unidades(p.id, v->>'nombre'))
                       ORDER BY n)
                       FROM jsonb_array_elements(p.variantes) WITH ORDINALITY x(v,n)),
                       '[]'::jsonb) AS variantes, p.activo,
                   pd.disponible, producto_max_unidades(p.id) AS max_unidades,
                   ARRAY(SELECT i.nombre FROM producto_ingrediente pi
                         JOIN ingrediente i ON i.id=pi.ingrediente_id
                         WHERE pi.producto_id=p.id AND pi.eliminado_en IS NULL
                         ORDER BY lower(i.nombre),i.id)
                   AS ingredientes_receta
            FROM producto p
            JOIN categoria c ON c.id = p.categoria_id
            JOIN producto_disponible pd ON pd.producto_id = p.id
            WHERE p.id = %s
            """,
            (producto_id,),
        )

    async def _guardar_variantes(self, producto_id: int, variantes) -> None:
        """Inserta o reactiva cada relación de las recetas de variantes."""
        for variante in variantes:
            for item in variante.ingredientes:
                await self.uow.ejecutar(
                    """
                    INSERT INTO producto_variante_ingrediente
                        (producto_id, variante, ingrediente_id, cantidad_requerida, es_base)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (producto_id, variante, ingrediente_id) DO UPDATE
                    SET cantidad_requerida=EXCLUDED.cantidad_requerida,
                        es_base=EXCLUDED.es_base, eliminado_en=NULL
                    WHERE producto_variante_ingrediente.eliminado_en IS NOT NULL
                       OR (producto_variante_ingrediente.cantidad_requerida,
                           producto_variante_ingrediente.es_base)
                          IS DISTINCT FROM (EXCLUDED.cantidad_requerida, EXCLUDED.es_base)
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
        """Devuelve la receta base y la de cada variante del producto.

        Con ``bloquear`` toma FOR UPDATE (para editar); si no, FOR SHARE.
        """
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
        # Para cada variante se indica si tiene receta propia configurada.
        for variante in producto["variantes"]:
            nombre = variante["nombre"]
            configurada = await self.uow.valor(
                """SELECT EXISTS(SELECT 1 FROM producto_variante_ingrediente
                   WHERE producto_id=%s AND eliminado_en IS NULL
                     AND lower(btrim(variante))=lower(btrim(%s)))""",
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
            "extras": await self.uow.todos(
                "SELECT ingrediente_id,cantidad_requerida,costo_adicional AS precio,max_por_item "
                "FROM producto_opcion WHERE producto_id=%s AND tipo='AGREGADO' AND activo "
                "AND costo_adicional>0 AND cantidad_requerida>0 ORDER BY ingrediente_id",
                (producto_id,),
            ),
        }

    async def _leer_ingredientes(self, producto_id: int, variante: str | None) -> list[dict]:
        """Lee la receta efectiva (base o de una variante) con nombre y unidad."""
        return await self.uow.todos(
            """SELECT r.ingrediente_id, i.nombre, i.unidad_medida,
                      r.cantidad_requerida, r.es_base
               FROM receta_producto(%s, %s) r JOIN ingrediente i ON i.id=r.ingrediente_id
               ORDER BY lower(i.nombre), i.id""",
            (producto_id, variante),
        )

    async def obtener_edicion(self, producto_id: int, *, bloquear: bool = False) -> dict | None:
        """Lee metadata y composición bajo la misma versión bloqueada del producto."""
        receta = await self.obtener_receta(producto_id, bloquear=bloquear)
        if receta is None:
            return None
        producto = await self.uow.uno(
            "SELECT p.categoria_id,c.nombre AS categoria,p.nombre,p.descripcion,p.precio_base,"
            "p.imagen_url,p.activo,p.orden FROM producto p JOIN categoria c ON c.id=p.categoria_id "
            "WHERE p.id=%s",
            (producto_id,),
        )
        categorias = await self.uow.todos(
            "SELECT id,nombre,activa FROM categoria WHERE activa OR id=%s ORDER BY orden,nombre",
            (producto["categoria_id"],),
        )
        return receta | producto | {"categorias": categorias}

    async def guardar_receta(self, producto_id: int, datos: CambioReceta) -> dict:
        # El servicio mantiene FOR UPDATE sobre producto durante toda la UoW.
        fila = await self.uow.uno(
            """UPDATE producto SET actualizado_en=clock_timestamp()
               WHERE id=%s AND actualizado_en=%s RETURNING id""",
            (producto_id, datos.actualizado_en_esperado),
        )
        if fila is None:
            raise ReglaDeNegocio("La receta fue modificada; recargala antes de guardar")
        await self._guardar_composicion(producto_id, datos)
        return await self.obtener_receta(producto_id)

    async def guardar_producto(self, producto_id: int, cambio: CambioProducto) -> dict:
        """Guarda metadata y composición atómicamente sin tocar ventas ni stock."""
        datos = cambio.producto
        try:
            fila = await self.uow.uno(
                "UPDATE producto SET categoria_id=%s,nombre=%s,descripcion=%s,precio_base=%s,"
                "imagen_url=%s,activo=%s,orden=%s,variantes=%s,actualizado_en=clock_timestamp() "
                "WHERE id=%s AND actualizado_en=%s RETURNING id",
                (
                    datos.categoria_id,
                    datos.nombre,
                    datos.descripcion,
                    datos.precio_base,
                    datos.imagen_url,
                    datos.activo,
                    datos.orden,
                    Jsonb([{"nombre": v.nombre, "precio": str(v.precio)} for v in datos.variantes]),
                    producto_id,
                    cambio.actualizado_en_esperado,
                ),
            )
        except UniqueViolation as exc:
            raise ReglaDeNegocio("Ya existe un producto con ese nombre en la categoria") from exc
        if fila is None:
            raise ReglaDeNegocio("El producto fue modificado; recargalo antes de guardar")
        await self._guardar_composicion(producto_id, datos)
        return await self.obtener_edicion(producto_id)

    async def _guardar_composicion(
        self, producto_id: int, datos: CambioReceta | DatosProducto
    ) -> None:
        """Actualiza relaciones conservando las claves de recetas ya utilizadas."""
        # Solo retira relaciones ausentes; los upserts conservan las claves históricas.
        variantes = [
            {"variante": variante.nombre, "ingrediente_id": item.ingrediente_id}
            for variante in datos.variantes
            for item in variante.ingredientes
        ]
        await self.uow.ejecutar(
            """UPDATE producto_variante_ingrediente r SET eliminado_en=now()
               WHERE r.producto_id=%s AND r.eliminado_en IS NULL
                 AND NOT EXISTS (
                     SELECT 1 FROM jsonb_to_recordset(%s::jsonb)
                         AS v(variante text, ingrediente_id bigint)
                     WHERE v.variante=r.variante AND v.ingrediente_id=r.ingrediente_id
                 )""",
            (producto_id, Jsonb(variantes)),
        )
        await self.uow.ejecutar(
            "UPDATE producto_ingrediente SET eliminado_en=now() "
            "WHERE producto_id=%s AND eliminado_en IS NULL "
            "AND NOT (ingrediente_id=ANY(%s::bigint[]))",
            (producto_id, [item.ingrediente_id for item in datos.ingredientes]),
        )
        for item in datos.ingredientes:
            await self.uow.ejecutar(
                """INSERT INTO producto_ingrediente
                   (producto_id,ingrediente_id,cantidad_requerida,es_base) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (producto_id,ingrediente_id) DO UPDATE
                   SET cantidad_requerida=EXCLUDED.cantidad_requerida,
                       es_base=EXCLUDED.es_base, eliminado_en=NULL
                   WHERE producto_ingrediente.eliminado_en IS NOT NULL
                      OR (producto_ingrediente.cantidad_requerida, producto_ingrediente.es_base)
                         IS DISTINCT FROM (EXCLUDED.cantidad_requerida, EXCLUDED.es_base)""",
                (producto_id, item.ingrediente_id, item.cantidad_requerida, item.es_base),
            )
        await self._guardar_variantes(producto_id, datos.variantes)
        await self._guardar_extras(producto_id, datos.extras)

    async def cambiar_estado(self, producto_id: int, activo: bool) -> dict | None:
        """Activa o desactiva el producto y lo devuelve completo, o ``None`` si no existe."""
        fila = await self.uow.uno(
            """
            UPDATE producto SET activo = %s, actualizado_en = clock_timestamp()
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
                       'disponible', variante_producto_disponible(p.id, v->>'nombre'),
                       'max_unidades', variante_producto_max_unidades(p.id, v->>'nombre'))
                       ORDER BY n)
                       FROM jsonb_array_elements(p.variantes) WITH ORDINALITY x(v,n)),
                       '[]'::jsonb) AS variantes, p.activo,
                   pd.disponible, producto_max_unidades(p.id) AS max_unidades,
                   ARRAY(SELECT i.nombre FROM producto_ingrediente pi
                         JOIN ingrediente i ON i.id=pi.ingrediente_id
                         WHERE pi.producto_id=p.id AND pi.eliminado_en IS NULL
                         ORDER BY lower(i.nombre),i.id)
                   AS ingredientes_receta
            FROM producto p
            JOIN categoria c ON c.id = p.categoria_id
            JOIN producto_disponible pd ON pd.producto_id = p.id
            WHERE p.id = %s
            """,
            (producto_id,),
        )

    async def _guardar_extras(self, producto_id: int, extras) -> None:
        """Reemplaza configuración explícita; omitirla conserva las opciones anteriores."""
        if extras is not None:
            await self.uow.ejecutar(
                "UPDATE producto_opcion SET activo=FALSE WHERE producto_id=%s AND tipo='AGREGADO'",
                (producto_id,),
            )
            for extra in extras:
                await self.uow.ejecutar(
                    """INSERT INTO producto_opcion(producto_id,ingrediente_id,tipo,
                           cantidad_requerida,costo_adicional,max_por_item,activo)
                       VALUES (%s,%s,'AGREGADO',%s,%s,%s,TRUE)
                       ON CONFLICT(producto_id,ingrediente_id,tipo) DO UPDATE SET
                           cantidad_requerida=EXCLUDED.cantidad_requerida,
                           costo_adicional=EXCLUDED.costo_adicional,
                           max_por_item=EXCLUDED.max_por_item,activo=TRUE""",
                    (
                        producto_id,
                        extra.ingrediente_id,
                        extra.cantidad_requerida,
                        extra.precio,
                        extra.max_por_item,
                    ),
                )

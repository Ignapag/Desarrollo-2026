"""Normalizacion de composicion: el catalogo y el pedido son la autoridad."""

from decimal import Decimal
from typing import Protocol

from app.errores import DatosInvalidos, NoEncontrado, ReglaDeNegocio
from app.modules.stock.domain.entidades import INGREDIENTES_QUITABLES


class RepositorioEdicionItems(Protocol):
    async def productos(self, ids: list[int]) -> list[dict]: ...
    async def items_edicion(self, pedido_id: int) -> list[dict]: ...
    async def receta_edicion(self, producto_id: int, variante: str | None) -> list[dict]: ...
    async def nombres_ingredientes(self, ids: list[int]) -> dict[int, str]: ...
    async def guardar_items(
        self,
        pedido_id: int,
        items: list[dict],
        subtotal: Decimal,
        total: Decimal,
        *,
        usuario_id: int | None,
        origen: str,
        anteriores: list[dict],
    ) -> dict: ...


def entero(valor, nombre: str, *, maximo: int | None = None) -> int:
    if (
        isinstance(valor, bool)
        or not isinstance(valor, int)
        or valor <= 0
        or maximo is not None
        and valor > maximo
    ):
        raise DatosInvalidos(f"{nombre} no es valido")
    return valor


def normalizar_aclaraciones(
    aclaraciones, nombres: dict[int, str], receta: list[dict]
) -> str | None:
    if aclaraciones is None or aclaraciones == "":
        return None
    if not isinstance(aclaraciones, str) or len(aclaraciones) > 500:
        raise DatosInvalidos("Las aclaraciones no son validas")
    disponibles = {nombres[fila["ingrediente_id"]].casefold() for fila in receta}
    aliases = {
        "bacon": {"panceta", "bacon en cubos"},
        "cheddar": {"queso cheddar"},
        "cebolla": {"cebolla cruda", "cebolla en cubos", "cebolla caramelizada", "cebolla crispy"},
    }
    retirados = []
    for nota in aclaraciones.split(","):
        nota = nota.strip().casefold()
        if not nota.startswith("sin "):
            raise DatosInvalidos("Solo se admiten retiros de ingredientes de la receta")
        nombre = nota[4:].strip()
        candidatos = disponibles & (aliases.get(nombre, set()) | {nombre})
        if len(candidatos) != 1:
            raise DatosInvalidos("El ingrediente no pertenece a la receta o requiere aclaracion")
        canonico = candidatos.pop()
        if canonico not in INGREDIENTES_QUITABLES:
            raise DatosInvalidos("El ingrediente no se puede retirar")
        if canonico not in retirados:
            retirados.append(canonico)
    return ", ".join(f"Sin {nombre.capitalize()}" for nombre in retirados)


async def preparar_items(
    repo: RepositorioEdicionItems,
    anteriores: list[dict],
    solicitados: list[dict],
) -> list[dict]:
    if not isinstance(solicitados, list) or not 1 <= len(solicitados) <= 50:
        raise DatosInvalidos("El pedido debe contener entre 1 y 50 lineas; para vaciarlo cancelelo")
    existentes = {item["id"]: item for item in anteriores}
    nuevos_ids = []
    vistos = set()
    for item in solicitados:
        if not isinstance(item, dict):
            raise DatosInvalidos("El item no es valido")
        permitidos = {
            "id",
            "producto_id",
            "variante",
            "cantidad",
            "aclaraciones",
            "nombre_producto",
            "precio_unitario",
            "costo_opciones",
            "subtotal",
            "receta_snapshot",
            "pedido_id",
        }
        if set(item) - permitidos:
            raise DatosInvalidos("El item contiene opciones no admitidas")
        entero(item.get("cantidad"), "La cantidad", maximo=50)
        if item.get("id") is not None:
            item_id = entero(item["id"], "El item")
            if item_id not in existentes or item_id in vistos:
                raise DatosInvalidos("El item no pertenece al pedido o esta repetido")
            vistos.add(item_id)
            anterior = existentes[item_id]
            if item["cantidad"] > anterior["cantidad"]:
                nuevos_ids.append(anterior["producto_id"])
            if item.get("producto_id", anterior["producto_id"]) != anterior[
                "producto_id"
            ] or item.get("variante", anterior.get("variante")) != anterior.get("variante"):
                raise DatosInvalidos(
                    "Para reemplazar producto o variante debe agregar una linea nueva"
                )
        else:
            nuevos_ids.append(entero(item.get("producto_id"), "El producto"))
    productos = (
        {p["id"]: p for p in await repo.productos(sorted(set(nuevos_ids)))} if nuevos_ids else {}
    )
    resultado = []
    acumuladas = {}
    for solicitado in solicitados:
        anterior = existentes.get(solicitado.get("id"))
        if anterior is not None:
            item = dict(anterior)
            if solicitado["cantidad"] > anterior["cantidad"]:
                producto = productos.get(anterior["producto_id"])
                if producto is None or not producto.get("activo", producto["disponible"]):
                    raise ReglaDeNegocio("El producto esta inactivo")
            receta = item.get("receta_snapshot")
            if receta is None:
                receta = await repo.receta_edicion(item["producto_id"], item.get("variante"))
        else:
            producto = productos.get(solicitado["producto_id"])
            if producto is None:
                raise NoEncontrado("El producto no existe")
            if not producto.get("activo", producto["disponible"]):
                raise ReglaDeNegocio("El producto esta inactivo")
            variante = solicitado.get("variante")
            variantes = producto.get("variantes") or []
            seleccionada = next((v for v in variantes if v["nombre"] == variante), None)
            if variantes and seleccionada is None or not variantes and variante is not None:
                raise DatosInvalidos("Debe seleccionar una variante valida del producto")
            if seleccionada and seleccionada.get("activo") is False:
                raise ReglaDeNegocio("La variante esta inactiva")
            receta = await repo.receta_edicion(producto["id"], variante)
            item = {
                "producto_id": producto["id"],
                "variante": variante,
                "nombre_producto": producto["nombre"] + (f" ({variante})" if variante else ""),
                "precio_unitario": Decimal(
                    str(seleccionada["precio"] if seleccionada else producto["precio_base"])
                ),
                "costo_opciones": Decimal("0"),
                "receta_snapshot": receta,
                "aclaraciones": None,
            }
        if not receta:
            raise ReglaDeNegocio("El producto no tiene una receta valida")
        if anterior is None or (
            "aclaraciones" in solicitado and solicitado["aclaraciones"] != anterior["aclaraciones"]
        ):
            nombres = await repo.nombres_ingredientes([r["ingrediente_id"] for r in receta])
            if set(nombres) != {r["ingrediente_id"] for r in receta}:
                raise ReglaDeNegocio("La receta contiene ingredientes inexistentes")
            item["aclaraciones"] = normalizar_aclaraciones(
                solicitado.get("aclaraciones"), nombres, receta
            )
        item["cantidad"] = solicitado["cantidad"]
        item["subtotal"] = (
            Decimal(str(item["precio_unitario"])) + Decimal(str(item.get("costo_opciones", 0)))
        ) * item["cantidad"]
        clave = (item["producto_id"], item.get("variante"))
        acumuladas[clave] = acumuladas.get(clave, 0) + item["cantidad"]
        if acumuladas[clave] > 50:
            raise DatosInvalidos("La cantidad acumulada del producto no puede superar 50")
        resultado.append(item)
    return resultado

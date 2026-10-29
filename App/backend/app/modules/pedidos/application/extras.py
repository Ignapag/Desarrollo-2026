"""Cotización de agregados usando únicamente configuración del local."""

from decimal import Decimal

from app.errores import DatosInvalidos


def cotizar_extras(extras, receta: list[dict], opciones: list[dict], aclaraciones=None) -> dict:
    """Valida cantidades y congela porción/precio; suma demanda en la unidad del inventario."""
    if not isinstance(extras, list | tuple) or len(extras) > 50:
        raise DatosInvalidos("Los extras no son validos")
    por_id = {r["ingrediente_id"]: dict(r) for r in receta}
    disponibles = {o["ingrediente_id"]: o for o in opciones if o["ingrediente_id"] in por_id}
    retirados = {
        nota.strip()[4:].strip().casefold()
        for nota in (aclaraciones or "").split(",")
        if nota.strip().casefold().startswith("sin ")
    }
    snapshot = []
    vistos = set()
    costo = Decimal("0")
    for extra in extras:
        if not isinstance(extra, dict) or set(extra) != {"ingrediente_id", "cantidad"}:
            raise DatosInvalidos("El extra contiene datos no admitidos")
        ingrediente_id, cantidad = extra["ingrediente_id"], extra["cantidad"]
        if (
            isinstance(ingrediente_id, bool)
            or not isinstance(ingrediente_id, int)
            or isinstance(cantidad, bool)
            or not isinstance(cantidad, int)
            or cantidad < 0
        ):
            raise DatosInvalidos("El ingrediente o la cantidad del extra no son validos")
        if ingrediente_id in vistos:
            raise DatosInvalidos("No se puede repetir un extra")
        vistos.add(ingrediente_id)
        opcion = disponibles.get(ingrediente_id)
        if opcion is None:
            raise DatosInvalidos("El extra no esta habilitado en la receta seleccionada")
        if cantidad > opcion["max_por_item"]:
            raise DatosInvalidos("La cantidad del extra supera el maximo por hamburguesa")
        if not cantidad:
            continue
        if opcion["nombre"].casefold() in retirados:
            raise DatosInvalidos("No se puede quitar y agregar el mismo ingrediente")
        precio = Decimal(str(opcion["precio"]))
        porcion = Decimal(str(opcion["cantidad_requerida"]))
        if not precio.is_finite() or precio <= 0 or not porcion.is_finite() or porcion <= 0:
            raise DatosInvalidos("El extra no tiene precio y porcion validos configurados")
        snapshot.append(
            {
                key: opcion[key]
                for key in ("ingrediente_id", "nombre", "unidad_medida", "max_por_item")
            }
            | {"cantidad": cantidad, "precio": str(precio), "cantidad_requerida": str(porcion)}
        )
        costo += precio * cantidad
        por_id[ingrediente_id]["cantidad_requerida"] = str(
            Decimal(str(por_id[ingrediente_id]["cantidad_requerida"])) + porcion * cantidad
        )
    snapshot.sort(key=lambda e: e["ingrediente_id"])
    return {
        "extras": [
            {"ingrediente_id": e["ingrediente_id"], "cantidad": e["cantidad"]} for e in snapshot
        ],
        "extras_snapshot": snapshot,
        "costo_opciones": costo,
        "receta_snapshot": list(por_id.values()),
    }

"""Descubrimiento y registro de capacidades de negocio.

Este archivo pertenece a la raiz de composicion: conoce ``app.modules`` para
conectar sus adaptadores HTTP, pero los modulos no dependen de el. Cada
capacidad puede publicar routers en archivos ``presentation/router*.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from fastapi import APIRouter, FastAPI

import app.modules as paquete_modulos


@dataclass(frozen=True, slots=True)
class RouterDescubierto:
    capacidad: str
    modulo: str
    router: APIRouter


def descubrir_routers() -> list[RouterDescubierto]:
    """Importa los ``router*.py`` publicados por cada capacidad.

    Un archivo que siga la convencion debe exportar una instancia ``router``.
    Si no lo hace, el arranque falla con un mensaje concreto en vez de dejar
    un modulo parcialmente integrado y dificil de diagnosticar.
    """
    raiz = Path(next(iter(paquete_modulos.__path__)))
    encontrados: list[RouterDescubierto] = []

    for capacidad_dir in sorted(raiz.iterdir(), key=lambda ruta: ruta.name):
        if not capacidad_dir.is_dir() or capacidad_dir.name.startswith("_"):
            continue

        presentacion = capacidad_dir / "presentation"
        if not presentacion.is_dir():
            continue

        for archivo in sorted(presentacion.glob("router*.py")):
            if archivo.name == "__init__.py":
                continue

            nombre_modulo = (
                f"app.modules.{capacidad_dir.name}.presentation.{archivo.stem}"
            )
            modulo = import_module(nombre_modulo)
            router = getattr(modulo, "router", None)
            if not isinstance(router, APIRouter):
                raise RuntimeError(
                    f"{nombre_modulo} debe exportar una instancia APIRouter "
                    "llamada 'router'"
                )
            encontrados.append(
                RouterDescubierto(
                    capacidad=capacidad_dir.name,
                    modulo=nombre_modulo,
                    router=router,
                )
            )

    return encontrados


def registrar_routers(app: FastAPI) -> list[RouterDescubierto]:
    """Monta todos los routers y devuelve el inventario registrado."""
    encontrados = descubrir_routers()
    for encontrado in encontrados:
        app.include_router(encontrado.router)
    return encontrados

"""Punto de entrada de la API de Monu Burger.

Monolito modular: una sola aplicacion FastAPI que monta el router de cada
modulo. Las capas siguen Clean Architecture (presentation / application /
domain / infrastructure) dentro de cada modulo.

Alcance de este repositorio: Base de Datos (EDT 1.9.2) y Asignacion de
Repartidores (EDT 1.3.1). Los demas modulos estan a cargo de otros
integrantes del grupo y se integran mas adelante.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg import OperationalError
from psycopg_pool import PoolTimeout

from app.core.config import settings
from app.core.db import abrir_pool, cerrar_pool, verificar_conexion
from app.core.errores import (
    ErrorDominio,
    manejador_base_no_disponible,
    manejador_error_dominio,
)
from app.modules.delivery.presentation.router import router as router_delivery
from app.modules.pagos.presentation.router import router as router_pagos

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("monuburger")


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
    await abrir_pool()
    try:
        await verificar_conexion()
        log.info("Conectado a la base %s", settings.dsn_visible)
    except Exception as exc:
        log.warning(
            "La base %s no responde (%s). La API arranca igual; revisa /api/salud.",
            settings.dsn_visible,
            exc.__class__.__name__,
        )
    try:
        yield
    finally:
        await cerrar_pool()
        log.info("Pool de conexiones cerrado")


app = FastAPI(
    title=settings.app_nombre,
    version="0.1.0",
    description=(
        "Sistema de Gestion para Monu Burger - Seminario Integrador 2026, Grupo 19."
    ),
    lifespan=ciclo_de_vida,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origenes_permitidos,
    allow_credentials=True,  # necesario para la cookie de sesion
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(ErrorDominio, manejador_error_dominio)  # type: ignore[arg-type]
app.add_exception_handler(PoolTimeout, manejador_base_no_disponible)
app.add_exception_handler(OperationalError, manejador_base_no_disponible)

# Los routers de cada modulo se montan aca:
app.include_router(router_delivery)
app.include_router(router_pagos)


@app.get("/api/salud", tags=["infra"])
async def salud() -> dict:
    """Healthcheck: verifica que la API responde y la base esta accesible."""
    estado_bd = "ok"
    try:
        await verificar_conexion()
    except Exception as exc:  # pragma: no cover - diagnostico de infraestructura
        estado_bd = f"error: {exc.__class__.__name__}"

    return {
        "aplicacion": settings.app_nombre,
        "entorno": settings.entorno,
        "base_de_datos": estado_bd,
        "estado": "ok" if estado_bd == "ok" else "degradado",
    }

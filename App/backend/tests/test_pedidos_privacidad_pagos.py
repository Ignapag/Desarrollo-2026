"""Revocar pagos.ver también retira el historial anidado en pedidos."""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos
from app.modules.pedidos.presentation.router import router
from app.modules.usuarios.domain.entidades import ClaimsSesion, Rol
from app.modules.usuarios.presentation.dependencias import sesion_vigente


@pytest.mark.parametrize("puede_ver", [False, True])
@pytest.mark.parametrize("metodo,ruta,cuerpo", [
    ("get", "/api/pedidos", None),
    ("get", "/api/pedidos/1", None),
    ("post", "/api/pedidos", {
        "cliente_id": 1, "items": [{"producto_id": 1, "cantidad": 1}],
    }),
    ("patch", "/api/pedidos/1/operacion", {
        "motivo": "Ajustar nota", "version_esperada": 1, "observaciones": "Sin sal",
    }),
    ("patch", "/api/pedidos/1/estado", {"estado": "CONFIRMADO"}),
])
def test_historial_de_pagos_respeta_permiso_en_lecturas_y_mutaciones(
    puede_ver, metodo, ruta, cuerpo,
):
    fila = {
        "id": 1, "numero": 1, "cliente_id": 1, "cliente": "Prueba",
        "tipo_entrega": "RETIRO", "direccion_id": None, "estado": "CONFIRMADO",
        "subtotal": "100", "costo_envio": "0", "total": "100",
        "observaciones": None, "creado_en": datetime(2026, 10, 22, tzinfo=UTC),
        "items": [], "pagos": [{"id": 7, "monto": "80", "estado": "CONCILIADO"}],
        "neto_cobrado": "80", "saldo_pendiente": "20",
    }

    class Servicio:
        async def detalle(self, *args, **kwargs):
            return fila

        crear = editar_operacion = cambiar_estado = detalle

        async def listar(self, **kwargs):
            return [fila]

    permisos = {"pedidos.ver", "pedidos.crear", "pedidos.editar", "pedidos.cambiar_estado"}
    if puede_ver:
        permisos.add("pagos.ver")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[sesion_vigente] = lambda: ClaimsSesion(
        1, Rol.EMPLEADO, "prueba", frozenset(permisos)
    )
    app.dependency_overrides[obtener_servicio_pedidos] = Servicio
    with TestClient(app) as api:
        respuesta = getattr(api, metodo)(ruta, **({"json": cuerpo} if cuerpo else {}))
    assert respuesta.status_code in (200, 201), respuesta.text
    datos = respuesta.json()[0] if isinstance(respuesta.json(), list) else respuesta.json()
    assert datos["pagos"] == (fila["pagos"] if puede_ver else [])
    assert datos["neto_cobrado"] == "80"
    assert datos["saldo_pendiente"] == "20"
    assert len(fila["pagos"]) == 1  # La proyección no altera el estado del servicio.

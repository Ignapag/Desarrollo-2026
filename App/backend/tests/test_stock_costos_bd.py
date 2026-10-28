"""Costo unitario de ingredientes por HTTP y su efecto en el costo estimado, en BD descartable."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest_asyncio
from fastapi import FastAPI

from app.core.config import settings
from app.core.dependencias import obtener_uow
from app.core.errores import manejador_error_dominio
from app.core.seguridad import crear_token
from app.errores import ErrorDominio
from app.modules.reportes.infrastructure.repositorio_sql import RepositorioReportesSQL
from app.modules.stock.presentation.router import router as stock
from tests.test_reportes_bd import escenario, pedido_con_item


@pytest_asyncio.fixture
async def api(uow):
    app = FastAPI()
    app.include_router(stock)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://prueba"
    ) as cliente:
        yield cliente


async def autenticar(api, uow, username):
    fila = await uow.uno("SELECT id, rol, username FROM usuario WHERE username = %s", (username,))
    api.cookies.set(settings.cookie_sesion, crear_token(
        usuario_id=fila["id"], rol=fila["rol"], username=fila["username"],
    ))


async def test_alta_y_edicion_de_costo_se_reflejan_en_el_costo_estimado(api, uow):
    await autenticar(api, uow, "admin")
    nombre = f"Insumo costo {uuid4().hex}"
    creado = await api.post("/api/stock/ingredientes", json={
        "nombre": nombre, "unidad_medida": "GR", "cantidad_actual": 100,
        "umbral_minimo": 10, "costo_unitario": "4.50",
    })
    assert creado.status_code == 201, creado.text
    cuerpo = creado.json()
    assert Decimal(cuerpo["costo_unitario"]) == Decimal("4.50")
    assert cuerpo["nivel"] == "NORMAL" and cuerpo["indicador_alerta"] is False

    categoria_id = await uow.valor("SELECT id FROM categoria LIMIT 1")
    producto_id = await uow.valor(
        "INSERT INTO producto (categoria_id, nombre, precio_base) "
        "VALUES (%s, %s, 1000) RETURNING id",
        (categoria_id, nombre),
    )
    await uow.ejecutar(
        "INSERT INTO producto_ingrediente (producto_id, ingrediente_id, cantidad_requerida) "
        "VALUES (%s, %s, 20)",
        (producto_id, cuerpo["id"]),
    )
    costo = "SELECT costo_insumos FROM producto_costo WHERE producto_id = %s"
    assert await uow.valor(costo, (producto_id,)) == Decimal("90")

    editado = await api.patch(
        f"/api/stock/ingredientes/{cuerpo['id']}", json={"costo_unitario": "6.25"}
    )
    assert editado.status_code == 200, editado.text
    assert Decimal(editado.json()["costo_unitario"]) == Decimal("6.25")
    assert Decimal(editado.json()["cantidad_actual"]) == 100
    assert await uow.valor(costo, (producto_id,)) == Decimal("125")

    listado = (await api.get("/api/stock/ingredientes", params={"nombre": nombre})).json()
    assert [Decimal(fila["costo_unitario"]) for fila in listado] == [Decimal("6.25")]


async def test_rentabilidad_usa_el_costo_actual_tambien_para_ventas_anteriores(api, uow):
    await autenticar(api, uow, "admin")
    cliente_id, categorias, productos = await escenario(uow)
    venta = datetime(2026, 9, 1, 15, tzinfo=UTC)
    await pedido_con_item(uow, cliente_id, productos[0], "ENTREGADO", venta, cantidad=3)
    repo = RepositorioReportesSQL(uow)
    periodo = (date(2026, 9, 1), date(2026, 9, 30), categorias[0], productos[0])
    assert (await repo.rentabilidad(*periodo))[0]["costo_estimado"] == 60

    ingrediente_id = await uow.valor(
        "SELECT ingrediente_id FROM producto_ingrediente WHERE producto_id = %s", (productos[0],)
    )
    editado = await api.patch(
        f"/api/stock/ingredientes/{ingrediente_id}", json={"costo_unitario": "35.50"}
    )
    assert editado.status_code == 200, editado.text
    assert (await repo.rentabilidad(*periodo))[0]["costo_estimado"] == Decimal("106.50")


async def test_alta_bajo_umbral_responde_nivel_y_alerta_sincronizados(api, uow):
    await autenticar(api, uow, "admin")
    creado = await api.post("/api/stock/ingredientes", json={
        "nombre": f"Insumo costo {uuid4().hex}", "unidad_medida": "KG",
        "cantidad_actual": 0, "umbral_minimo": 2, "costo_unitario": "12000",
    })
    assert creado.status_code == 201, creado.text
    assert creado.json()["nivel"] == "SIN_STOCK" and creado.json()["indicador_alerta"] is True
    editado = await api.patch(
        f"/api/stock/ingredientes/{creado.json()['id']}", json={"activo": False}
    )
    assert editado.status_code == 200, editado.text
    assert editado.json()["indicador_alerta"] is False


async def test_costo_invalido_se_rechaza_sin_modificar(api, uow):
    await autenticar(api, uow, "admin")
    creado = (await api.post("/api/stock/ingredientes", json={
        "nombre": f"Insumo costo {uuid4().hex}", "unidad_medida": "UNIDAD",
        "cantidad_actual": 1, "umbral_minimo": 1,
    })).json()
    assert Decimal(creado["costo_unitario"]) == 0
    for invalido in ("-1", "abc", "0.001", "10000000000"):
        respuesta = await api.patch(
            f"/api/stock/ingredientes/{creado['id']}", json={"costo_unitario": invalido}
        )
        assert respuesta.status_code == 422, invalido
    assert await uow.valor(
        "SELECT costo_unitario FROM ingrediente WHERE id = %s", (creado["id"],)
    ) == 0


async def test_editar_costo_exige_stock_gestionar(api, uow):
    ingrediente_id = await uow.valor("SELECT id FROM ingrediente LIMIT 1")
    cliente = await uow.uno(
        "SELECT id, rol, username FROM usuario WHERE rol = 'CLIENTE' AND estado = 'ACTIVO' LIMIT 1"
    )
    api.cookies.set(settings.cookie_sesion, crear_token(
        usuario_id=cliente["id"], rol=cliente["rol"], username=cliente["username"],
    ))
    respuesta = await api.patch(
        f"/api/stock/ingredientes/{ingrediente_id}", json={"costo_unitario": "1"}
    )
    assert respuesta.status_code == 403

"""Directorio real y filtros por identidad, sobre PostgreSQL descartable."""

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.dependencias import obtener_uow
from app.core.errores import manejador_error_dominio
from app.core.seguridad import crear_token
from app.errores import ErrorDominio, SinPermiso
from app.modules.pedidos.presentation.router import router as pedidos_router
from app.modules.reportes.infrastructure.repositorio_sql import RepositorioReportesSQL
from app.modules.reportes.presentation.dependencias import obtener_servicio_reportes
from app.modules.reportes.presentation.router import router as reportes_router
from app.modules.usuarios.presentation.dependencias import sesion_vigente, usuario_actual


def aplicacion():
    app = FastAPI()
    # Identidad sintetica: esta suite verifica negocio, no resolucion de sesiones.
    app.dependency_overrides[sesion_vigente] = usuario_actual
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)
    app.include_router(reportes_router)
    app.include_router(pedidos_router)
    return app


def cookies(rol, usuario_id=1):
    return {settings.cookie_sesion: crear_token(usuario_id=usuario_id, rol=rol, username="test")}


@pytest.mark.parametrize("rol", [None, "CLIENTE", "REPARTIDOR"])
def test_directorio_rechaza_sin_obtener_conexion(rol):
    app = aplicacion()

    async def no_conectar():
        raise AssertionError("No debe obtener conexión antes de autorizar el directorio")

    app.dependency_overrides[obtener_uow] = no_conectar
    with TestClient(app) as navegador:
        if rol:
            navegador.cookies.update(cookies(rol))
        respuesta = navegador.get("/api/reportes/clientes")
    assert respuesta.status_code == (403 if rol else 401)


@pytest_asyncio.fixture
async def datos(uow):
    marca = "directorio_" + uuid4().hex
    usuario = await uow.valor(
        "INSERT INTO usuario(nombre,apellido,username,password_hash,rol) "
        "VALUES('Cuenta','Visible',%s,'x','CLIENTE') RETURNING id",
        (marca,),
    )
    ids = []
    for posicion in range(4):
        ids.append(
            await uow.valor(
                "INSERT INTO cliente(usuario_id,nombre,telefono_whatsapp) VALUES(%s,%s,%s) "
                "RETURNING id",
                (
                    usuario if posicion == 0 else None,
                    f"{marca} {posicion}",
                    f"549221987654{posicion}",
                ),
            )
        )
    zona = await uow.valor("SELECT id FROM zona_cobertura ORDER BY id LIMIT 1")
    zona_nombre = await uow.valor("SELECT nombre FROM zona_cobertura WHERE id=%s", (zona,))
    direccion = await uow.valor(
        "INSERT INTO direccion(cliente_id,calle,numero,localidad,zona_id) "
        "VALUES(%s,'Prueba','1','Localidad histórica',%s) RETURNING id",
        (ids[0], zona),
    )
    # Una dirección sin pedidos nunca debe influir en la zona ni multiplicar el conteo.
    await uow.ejecutar(
        "INSERT INTO direccion(cliente_id,calle,numero,localidad) "
        "VALUES(%s,'Sin uso','2','Localidad sin uso')",
        (ids[0],),
    )
    fechas = [datetime(2026, 10, dia, 15, tzinfo=UTC) for dia in (1, 2, 3)]
    pedidos = []
    for posicion, cliente, modalidad, dir_id, estado in (
        (0, ids[0], "DELIVERY", direccion, "CANCELADO"),
        (1, ids[0], "DELIVERY", direccion, "ENTREGADO"),
        (2, ids[0], "RETIRO", None, "PENDIENTE"),
        (2, ids[1], "RETIRO", None, "PENDIENTE"),
    ):
        pedidos.append(
            await uow.valor(
                "INSERT INTO pedido(cliente_id,tipo_entrega,direccion_id,estado,creado_en) "
                "VALUES(%s,%s,%s,%s,%s) RETURNING id",
                (cliente, modalidad, dir_id, estado, fechas[posicion]),
            )
        )
    producto = await uow.valor("SELECT id FROM producto ORDER BY id LIMIT 1")
    for _ in range(3):
        await uow.ejecutar(
            "INSERT INTO pedido_item(pedido_id,producto_id,nombre_producto,cantidad,"
            "precio_unitario,subtotal) VALUES(%s,%s,'Histórico',1,100,100)",
            (pedidos[0], producto),
        )
    for _ in range(2):
        await uow.ejecutar(
            "INSERT INTO pago(pedido_id,tipo,metodo_pago,monto) "
            "VALUES(%s,'COBRO','EFECTIVO',100)",
            (pedidos[0],),
        )
    return dict(
        marca=marca, ids=ids, usuario=usuario, fechas=fechas, pedidos=pedidos, zona=zona_nombre
    )


@pytest.mark.asyncio
async def test_directorio_incluye_sin_cuenta_y_no_multiplica_pedidos(uow, datos):
    salida = await RepositorioReportesSQL(uow).clientes(
        q=datos["marca"], limite=50, desplazamiento=0
    )
    assert salida["total"] == 4
    assert [c["id"] for c in salida["clientes"]] == [
        datos["ids"][1],
        datos["ids"][0],
        datos["ids"][3],
        datos["ids"][2],
    ]
    cuenta = salida["clientes"][1]
    assert cuenta["pedidos_count"] == 3
    assert cuenta["primer_pedido_en"] == datos["fechas"][0]
    assert cuenta["ultimo_pedido_en"] == datos["fechas"][2]
    assert cuenta["zona_frecuente"] == datos["zona"]
    invitado = salida["clientes"][0]
    assert invitado["zona_frecuente"] == "Retiro en local"
    assert invitado["pedidos_count"] == 1
    sin_pedidos = salida["clientes"][2]
    assert sin_pedidos["pedidos_count"] == 0
    assert sin_pedidos["zona_frecuente"] is None
    assert sin_pedidos["primer_pedido_en"] is None
    assert sin_pedidos["ultimo_pedido_en"] is None


@pytest.mark.asyncio
async def test_busqueda_paginas_estables_y_total_de_pagina_vacia(uow, datos):
    repo = RepositorioReportesSQL(uow)
    pagina = await repo.clientes(q=datos["marca"], limite=1, desplazamiento=1)
    assert pagina["total"] == 4
    assert [c["id"] for c in pagina["clientes"]] == [datos["ids"][0]]
    assert await repo.clientes(q=datos["marca"], limite=1, desplazamiento=1) == pagina
    vacia = await repo.clientes(q=datos["marca"], limite=1, desplazamiento=4)
    assert vacia == {"clientes": [], "total": 4, "limite": 1, "desplazamiento": 4}
    sin_coincidencias = await repo.clientes(q=uuid4().hex, limite=50, desplazamiento=0)
    assert sin_coincidencias["total"] == 0
    assert sin_coincidencias["clientes"] == []
    telefono = await repo.clientes(q="5492219876541", limite=100, desplazamiento=0)
    assert datos["ids"][1] in [c["id"] for c in telefono["clientes"]]


@pytest.mark.asyncio
async def test_zona_usa_localidad_y_desempata_por_pedido_reciente(uow, datos):
    repo = RepositorioReportesSQL(uow)
    await uow.ejecutar("UPDATE direccion SET zona_id=NULL WHERE cliente_id=%s", (datos["ids"][0],))
    salida = await repo.clientes(q=datos["marca"], limite=50, desplazamiento=0)
    assert salida["clientes"][1]["zona_frecuente"] == "Localidad histórica"
    await uow.ejecutar(
        "INSERT INTO pedido(cliente_id,tipo_entrega,creado_en) "
        "VALUES(%s,'RETIRO','2026-10-04T15:00:00Z')",
        (datos["ids"][0],),
    )
    salida = await repo.clientes(q=datos["marca"], limite=50, desplazamiento=0)
    assert salida["clientes"][0]["zona_frecuente"] == "Retiro en local"


@pytest.mark.asyncio
async def test_servicio_no_expone_directorio_a_roles_no_autorizados(uow):
    servicio = obtener_servicio_reportes(uow)
    for rol in ("CLIENTE", "REPARTIDOR"):
        with pytest.raises(SinPermiso):
            await servicio.clientes(rol=rol)


@pytest.mark.asyncio
@pytest.mark.parametrize("rol", ["EMPLEADO", "ADMINISTRADOR", "DUENIO"])
async def test_http_directorio_y_filtro_exacto_por_id(uow, datos, rol):
    app = aplicacion()
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        api.cookies.update(cookies(rol))
        respuesta = await api.get("/api/reportes/clientes", params={"q": datos["marca"]})
        assert respuesta.status_code == 200
        salida = respuesta.json()
        assert salida["total"] == 4
        assert salida["limite"] == 50
        assert salida["desplazamiento"] == 0
        assert set(salida["clientes"][0]) == {
            "id",
            "nombre",
            "telefono",
            "zona_frecuente",
            "pedidos_count",
            "primer_pedido_en",
            "ultimo_pedido_en",
        }
        respuesta = await api.get("/api/pedidos", params={"cliente_id": datos["ids"][1]})
        assert respuesta.status_code == 200
        assert [p["id"] for p in respuesta.json()] == [datos["pedidos"][3]]
        for params in ({"limite": 101}, {"limite": 0}, {"desplazamiento": -1}):
            assert (await api.get("/api/reportes/clientes", params=params)).status_code == 422
        assert (await api.get("/api/pedidos", params={"cliente_id": 0})).status_code == 422


@pytest.mark.asyncio
async def test_cliente_no_puede_filtrar_historial_ajeno(uow, datos):
    app = aplicacion()
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        api.cookies.update(cookies("CLIENTE", datos["usuario"]))
        for params in ({}, {"cliente_id": datos["ids"][0]}):
            respuesta = await api.get("/api/pedidos", params=params)
            assert respuesta.status_code == 200
            assert {p["id"] for p in respuesta.json()} == set(datos["pedidos"][:3])
        respuesta = await api.get("/api/pedidos", params={"cliente_id": datos["ids"][1]})
        assert respuesta.status_code == 403


@pytest.mark.asyncio
async def test_repartidor_no_puede_usar_filtro_cliente(uow, datos):
    repartidor = await uow.valor(
        "INSERT INTO usuario(nombre,apellido,username,password_hash,rol) "
        "VALUES('Reparto','Prueba',%s,'x','REPARTIDOR') RETURNING id",
        (uuid4().hex,),
    )
    await uow.ejecutar("INSERT INTO repartidor(usuario_id) VALUES(%s)", (repartidor,))
    viaje = await uow.valor(
        "INSERT INTO viaje(repartidor_id) VALUES(%s) RETURNING id",
        (repartidor,),
    )
    await uow.ejecutar(
        "INSERT INTO envio(pedido_id,viaje_id,estado) VALUES(%s,%s,'ASIGNADO')",
        (datos["pedidos"][0], viaje),
    )
    app = aplicacion()
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        api.cookies.update(cookies("REPARTIDOR", repartidor))
        respuesta = await api.get("/api/pedidos")
        assert respuesta.status_code == 200
        assert [p["id"] for p in respuesta.json()] == [datos["pedidos"][0]]
        respuesta = await api.get("/api/pedidos", params={"cliente_id": datos["ids"][1]})
        assert respuesta.status_code == 403

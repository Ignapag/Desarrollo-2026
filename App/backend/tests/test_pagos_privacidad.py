"""Los IDs de pedidos/pagos no habilitan acceso a finanzas ajenas."""

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
from app.errores import ErrorDominio
from app.modules.pagos.presentation.router import router
from app.modules.usuarios.presentation.dependencias import sesion_vigente, usuario_actual


def aplicacion():
    app = FastAPI()
    # Identidad sintetica: esta suite verifica negocio, no resolucion de sesiones.
    app.dependency_overrides[sesion_vigente] = usuario_actual
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)
    app.include_router(router)
    return app


def sesion(usuario_id, rol):
    return {
        settings.cookie_sesion: crear_token(
            usuario_id=usuario_id,
            rol=rol,
            username="prueba-pagos",
        )
    }


@pytest.mark.parametrize("rol", [None, "REPARTIDOR"])
@pytest.mark.parametrize(
    "ruta,metodo,cuerpo",
    [
        ("/pedido/1/estado", "get", None),
        ("/pedido/1", "get", None),
        ("/1", "get", None),
        ("/pendientes-conciliacion", "get", None),
    ],
)
def test_finanzas_rechazan_anonimo_y_repartidor_antes_de_conectar(rol, ruta, metodo, cuerpo):
    app = aplicacion()

    async def no_conectar():
        raise AssertionError("La guarda financiera debe rechazar antes de solicitar conexión")

    app.dependency_overrides[obtener_uow] = no_conectar
    with TestClient(app) as cliente:
        if rol:
            cliente.cookies.update(sesion(1, rol))
        respuesta = getattr(cliente, metodo)(
            "/api/pagos" + ruta,
            **({"json": cuerpo} if cuerpo else {}),
        )
    assert respuesta.status_code == (403 if rol else 401)


@pytest.mark.parametrize(
    "ruta,cuerpo",
    [
        ("/efectivo", {"pedido_id": 1, "monto_recibido": "100"}),
        ("/transferencia", {"pedido_id": 1, "monto": "100"}),
        ("/devolucion", {"pedido_id": 1, "monto": "10", "motivo": "prueba"}),
        ("/conciliar-lote", {"pago_ids": [1]}),
        ("/1/conciliar", {}),
        ("/1/anular", {"motivo": "prueba"}),
    ],
)
def test_repartidor_no_opera_finanzas_antes_de_conectar(ruta, cuerpo):
    app = aplicacion()

    async def no_conectar():
        raise AssertionError("El repartidor no debe obtener conexión financiera")

    app.dependency_overrides[obtener_uow] = no_conectar
    with TestClient(app) as cliente:
        cliente.cookies.update(sesion(1, "REPARTIDOR"))
        assert cliente.post("/api/pagos" + ruta, json=cuerpo).status_code == 403


@pytest_asyncio.fixture
async def datos_pagos(uow):
    usuarios = []
    pedidos = []
    pagos = []
    for posicion in range(3):
        usuario_id = None
        if posicion != 2:
            usuario_id = await uow.valor(
                "INSERT INTO usuario (nombre, apellido, username, password_hash, rol) "
                "VALUES ('Cliente', 'Prueba', %s, 'sin-acceso-real', 'CLIENTE') RETURNING id",
                ("pago-" + uuid4().hex,),
            )
            cliente_id = await uow.valor(
                "INSERT INTO cliente (id, usuario_id, nombre, telefono_whatsapp) "
                "VALUES (%s, %s, 'Cliente prueba', %s) RETURNING id",
                (900000000 + usuario_id, usuario_id, f"549221{usuario_id:07d}"),
            )
        else:
            cliente_id = await uow.valor(
                "INSERT INTO cliente (nombre, telefono_whatsapp) "
                "VALUES ('Comprador sin cuenta', '5492219876543') RETURNING id"
            )
        pedido_id = await uow.valor(
            "INSERT INTO pedido (cliente_id, tipo_entrega, canal, estado, subtotal, total) "
            "VALUES (%s, 'RETIRO', 'WEB', 'PENDIENTE', 1000, 1000) RETURNING id",
            (cliente_id,),
        )
        pago_id = await uow.valor(
            "INSERT INTO pago (pedido_id, tipo, metodo_pago, monto, propina, estado) "
            "VALUES (%s, 'COBRO', 'EFECTIVO', 100, 0, 'PENDIENTE') RETURNING id",
            (pedido_id,),
        )
        usuarios.append(usuario_id)
        pedidos.append(pedido_id)
        pagos.append(pago_id)
    return usuarios, pedidos, pagos


@pytest.mark.parametrize("objetivo", [1, 2])
async def test_cliente_no_lee_finanzas_de_otro_cliente_o_huesped(
    uow,
    datos_pagos,
    objetivo,
    monkeypatch,
):
    monkeypatch.setattr(settings, "mp_access_token", "")
    usuarios, pedidos, pagos = datos_pagos
    app = aplicacion()
    app.dependency_overrides[obtener_uow] = lambda: uow
    cantidad_antes = await uow.valor("SELECT count(*) FROM pago")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://prueba",
        cookies=sesion(usuarios[0], "CLIENTE"),
    ) as cliente:
        for ruta in (
            f"/pedido/{pedidos[objetivo]}/estado",
            f"/pedido/{pedidos[objetivo]}",
            f"/{pagos[objetivo]}",
        ):
            respuesta = await cliente.get("/api/pagos" + ruta)
            assert respuesta.status_code == 404, respuesta.text
    assert await uow.valor("SELECT count(*) FROM pago") == cantidad_antes


async def test_cliente_con_id_comercial_distinto_consulta_solo_su_pedido(
    uow,
    datos_pagos,
    monkeypatch,
):
    monkeypatch.setattr(settings, "mp_access_token", "")
    usuarios, pedidos, pagos = datos_pagos
    app = aplicacion()
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://prueba",
        cookies=sesion(usuarios[0], "CLIENTE"),
    ) as cliente:
        assert (await cliente.get(f"/api/pagos/pedido/{pedidos[0]}/estado")).status_code == 200
        listado = await cliente.get(f"/api/pagos/pedido/{pedidos[0]}")
        assert listado.status_code == 200 and listado.json()[0]["id"] == pagos[0]
        assert (await cliente.get(f"/api/pagos/{pagos[0]}")).status_code == 200


async def test_recurso_ajeno_e_inexistente_no_revelan_datos_distintos(uow, datos_pagos):
    usuarios, pedidos, pagos = datos_pagos
    app = aplicacion()
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://prueba",
        cookies=sesion(usuarios[0], "CLIENTE"),
    ) as cliente:
        for ruta_ajena, ruta_inexistente in (
            (f"/pedido/{pedidos[1]}/estado", "/pedido/0/estado"),
            (f"/pedido/{pedidos[1]}", "/pedido/0"),
            (f"/{pagos[1]}", "/0"),
        ):
            ajeno = await cliente.get("/api/pagos" + ruta_ajena)
            inexistente = await cliente.get("/api/pagos" + ruta_inexistente)
            assert ajeno.status_code == inexistente.status_code == 404
            assert ajeno.json()["codigo"] == inexistente.json()["codigo"] == "no_encontrado"


@pytest.mark.parametrize("rol", ["EMPLEADO", "ADMINISTRADOR", "DUENIO"])
async def test_personal_consulta_cobro_para_huesped(uow, datos_pagos, rol, monkeypatch):
    monkeypatch.setattr(settings, "mp_access_token", "")
    _, pedidos, pagos = datos_pagos
    usuario_id = await uow.valor("SELECT id FROM usuario WHERE rol=%s LIMIT 1", (rol,))
    app = aplicacion()
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://prueba",
        cookies=sesion(usuario_id, rol),
    ) as cliente:
        for ruta in (f"/pedido/{pedidos[2]}/estado", f"/pedido/{pedidos[2]}", f"/{pagos[2]}"):
            respuesta = await cliente.get("/api/pagos" + ruta)
            assert respuesta.status_code == 200, respuesta.text


@pytest.mark.parametrize("rol", [None, "CLIENTE", "EMPLEADO", "DUENIO"])
def test_billetera_y_webhook_no_exponen_operaciones_activas(rol):
    app = aplicacion()

    async def no_conectar():
        raise AssertionError("Las rutas retiradas no solicitan conexión")

    app.dependency_overrides[obtener_uow] = no_conectar
    with TestClient(app) as cliente:
        if rol:
            cliente.cookies.update(sesion(1, rol))
        for ruta in ("/billetera/iniciar", "/webhook/mercadopago?id=sim_falso"):
            assert cliente.post("/api/pagos" + ruta, json={"pedido_id": 1}).status_code == 404

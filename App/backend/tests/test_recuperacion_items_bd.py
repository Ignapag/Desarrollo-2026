"""Recuperar una línea conserva su identidad y respeta stock y estado del pedido."""

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import settings
from app.core.dependencias import obtener_uow
from app.core.errores import manejador_error_dominio
from app.core.seguridad import crear_token
from app.errores import ErrorDominio, NoEncontrado, ReglaDeNegocio
from app.modules.pedidos.domain.entidades import EstadoPedido
from app.modules.pedidos.presentation.router import router
from tests.test_edicion_items_bd import crear


async def retirar_linea(uow, *, confirmado=False):
    servicio, pedido, producto, ingrediente = await crear(uow)
    if confirmado:
        pedido = await servicio.cambiar_estado(
            pedido["id"], EstadoPedido.CONFIRMADO, usuario_id=None
        )
    agregado = await servicio.editar_items(
        pedido["id"], version_esperada=pedido["version"],
        items=[{"id": pedido["items"][0]["id"], "cantidad": 1},
               {"producto_id": producto, "cantidad": 1}],
    )
    retirado = agregado["items"][1]
    vigente = await servicio.editar_items(
        pedido["id"], version_esperada=agregado["version"],
        items=[{"id": agregado["items"][0]["id"], "cantidad": 1}],
    )
    return servicio, vigente, retirado, producto, ingrediente


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmado", [False, True])
async def test_recuperar_conserva_id_precio_snapshot_y_ajusta_stock(uow, confirmado):
    servicio, vigente, retirado, producto, ingrediente = await retirar_linea(
        uow, confirmado=confirmado
    )
    saldo = await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,))
    await uow.ejecutar("UPDATE producto SET precio_base=900 WHERE id=%s", (producto,))
    recuperado = await servicio.recuperar_item(
        vigente["id"], retirado["id"], version_esperada=vigente["version"]
    )
    linea = next(i for i in recuperado["items"] if i["id"] == retirado["id"])
    assert linea["precio_unitario"] == retirado["precio_unitario"]
    assert linea["receta_snapshot"] == retirado["receta_snapshot"]
    assert recuperado["total"] == vigente["total"] + retirado["subtotal"]
    assert recuperado["version"] == vigente["version"] + 1
    assert await uow.valor(
        "SELECT eliminado_en IS NULL FROM pedido_item WHERE id=%s", (retirado["id"],)
    )
    actual = await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,))
    assert actual == saldo - (1 if confirmado else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "causa", ["inactivo", "version", "cocina", "ajeno", "stock", "ingrediente"]
)
async def test_recuperacion_invalida_no_modifica_composicion(uow, causa):
    servicio, vigente, retirado, producto, ingrediente = await retirar_linea(uow)
    version = vigente["version"]
    item_id = retirado["id"]
    if causa == "inactivo":
        await uow.ejecutar("UPDATE producto SET activo=FALSE WHERE id=%s", (producto,))
    elif causa == "version":
        version -= 1
    elif causa == "cocina":
        await uow.ejecutar("UPDATE pedido SET preparacion_en=now() WHERE id=%s", (vigente["id"],))
    elif causa == "stock":
        await uow.ejecutar("UPDATE ingrediente SET cantidad_actual=0 WHERE id=%s", (ingrediente,))
    elif causa == "ingrediente":
        await uow.ejecutar("UPDATE ingrediente SET activo=FALSE WHERE id=%s", (ingrediente,))
    else:
        item_id = 999999999
    with pytest.raises((ReglaDeNegocio, NoEncontrado)):
        await servicio.recuperar_item(vigente["id"], item_id, version_esperada=version)
    detalle = await servicio.detalle(vigente["id"])
    assert detalle["items"] == vigente["items"]
    assert detalle["version"] == vigente["version"]


@pytest.mark.asyncio
async def test_recuperacion_con_opciones_conservadas_requiere_revision(uow):
    servicio, vigente, retirado, _, ingrediente = await retirar_linea(uow)
    await uow.ejecutar(
        "INSERT INTO pedido_item_opcion(pedido_item_id,ingrediente_id,nombre_opcion,tipo) "
        "VALUES (%s,%s,'Agregado conservado','AGREGADO')", (retirado["id"], ingrediente),
    )
    with pytest.raises(ReglaDeNegocio, match="opciones estructuradas"):
        await servicio.recuperar_item(
            vigente["id"], retirado["id"], version_esperada=vigente["version"]
        )
    detalle = await servicio.detalle(vigente["id"])
    assert detalle["items"] == vigente["items"]
    assert detalle["version"] == vigente["version"]
    assert await uow.valor(
        "SELECT count(*) FROM pedido_item_opcion WHERE pedido_item_id=%s", (retirado["id"],)
    ) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("cuenta,esperado", [(None, 401), ("acliente", 403), ("admin", 200)])
async def test_recuperacion_http_valida_permiso_version_y_atribucion(uow, cuenta, esperado):
    _, vigente, retirado, _, _ = await retirar_linea(uow)
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://prueba"
    ) as client:
        if cuenta:
            usuario = await uow.uno(
                "SELECT id,rol,username FROM usuario WHERE username=%s", (cuenta,)
            )
            client.cookies.set(settings.cookie_sesion, crear_token(
                usuario_id=usuario["id"], rol=usuario["rol"], username=usuario["username"]
            ))
        ruta = f"/api/pedidos/{vigente['id']}/items/{retirado['id']}/recuperar"
        if esperado == 200:
            bajas = await client.get(f"/api/pedidos/{vigente['id']}/items-retirados")
            assert [i["id"] for i in bajas.json()] == [retirado["id"]]
            conflicto = await client.post(ruta, json={"version_esperada": vigente["version"] - 1})
            assert conflicto.status_code == 409
        respuesta = await client.post(ruta, json={"version_esperada": vigente["version"]})
        assert respuesta.status_code == esperado, respuesta.text
        if esperado == 200:
            assert retirado["id"] in {i["id"] for i in respuesta.json()["items"]}
            evento = await uow.uno(
                "SELECT usuario_id,datos FROM auditoria WHERE entidad='pedido_item' "
                "AND entidad_id=%s ORDER BY id DESC LIMIT 1", (str(retirado["id"]),)
            )
            assert evento["usuario_id"] == usuario["id"]
            assert evento["datos"]["antes"]["eliminado_en"] is not None
            assert evento["datos"]["despues"]["eliminado_en"] is None

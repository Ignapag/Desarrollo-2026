"""Edición integral de un producto sin recrearlo ni alterar ventas históricas."""

from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.core.dependencias import obtener_uow
from app.core.errores import manejador_error_dominio
from app.errores import DatosInvalidos, ErrorDominio, ReglaDeNegocio
from app.modules.productos.presentation.router import router
from app.modules.usuarios.domain.entidades import ClaimsSesion, Rol
from app.modules.usuarios.presentation.dependencias import sesion_vigente
from tests.test_productos_recetas import crear_producto_prueba


def cuerpo(detalle, **cambios):
    campos = {
        "categoria_id",
        "nombre",
        "descripcion",
        "precio_base",
        "imagen_url",
        "activo",
        "orden",
        "extras",
    }
    resultado = {k: v for k, v in detalle.items() if k in campos}

    def ingrediente(i):
        return {
            k: v for k, v in i.items() if k in {"ingrediente_id", "cantidad_requerida", "es_base"}
        }

    resultado.update(
        actualizado_en_esperado=detalle["actualizado_en"],
        ingredientes=[ingrediente(i) for i in detalle["ingredientes"]],
        variantes=[
            {
                "nombre": v["nombre"],
                "precio": v["precio"],
                "ingredientes": [ingrediente(i) for i in v["ingredientes"]],
            }
            for v in detalle["variantes"]
        ],
    )
    return resultado | cambios


def entrada(detalle, **cambios):
    from app.modules.productos.presentation.esquemas import ProductoActualizar

    return ProductoActualizar(**cuerpo(detalle, **cambios)).a_dominio()


@pytest.mark.parametrize(
    "metodo,rol,esperado",
    [("GET", None, 401), ("PUT", None, 401), ("GET", Rol.CLIENTE, 403), ("PUT", Rol.EMPLEADO, 403)],
)
async def test_edicion_producto_exige_permiso_antes_de_abrir_conexion(metodo, rol, esperado):
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)
    if rol:
        app.dependency_overrides[sesion_vigente] = lambda: ClaimsSesion(1, rol, "prueba")

    async def prohibida():
        pytest.fail("No abrir conexión sin permiso de producto")

    app.dependency_overrides[obtener_uow] = prohibida
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as cliente:
        respuesta = await cliente.request(metodo, "/api/productos/1", json={})
    assert respuesta.status_code == esperado


@pytest.mark.parametrize(
    "imagen",
    [
        "javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "data:image/svg+xml;base64,PHN2Zz4=",
        "data:image/png;base64,no valido!",
        "https://example.com/foto.svg",
        "//otro.example/foto.png",
    ],
)
def test_actualizar_rechaza_imagenes_no_raster_o_datos_invalidos(imagen):
    from app.modules.productos.presentation.esquemas import ProductoActualizar

    with pytest.raises(ValidationError):
        ProductoActualizar(
            categoria_id=1,
            nombre="Burger",
            precio_base="100",
            imagen_url=imagen,
            actualizado_en_esperado="2026-10-29T00:00:00Z",
            ingredientes=[{"ingrediente_id": 1, "cantidad_requerida": "1"}],
        )


async def test_edicion_integral_conserva_id_stock_e_historia(uow):
    from app.modules.pedidos.application.servicio_pedidos import ItemNuevoPedido
    from app.modules.pedidos.domain.entidades import EstadoPedido
    from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos

    servicio, creado, insumo = await crear_producto_prueba(uow)
    cliente = await uow.valor(
        "INSERT INTO cliente(nombre,telefono_whatsapp) "
        "VALUES ('Edición producto','5492215559998') RETURNING id"
    )
    pedidos = obtener_servicio_pedidos(uow)
    pedido = await pedidos.crear(
        cliente_id=cliente,
        tipo_entrega="RETIRO",
        direccion_id=None,
        direccion_nueva=None,
        observaciones=None,
        items=[ItemNuevoPedido(creado["id"], 1, variante="Simple")],
    )
    await pedidos.cambiar_estado(pedido["id"], EstadoPedido.CONFIRMADO, usuario_id=None)
    antes = await pedidos.detalle(pedido["id"])
    saldo = await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (insumo,))
    detalle = await servicio.obtener_edicion(creado["id"])
    receta = [{"ingrediente_id": insumo, "cantidad_requerida": "0.250", "es_base": True}]
    actualizado = await servicio.actualizar(
        creado["id"],
        entrada(
            detalle,
            nombre="Burger editada",
            descripcion="Descripción nueva",
            precio_base="900",
            orden=7,
            imagen_url="/images/burger-nueva.webp",
            ingredientes=receta,
            variantes=[{"nombre": "Mediana", "precio": "950", "ingredientes": receta}],
            extras=[
                {
                    "ingrediente_id": insumo,
                    "cantidad_requerida": "0.025",
                    "precio": "50",
                    "max_por_item": 2,
                }
            ],
        ),
    )
    assert actualizado["producto_id"] == creado["id"]
    assert actualizado["nombre"] == "Burger editada"
    assert actualizado["precio_base"] == Decimal("900")
    assert actualizado["imagen_url"] == "/images/burger-nueva.webp"
    assert actualizado["orden"] == 7
    assert actualizado["variantes"][0]["nombre"] == "Mediana"
    assert actualizado["variantes"][0]["precio"] == "950"
    assert actualizado["extras"][0]["precio"] == Decimal("50")
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (insumo,)) == saldo
    )
    despues = await pedidos.detalle(pedido["id"])
    assert despues["items"] == antes["items"]
    assert despues["total"] == antes["total"]
    assert actualizado["actualizado_en"] != detalle["actualizado_en"]
    with pytest.raises(ReglaDeNegocio):
        await servicio.actualizar(creado["id"], entrada(detalle, nombre="Cambio obsoleto"))
    await pedidos.cambiar_estado(pedido["id"], EstadoPedido.CANCELADO, usuario_id=None)
    assert await uow.valor(
        "SELECT cantidad_actual FROM ingrediente WHERE id=%s", (insumo,)
    ) == Decimal("0.500")


async def test_imagen_nula_borra_foto_y_precio_propio_actualiza_sin_nombre_duplicado(uow):
    servicio, creado, _ = await crear_producto_prueba(uow)
    await uow.ejecutar(
        "UPDATE producto SET imagen_url='https://example.com/burger.jpg',"
        "hamburguesas_por_unidad=2 WHERE id=%s",
        (creado["id"],),
    )
    detalle = await servicio.obtener_edicion(creado["id"])
    actualizado = await servicio.actualizar(
        creado["id"], entrada(detalle, imagen_url=None, precio_base="120")
    )
    assert actualizado["nombre"] == creado["nombre"]
    assert actualizado["imagen_url"] is None
    assert (
        await uow.valor("SELECT hamburguesas_por_unidad FROM producto WHERE id=%s", (creado["id"],))
        == 2
    )


async def test_no_acepta_nombre_ajeno_en_categoria_ni_categoria_destino_inactiva(uow):
    servicio, creado, _ = await crear_producto_prueba(uow)
    detalle = await servicio.obtener_edicion(creado["id"])
    await uow.ejecutar(
        "INSERT INTO producto(categoria_id,nombre,precio_base) VALUES (%s,'Ocupado',1)",
        (creado["categoria_id"],),
    )
    with pytest.raises(ReglaDeNegocio):
        await servicio.actualizar(creado["id"], entrada(detalle, nombre="OCUPADO"))
    categoria = await uow.valor(
        "INSERT INTO categoria(nombre,activa) VALUES ('Inactiva edición',false) RETURNING id"
    )
    with pytest.raises(DatosInvalidos):
        await servicio.actualizar(creado["id"], entrada(detalle, categoria_id=categoria))
    assert (await servicio.obtener_edicion(creado["id"]))["actualizado_en"] == detalle[
        "actualizado_en"
    ]


async def test_conserva_insumo_inactivo_historico_pero_rechaza_nueva_demanda(uow):
    servicio, creado, insumo = await crear_producto_prueba(uow)
    await uow.ejecutar("UPDATE ingrediente SET activo=false WHERE id=%s", (insumo,))
    detalle = await servicio.obtener_edicion(creado["id"])
    actualizado = await servicio.actualizar(creado["id"], entrada(detalle, nombre="Solo metadatos"))
    with pytest.raises(DatosInvalidos):
        datos = cuerpo(actualizado)
        datos["ingredientes"][0]["cantidad_requerida"] = "0.250"
        datos["variantes"][0]["ingredientes"][0]["cantidad_requerida"] = "0.250"
        from app.modules.productos.presentation.esquemas import ProductoActualizar

        await servicio.actualizar(creado["id"], ProductoActualizar(**datos).a_dominio())


async def test_http_guarda_todo_y_comparte_version_con_edicion_de_receta(uow):
    servicio, creado, _ = await crear_producto_prueba(uow)
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)

    async def conexion():
        yield uow

    app.dependency_overrides[obtener_uow] = conexion
    app.dependency_overrides[sesion_vigente] = lambda: ClaimsSesion(1, Rol.DUENIO, "prueba")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as cliente:
        url = f"/api/productos/{creado['id']}"
        respuesta = await cliente.get(url)
        assert respuesta.status_code == 200
        detalle = respuesta.json()
        assert detalle["categorias"]
        actualizado = await cliente.put(
            url, json=cuerpo(detalle, nombre="Nuevo HTTP", precio_base="320")
        )
        assert actualizado.status_code == 200
        assert actualizado.json()["nombre"] == "Nuevo HTTP"
        repetido = await cliente.put(url, json=cuerpo(detalle, nombre="Viejo HTTP"))
        assert repetido.status_code == 409
        assert (await servicio.obtener_receta(creado["id"]))["actualizado_en"] != detalle[
            "actualizado_en"
        ]


async def test_cambio_estado_invalida_el_editor_incluso_en_misma_transaccion(uow):
    servicio, creado, _ = await crear_producto_prueba(uow)
    detalle = await servicio.obtener_edicion(creado["id"])
    await servicio.cambiar_estado(creado["id"], activo=False)
    with pytest.raises(ReglaDeNegocio):
        await servicio.actualizar(creado["id"], entrada(detalle, nombre="Editor obsoleto"))


@pytest.mark.parametrize(
    "imagen",
    [
        None,
        "/images/menu/burger.webp",
        "https://example.com/burger.jpg",
        "http://example.com/menu.png",
    ],
)
def test_actualizar_admite_referencias_de_imagen_o_quitarlas(imagen):
    from app.modules.productos.presentation.esquemas import ProductoActualizar

    datos = ProductoActualizar(
        categoria_id=1,
        nombre="Burger",
        precio_base="100",
        imagen_url=imagen,
        actualizado_en_esperado="2026-10-29T00:00:00Z",
        ingredientes=[{"ingrediente_id": 1, "cantidad_requerida": "1"}],
    )
    assert datos.imagen_url == imagen


def test_imagen_embebida_requiere_firma_y_respeta_maximo_cinco_mib():
    import base64

    from app.modules.productos.domain.imagenes import MAX_IMAGEN_BYTES, validar_imagen_producto

    prefijo = "data:image/png;base64,"
    valida = prefijo + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"a" * 10).decode()
    assert validar_imagen_producto(valida) == valida
    for contenido in [b"<html>No es PNG</html>", b"\x89PNG\r\n\x1a\n" + b"a" * MAX_IMAGEN_BYTES]:
        with pytest.raises(ValueError):
            validar_imagen_producto(prefijo + base64.b64encode(contenido).decode())


async def test_producto_inactivo_puede_conservar_categoria_inactiva_y_no_reactivarse(uow):
    servicio, creado, _ = await crear_producto_prueba(uow)
    await uow.ejecutar("UPDATE producto SET activo=false WHERE id=%s", (creado["id"],))
    await uow.ejecutar("UPDATE categoria SET activa=false WHERE id=%s", (creado["categoria_id"],))
    detalle = await servicio.obtener_edicion(creado["id"])
    assert any(c["id"] == creado["categoria_id"] and not c["activa"] for c in detalle["categorias"])
    actualizado = await servicio.actualizar(
        creado["id"], entrada(detalle, nombre="Inactivo editado")
    )
    assert actualizado["activo"] is False
    with pytest.raises(DatosInvalidos):
        await servicio.actualizar(creado["id"], entrada(actualizado, activo=True))


async def test_producto_activo_oculto_por_categoria_inactiva_puede_editar_metadatos(uow):
    servicio, creado, _ = await crear_producto_prueba(uow)
    await uow.ejecutar("UPDATE categoria SET activa=false WHERE id=%s", (creado["categoria_id"],))
    detalle = await servicio.obtener_edicion(creado["id"])
    assert detalle["activo"] is True
    actualizado = await servicio.actualizar(creado["id"], entrada(detalle, nombre="Oculto editado"))
    assert actualizado["activo"] is True
    assert actualizado["nombre"] == "Oculto editado"


async def test_categoria_dips_exige_retirar_extras_al_editar(uow):
    servicio, creado, insumo = await crear_producto_prueba(uow)
    detalle = await servicio.obtener_edicion(creado["id"])
    dips = await uow.valor("SELECT id FROM categoria WHERE lower(nombre)='dips extra'")
    with pytest.raises(DatosInvalidos):
        await servicio.actualizar(
            creado["id"],
            entrada(
                detalle,
                categoria_id=dips,
                extras=[
                    {
                        "ingrediente_id": insumo,
                        "cantidad_requerida": "0.1",
                        "precio": "50",
                        "max_por_item": 1,
                    }
                ],
            ),
        )
    actualizado = await servicio.actualizar(
        creado["id"], entrada(detalle, categoria_id=dips, extras=[])
    )
    assert actualizado["categoria_id"] == dips
    assert actualizado["extras"] == []


async def test_alta_fija_categoria_para_serializar_unicidad_con_edicion(uow):
    from psycopg.errors import LockNotAvailable

    from app.modules.productos.infrastructure.repositorio_sql import RepositorioProductosSQL
    from tests.soporte_bd import conectar_o_omitir

    categoria = await uow.valor("SELECT id FROM categoria WHERE activa ORDER BY id LIMIT 1")
    assert await RepositorioProductosSQL(uow).categoria_existe(categoria)
    otra = await conectar_o_omitir()
    try:
        with pytest.raises(LockNotAvailable):
            await otra.execute(
                "SELECT id FROM categoria WHERE id=%s FOR UPDATE NOWAIT", (categoria,)
            )
    finally:
        await otra.rollback()
        await otra.close()

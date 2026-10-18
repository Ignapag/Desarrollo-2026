"""Recetas explícitas por variante y edición con control de versión."""

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.core.dependencias import obtener_uow
from app.core.errores import manejador_error_dominio
from app.errores import DatosInvalidos, ErrorDominio, ReglaDeNegocio
from app.modules.productos.application.servicio_productos import ServicioProductos
from app.modules.productos.infrastructure.repositorio_sql import RepositorioProductosSQL
from app.modules.productos.presentation.esquemas import ProductoCrear, RecetaActualizar
from app.modules.productos.presentation.router import router
from app.modules.usuarios.domain.entidades import ClaimsSesion, Rol
from app.modules.usuarios.presentation.dependencias import usuario_actual


def producto(**cambios):
    datos = dict(
        categoria_id=1,
        nombre="Nueva",
        precio_base="100",
        ingredientes=[dict(ingrediente_id=1, cantidad_requerida="0.125")],
    )
    return datos | cambios


def test_cantidades_no_redondean_ni_aceptan_no_finitos():
    for cantidad in ["0.0001", "0", "NaN", "Infinity"]:
        with pytest.raises(ValidationError):
            ProductoCrear(
                **producto(ingredientes=[dict(ingrediente_id=1, cantidad_requerida=cantidad)])
            )
    assert ProductoCrear(**producto()).ingredientes[0].cantidad_requerida == Decimal("0.125")
    assert ProductoCrear(
        **producto(ingredientes=[dict(ingrediente_id=1, cantidad_requerida=0.125)])
    ).ingredientes[0].cantidad_requerida == Decimal("0.125")


def test_creacion_admite_recetas_distintas_y_nombres_unicos():
    variantes = [
        dict(nombre=" Simple ", precio="100", ingredientes=producto()["ingredientes"]),
        dict(
            nombre="Doble",
            precio="200",
            ingredientes=[dict(ingrediente_id=1, cantidad_requerida="0.250")],
        ),
    ]
    datos = ProductoCrear(**producto(variantes=variantes))
    assert datos.variantes[0].nombre == "Simple"
    variantes[1]["nombre"] = "simple"
    with pytest.raises(ValidationError):
        ProductoCrear(**producto(variantes=variantes))


@pytest.mark.parametrize(
    "ingredientes",
    [
        [dict(ingrediente_id=2, cantidad_requerida="1")],
        [dict(ingrediente_id=1, cantidad_requerida="0.250")],
    ],
)
def test_primera_variante_debe_coincidir_con_receta_base(ingredientes):
    with pytest.raises(ValidationError):
        ProductoCrear(
            **producto(variantes=[dict(nombre="Simple", precio="100", ingredientes=ingredientes)])
        )


def test_variante_no_permite_ingredientes_distintos():
    with pytest.raises(ValidationError):
        ProductoCrear(
            **producto(
                variantes=[
                    dict(nombre="Simple", precio="100", ingredientes=producto()["ingredientes"]),
                    dict(
                        nombre="Doble",
                        precio="200",
                        ingredientes=[dict(ingrediente_id=2, cantidad_requerida="1")],
                    ),
                ]
            )
        )


async def test_edicion_rechaza_version_vieja_sin_escribir():
    class Repo:
        escrituras = 0

        async def obtener_receta(self, producto_id, *, bloquear=False):
            assert bloquear
            return dict(actualizado_en=datetime(2026, 1, 2, tzinfo=UTC), variantes=[])

        async def guardar_receta(self, *args):
            self.escrituras += 1

    repo = Repo()
    datos = RecetaActualizar(
        actualizado_en_esperado=datetime(2026, 1, 1, tzinfo=UTC),
        ingredientes=producto()["ingredientes"],
        variantes=[],
    )
    with pytest.raises(ReglaDeNegocio, match="modific"):
        await ServicioProductos(repo).actualizar_receta(1, datos.a_dominio())
    assert repo.escrituras == 0


async def test_edicion_no_permite_cambiar_variantes():
    version = datetime(2026, 1, 1, tzinfo=UTC)

    class Repo:
        async def obtener_receta(self, producto_id, *, bloquear=False):
            return dict(actualizado_en=version, variantes=[dict(nombre="Simple", precio="100")])

    datos = RecetaActualizar(
        actualizado_en_esperado=version, ingredientes=producto()["ingredientes"], variantes=[]
    )
    with pytest.raises(DatosInvalidos, match="variantes"):
        await ServicioProductos(Repo()).actualizar_receta(1, datos.a_dominio())


async def test_recetas_sin_sesion_rechazan_antes_de_abrir_uow():
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)

    async def conexion_prohibida():
        pytest.fail("No debe abrir conexión sin autorización")

    app.dependency_overrides[obtener_uow] = conexion_prohibida
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        assert (await c.get("/api/productos/1/receta")).status_code == 401
        respuesta = await c.put(
            "/api/productos/1/receta",
            json={
                "actualizado_en_esperado": "2026-01-01T00:00:00Z",
                "ingredientes": producto()["ingredientes"],
                "variantes": [],
            },
        )
        assert respuesta.status_code == 401


@pytest.mark.parametrize(
    "rol,metodo",
    [
        (Rol.CLIENTE, "GET"),
        (Rol.CLIENTE, "PUT"),
        (Rol.EMPLEADO, "PUT"),
        (Rol.REPARTIDOR, "PUT"),
    ],
)
async def test_roles_receta_no_autorizados_no_abren_uow(rol, metodo):
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)
    app.dependency_overrides[usuario_actual] = lambda: ClaimsSesion(1, rol, "prueba")

    async def conexion_prohibida():
        pytest.fail("Un rol sin permiso no debe abrir conexión")

    app.dependency_overrides[obtener_uow] = conexion_prohibida
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as cliente:
        respuesta = await cliente.request(
            metodo,
            "/api/productos/1/receta",
            json={
                "actualizado_en_esperado": "2026-01-01T00:00:00Z",
                "ingredientes": producto()["ingredientes"],
                "variantes": [],
            },
        )
        assert respuesta.status_code == 403


async def crear_producto_prueba(uow):
    categoria_id = await uow.valor(
        "INSERT INTO categoria(nombre) VALUES ('Recetas test') RETURNING id"
    )
    ingrediente_id = await uow.valor(
        """INSERT INTO ingrediente(nombre,unidad_medida,cantidad_actual,umbral_minimo)
           VALUES ('Fracción test','KG',0.500,1) RETURNING id"""
    )
    receta = [dict(ingrediente_id=ingrediente_id, cantidad_requerida="0.125")]
    datos = ProductoCrear(
        **producto(
            categoria_id=categoria_id,
            ingredientes=receta,
            variantes=[
                dict(nombre="Simple", precio="100", ingredientes=receta),
                dict(
                    nombre="Doble",
                    precio="200",
                    ingredientes=[dict(ingrediente_id=ingrediente_id, cantidad_requerida="0.750")],
                ),
            ],
        )
    )
    servicio = ServicioProductos(RepositorioProductosSQL(uow))
    creado = await servicio.crear(datos.a_dominio())
    return servicio, creado, ingrediente_id


async def test_bd_recetas_variantes_persisten_exactas_y_disponibilidad_independiente(uow):
    servicio, creado, ingrediente_id = await crear_producto_prueba(uow)
    assert creado["disponible"] is True
    assert [v["disponible"] for v in creado["variantes"]] == [True, False]
    receta = await servicio.obtener_receta(creado["id"])
    assert [v["ingredientes"][0]["cantidad_requerida"] for v in receta["variantes"]] == [
        Decimal("0.125"),
        Decimal("0.750"),
    ]
    assert all(v["receta_configurada"] for v in receta["variantes"])
    assert receta["ingredientes"][0]["ingrediente_id"] == ingrediente_id


async def test_bd_edicion_atomica_no_cambia_precios_y_version_vieja_conflicta(uow):
    servicio, creado, ingrediente_id = await crear_producto_prueba(uow)
    actual = await servicio.obtener_receta(creado["id"])
    base = [dict(ingrediente_id=ingrediente_id, cantidad_requerida="0.150", es_base=True)]
    datos = RecetaActualizar(
        actualizado_en_esperado=actual["actualizado_en"],
        ingredientes=base,
        variantes=[
            dict(nombre="Simple", ingredientes=base),
            dict(
                nombre="Doble",
                ingredientes=[
                    dict(ingrediente_id=ingrediente_id, cantidad_requerida="0.300", es_base=True)
                ],
            ),
        ],
    )
    nueva = await servicio.actualizar_receta(creado["id"], datos.a_dominio())
    assert nueva["actualizado_en"] != actual["actualizado_en"]
    assert nueva["ingredientes"][0]["cantidad_requerida"] == Decimal("0.150")
    assert [Decimal(v["precio"]) for v in nueva["variantes"]] == [Decimal("100"), Decimal("200")]
    with pytest.raises(ReglaDeNegocio):
        await servicio.actualizar_receta(creado["id"], datos.a_dominio())
    assert await servicio.obtener_receta(creado["id"]) == nueva


async def test_bd_receta_legada_no_inventa_multiplicadores(uow):
    servicio, creado, _ = await crear_producto_prueba(uow)
    await uow.ejecutar(
        "DELETE FROM producto_variante_ingrediente WHERE producto_id=%s", (creado["id"],)
    )
    receta = await servicio.obtener_receta(creado["id"])
    assert all(not v["receta_configurada"] for v in receta["variantes"])
    assert all(v["ingredientes"] == receta["ingredientes"] for v in receta["variantes"])


async def test_bd_receta_http_valida_permiso_cantidades_y_guarda(uow):
    _, creado, _ = await crear_producto_prueba(uow)
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)

    async def conexion_prueba():
        yield uow

    app.dependency_overrides[obtener_uow] = conexion_prueba
    app.dependency_overrides[usuario_actual] = lambda: ClaimsSesion(1, Rol.DUENIO, "prueba")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as cliente:
        url = f"/api/productos/{creado['id']}/receta"
        respuesta = await cliente.get(url)
        assert respuesta.status_code == 200
        receta = respuesta.json()
        assert receta["variantes"][1]["ingredientes"][0]["cantidad_requerida"] == "0.750"
        cuerpo = {
            "actualizado_en_esperado": receta["actualizado_en"],
            "ingredientes": [
                {
                    k: v
                    for k, v in i.items()
                    if k in {"ingrediente_id", "cantidad_requerida", "es_base"}
                }
                for i in receta["ingredientes"]
            ],
            "variantes": [
                {
                    "nombre": v["nombre"],
                    "ingredientes": [
                        {
                            k: valor
                            for k, valor in i.items()
                            if k in {"ingrediente_id", "cantidad_requerida", "es_base"}
                        }
                        for i in v["ingredientes"]
                    ],
                }
                for v in receta["variantes"]
            ],
        }
        assert (await cliente.put(url, json=cuerpo | {"precio_base": "1"})).status_code == 422
        cuerpo["variantes"][1]["ingredientes"][0]["cantidad_requerida"] = "0.350"
        guardada = await cliente.put(url, json=cuerpo)
        assert guardada.status_code == 200
        assert guardada.json()["variantes"][1]["ingredientes"][0]["cantidad_requerida"] == "0.350"
        assert (await cliente.put(url, json=cuerpo)).status_code == 409

"""Las opciones ofrecidas por el menú respetan receta, bot y consumo de stock."""

import httpx
from fastapi import FastAPI

from app.core.dependencias import obtener_uow
from app.core.errores import manejador_error_dominio
from app.errores import ErrorDominio
from app.modules.productos.application.servicio_productos import ServicioProductos
from app.modules.productos.presentation.router import router as productos
from app.modules.whatsapp.presentation.router import router as whatsapp


async def test_catalogo_solo_ofrece_retiros_permitidos_de_la_receta():
    class Repositorio:
        async def listar(self, *, solo_activos):
            return [{"id": 54, "ingredientes_receta": [
                "Pan de Hamburguesa", "Medallón de Carne", "Queso Cheddar", "Salsa Monu"
            ]}]

    resultado = await ServicioProductos(Repositorio()).listar()
    assert resultado[0]["ingredientes_quitables"] == ["Queso Cheddar", "Salsa Monu"]
    assert "ingredientes_receta" not in resultado[0]


async def test_todas_las_opciones_del_catalogo_son_aceptadas_en_checkout(uow):
    app = FastAPI()
    app.include_router(productos)
    app.include_router(whatsapp)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)

    async def conexion_prueba():
        yield uow

    app.dependency_overrides[obtener_uow] = conexion_prueba
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as cliente:
        respuesta = await cliente.get("/api/productos")
        assert respuesta.status_code == 200
        catalogo = respuesta.json()
        cheese = next(p for p in catalogo if p["nombre"] == "Cheese")
        assert {i.casefold() for i in cheese["ingredientes_quitables"]} == {
            "queso cheddar", "salsa monu"
        }
        assert all(p["ingredientes_quitables"] == [] for p in catalogo if p["nombre"] == "Fanta")
        comprobados = 0
        for producto in catalogo:
            opciones = producto["ingredientes_quitables"]
            if not opciones or not producto["disponible"]:
                continue
            variante = (producto["variantes"] or [{}])[0].get("nombre")
            respuesta = await cliente.post("/api/whatsapp/borradores", json={"items": [{
                "producto_id": producto["id"], "cantidad": 1, "variante": variante,
                "aclaraciones": ", ".join("Sin " + ingrediente for ingrediente in opciones),
            }]})
            assert respuesta.status_code == 201, (producto["nombre"], respuesta.json())
            comprobados += 1
        assert comprobados > 0

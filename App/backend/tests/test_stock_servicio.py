"""Validaciones del servicio de stock sin base de datos."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date
from decimal import Decimal

import pytest

from app.core.errores import DatosInvalidos, ReglaDeNegocio
from app.modules.stock.application.servicio_stock import ServicioStock
from app.modules.stock.domain.entidades import DatosIngrediente, nivel_stock


class RepositorioFalso:
    def __init__(self) -> None:
        self.filas: dict[int, dict] = {}
        self.consulta_historial: dict | None = None
        self.con_producto_activo = False

    async def existe_nombre(self, nombre, *, excepto_id=None):
        return any(
            fila["nombre"].casefold() == nombre.casefold() and id_ != excepto_id
            for id_, fila in self.filas.items()
        )

    async def responsable_valido(self, responsable_id):
        return responsable_id == 7

    async def asociado_a_producto_activo(self, ingrediente_id):
        return self.con_producto_activo

    async def crear(self, datos):
        fila = {**asdict(datos), "id": len(self.filas) + 1}
        self.filas[fila["id"]] = fila
        return fila

    async def ingrediente(self, ingrediente_id, *, bloquear=False):
        return self.filas.get(ingrediente_id)

    async def modificar(self, ingrediente_id, datos):
        fila = {**asdict(datos), "id": ingrediente_id}
        self.filas[ingrediente_id] = fila
        return fila

    async def listar(self, **filtros):
        return list(self.filas.values())

    async def reponer(self, ingrediente_id, cantidad, *, usuario_id, origen):
        fila = self.filas[ingrediente_id]
        anterior = fila["cantidad_actual"]
        fila["cantidad_actual"] += cantidad
        return {"saldo_anterior": anterior, "saldo_resultante": fila["cantidad_actual"]}

    async def historial(self, **filtros):
        self.consulta_historial = filtros
        return []


@pytest.fixture
def datos():
    return DatosIngrediente(" Pan ", "UNIDAD", Decimal("10"), Decimal("2"))


@pytest.fixture
def servicio():
    return ServicioStock(RepositorioFalso())


@pytest.mark.asyncio
async def test_alta_correcta_y_nombre_normalizado(servicio, datos):
    fila = await servicio.registrar(datos)
    assert fila["nombre"] == "Pan"
    assert fila["cantidad_actual"] == 10


@pytest.mark.asyncio
async def test_rechaza_nombre_duplicado_sin_distinguir_mayusculas(servicio, datos):
    await servicio.registrar(datos)
    with pytest.raises(ReglaDeNegocio):
        await servicio.registrar(replace(datos, nombre="pan"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cambios",
    [
        {"nombre": "   "},
        {"unidad_medida": "CAJA"},
        {"cantidad_actual": Decimal("-1")},
        {"umbral_minimo": Decimal("0")},
        {"umbral_minimo": Decimal("-1")},
        {"responsable_id": 999},
    ],
)
async def test_alta_rechaza_datos_invalidos(servicio, datos, cambios):
    with pytest.raises(DatosInvalidos):
        await servicio.registrar(replace(datos, **cambios))


@pytest.mark.asyncio
async def test_modificar_no_permite_editar_cantidad(servicio, datos):
    await servicio.registrar(datos)
    with pytest.raises(DatosInvalidos):
        await servicio.modificar(1, {"cantidad_actual": Decimal("50")})


@pytest.mark.asyncio
async def test_modificar_umbral_conserva_cantidad(servicio, datos):
    await servicio.registrar(datos)
    fila = await servicio.modificar(1, {"umbral_minimo": Decimal("3")})
    assert fila["cantidad_actual"] == 10
    assert fila["umbral_minimo"] == 3


@pytest.mark.asyncio
async def test_modificar_rechaza_nombre_nulo(servicio, datos):
    await servicio.registrar(datos)
    with pytest.raises(DatosInvalidos):
        await servicio.modificar(1, {"nombre": None})


@pytest.mark.asyncio
async def test_no_desactiva_ingrediente_asociado_a_producto_activo(servicio, datos):
    await servicio.registrar(datos)
    servicio.repo.con_producto_activo = True
    with pytest.raises(ReglaDeNegocio):
        await servicio.modificar(1, {"activo": False})


@pytest.mark.asyncio
@pytest.mark.parametrize("cantidad", [Decimal("0"), Decimal("-1")])
async def test_reposicion_rechaza_cantidad_no_positiva(servicio, datos, cantidad):
    await servicio.registrar(datos)
    with pytest.raises(DatosInvalidos):
        await servicio.reponer(1, cantidad)


@pytest.mark.asyncio
async def test_reposicion_valida_actualiza_saldo(servicio, datos):
    await servicio.registrar(datos)
    resultado = await servicio.reponer(1, Decimal("2.5"))
    assert resultado == {"saldo_anterior": 10, "saldo_resultante": Decimal("12.5")}


@pytest.mark.asyncio
async def test_historial_pasa_filtros_y_valida_rango(servicio, datos):
    await servicio.registrar(datos)
    await servicio.historial(
        ingrediente_id=1,
        desde=date(2026, 1, 1),
        hasta=date(2026, 1, 31),
        tipo="REPOSICION",
    )
    assert servicio.repo.consulta_historial["tipo"] == "REPOSICION"
    with pytest.raises(DatosInvalidos):
        await servicio.historial(desde=date(2026, 2, 1), hasta=date(2026, 1, 1))


def test_niveles_de_stock():
    assert nivel_stock(Decimal("0"), Decimal("5")) == "SIN_STOCK"
    assert nivel_stock(Decimal("5"), Decimal("5")) == "BAJO_UMBRAL"
    assert nivel_stock(Decimal("6"), Decimal("5")) == "NORMAL"

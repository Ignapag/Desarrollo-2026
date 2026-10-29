"""Las bajas conservan filas y sus relaciones sin afectar las lecturas operativas."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.modules.productos.application.servicio_productos import ServicioProductos
from app.modules.productos.infrastructure.repositorio_sql import RepositorioProductosSQL
from app.modules.productos.presentation.esquemas import ProductoCrear, RecetaActualizar
from app.modules.reportes.infrastructure.repositorio_sql import RepositorioReportesSQL
from app.modules.usuarios.infrastructure.acceso_sql import RepositorioAccesoSQL
from tests.test_edicion_items_bd import crear
from tests.test_reportes_bd import escenario, pedido_con_item


async def test_retirar_y_reincorporar_ingrediente_conserva_clave_y_filtra_costo(uow):
    categoria = await uow.valor("INSERT INTO categoria(nombre) VALUES ('Bajas test') RETURNING id")
    ingredientes = []
    for nombre, costo in (("Base baja test", 2), ("Extra baja test", 3)):
        ingredientes.append(await uow.valor(
            "INSERT INTO ingrediente(nombre,unidad_medida,cantidad_actual,umbral_minimo,"
            "costo_unitario) VALUES (%s,'UNIDAD',10,1,%s) RETURNING id", (nombre, costo),
        ))
    receta = [dict(ingrediente_id=i, cantidad_requerida="1") for i in ingredientes]
    servicio = ServicioProductos(RepositorioProductosSQL(uow))
    creado = await servicio.crear(ProductoCrear(
        categoria_id=categoria, nombre="Baja receta test", precio_base="100", ingredientes=receta,
    ).a_dominio())
    actual = await servicio.obtener_receta(creado["id"])
    retirada = await servicio.actualizar_receta(creado["id"], RecetaActualizar(
        actualizado_en_esperado=actual["actualizado_en"], ingredientes=receta[:1], variantes=[],
    ).a_dominio())

    assert await uow.valor(
        "SELECT count(*) FROM producto_ingrediente WHERE producto_id=%s", (creado["id"],),
    ) == 2
    assert await uow.valor(
        "SELECT eliminado_en IS NOT NULL FROM producto_ingrediente "
        "WHERE producto_id=%s AND ingrediente_id=%s", (creado["id"], ingredientes[1]),
    ) is True
    assert [i["ingrediente_id"] for i in retirada["ingredientes"]] == ingredientes[:1]
    assert await uow.valor(
        "SELECT costo_insumos FROM producto_costo WHERE producto_id=%s", (creado["id"],),
    ) == Decimal("2")

    recuperada = await servicio.actualizar_receta(creado["id"], RecetaActualizar(
        actualizado_en_esperado=retirada["actualizado_en"], ingredientes=receta, variantes=[],
    ).a_dominio())
    assert {i["ingrediente_id"] for i in recuperada["ingredientes"]} == set(ingredientes)
    assert await uow.valor(
        "SELECT count(*) FROM producto_ingrediente WHERE producto_id=%s "
        "AND eliminado_en IS NULL", (creado["id"],),
    ) == 2


async def test_revocar_y_reconceder_permiso_conserva_relacion_sin_dar_acceso(uow):
    repo = RepositorioAccesoSQL(uow)
    originales = await repo.permisos("EMPLEADO")
    version = await uow.valor("SELECT version FROM rol_acceso WHERE rol='EMPLEADO'")
    assert "stock.ver" in originales
    nuevos = [p for p in originales if p != "stock.ver"]
    await repo.guardar("EMPLEADO", nuevos, version, None)

    assert await uow.valor(
        "SELECT count(*) FROM rol_permiso WHERE rol='EMPLEADO' AND permiso='stock.ver'",
    ) == 1
    assert "stock.ver" not in await repo.permisos("EMPLEADO")
    rol = next(r for r in await repo.roles() if r["rol"] == "EMPLEADO")
    assert "stock.ver" not in rol["permisos"]
    await repo.guardar("EMPLEADO", originales, version + 1, None)
    assert "stock.ver" in await repo.permisos("EMPLEADO")
    assert await uow.valor(
        "SELECT count(*) FROM rol_permiso WHERE rol='EMPLEADO' AND permiso='stock.ver'",
    ) == 1


async def test_quitar_item_conserva_snapshot_y_no_lo_devuelve_en_detalle_o_stock(uow):
    servicio, pedido, producto, _ = await crear(uow)
    original = pedido["items"][0]
    ampliado = await servicio.editar_items(
        pedido["id"],
        items=[{"id": original["id"], "cantidad": 1}, {"producto_id": producto, "cantidad": 2}],
        version_esperada=pedido["version"],
    )
    retirado = ampliado["items"][1]
    quitado = await servicio.editar_items(
        pedido["id"], items=[{"id": original["id"], "cantidad": 1}],
        version_esperada=ampliado["version"],
    )

    assert await uow.valor(
        "SELECT count(*) FROM pedido_item WHERE pedido_id=%s", (pedido["id"],),
    ) == 2
    fila = await uow.uno("SELECT * FROM pedido_item WHERE id=%s", (retirado["id"],))
    assert fila["eliminado_en"] is not None
    assert fila["receta_snapshot"] == retirado["receta_snapshot"]
    assert [i["id"] for i in quitado["items"]] == [original["id"]]
    assert len(await servicio.repo.items_para_stock(pedido["id"])) == 1
    recuperables = await servicio.repo.items_retirados(pedido["id"])
    assert [i["id"] for i in recuperables] == [retirado["id"]]
    assert recuperables[0]["receta_snapshot"] == retirado["receta_snapshot"]


async def test_reportes_no_suman_items_retirados_de_un_pedido_vendido(uow):
    cliente, _, productos = await escenario(uow)
    pedido = await pedido_con_item(
        uow, cliente, productos[0], "CONFIRMADO", datetime(2026, 9, 1, 15, tzinfo=UTC),
    )
    await uow.ejecutar(
        "INSERT INTO pedido_item(pedido_id,producto_id,nombre_producto,cantidad,precio_unitario,"
        "subtotal,eliminado_en) VALUES (%s,%s,'Retirado',99,100,9900,now())",
        (pedido, productos[0]),
    )
    repo = RepositorioReportesSQL(uow)
    dia = date(2026, 9, 1)
    ventas = await repo.ventas(dia, dia, "day", None, productos[0], incluir_montos=True)
    assert ventas[0]["cantidad_vendida"] == 1
    assert ventas[0]["monto_total"] == 100
    rentabilidad = await repo.rentabilidad(dia, dia, None, productos[0])
    assert rentabilidad[0]["unidades_vendidas"] == 1
    assert rentabilidad[0]["ingreso_estimado"] == 100
    assert rentabilidad[0]["costo_estimado"] == 20

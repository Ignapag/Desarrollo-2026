"""La limpieza administrativa de tests conserva FK y restaura las guardas de datos."""

import psycopg
import pytest

from tests.soporte_bd import mantenimiento_pruebas


async def guardas(uow):
    return await uow.todos(
        "SELECT t.tgrelid,t.tgname,t.tgenabled FROM pg_trigger t "
        "JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND NOT t.tgisinternal AND t.tgname LIKE 'monu_conservar_%' "
        "ORDER BY t.tgrelid,t.tgname"
    )


async def test_mantenimiento_temporal_conserva_cascadas_y_reactiva_guardas(uow):
    cliente = await uow.valor(
        "INSERT INTO cliente(nombre,telefono_whatsapp) VALUES ('Limpieza test','5492210000001') "
        "RETURNING id"
    )
    pedido = await uow.valor(
        "INSERT INTO pedido(cliente_id,tipo_entrega) VALUES (%s,'RETIRO') RETURNING id", (cliente,),
    )
    producto = await uow.valor("SELECT id FROM producto ORDER BY id LIMIT 1")
    item = await uow.valor(
        "INSERT INTO pedido_item(pedido_id,producto_id,nombre_producto,cantidad,precio_unitario,"
        "subtotal) VALUES (%s,%s,'Limpieza',1,100,100) RETURNING id", (pedido, producto),
    )
    original = await guardas(uow)
    assert original
    async with mantenimiento_pruebas(uow):
        await uow.ejecutar("DELETE FROM pedido WHERE id=%s", (pedido,))
    assert await uow.valor("SELECT count(*) FROM pedido_item WHERE id=%s", (item,)) == 0
    assert await guardas(uow) == original
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        async with uow.conn.transaction():
            await uow.ejecutar("DELETE FROM cliente WHERE id=%s", (cliente,))


async def test_excepcion_revierte_limpieza_y_restituye_modos_de_triggers(uow):
    cliente = await uow.valor(
        "INSERT INTO cliente(nombre,telefono_whatsapp) "
        "VALUES ('Rollback limpieza','5492210000002') RETURNING id"
    )
    original = await guardas(uow)
    with pytest.raises(ValueError, match="fallo simulado"):
        async with mantenimiento_pruebas(uow):
            await uow.ejecutar("DELETE FROM cliente WHERE id=%s", (cliente,))
            raise ValueError("fallo simulado")
    assert await uow.valor("SELECT count(*) FROM cliente WHERE id=%s", (cliente,)) == 1
    assert await guardas(uow) == original


async def test_mantenimiento_purga_actor_previo_sin_referencia_huerfana(uow):
    actor = await uow.valor(
        "INSERT INTO usuario(nombre,apellido,username,password_hash,rol) "
        "VALUES ('Actor','Limpieza','actor_mantenimiento_test','x','EMPLEADO') RETURNING id"
    )
    await uow.configurar_auditoria(origen="HTTP:PRUEBA")
    await uow.atribuir_actor(actor)
    async with mantenimiento_pruebas(uow):
        await uow.ejecutar("DELETE FROM usuario WHERE id=%s", (actor,))
    assert await uow.valor("SELECT current_setting('monu.usuario_id',true)") == ""
    assert await uow.valor("SELECT current_setting('monu.origen',true)") == "HTTP:PRUEBA"


@pytest.mark.parametrize("entorno", [
    {"DATABASE_URL": "postgresql://u@remota.example/base"},
    {"PGSERVICE": "servicio_remoto"},
    {"PGHOSTADDR": "203.0.113.5"},
    {"DATABASE_URL": "postgresql://u@remota.example/base", "MONU_PERMITIR_BD_REMOTA": "1"},
])
async def test_mantenimiento_rechaza_destinos_remotos_incluso_con_opt_in(uow, monkeypatch, entorno):
    for clave, valor in entorno.items():
        monkeypatch.setenv(clave, valor)
    with pytest.raises(RuntimeError, match="no admite bases remotas"):
        async with mantenimiento_pruebas(uow):
            pytest.fail("No debe entrar al bloque de mantenimiento")

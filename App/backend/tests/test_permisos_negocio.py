"""Las capacidades concedidas reemplazan barreras de rol sin perder propiedad."""

import pytest

from app.errores import SinPermiso
from app.modules.delivery.application.servicio_delivery import ServicioDelivery
from app.modules.reportes.application.servicio_reportes import ServicioReportes
from app.modules.reportes.domain.reglas import validar_rol


def test_reporte_concedido_a_empleado_y_financiero_revocado_a_duenio():
    validar_rol("EMPLEADO", autorizado=True)
    validar_rol("ADMINISTRADOR", financiero=True, autorizado=True)
    with pytest.raises(SinPermiso):
        validar_rol("DUENIO", financiero=True, autorizado=False)


async def test_directorio_concedido_a_repartidor_y_revocado_a_empleado():
    class Repositorio:
        async def clientes(self, **filtros):
            return {"clientes": [{"id": 9}], "total": 1}

    servicio = ServicioReportes(Repositorio(), None)
    assert await servicio.clientes(rol="REPARTIDOR", autorizado=True) == {
        "clientes": [{"id": 9}],
        "total": 1,
    }
    with pytest.raises(SinPermiso):
        await servicio.clientes(rol="EMPLEADO", autorizado=False)


def test_delivery_concedido_no_elimina_propiedad_del_repartidor():
    ServicioDelivery._personal("REPARTIDOR", autorizado=True)
    with pytest.raises(SinPermiso):
        ServicioDelivery._personal("EMPLEADO", autorizado=False)
    with pytest.raises(SinPermiso):
        ServicioDelivery._autorizar({"repartidor_id": 2}, 1, "REPARTIDOR")


async def test_cobrar_no_habilita_conciliar_ingreso():
    from types import SimpleNamespace

    from app.modules.pagos.presentation.router import (
        registrar_pago_efectivo,
        registrar_transferencia,
    )

    class SesionSinConciliacion:
        usuario_id = 1

        def puede(self, permiso):
            return permiso == "pagos.registrar"

    with pytest.raises(SinPermiso):
        await registrar_pago_efectivo(
            SimpleNamespace(conciliar_inmediato=True),
            SesionSinConciliacion(),
            None,
            None,
        )
    with pytest.raises(SinPermiso):
        await registrar_transferencia(
            SimpleNamespace(),
            SesionSinConciliacion(),
            None,
            None,
            None,
            confirmar_ingreso=True,
        )


@pytest.mark.parametrize(
    "metodo,ruta",
    [
        ("get", "/api/pedidos"),
        ("post", "/api/pedidos"),
        ("patch", "/api/pedidos/1/operacion"),
        ("patch", "/api/pedidos/1/estado"),
        ("get", "/api/productos/1/receta"),
        ("post", "/api/productos"),
        ("get", "/api/stock/ingredientes"),
        ("post", "/api/stock/ingredientes"),
        ("post", "/api/stock/ingredientes/1/reposiciones"),
        ("get", "/api/pagos/1"),
        ("post", "/api/pagos/efectivo"),
        ("post", "/api/pagos/1/conciliar"),
        ("post", "/api/pagos/1/anular"),
        ("get", "/api/caja/cierres"),
        ("post", "/api/caja/cierres/generar"),
        ("post", "/api/caja/cierres/1/aprobar"),
        ("get", "/api/delivery/viajes"),
        ("post", "/api/delivery/planificacion"),
        ("post", "/api/delivery/viajes/1/iniciar"),
        ("post", "/api/delivery/envios/1/corregir-entrega"),
        ("get", "/api/reportes/clientes"),
        ("get", "/api/reportes/ventas"),
        ("get", "/api/reportes/rentabilidad"),
        ("get", "/api/whatsapp/bandeja"),
        ("post", "/api/whatsapp/atenciones/1/resolucion"),
        ("get", "/api/notificaciones"),
        ("post", "/api/notificaciones/plantillas"),
    ],
)
def test_permiso_revocado_rechaza_antes_de_servicio_de_negocio(metodo, ruta):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.dependencias import obtener_uow
    from app.core.errores import manejador_error_dominio
    from app.errores import ErrorDominio
    from app.modules.usuarios.domain.entidades import ClaimsSesion, Rol
    from app.modules.usuarios.presentation.dependencias import sesion_vigente
    from app.registro_modulos import registrar_routers

    app = FastAPI()
    registrar_routers(app)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)
    app.dependency_overrides[sesion_vigente] = lambda: ClaimsSesion(
        1,
        Rol.DUENIO,
        "duenio",
        frozenset(),
    )

    def negocio_prohibido():
        raise AssertionError("No debe obtener unidad de trabajo de negocio sin permiso")

    app.dependency_overrides[obtener_uow] = negocio_prohibido
    with TestClient(app) as cliente:
        respuesta = getattr(cliente, metodo)(ruta)
    assert respuesta.status_code == 403, respuesta.text


async def test_repartidor_despromovido_conserva_perfil_sin_ofrecerse_para_viajes(uow):
    from uuid import uuid4

    from app.modules.delivery.infrastructure.repositorio_sql import RepositorioDeliverySQL

    usuario = await uow.valor(
        "INSERT INTO usuario(nombre,apellido,username,password_hash,rol) "
        "VALUES('Repartidor','Historico',%s,'x','REPARTIDOR') RETURNING id",
        (uuid4().hex,),
    )
    await uow.ejecutar("INSERT INTO repartidor(usuario_id) VALUES(%s)", (usuario,))
    repo = RepositorioDeliverySQL(uow)
    assert usuario in {r.repartidor_id for r in await repo.repartidores_disponibles()}
    await uow.ejecutar("UPDATE usuario SET rol='EMPLEADO' WHERE id=%s", (usuario,))
    assert usuario not in {r.repartidor_id for r in await repo.repartidores_disponibles()}
    assert (
        await uow.valor("SELECT usuario_id FROM repartidor WHERE usuario_id=%s", (usuario,))
        == usuario
    )


@pytest.mark.parametrize(
    "ruta,permisos",
    [
        ("/comprobantes/1/revision", {"whatsapp.gestionar"}),
        ("/comprobantes/1/revision", {"whatsapp.gestionar", "pagos.registrar"}),
        ("/comprobantes/1/revision", {"whatsapp.gestionar", "pagos.conciliar"}),
        ("/cambios/1/revision", {"whatsapp.gestionar"}),
    ],
)
def test_revision_whatsapp_no_elude_permisos_del_negocio(ruta, permisos):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.dependencias import obtener_uow
    from app.core.errores import manejador_error_dominio
    from app.errores import ErrorDominio
    from app.modules.usuarios.domain.entidades import ClaimsSesion, Rol
    from app.modules.usuarios.presentation.dependencias import sesion_vigente
    from app.modules.whatsapp.presentation.router import router

    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)
    app.dependency_overrides[sesion_vigente] = lambda: ClaimsSesion(
        1,
        Rol.EMPLEADO,
        "operador",
        frozenset(permisos),
    )

    def negocio_prohibido():
        raise AssertionError("La aprobacion requiere todos los permisos antes del servicio")

    app.dependency_overrides[obtener_uow] = negocio_prohibido
    with TestClient(app) as cliente:
        respuesta = cliente.post(
            "/api/whatsapp" + ruta,
            json={
                "aprobar": True,
                "motivo": "Verificado",
                "total_verificado": 100,
            },
        )
    assert respuesta.status_code == 403, respuesta.text


@pytest.mark.parametrize("campo,nuevo", [("estado", "INACTIVO"), ("rol", "EMPLEADO")])
async def test_gestion_bloqueada_no_ofrece_candidato_y_revalida_al_confirmar(campo, nuevo):
    import asyncio
    from uuid import uuid4

    from app.core.db import UnidadDeTrabajo
    from app.modules.delivery.infrastructure.repositorio_sql import RepositorioDeliverySQL
    from tests.soporte_bd import conectar_o_omitir

    gestion, asignacion = await conectar_o_omitir(), await conectar_o_omitir()
    ug, ua = UnidadDeTrabajo(gestion), UnidadDeTrabajo(asignacion)
    usuario = None
    tarea = None
    try:
        usuario = await ug.valor(
            "INSERT INTO usuario(nombre,apellido,username,password_hash,rol) "
            "VALUES('Cuenta','Concurrente',%s,'x','REPARTIDOR') RETURNING id",
            (uuid4().hex,),
        )
        await ug.ejecutar("INSERT INTO repartidor(usuario_id) VALUES(%s)", (usuario,))
        await gestion.commit()
        await ug.valor(
            "SELECT usuario_id FROM repartidor WHERE usuario_id=%s FOR UPDATE", (usuario,)
        )
        candidatos = await asyncio.wait_for(
            RepositorioDeliverySQL(ua).repartidores_disponibles(bloquear=True),
            timeout=2,
        )
        assert usuario not in {r.repartidor_id for r in candidatos}
        if campo == "estado":
            await ug.ejecutar("UPDATE usuario SET estado=%s WHERE id=%s", (nuevo, usuario))
        else:
            await ug.ejecutar("UPDATE usuario SET rol=%s WHERE id=%s", (nuevo, usuario))
        await gestion.commit()
        candidatos = await RepositorioDeliverySQL(ua).repartidores_disponibles(bloquear=True)
        assert usuario not in {r.repartidor_id for r in candidatos}
    finally:
        if tarea is not None and not tarea.done():
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)
        await asignacion.rollback()
        await gestion.rollback()
        if usuario is not None:
            await ug.ejecutar("DELETE FROM repartidor WHERE usuario_id=%s", (usuario,))
            await ug.ejecutar("DELETE FROM usuario WHERE id=%s", (usuario,))
            await gestion.commit()
        await asignacion.close()
        await gestion.close()

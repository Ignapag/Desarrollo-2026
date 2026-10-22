"""Catálogo de capacidades; las concesiones vigentes se guardan por rol en SQL."""

MODULOS = (
    ("pedidos", "Pedidos", (
        ("ver", "Ver pedidos"), ("crear", "Crear pedidos"), ("editar", "Modificar pedidos"),
        ("cambiar_estado", "Cambiar estado"), ("recuperar", "Recuperar pedidos cerrados"),
    )),
    ("productos", "Menú / Catálogo", (
        ("ver_receta", "Ver recetas"), ("gestionar", "Crear y modificar productos y recetas"),
    )),
    ("stock", "Inventario", (
        ("ver", "Ver inventario"), ("gestionar", "Crear y modificar ingredientes"),
        ("reponer", "Registrar reposiciones"),
    )),
    ("pagos", "Pagos", (
        ("ver", "Ver pagos"), ("registrar", "Registrar cobros"),
        ("conciliar", "Conciliar transferencias"), ("corregir", "Anular y devolver pagos"),
    )),
    ("caja", "Caja", (
        ("ver", "Ver caja y cierres"), ("generar", "Generar cierres"),
        ("aprobar", "Aprobar cierres"),
    )),
    ("delivery", "Reparto", (
        ("ver", "Ver viajes"), ("operar", "Iniciar viajes y registrar entregas"),
        ("planificar", "Planificar y asignar repartos"), ("corregir", "Corregir entregas"),
    )),
    ("reportes", "Reportes", (
        ("ver", "Ver reportes de ventas"), ("financieros", "Ver rentabilidad y montos"),
    )),
    ("clientes", "Clientes", (("ver", "Ver directorio de clientes"),)),
    ("whatsapp", "Atención y notificaciones", (
        ("ver", "Ver bandeja y comprobantes"), ("gestionar", "Atender y revisar solicitudes"),
        ("ver_notificaciones", "Ver notificaciones"),
        ("gestionar_notificaciones", "Administrar plantillas y envíos"),
    )),
    ("auditoria", "Auditoría", (("ver", "Consultar auditoría"),)),
    ("usuarios", "Control de acceso", (
        ("ver", "Ver usuarios"), ("gestionar", "Crear y modificar cuentas"),
        ("asignar_roles", "Asignar roles"), ("administrar_permisos", "Administrar permisos"),
    )),
)

TODOS_LOS_PERMISOS = frozenset(
    f"{modulo}.{accion}" for modulo, _, acciones in MODULOS for accion, _ in acciones
)
PERMISOS_ADMINISTRACION = frozenset(p for p in TODOS_LOS_PERMISOS if p.startswith("usuarios."))
ROLES = {
    "ADMINISTRADOR": "Administrador", "DUENIO": "Dueño", "EMPLEADO": "Empleado",
    "REPARTIDOR": "Repartidor", "CLIENTE": "Cliente",
}
PERMISOS_INICIALES = {
    "ADMINISTRADOR": TODOS_LOS_PERMISOS,
    "DUENIO": TODOS_LOS_PERMISOS - PERMISOS_ADMINISTRACION,
    "EMPLEADO": frozenset({
        "pedidos.ver", "pedidos.crear", "pedidos.editar", "pedidos.cambiar_estado",
        "productos.ver_receta", "stock.ver", "stock.gestionar", "stock.reponer",
        "pagos.ver", "pagos.registrar", "pagos.conciliar", "pagos.corregir",
        "caja.ver", "caja.generar", "delivery.ver", "delivery.operar", "delivery.planificar",
        "clientes.ver", "whatsapp.ver", "whatsapp.gestionar", "whatsapp.ver_notificaciones",
    }),
    "REPARTIDOR": frozenset({
        "pedidos.ver", "productos.ver_receta", "stock.ver", "stock.gestionar", "stock.reponer",
        "caja.ver", "caja.generar", "delivery.ver", "delivery.operar",
        "whatsapp.ver_notificaciones",
    }),
    "CLIENTE": frozenset(),
}


def permisos_disponibles(rol: str) -> frozenset[str]:
    if rol == "ADMINISTRADOR":
        return TODOS_LOS_PERMISOS
    if rol == "CLIENTE":
        return frozenset()
    disponibles = TODOS_LOS_PERMISOS - PERMISOS_ADMINISTRACION
    if rol == "REPARTIDOR":
        disponibles = frozenset(
            p for p in disponibles if not p.startswith("pagos.")
            and p not in {"pedidos.crear", "delivery.planificar"}
        )
    return disponibles


def catalogo_modulos() -> list[dict]:
    return [
        {"clave": clave, "nombre": nombre,
         "acciones": [{"clave": accion, "nombre": etiqueta} for accion, etiqueta in acciones]}
        for clave, nombre, acciones in MODULOS
    ]

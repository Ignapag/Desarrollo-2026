# Usuarios, roles y permisos

La pantalla **Control de Acceso** consulta usuarios reales y las matrices de permisos
persistidas. Solo `ADMINISTRADOR` puede asignar roles y editar matrices. El contador
se calcula a partir de las cuentas devueltas por la API, sin cifras de muestra.

**Crear cuenta** permite al administrador dar de alta nombre, apellido, usuario único,
contraseña inicial y rol. Cada persona tiene su propio ID y sus credenciales de ingreso;
las cuentas precargadas en localhost son datos de desarrollo. La nueva cuenta aparece
en el listado solo después de confirmar el alta en la API. La contraseña se limpia del
formulario al terminar y nunca se muestra en el listado ni se persiste en almacenamiento del navegador.
La API valida la política de contraseña y responde con un error corregible si no se cumple.

## Modelo

Cada cuenta tiene un rol: `ADMINISTRADOR`, `DUENIO`, `EMPLEADO`, `REPARTIDOR` o
`CLIENTE`. Los permisos pertenecen al rol y sus cambios afectan a todas sus cuentas.
No hay roles nuevos ni excepciones de permisos por persona.

El catálogo define acciones concretas según lo que implementa cada módulo: ver,
crear/modificar, cambiar estados, reponer, conciliar, devolver, aprobar cierres,
planificar repartos, consultar reportes y atender solicitudes. No se ofrecen acciones
de eliminación que el módulo no implemente.

- Administrador conserva todas las capacidades, incluida rentabilidad. Su matriz
  está protegida y la administración de cuentas/permisos no se delega a otros roles.
- Cliente mantiene sus recorridos propios; no tiene matriz administrativa editable.
- Dueño, Empleado y Repartidor tienen matrices editables. El backend rechaza permisos
  desconocidos o incompatibles, aunque se envíen manualmente.
- Un repartidor sigue limitado a sus viajes/pedidos. No puede recibir pagos ni creación
  de pedidos o planificación global; para esas funciones se le asigna un rol operativo
  diferente. Conceder un permiso no elimina propiedad, estados ni reglas financieras.

La migración `028_permisos_por_rol.sql` crea `rol_acceso` (versión por rol) y
`rol_permiso` (concesiones). Conserva los accesos iniciales anteriores, incluida la
gestión de stock y generación de cierres que ya tenía Repartidor. Administrador recibe
también el permiso financiero que antes estaba reservado al Dueño.

## Sesiones vigentes

El JWT HttpOnly identifica al usuario, pero su rol firmado ya no decide autoridad.
Cada request autenticado vuelve a consultar cuenta activa, rol y permisos en la base.
Una revocación o cambio de rol confirmado se aplica en la siguiente petición, sin
esperar al vencimiento de la cookie. Las operaciones ya autorizadas y en curso no se
cancelan retroactivamente.

El panel refresca la sesión al recuperar foco y periódicamente (15 segundos), y adapta
rutas, navegación y acciones. La API es la autoridad incluso durante ese intervalo.
Los recorridos públicos del menú, Meta y chat demo conservan sus guardas propias.

## API y concurrencia

| Operación | Contrato |
| --- | --- |
| `GET /api/acceso` | Catálogo `modulos` y `roles`, con `permisos`, `disponibles`, `editable` y `version`. Solo administrador. |
| `PUT /api/acceso/roles/{rol}` | `{permisos: string[], version: int}`. Guarda matriz y auditoría en la misma transacción. |
| `POST /api/usuarios/{id}/rol` | `{rol: string}`. Asigna rol y asegura perfil operativo de Cliente/Repartidor sin borrar historial. |
| `GET /api/auth/me` y login | Incluyen permisos vigentes junto con la identidad y el rol. |

Si dos administradores editan la misma versión, el segundo guardado obsoleto devuelve
409. La pantalla conserva el aviso y exige actualizar el rol antes de volver a editar;
no sobrescribe silenciosamente cambios ajenos.

El administrador no puede quitarse su propio acceso ni dejar al sistema sin otro
administrador activo. Los viajes abiertos bloquean bajas y cambios de rol; la gestión
de cuentas y la asignación de viajes comparten bloqueo del perfil de repartidor.

Las autorizaciones compuestas también se validan: aprobar comprobantes por WhatsApp
exige registrar y conciliar pagos; aprobar cambios exige editar pedidos. Registrar un
cobro con conciliación inmediata necesita ambos permisos.

## Verificación y despliegue

El historial de movimientos anidado en pedidos requiere `pagos.ver`, incluso en
respuestas de cambios de estado, edición y cobros con `incluir_pedido=true`.
Sin ese permiso se devuelve `pagos: []`; se conservan total, neto cobrado y saldo
como resumen operativo necesario para preparar y entregar el pedido. Los clientes
mantienen acceso a sus propios movimientos, con la propiedad validada por el servicio.

Las pruebas de API, persistencia, revocación sobre la misma cookie y concurrencia se
ejecutan únicamente con PostgreSQL descartable explícito. Las pruebas de frontend
ejercitan edición, conflictos, rutas y actualización de sesión mediante HTTP simulado.
Estas verificaciones no acreditan un despliegue ni una prueba visual del sitio publicado.

El despliegue necesita backend, frontend y la migración 028 compatibles. El arranque
habitual `python -m scripts.serve --migrar` aplica pendientes, sin seed. No ejecutar
pruebas, seed ni limpieza sobre la base compartida como preparación del despliegue.

# Conservación, auditoría y trazabilidad

El esquema y el backend implementan bajas lógicas y auditoría automática desde
las migraciones `029_bajas_logicas` y `030_auditoria_automatica`. Estas capacidades
requieren aplicar ambas migraciones en cada entorno; modificar los archivos del
repositorio no actualiza por sí solo la base compartida.

## Bajas y consultas

Usuarios y clientes conservan `estado = 'ACTIVO'/'INACTIVO'`. Productos,
ingredientes, categorías, direcciones, zonas, puntos de encuentro, promociones y
plantillas conservan sus banderas `activo`/`activa`. Una baja cambia ese estado;
no elimina la fila ni sus referencias históricas.

Las relaciones de recetas (`producto_ingrediente`,
`producto_variante_ingrediente`), las concesiones `rol_permiso` y las líneas
`pedido_item` usan `eliminado_en`: nulo significa vigente. La edición marca las
filas retiradas y el upsert/reactivación conserva sus claves. Los ítems mantienen
su precio, opciones y receta congelada. No se reconstruyen datos físicamente
borrados antes de incorporar estas migraciones.

Repositorios y funciones SQL filtran las relaciones vigentes en detalle,
disponibilidad, costos, stock, reportes, WhatsApp y autorización. Los estados
cancelado, anulado, resuelto o terminado siguen formando parte de los históricos
del negocio; no equivalen a borrar ni ocultar una operación financiera.

Los listados HTTP de usuarios, ingredientes, plantillas y el directorio de
clientes (`/api/reportes/clientes`) muestran activos por
defecto. Gestión puede pedir `incluir_inactivos=true` para consultar todos, o el
estado concreto (`estado=INACTIVO`, `activo=false`, `activa=false`). El catálogo
público muestra activos por defecto; `solo_activos=false` permite la consulta
explícita usada por gestión. Las consultas históricas pueden referir entidades
inactivas sin perder su identidad.

## Recuperación

La reactivación utiliza los permisos y validaciones existentes:

- Producto: `PATCH /api/productos/{id}/estado`, cuerpo `{"activo": true}`.
- Ingrediente: `PATCH /api/stock/ingredientes/{id}`, cuerpo `{"activo": true}`.
- Usuario: modificación de cuenta con `estado = 'ACTIVO'` y sus campos obligatorios.
- Plantilla: modificación de plantilla con `activa = true` y sus campos obligatorios.
- Permisos y recetas: volver a incluir la relación al editar su configuración.

Las pantallas de catálogo e inventario consultan los inactivos separadamente y
permiten reactivarlos. Esas filas no se mezclan en el menú o inventario activo
compartido con otros recorridos.

Para líneas de pedidos existe `GET /api/pedidos/{id}/items-retirados` y
`POST /api/pedidos/{id}/items/{item_id}/recuperar`, con cuerpo
`{"version_esperada": 3}`. Ambos exigen `pedidos.editar`; un repartidor además
debe tener acceso al pedido. La recuperación reutiliza la edición versionada:
solo antes de cocina/asignación y con estado editable, revalidando pertenencia,
producto activo, disponibilidad, stock, totales y cobros. Conserva ID, precio y
snapshot originales; registra el ajuste y la reactivación en la misma transacción.
Las líneas con opciones estructuradas conservadas requieren revisión del personal,
igual que el flujo existente de edición: no se reactivan omitiendo el stock de sus
agregados. Las aclaraciones admitidas sobre la receta congelada siguen soportadas.
La API no ofrece restauración arbitraria de filas ni de JSON de auditoría.

## Registro automático

Los triggers `monu_auditar_cambio` escriben en `auditoria` después de cada
INSERT/UPDATE/DELETE efectivo en las tablas operativas configuradas. Un cambio
de fila genera una acción `DATOS_INSERTADOS`, `DATOS_MODIFICADOS` o
`DATOS_ELIMINADOS` (esta última únicamente durante mantenimiento autorizado).
Las bajas y reactivaciones son UPDATE. Actualizar solo `actualizado_en` sin
otro cambio no genera un evento nuevo.

El campo `datos` contiene:

- `operacion` y `clave`, incluida la clave completa de relaciones compuestas.
- `antes` y `despues`, con los campos de negocio admitidos para esa tabla.
- `campos_modificados`, con los nombres de los campos que cambiaron.
- `sesion_bd`, con la identidad de conexión de PostgreSQL.

Las altas tienen `antes = null`; los cambios de campos reservados se indican
por nombre sin copiar sus valores. El registro pertenece a la misma transacción:
un rollback revierte tanto los datos como su auditoría. Por eso los intentos
fallidos que terminan en rollback no se consideran cambios persistidos; el
mecanismo no es un registro independiente de intentos de autenticación fallidos.

Se mantienen los eventos de negocio existentes (por ejemplo, `ROL_ASIGNADO`)
para expresar la intención del caso de uso. Los eventos `DATOS_*` describen
las filas modificadas; no se deben contar ambos tipos como dos operaciones de
negocio. `identificador_operacion` permite agrupar sus cambios.

La cobertura comprende usuarios, clientes y repartidores; datos de entrega;
catálogo/recetas, inventario, movimientos y alertas; pedidos, ítems, opciones e
historial; promociones; viajes/envíos; pagos/cierres; parámetros; roles/permisos;
plantillas/notificaciones; y borradores, cambios, comprobantes y atención de
WhatsApp. La lista exacta de tablas y campos está en la migración 030.
No se audita recursivamente la propia tabla `auditoria`, ni la tabla de
migraciones, ni las colas/sesiones/archivos técnicos de demostración. Las
escrituras operativas que esos procesos producen sí quedan registradas.

## Usuario y origen

Cada request configura IP normalizada, canal e identificador generado por el
servidor. La sesión vigente carga la identidad y los permisos de la base antes
de atribuir el actor. Un login exitoso atribuye al usuario antes de actualizar
su acceso. Los workers identifican WhatsApp o demostración, conservan una
correlación entre etapas y no heredan la identidad de un request anterior.

La unidad de trabajo instala `monu.usuario_id`, `monu.ip`, `monu.origen` y
`monu.identificador_operacion` mediante `set_config(..., true)`, local a la
transacción. PostgreSQL descarta esos valores al confirmar o revertir; no se
almacena un actor permanente en una conexión del pool. Los procesos automáticos
sin usuario llevan actor nulo y canal propio.

Una escritura SQL sin contexto de aplicación queda con usuario de aplicación
nulo, origen `SQL:<session_user>` y correlación `sql:<id_transaccion>`. No se
inventa quién fue la persona que utilizó una credencial SQL compartida.
La IP puede ser nula en scripts o procesos automáticos; su extracción HTTP
conserva la política de proxy existente.

La consulta protegida `GET /api/auditoria` expone datos, usuario, fecha, IP,
origen e identificador de operación. Requiere el permiso `auditoria.ver`.

## Datos reservados y conservación del log

Las imágenes usan listas explícitas de columnas y proyecciones de JSON de
negocio. No copian hashes de contraseña, tokens, cookies, credenciales,
binarios ni cuerpos técnicos del proveedor. Las imágenes embebidas y URLs que
puedan contener firmas o credenciales se redactan. Las referencias derivadas
de acceso se pseudonimizan cuando actúan como clave del evento. Los campos
reservados no se pueden recuperar desde la auditoría.

Las guardas `monu_conservar_*` impiden DELETE/TRUNCATE de tablas operativas y
UPDATE/DELETE/TRUNCATE del log, con SQLSTATE `55000`. El backend no tiene una
bandera para desactivarlas. Purga temporal, cumplimiento normativo y corrección
administrativa requieren un procedimiento separado con privilegios PostgreSQL;
no son endpoints ordinarios. Un propietario o superusuario puede modificar o
desactivar triggers: esto no constituye protección frente a un administrador
malicioso de la base. Conviene que las credenciales de ejecución tengan solo
los permisos necesarios y no sean las del propietario del esquema.

## Migración y pruebas

Aplicar únicamente las migraciones nuevas, siguiendo la
[coordinación de la base](GUIA_EQUIPO.md), y desplegar backend y frontend
compatibles. El backend anterior todavía usa DELETE y no debe seguir
atendiendo escrituras cuando las protecciones de 030 estén activas. Preparar
una ventana coordinada: detener escritores anteriores, migrar, iniciar las
versiones nuevas y comprobar bajas, reactivaciones y auditoría.

La suite SQL/HTTP usa PostgreSQL local descartable con `DATABASE_URL` explícita.
Los tests que confirman datos limpian únicamente sus propios registros mediante
`tests.soporte_bd.mantenimiento_pruebas`. Ese contexto administrativo de tests
deshabilita temporalmente solo las guardas de conservación, conserva FK y
cascadas y restaura los triggers al terminar. No se usa durante el ejercicio
del caso de negocio ni se importa desde producción. Las pruebas de prohibición
usan las protecciones activas.

Comandos y preparación: [Desarrollo](DESARROLLO.md). El
[DER](DER.md) y [diccionario](DICCIONARIO_DATOS.md) se generan desde las migraciones.

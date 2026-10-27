# Auditoría de validaciones del frontend

Fecha: 27/10/2026. Alcance: los dos portales y las capacidades existentes de Monu Burger.
La API conserva autoridad sobre permisos, importes, stock, estados e idempotencia.

## Plan y criterios

1. Conservar los cuatro cambios locales de catálogo/recetas y arquitectura; trabajar
   en ramas `fix/auditoria-validaciones-frontend` de ambas materias. Comparar fuentes
   funcionales sin copiar seeds, entregables ni identidad de cada repositorio.
2. Contrastar pantallas y acciones con esquemas, servicios y guardas de la API.
   Demostrar defectos con regresiones antes de corregirlos. Priorizar sesión,
   dinero, inventario y conservación de formularios.
3. Verificar cliente HTTP, autenticación/store, catálogo/inventario/accesos,
   pedidos/cocina/reparto/pagos, carrito/chat y reportes/clientes. Cada área conserva
   sus interfaces; los cambios compartidos se coordinan en el agente principal.
4. Ejecutar regresiones, lint, builds y recorridos en navegador (móvil y teclado).
   Fallas simuladas usan mocks; toda prueba con SQL usa exclusivamente un contenedor
   descartable propio en un puerto distinto al PostgreSQL del usuario. Mantener
   `node_modules/.vite-tests` separado del servidor de desarrollo.
5. Revisión independiente del diff, resolver bloqueos, sincronizar los cambios
   funcionales, publicar PR y esperar CI antes de integrar respetando protecciones.
   Comprobar despliegues disparados e informar por separado subida/integración/despliegue.

## Matriz de cobertura

Una revisión de código no equivale a una prueba interactiva ni a una garantía de
cobertura exhaustiva. Los archivos citados viven en `App/frontend/tests/`.

| Flujo | Contrato esperado | Hallazgo inicial | Evidencia / resultado |
| --- | --- | --- | --- |
| HTTP compartido | Confirmación, HTTP relevantes, cancelación y plazo | JSON inválido se convertía en null; faltaba timeout | `http-validaciones.test.js`: aprobadas respuestas 400/401/403/409/422/429/500/503, HTML 200, desconexión, cancelación y timeout de headers/cuerpo; sin POST automático de reintento |
| Sesión, login y rutas | Cookie, identidad actual y acceso antes de consultar | Logout fallido podía restaurar cookie anterior; login doble/blancos | `acceso-sesion`, `login-validaciones`, `store-validaciones`, `portal-routes`, `acceso`: aprobadas; inventario oculto desde primer render de otra sesión, handlers anteriores no escriben, 401 retira sesión |
| Catálogo y recetas | Nombre hasta 120; precios Decimal(12,2); categorías existentes; cantidades Decimal(12,3); versión | FileReader pisaba campos; opciones retiradas; errores poco localizables | `recetas-ui`, `recetas-cantidades`, `validaciones-gestion-ui`, `store-validaciones`: aprobadas; borrador conservado en 409; acuse incompleto no cierra receta; región de tabla desplazable con teclado en móvil |
| Inventario | Stock >=0, mínimo >0, Decimal(12,3); saldo del servidor | Vacíos/números inválidos y doble envío | `validaciones-gestion-ui`, `clientes-carga`, `store-validaciones`: aprobadas; coma/fracción explícita y aproximación visible; guard síncrono, rollback y saldo confirmado; 403 retira snapshot |
| Cuentas, roles y permisos | Solo administrador; política real de contraseña y versiones de matriz | GET sin guarda; doble envío; acuse vacío podía limpiar contraseña/anunciar guardado | `acceso`, `validaciones-gestion-ui`: aprobadas; conserva formulario en error; verifica ID/rol/usuario/versión del acuse |
| Pedidos y cocina | Estados/versiones backend; conservar ediciones y rollback | Cierre anticipado; reload tras 409 destruía borrador | `operaciones-validacion`, `operacion-privacidad`, `operacion-segundo-plano`, `operacion-regresiones`: aprobadas; rebase explícito conserva campos editados; respuesta incompleta no confirma; PII retirada en 401/403 |
| Pagos y devoluciones | Decimal(12,2), motivo y UUID persistido | Precisión/motivo corto e identificación parcial del pago | `operacion-pedidos`, `operaciones-validacion`, `operacion-regresiones`: aprobadas; coma decimal; rechazo de acuse incompleto/inconsistente; mismo cuerpo y UUID al reintentar |
| Reparto | delivery.ver, planificación autorizada y repartidor vigente | GET de viaje sin permiso y selección retirada; viajes visibles tras 403 | `operaciones-validacion`, `operacion-privacidad` y suites operativas: aprobadas; retira datos rechazados y revalida sesión; conserva datos ante 503 |
| Menú, carrito, WhatsApp y chat | Productos/variantes vigentes; 1–50 unidades/ítems; dirección 160/30 | Cambio silencioso de variante; límites/blancos; envío tardío borraba carrito nuevo | `ordering-validacion`, `chat-demo`, `portal`, `operacion-pedidos`: aprobadas; conserva personalización, borrador/UUID incierto y carritos distintos; menú carga también para personal |
| Reportes, panel y clientes | Fechas reales años 1–9999; financieros con permiso; aislamiento | Datos/errores por rol o ruta cruzaban sesiones; año 0000; paginación imposible | `analytics`, `clientes-carga`, `panel-datos`: aprobadas; filtros/respuestas tardías, 401/403 retiran datos; 503 conserva solo datos de identidad actual |

## Inventario de pantallas y contratos

`App.jsx` registra `/menu`, `/login`, `/dashboard`, `/dashboard/orders`,
`/dashboard/kitchen`, `/dashboard/catalog`, `/dashboard/inventory`,
`/dashboard/customers`, `/dashboard/analytics`, `/dashboard/access` y `/delivery`.
Los modos clientes/personal seleccionan sus rutas en el build. `ProtectedRoute`
comprueba rol y permiso y remonta el árbol cuando cambia la identidad o sus permisos.

- Menú/carrito: catálogo público `/api/productos`; variantes/personalizaciones;
  borradores `/api/whatsapp/borradores` y conversación `/api/chat-demo/*`.
- Sesión y cuentas: `/api/auth/*`, `/api/usuarios` y `/api/acceso`. Administrador
  gestiona usuarios/matrices; Dueño, Empleado y Repartidor tienen permisos por rol;
  Cliente conserva recorridos propios. La API vuelve a comprobarlos por petición.
- Catálogo/recetas: productos y `/{id}/receta`, `/{id}/estado`; stock autorizado
  `/api/stock/ingredientes` y `/{id}/reposiciones`.
- Pedidos/cocina: `/api/pedidos`, detalle, `/operacion` y `/estado`; versión esperada,
  estados físicos y tratamiento de stock establecidos por el backend.
- Reparto: `/api/delivery/repartidores`, viajes, asignación y envíos; el repartidor
  conserva restricciones de propiedad en servidor.
- Pagos: `/api/pagos/efectivo`, `/transferencia`, `/devolucion`, conciliación y estado
  financiero por pedido. La UI no contiene una pantalla de cierre/aprobación de caja;
  esos contratos backend no se presentan como un flujo de navegador verificado.
- Panel/reportes/clientes: `/api/reportes/dashboard`, `/ventas`, `/rentabilidad` y
  `/clientes`; los reportes financieros requieren permiso adicional.

## Verificación observada

- Las nuevas regresiones reprodujeron defectos antes del fix (RED) y luego pasaron
  (GREEN). Los fixtures financieros incompletos heredados se ajustaron al contrato
  real para no aceptar respuestas que el servidor no produce.
- Suite backend: **1177 aprobadas**, sin omisiones, PostgreSQL 16 descartable propio
  `monu_validaciones_20261027`, puerto 55443; migraciones con seed propias y sin
  pendientes. Ruff aprobado. Una advertencia heredada de deprecación de Starlette.
- Suite completa frontend: `node --test tests/*.test.js`; lint aprobado con las dos
  advertencias de exports de Fast Refresh existentes; builds completo/clientes/personal
  aprobados. Los números finales y CI se registran en los PR.
- Navegador Chromium con fixtures: **18/18 comprobaciones**, escritorio 1440×1000 y
  móvil 375×812. Login con teclado, errores/reintento, guardas, inventario, catálogo,
  menú autenticado, carrito, personalizaciones y restauración de foco. La tabla móvil
  permite desplazamiento con ArrowRight. Diez capturas y JSON de evidencia temporal;
  cero excepciones JS, sin endpoints API desconocidos ni solicitudes a la base real.
- Revisión independiente en lectura: confirmó pérdida de borrador tras 409 y PII
  retenida en Pedidos/Reparto tras 403; se corrigieron con regresiones. También se
  resolvieron acuses incompletos en operaciones, recursos, cuentas y pagos.

## Límites

Registro y recuperación no tienen endpoints ni pantallas activas; el router los
redirige al login. El pedido público continúa por WhatsApp o chat académico: no
equivale a un checkout bancario. Las notificaciones y datos demostrativos se
identifican conforme a la documentación existente. No se prueban cobros reales,
proveedores externos ni operaciones de producción como parte de esta auditoría.

No se verificaron manualmente en navegador cobros/devoluciones reales, cocina,
viajes/reparto, bandeja de comprobantes, reportes completos ni cierre de caja;
tienen revisión de código y cobertura automatizada pertinente, según la matriz.
Tampoco se verificaron Meta/Gemini reales, archivos maliciosos, lector de pantalla,
todos los tamaños/orientaciones ni todas las combinaciones de rol/permiso.

Las altas de producto/insumo y reposiciones no exponen una clave idempotente en su
API. El guard evita doble clic y no hay reenvío HTTP automático, pero tras perder
la respuesta se debe consultar el recurso antes de repetir. No se garantiza ausencia
de duplicados en un reintento manual incierto. Los pagos y envíos de chat conservan
sus identificadores de reintento. No se agregaron límites de archivo inventados que
el backend no define; se comprueba lectura y MIME para la selección de imagen.

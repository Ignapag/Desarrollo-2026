# Auditoría de validaciones del frontend

Fecha: 27/10/2026. Alcance: los dos portales y las capacidades existentes de Monu Burger.
La API conserva autoridad sobre permisos, importes, stock, estados e idempotencia.
Las secciones de auditoría conservan su evidencia original. La incorporación de
Caja se describe aparte y no hereda las pruebas aprobadas de otros flujos.

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
`/dashboard/customers`, `/dashboard/analytics`, `/dashboard/access`, `/dashboard/caja` y `/delivery`.
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
  financiero por pedido.
- Caja: `/api/caja/turnos/actual/consolidado`, `/turnos/consolidado`, `/cierres`,
  detalle, generación y aprobación. Contrato y evidencia separados en la sección
  de Caja; no se presentan como parte de la auditoría original de pagos.
- Panel/reportes/clientes: `/api/reportes/dashboard`, `/ventas`, `/rentabilidad` y
  `/clientes`; los reportes financieros requieren permiso adicional.

## Caja: contrato y verificación

Incorporación del 27/10/2026 en `/dashboard/caja`, con `cash/Caja.jsx`,
`cajaController` y `cajaContract`. La evidencia de esta incorporación se distingue
de la auditoría previa y de los checks remotos de cada PR.

| Flujo | Criterio de verificación |
| --- | --- |
| Contratos y filtros | Consolidado actual/específico; historial por rango/estado; detalle por ID; fechas y turnos válidos; acuses completos y coherentes; conservar fecha contable y ventanas sin conversión UTC |
| Permisos y privacidad | Ruta y lecturas con `caja.ver`; generar con `caja.generar`; aprobar con `caja.aprobar`; sin endpoints de Caja desde clientes; 401/403 retiran datos; respuestas tardías de otra sesión descartadas |
| Confirmaciones | Generación/regeneración y aprobación explícitas; prelectura y revisión de cambios; aprobado bloqueado; doble clic no duplica comandos simultáneos |
| Observaciones | Vacío se envía como `null` y conserva texto existente; texto nuevo reemplaza con elección explícita; no anunciar que `null` borra notas |
| Respuesta incierta | No POST automático; conservar intento; recuperar por fecha/turno al generar y por ID al aprobar; encontrar un cierre no prueba autoría del POST ni persistencia de sus notas |
| Concurrencia | La prelectura reduce obsolescencia; la API no expone versión, CAS ni clave de idempotencia y conserva una carrera entre GET y POST |
| Interfaz | Estados de carga, vacío, error/reintento y detalle; navegación por teclado, confirmación y restauración de foco; móvil sin pérdida de datos ni acciones |

Las comprobaciones deben usar fixtures o una base descartable explícita. Ninguna
prueba de este recorrido debe generar, regenerar o aprobar cierres de producción.
Contrato operativo en [operación de Caja](OPERACION_PEDIDOS.md#caja-en-el-panel).

Verificación de esta incorporación:

- `npm run test:caja`: 24 aprobadas, sin omisiones. El controlador cubre errores
  400/401/403/404/409/422/429/5xx, selección parcial, doble envío, arrastre,
  acuses incompletos, notas no confirmadas, pérdida de respuesta, reconciliación,
  GET tardíos y conflictos entre operadores. Las regresiones del cliente HTTP
  compartido comprueban HTML, desconexión, cancelación y timeout de cabecera/cuerpo.
- Suite frontend completa: 301 aprobadas, sin omisiones; lint con solo las dos
  advertencias Fast Refresh heredadas y builds completo/clientes/personal aprobados.
- Rutas directas, navegación, destino inicial y roles configurables: regresiones
  de `acceso.test.js` y `portal-routes.test.js`. Caja no cambia la matriz backend.
- Backend completo: 1182 aprobadas, sin omisiones, PostgreSQL 16 descartable propio
  `monu_caja_codex_20261027` en 55439. Ruff aprobado. Cinco regresiones nuevas de
  zona horaria incluyen SQL en UTC, Tokio y Argentina. Una advertencia heredada
  de deprecación de Starlette; ninguna base habitual o compartida utilizada.
- Chromium con fixtures: 22 comprobaciones aprobadas en escritorio 1440×1000 y
  móvil 375×812, con movimiento reducido. Login por teclado, carga, 503/reintento,
  selección parcial, foco al fallar, Escape/restauración de foco, diálogo nativo,
  generación/aprobación sin doble POST, 409 con notas conservadas, historial y
  detalle, lectura sola, revocación 403, ruta rechazada y logout. Sin excepciones
  JavaScript, endpoints desconocidos ni solicitudes a una API real.
- Recorrido adicional con navegador y API local real, sin mocks, sobre esa base
  descartable: login administrador, Noche 27/10/2190, consolidado 160 con un
  pendiente, cierre 280 por arrastre y aprobación confirmada. Servidor y base
  propios detenidos al finalizar. No se generaron cierres de producción.
- Revisión independiente del diff: sin bloqueos financieros demostrados. Su
  observación sobre la enumeración de `ABIERTO` quedó corregida. La prueba de
  navegador detectó pérdida de foco al cancelar; se corrigió y el mismo recorrido
  pasó en ambos tamaños.

No se verificaron lectores de pantalla, todos los tamaños/orientaciones ni cada
combinación de permisos en navegador. El flujo real local se comprobó en escritorio;
las fallas y el recorrido móvil se comprobaron con fixtures. CI y despliegues se
acreditan por SHA y enlaces de cada PR, no por estos resultados locales.

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
viajes/reparto, bandeja de comprobantes ni reportes completos;
tienen revisión de código y cobertura automatizada pertinente, según la matriz.
Tampoco se verificaron Meta/Gemini reales, archivos maliciosos, lector de pantalla,
todos los tamaños/orientaciones ni todas las combinaciones de rol/permiso.
El recorrido de Caja incorporado después de esta auditoría tiene su evidencia
separada en la sección anterior.

Las altas de producto/insumo y reposiciones no exponen una clave idempotente en su
API. El guard evita doble clic y no hay reenvío HTTP automático, pero tras perder
la respuesta se debe consultar el recurso antes de repetir. No se garantiza ausencia
de duplicados en un reintento manual incierto. Los pagos y envíos de chat conservan
sus identificadores de reintento. No se agregaron límites de archivo inventados que
el backend no define; se comprueba lectura y MIME para la selección de imagen.

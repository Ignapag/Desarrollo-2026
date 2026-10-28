# Auditoría de validaciones del frontend

Fecha: 27/10/2026. Alcance: los dos portales y las capacidades existentes de Monu Burger.
La API conserva autoridad sobre permisos, importes, stock, estados e idempotencia.
Las secciones de auditoría conservan su evidencia original. La incorporación de
Caja se describe aparte y no hereda las pruebas aprobadas de otros flujos.

## Encuadre de las salsas en el menú (28/10/2026)

Las fotos de 138 × 135 px aparecían a tamaño nativo en un cuadro 4:3 mucho
mayor. Se reprodujo el desajuste: la comprobación de cuadro compacto falló
antes del cambio. Menu.jsx ahora presenta Dips Extra en tarjetas horizontales
con una miniatura de 96 px de ancho y proporción 138:135; el botón de agregar
queda junto al precio y no tapa la foto. Las otras categorías conservan sus
cuadros 4:3. No cambian archivos de imagen, asociaciones, prioridad de imagen_url,
precios, recetas, disponibilidad ni datos del catálogo.

Verificaciones ejecutadas desde App/frontend:

| Comando | Resultado |
| --- | --- |
| npm.cmd run test:portales | 23 aprobadas, sin fallos ni omisiones. |
| npm.cmd run lint | Aprobado, con las dos advertencias previas de Fast Refresh. |
| npm.cmd run build | Aprobado. |
| node tests/salsas-browser.mjs | Ocho escenarios aprobados: clientes y personal a 1440, 390 y 320 px, más 390 px con doble densidad. |

El navegador usa fixtures locales y bloquea servicios externos. Comprueba las
cinco fotos antes y después de recargar, proporción, ocupación del cuadro,
ausencia de ampliación, área táctil de 44 px y botón fuera de la imagen.
Tab y Enter agregan Alioli al carrito en los cuatro escenarios de clientes.
Las 80 respuestas de imágenes fueron 200, sin errores de página ni solicitudes
API desconocidas. Se inspeccionaron capturas de escritorio, móvil, doble densidad
y catálogo. Esta verificación no prueba operaciones sobre una base real.

Limitación pendiente: el detalle perdido en la captura original no se recupera
con CSS. Para eliminar la falta de nitidez se necesitan los archivos originales
de las cinco fotografías en mayor resolución. No se generaron reemplazos ni
se aumentó artificialmente la resolución. Cambios locales, sin commit, push ni
despliegue; no hubo accesos de escritura a la base.

## Etiqueta Pagados y fotografías de salsas (28/10/2026)

El tablero muestra **Pagados**, conservando el identificador interno PAGADOS y
las reglas financieras. Las cinco fotos originales se vinculan como respaldo a
los dips existentes; contrato en el [frontend](../App/frontend/README.md#fotografías-de-salsas).
No hubo cambios de backend, base, precios, recetas, stock ni disponibilidad.

Verificaciones ejecutadas el 28/10/2026 desde App/frontend:

| Comando | Resultado |
| --- | --- |
| npm.cmd run test:operacion | 120 aprobadas; encabezados, etiquetas accesibles y reclasificación por pago. |
| npm.cmd run test:portales | 23 aprobadas; incluye cinco asociaciones, archivos WebP, prioridad de imagen_url y aislamiento de otros productos/categorías. |
| npm.cmd run test:panel | 54 aprobadas; consultas compartidas y recorridos de catálogo. |
| npm.cmd run lint | Aprobado; conserva dos advertencias previas de Fast Refresh. |
| npm.cmd run build | Aprobado. |
| node tests/pagados-retiro-browser.mjs | Chrome con fixtures: etiqueta Pagados, pago y retiro a 1440, 390 y 320 px. Aprobado. |
| node tests/salsas-browser.mjs | Chrome con fixtures en modos clientes y personal: cinco fotos en menú y catálogo a 1440, 390 y 320 px, antes y después de recargar. Aprobado en la ejecución final. |
| git diff --check | Aprobado. |

Los scripts de navegador requieren Playwright y Chrome; admiten
MONU_PLAYWRIGHT_PATH y MONU_CHROMIUM_PATH para instalaciones externas.
El primer intento del script de salsas detectó que faltaba interceptar la
configuración del chat. Se agregó el fixture deshabilitado y se repitió: la
ejecución final completó los seis escenarios sin solicitudes desconocidas ni
errores de página; las 60 respuestas de fotos fueron 200.
Se comprobaron texto alternativo, proporción, dimensiones originales y ausencia
de ampliación en el menú. Se inspeccionaron capturas de escritorio y móvil.
Cada WebP decodificado coincide con los píxeles del recorte RGB original.

Las pruebas usan fixtures interceptados y bloquean servicios externos. La
consulta pública previa del catálogo confirmó nombres, categoría y ausencia de
fotos; no acredita integración con la base. No hubo seeds, pruebas de backend
ni escrituras en la base compartida. Cambios locales, sin commit, push ni despliegue.

## PAGADOS, retiro y solapas STOCK/CLIENTES (28/10/2026)

El tablero separa la agrupación financiera de los estados operativos, y la
campanita divide stock y clientes conservando lectura, permisos y filtros.
Contrato vigente en [operación de pedidos](OPERACION_PEDIDOS.md).

Verificaciones ejecutadas el 28/10/2026, después de los cambios:

| Comando | Resultado |
| --- | --- |
| npm.cmd run test:operacion | Aprobado; incluye clasificación, actualización de contadores, retiro y lectura por solapa. |
| npm.cmd run test:validaciones | 189 aprobadas, 0 fallos, 0 omitidas. |
| npm.cmd run lint | Aprobado, con las dos advertencias previas de Fast Refresh. |
| npm.cmd run build | Aprobado. |
| node tests/notificaciones-browser.mjs | Chrome con fixtures: STOCK/CLIENTES, contadores, marcado independiente, teclado, permisos, errores y destinos a 1440, 390 y 320 px. Aprobado. |
| node tests/pagados-retiro-browser.mjs | Chrome con fixtures: acuse de cobro, reclasificación sin recargar, retiro pagado/efectivo y transferencia bloqueada a 1440, 390 y 320 px. Aprobado. |

Desde App/backend, con DATABASE_URL explícita a un puerto local de pruebas:

- .venv/Scripts/python.exe -m pytest tests/test_retiro_pedido.py tests/test_pedidos_privacidad_pagos.py tests/test_arquitectura.py -q: 26 aprobadas. Conserva una advertencia de deprecación de Starlette/AnyIO.
- .venv/Scripts/python.exe -m ruff check app/modules/pedidos/application/servicio_pedidos.py tests/test_retiro_pedido.py: aprobado.

Las pruebas del backend usan dobles de repositorio y dependencias de prueba;
no se ejecutaron casos SQL ni se conectó a una base real. Se reutiliza el
indicador existente leído tras el bloqueo del pedido, sin cambiar consultas,
esquema o migraciones. El navegador intercepta toda la API, bloquea servicios
externos y verifica que el retiro sólo envía el comando de estado, sin inventar
cobros. Las capturas de escritorio y móvil se inspeccionaron. Esto no acredita
integración con la base compartida ni constituye un despliegue.

Los resultados de la sección siguiente corresponden a la incorporación inicial
de la campanita; el alcance actual es el registrado aquí.

## Campanita de notificaciones (28/10/2026)

Implementación local del centro con comprobantes, atención humana y niveles
reales de inventario. Contrato y límites en
[operación de pedidos](OPERACION_PEDIDOS.md#centro-de-notificaciones).
No modifica backend, esquema, pagos ni procesos de revisión.

Verificaciones ejecutadas el 28/10/2026 desde App/frontend:

| Comando | Resultado |
| --- | --- |
| npm.cmd run test:operacion | 103 aprobadas, 0 fallos, 0 omitidas. Incluye modelo, recurso compartido, lectura, permisos, sesión, reintento y preservación del aviso de Reparto. |
| npm.cmd run test:panel | 54 aprobadas, 0 fallos, 0 omitidas. |
| npm.cmd run test:validaciones | 160 aprobadas, 0 fallos, 0 omitidas; prueba del layout preparada con el DataProvider real, conservando sus aserciones de permisos. |
| npm.cmd run test:portales | 16 aprobadas, 0 fallos, 0 omitidas. |
| npm.cmd run lint | Aprobado; conserva dos advertencias previas de Fast Refresh en AuthContext y DataContext. |
| npm.cmd run build | Aprobado. |
| node tests/notificaciones-browser.mjs | Aprobado en Chrome sin ventana visible, con fixtures locales, a 1440, 390 y 320 px. |

El navegador comprobó recorrido de Tab dentro del diálogo, Escape y retorno a
la campanita, contador y filtros, lectura frente a resolución, persistencia
al recargar y aislamiento entre cuentas, acceso y foco al comprobante e
ingrediente, permisos, errores y reintento. El reporte terminó sin errores
JavaScript, escrituras API ni consultas API desconocidas. Se inspeccionaron
capturas de escritorio y móvil. La regresión incluye una marca global que
abarca también los comprobantes revisados de Todas.

Después de incorporar las mejoras de main en pedidos, inventario y despliegue,
se repitieron el 28/10/2026 test:operacion, test:validaciones (189 aprobadas),
lint, build:personal y notificaciones-browser.mjs: todos aprobados. Se conservaron
el tablero compacto, los costos y las reposiciones manuales junto con los accesos
de la campanita.

Estas pruebas no usan la API desplegada ni una base real y no demuestran
integración con proveedores. No se ejecutó SQL, seed, migración ni despliegue.
La lectura se conserva en este navegador; no hay historial completo ni
sincronización entre dispositivos. No hubo decisiones nuevas sobre umbrales.

## Mensajes para usuarios finales (28/10/2026)

El cliente HTTP traduce rechazos por estado y una lista cerrada de mensajes de
negocio en `src/shared/api/userErrors.js`. No expone `mensaje`, `detail`, listas
de validación, códigos HTTP ni excepciones de transporte. Las pantallas usan
`userErrorMessage(error, mensajeDeLaAccion)`; solo `UserFacingError` permite
conservar instrucciones locales o traducciones controladas. Nunca construir
esa clase con texto recibido de la API, excepciones ni datos sensibles. Un error
desconocido conserva un mensaje seguro. El estado HTTP sigue disponible para
retirar datos sin acceso, revalidar sesiones y gestionar conflictos.
El chat también traduce los prefijos conocidos de fallos persistidos del bot,
descartando sus diagnósticos, y usa etiquetas cerradas para estados desconocidos.
Los formularios conservan avisos anunciados, errores asociados a campos y foco
en el resumen; los resúmenes de altas incluyen enlaces a los campos indicados.

Las consultas describen qué información no pudo cargarse. Las escrituras con
respuesta perdida, espera agotada o respuesta inesperada indican comprobar el
estado antes de repetir la acción. Pedidos, pagos, chat y Caja conservan sus
mecanismos de reconciliación y los identificadores de reintento existentes;
los mensajes no sustituyen esas garantías ni convierten una consulta posterior
en confirmación de autoría. No se registran cuerpos, credenciales ni excepciones
originales desde la capa de mensajes del navegador.

Ejemplos: «Origen de la solicitud no permitido» pasa a «No pudimos completar la
acción. Intentá nuevamente más tarde»; errores desconocidos de conversación
pasan a «No pudimos enviar tu mensaje»; las validaciones locales de teléfono,
campos requeridos y formatos PDF/PNG/JPEG siguen indicando cómo corregirlos.

Regresiones en `http-validaciones`, `user-errors`, `store-validaciones`,
`login-validaciones`, `acceso-sesion`, `chat-demo`, `validaciones-gestion-ui`,
`caja` y las suites operativas verifican filtrado, conservación de datos,
respuestas inesperadas y ausencia de éxito falso. `npm run test:validaciones`
incluye la política compartida. Las pruebas usan respuestas simuladas y DOM de
prueba; no equivalen a una integración con proveedores ni a una revisión visual.
En esta sesión no hubo un navegador conectado disponible para comprobar teclado,
responsive o lector de pantalla; esa verificación interactiva queda pendiente.

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
  `/api/stock/ingredientes`, `PATCH /{id}` (solo costo unitario, con `stock.gestionar`)
  y `/{id}/reposiciones`.
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
de duplicados en un reintento manual incierto. En la reposición con cantidad manual,
tras un resultado incierto el siguiente envío exige confirmar el resumen con el stock
ya refrescado; desde 200 unidades, 5000 g/ml o 50 kg/l siempre se confirma. Los pagos y envíos de chat conservan
sus identificadores de reintento. No se agregaron límites de archivo inventados que
el backend no define; se comprueba lectura y MIME para la selección de imagen.

# WhatsApp: desarrollo y demostración local

Esta guía describe la implementación de desarrollo al 17 de octubre de 2026.
El alcance de producto sigue en [WHATSAPP_ALCANCE.md](WHATSAPP_ALCANCE.md).
El backend interpreta mensajes, valida y persiste operaciones; Gemini propone
acciones y WhatsApp transporta mensajes. La apertura del chat no crea un pedido.
Las pruebas reales con credenciales de Google y recursos de prueba de Meta
quedan pendientes: una simulación aprobada no acredita esa integración externa.

## Preparar una base descartable

Usar una terminal dedicada y dependencias preparadas según
[DESARROLLO.md](DESARROLLO.md). Desde `App/backend`, iniciar un contenedor nuevo
sin volumen persistente; no reemplazar ni detener contenedores ajenos:

```powershell
docker run --rm -d --name monu_pg_whatsapp -e POSTGRES_USER=monu -e POSTGRES_PASSWORD=monu `
  -e POSTGRES_DB=monuburger -p 55432:5432 postgres:16-alpine
docker exec monu_pg_whatsapp pg_isready -U monu -d monuburger
```

Esperar a que `pg_isready` informe que acepta conexiones. Si el nombre o puerto
está ocupado, elegir otro para esta demo y ajustar la URL. Las credenciales
`monu` del ejemplo pertenecen exclusivamente a este contenedor de prueba.

```powershell
$env:DATABASE_URL = 'postgresql://monu:monu@127.0.0.1:55432/monuburger'
$env:ENTORNO = 'desarrollo'
$env:WHATSAPP_MODO = 'simulado'
$env:GEMINI_MODO = 'simulado'
$env:WHATSAPP_NUMERO_NEGOCIO = ''
$env:WHATSAPP_TRANSFERENCIA_DATOS = ''
.\.venv\Scripts\python.exe -m scripts.migrate --seed
.\.venv\Scripts\python.exe -m scripts.migrate --status
```

La preparación aplica las migraciones, incluidas `011_whatsapp.sql`,
`012_whatsapp_estados_envio.sql`, `013_whatsapp_saldo_transferencia.sql` y
`014_whatsapp_atencion.sql`, y carga usuarios, catálogo y recetas de prueba.
Estas variables prevalecen sobre `App/.env`, que puede apuntar a la base
compartida. No aplicar estos comandos a esa base ni habilitar excepciones para
aceptar destinos remotos. No hace falta cambiar el `.env` existente.

## Ejecutar la demo completa

Desde la misma terminal de `App/backend`:

```powershell
.\.venv\Scripts\python.exe -m scripts.whatsapp_demo
```

[whatsapp_demo.py](../App/backend/scripts/whatsapp_demo.py) exige `DATABASE_URL`
definida explícitamente y un host `localhost`, `127.0.0.1` o `::1`; también
rechaza desvíos remotos mediante parámetros `host`/`hostaddr`, servicios indirectos, modo de
producción y proveedores distintos de `simulado`. La validación ocurre antes
de abrir el pool. No utiliza credenciales de Meta ni de Google.

El script trabaja con transacciones reales que se confirman entre etapas:

1. Usa un cliente y un empleado activos del seed y el producto **La Típica,
   variante Doble**, cuya receta contiene tomate. Genera dos teléfonos ficticios
   distintos, con prefijo `5492215`, que no tengan conversaciones previas.
2. Guarda un borrador sin crear un pedido operativo. Recibe su mensaje, pide
   modalidad y pago, y completa `retiro` y `efectivo` mediante el interpretador
   simulado. Repetir el ID del mensaje y volver a recibir la referencia con un
   ID diferente mantiene un único pedido.
3. Procesa “¿Le podés sacar el tomate?” y verifica **Sin Tomate** mediante el
   listado de pedidos que alimenta las vistas operativas. Solicitar `cantidad: 2`
   conserva la cantidad anterior hasta recibir `confirmar`.
4. Crea otro pedido por transferencia. Asocia un identificador de comprobante
   ficticio y verifica que no exista un pago por el solo hecho de recibirlo.
   Comprueba que cocina no pueda preparar antes de la revisión humana. Luego
   representa una aprobación del empleado de prueba, con el total observado,
   registra el pago ficticio y pasa a `EN_PREPARACION`.
5. Ejecuta un lote del worker y comprueba que sus respuestas queden
   `SIMULADO`, sin confundirlas con aceptación o entrega real.

La salida muestra IDs de pedidos, entradas, comprobante y mensajes de salida;
no imprime referencias de acceso `MB-`, cookies ni credenciales. La repetición
del mismo mensaje conserva su respuesta histórica, aunque luego se hayan
completado otros datos del pedido.

**Cada ejecución deja dos pedidos y un pago ficticio, además de historial y
colas; preparar el segundo pedido consume stock local.** No borra ni reinicia
tablas. Usar una base dedicada, sin otros workers activos durante la demo: el
lote procesa hasta 100 entradas y salidas pendientes de esa base, no solamente
las del script. Repetir la demo crea nuevos pedidos y necesita stock suficiente.
El comprobante simulado no tiene un archivo real descargable.

Para desechar exclusivamente el contenedor creado arriba, al terminar:

```powershell
docker stop monu_pg_whatsapp
```

Como se creó con `--rm` y sin volumen, se pierden sus datos locales al detenerlo.

## API, interfaz y worker

La demo anterior no necesita servidores HTTP ni navegador. Para recorrer la
interfaz, mantener el contenedor y abrir tres terminales:

| Proceso | Carpeta | Comando |
| --- | --- | --- |
| API | `App/backend`, con las variables locales anteriores | `.\.venv\Scripts\python.exe run.py` |
| Frontend | `App/frontend` | `npm run dev` |
| Worker | `App/backend`, con las mismas variables de API | `.\.venv\Scripts\python.exe -m scripts.whatsapp_worker` |

El worker continuo consulta cada dos segundos. Para una demostración por pasos,
reemplazarlo por `.\.venv\Scripts\python.exe -m scripts.whatsapp_worker --una-vez`
después de cada recepción. El webhook y `/simular` guardan inbox; no interpretan
ni envían respuestas dentro de la petición HTTP. No hay un scheduler automático
dentro de FastAPI: API y frontend sin worker no completan el procesamiento.

La API sirve `http://localhost:8000/docs`; Vite normalmente sirve
`http://localhost:5173`. Las credenciales de desarrollo están en
[seed.sql](../App/db/seed.sql); no reutilizarlas fuera de la base descartable.
El seed incluye `acliente` como cliente y `nleguizamon` como empleado; `admin`
permite inspeccionar las operaciones internas.

Recorrido manual:

1. Abrir `/` o `/menu` sin sesión, agregar La Típica Doble al carrito y elegir
   entrega y pago. No se pide nombre, teléfono ni credenciales. **Preparar mensaje de
   WhatsApp** guarda un borrador; conserva el carrito y permite copiar el
   mensaje. En simulación sin número de negocio no se abre un chat conectado.
   Para una recompra idéntica, **Preparar otro pedido igual** genera otra
   referencia; reenviar el mensaje anterior conserva el pedido original.
2. En una sesión independiente de empleado o administrador, usar `/docs` y
   `POST /api/auth/login` con credenciales del seed. Las llamadas posteriores
   usan la cookie HttpOnly; no copiarla ni exponerla en la consola.
3. Enviar el mensaje copiado a `POST /api/whatsapp/simular` con un ID nuevo y el
   teléfono ficticio que representará al remitente. Ejecutar el worker. Un ID ya recibido es
   idempotente; un mensaje distinto debe tener otro ID.
4. Repetir `/simular` con `sin tomate`, `cantidad: 2` y `confirmar`, ejecutando el
   worker entre mensajes. Si hay varios productos, el bot conserva la solicitud
   y pide `producto N`; no elige un producto arbitrario.
5. Revisar Pedidos/Cocina y la bandeja WhatsApp en Gestión de Pedidos
   (`/dashboard/orders`). Para transferencia, simular otro mensaje con
   `media_id` ficticio: el empleado debe revisar importe y acreditación antes de
   aprobar. En simulación, descargar ese adjunto no devuelve un archivo real.
6. Simular `quiero hablar con una persona` y ejecutar el worker. En la bandeja,
   **Conversaciones que requieren atención** muestra cliente, teléfono, estado
   del pedido o borrador, productos, el mensaje que originó la derivación y los
   últimos mensajes, con las referencias `MB-` ocultas. El empleado puede abrir
   el chat (`wa.me`) o llamar, **encolar una respuesta** por WhatsApp y
   **marcar la atención como resuelta** con el detalle de lo acordado. La
   respuesta queda `PENDIENTE` hasta que el worker la procesa; con el transporte
   simulado pasa a `SIMULADO` y no llega a WhatsApp. Pulsar **Actualizar bandeja**
   muestra el estado real de envío.

Ejemplo del cuerpo de una entrada simulada, con el texto obtenido de la web:

```json
{
  "id": "demo-ui-01",
  "telefono": "5492215550000",
  "texto": "<MENSAJE_COPIADO_DEL_BORRADOR>"
}
```

Para un adjunto ficticio, usar otro `id`, `texto: ""` y
`media_id: "comprobante-ficticio-01"`. No enviar comprobantes personales a la
demostración ni a Gemini.

## Contratos de desarrollo

Los contratos y permisos efectivos están en
[router.py](../App/backend/app/modules/whatsapp/presentation/router.py) y
[esquemas.py](../App/backend/app/modules/whatsapp/presentation/esquemas.py).

| Endpoint | Acceso y comportamiento |
| --- | --- |
| `POST /api/whatsapp/borradores` | Público, sin sesión; `201`. Acepta items y, opcionalmente, modalidad, pago y dirección nueva. Rechaza teléfono, cliente_id, precios y campos extra. Devuelve referencia, mensaje, vencimiento y enlace si hay número configurado. No crea cliente ni pedido operativo. |
| `POST /api/whatsapp/simular` | Empleado, administrador o dueño; solo entorno no productivo con WhatsApp simulado. `202`, guarda una entrada con `id`, `telefono`, `texto` y `media_id` opcional. |
| `GET /api/whatsapp/bandeja` | Empleado, administrador o dueño. Devuelve `comprobantes` con total vigente, `cambios` pendientes, `atenciones` pendientes y `salidas`. Cada atención incluye `id`, `motivo` (`SOLICITUD` o `PROVEEDOR`), `telefono`, `cliente`, `pedido_id`/`numero`/`estado_pedido`/`total` (nulos sin pedido), `tipo_entrega`, `metodo_pago`, `borrador_vencido`, `productos`, `mensaje` que la originó, hasta cinco `mensajes` recientes y sus `respuestas` con el estado de la outbox. Las referencias `MB-` se reemplazan por `[referencia]`. |
| `POST /api/whatsapp/atenciones/{id}/respuesta` | Mismos roles internos. Cuerpo `texto` (1 a 1000 caracteres) y `solicitud_id` (UUID). `202`: crea una salida en `whatsapp_salida` con `atencion_id` y `enviado_por`; devuelve `id`, `atencion_id` y `estado` (`PENDIENTE`). No significa enviado. Repetir el mismo `solicitud_id` devuelve la misma salida; una atención resuelta responde `409`. |
| `POST /api/whatsapp/atenciones/{id}/resolucion` | Mismos roles internos. Cuerpo `resolucion` (1 a 500 caracteres). Registra empleado, fecha y detalle; devuelve `estado: "RESUELTA"` y es idempotente. No envía mensajes. La conversación vuelve a `VINCULADO` o `CREADO` salvo que tenga un cambio pendiente de revisión. |
| `POST /api/whatsapp/comprobantes/{id}/revision` | Mismos roles internos. Cuerpo `aprobar`, `motivo` y, al aprobar, `total_verificado` observado en la bandeja. Una diferencia con el total vigente rechaza la aprobación: recargar y revisar nuevamente. |
| `GET /api/whatsapp/comprobantes/{id}/archivo` | Mismos roles internos. Solo modo real; descarga autenticada como adjunto, sin caché y con `nosniff`. |
| `POST /api/whatsapp/cambios/{id}/revision` | Mismos roles internos. `aprobar` y `motivo`; al cambiar importe requiere `total_verificado` igual al nuevo total y `resolucion_financiera: "COBRO_PENDIENTE"`. Revalida versión, estado, stock y saldo. |
| `GET /api/whatsapp/webhook` | Público, habilitado en modo real. Verifica `hub.mode`, `hub.verify_token` y responde el `hub.challenge`. |
| `POST /api/whatsapp/webhook` | Público con firma `X-Hub-Signature-256` válida sobre los bytes originales, límite de 256 KiB y coincidencia del phone-number-ID configurado. Persiste entradas y callbacks; el worker procesa después. |

Un repartidor o cliente no puede revisar comprobantes, simular mensajes,
consultar la bandeja interna, responder ni resolver atenciones. El checkout público
ofrece WhatsApp con efectivo o transferencia; Mercado Pago ya no se ofrece en
ese carrito. Las operaciones internas conservan sus guardas de sesión y rol.

### Identidad comercial y vinculación

La migración `015_clientes_sin_cuenta.sql` separa `cliente.id` de su vínculo
opcional `usuario_id`. Conserva los IDs de clientes existentes y las referencias
de pedidos, direcciones, notificaciones y borradores; copia nombre y estado del
usuario, sin modificar sus credenciales. Los clientes nuevos de WhatsApp no
tienen usuario ni contraseña. Sus pedidos aparecen en los listados internos,
reparto y atenciones del bot con su identificación comercial.

El borrador público nace con `cliente_id` y `telefono` nulos. Su referencia aleatoria
de 256 bits es secreta y solo se guarda su hash. Al procesar el primer mensaje
con esa referencia vigente, el worker reclama el borrador para el `from` recibido
por el webhook firmado de Meta. Usa el nombre de perfil del contacto cuyo
`wa_id` coincide, si viene disponible; en su ausencia identifica por WhatsApp y
número. No es necesario volver a pedir esos datos en la web.

El bloqueo transaccional del teléfono y de la fila del borrador serializa reclamos
concurrentes. Una referencia reclamada queda limitada a ese remitente. El campo
único `cliente.whatsapp_verificado` permite recomprar desde el mismo WhatsApp;
el teléfono histórico declarado no se copia a ese campo ni fusiona identidades.
Los historiales anteriores se conservan asociados a sus clientes: no se unen
automáticamente con un nuevo cliente sin cuenta por coincidir el número.
Los borradores antiguos ya vinculados conservan la validación de referencia y
teléfono existente. El método interno de creación conserva esa compatibilidad;
el endpoint público siempre crea un borrador anónimo.

No hay consulta pública de borradores, pedidos ni historial por teléfono. La web
autenticada filtra los pedidos de cuentas anteriores mediante `usuario_id → cliente.id`;
el seguimiento y las modificaciones de compras sin cuenta se hacen por WhatsApp.
Las consultas financieras y el inicio de cobro verifican titularidad para clientes
autenticados; el repartidor usa sus rutas de reparto y no el historial global.

Para desplegar, coordinar la aplicación de la migración 015 en la base destino
sin ejecutar el seed de desarrollo. Actualizar API y workers juntos antes de
publicar el frontend público: un worker anterior presupone que todo cliente tiene
usuario y no es compatible con nuevos borradores anónimos. Conservar las variables
y credenciales actuales de Meta/Gemini, el webhook firmado y las adaptaciones de
destinatarios de prueba. El cambio de código no demuestra un despliegue: después
corresponde comprobar compra, recompra y mensajes repetidos con WhatsApp real.

Para continuar una conversación se valida el remitente firmado. Con un único
pedido activo alcanza ese remitente; con varios, cada mensaje que consulte o
modifique un pedido debe incluir su referencia `MB-`, por ejemplo
`sin tomate MB-…` o `confirmar MB-…`. El bot nunca elige entre pedidos. Dos
referencias distintas o un token `MB-` mal formado no seleccionan ninguno. Los
comprobantes se asocian por la referencia incluida en el pie de la imagen o
documento. La referencia es de acceso: se retira del texto antes de enviarlo a
Gemini, se oculta en la bandeja y no se registra en logs de la demo. También se
retiran sus variantes de escritura (minúsculas, espacio o guiones Unicode).

### Interpretación, derivación y límites

1. El worker lee la entrada y su contexto en una transacción breve y la cierra.
   El saludo preparado por la web, los adjuntos y los comandos guiados
   (`producto N` o `producto N; variante: X`) no consumen Gemini. Tampoco los
   mensajes de un teléfono sin conversación identificable: reciben una respuesta
   fija que pide la referencia.
2. El resto se interpreta **completo**, sin la referencia. Si supera 2000
   caracteres no se interpreta ningún fragmento: se pide reformularlo en un
   mensaje más corto y no se modifica el pedido. El servicio aplica la misma
   regla aunque reciba una acción ya interpretada.
3. Cada interpretación viaja con un vínculo: referencia de la conversación,
   pedido, versión y huella del contexto enviado. Al aplicar, bajo los bloqueos
   de teléfono y conversación, se recalcula. Si la conversación resultante es
   otra, se responde que no se aplicó ningún cambio: la acción nunca se
   redirige a otro pedido. Si es la misma conversación pero cambió su contexto,
   el worker reinterpreta una vez con el contexto vigente y, si vuelve a
   cambiar, rechaza sin modificar.
4. La acción `humano`, explícita o producida por un fallo de Gemini (motivo
   `PROVEEDOR`), se atiende antes de completar un borrador o modificar un
   pedido: registra una atención `PENDIENTE` en `whatsapp_atencion`, deja la
   conversación en `HUMANO`, descarta una propuesta de importe sin confirmar,
   conserva los datos y no crea el pedido. Hay como máximo una atención
   pendiente por conversación.
5. Mientras la atención esté pendiente, el bot registra los mensajes siguientes
   (visibles en la bandeja) y responde que un empleado está atendiendo, sin crear
   ni modificar el pedido. Solo sigue aceptando comprobantes, que quedan para
   revisión humana. Al resolver la atención, el bot retoma la conversación.

La revisión de comprobantes **registra una decisión humana**, no una validación
bancaria. `total_verificado` obliga a aprobar el importe observado; si cambia
antes de la aprobación, el backend responde `409` y conserva el pedido. Rechazar
no necesita `total_verificado`. El motivo queda asociado al empleado y al pago.
La recepción de un archivo y la clasificación de Gemini nunca aprueban pagos.
La entrada a preparación comprueba además el neto conciliado contra el total
vigente; una devolución posterior no puede reutilizar la aprobación histórica.

Los cambios antes de preparación y sin diferencia de precio se aplican después
de validar la receta, el estado y los permisos. La disponibilidad de venta del
producto solo se exige para **aumentar** unidades: retirar un ingrediente o
reducir la cantidad devuelve insumos ya consumidos y se permite aunque la
confirmación haya agotado el último stock. Si cambia el importe de un
pedido sin cobros conciliados, se conserva una propuesta hasta la confirmación
explícita del cliente, incluso si el cambio luego necesita aprobación de cocina.
Desde preparación, o si cambia el total de un pedido con cobros conciliados,
se deriva al empleado. La bandeja exige aceptar expresamente el nuevo importe
y coordinar cocina y caja; esa aceptación **no registra un cobro**.

Un aumento deja el saldo adicional pendiente. Para transferencia se exige otro
comprobante y revisión del saldo: la aprobación anterior no lo acredita. Si ya
se cobró más que el nuevo total, primero debe registrarse la devolución real
mediante `POST /api/pagos/devolucion` (pedido, monto, método y motivo); de otro
modo la revisión responde `409`. Después de resolverlo, volver a aprobar el
cambio. Efectivo y los otros medios conservan los endpoints existentes de pagos.
Repetir la aprobación del mismo cambio no vuelve a modificar stock ni importes.

Los cambios de cantidad ajustan solo la diferencia de stock. Antes de preparar,
una reducción devuelve insumos; una vez iniciada la preparación conserva el
consumo, porque la aprobación no demuestra que se puedan recuperar. Retirar
un ingrediente ya descontado antes de cocina registra una devolución idempotente.
Cocina lee `pedido_item` vigente y muestra sus aclaraciones; `whatsapp_cambio`
conserva el historial y la versión. Los tableros del personal refrescan pedidos
cada ocho segundos, con pausa en pestañas ocultas; la bandeja se actualiza
manualmente.

Un borrador puede omitir modalidad, método, dirección y variante obligatoria.
El bot pregunta antes de crear el pedido. Para variantes usa un comando guiado
validado contra el catálogo, por ejemplo `producto 1; variante: Doble`. Las notas
del borrador admiten retiros `Sin ingrediente` pertenecientes a la receta;
extras y texto libre requieren atención humana.

## Inbox, outbox y fallos

`whatsapp_entrada` conserva cada ID de proveedor una vez, con estado `PENDIENTE`
o `PROCESADO`. `whatsapp_borrador` separa datos parciales del pedido operativo;
el borrador sin pedido vence a los 30 minutos, también si está derivado: la
bandeja lo marca como vencido y el cliente debe prepararlo de nuevo. Las
operaciones y sus respuestas se guardan transaccionalmente. El worker libera la
conexión antes de llamar a Gemini o Meta y revalida al aplicar los cambios.
Las respuestas del personal usan la misma outbox y sus estados.

| Estado de salida | Significado |
| --- | --- |
| `PENDIENTE` | Respuesta guardada, todavía sin reclamar. |
| `ENVIANDO` | Reclamada por un worker. |
| `SIMULADO` | Procesada por transporte local; no se envió a WhatsApp. |
| `ACEPTADO` | Meta devolvió un ID; todavía no acredita entrega. |
| `ENTREGADO` | Callback `delivered` o `read` validado. Un callback tardío no degrada este estado. |
| `FALLIDO` | Rechazo conocido. Los fallos reintentables tienen hasta tres intentos, con esperas de 120, 240 y 480 segundos; el tercer intento ya no se vuelve a reclamar. |
| `INCIERTO` | Timeout, respuesta ambigua o `ENVIANDO` abandonado más de cinco minutos. No se reenvía automáticamente. |

Los callbacks se persisten aunque lleguen antes de guardar el ID devuelto por
el envío y se reconcilian por proveedor y destinatario bajo un bloqueo común
por ID de proveedor, también entre transacciones concurrentes. Un callback `failed`
agota los intentos; no se transforma en un reenvío automático. Los mensajes
reales fuera de la ventana de 24 horas quedan fallidos y retenidos para atención
humana: no hay soporte de plantillas ni botón de reenvío manual seguro todavía.
Antes de resolver un `INCIERTO`, verificar el resultado con Meta; nunca asumir
que no se envió ni actualizarlo a éxito sin evidencia.

## Configurar recursos reales de prueba

Este paso es independiente de la demo y requiere recursos de las cuentas de
Google y Meta. Mantener las credenciales solo en el backend; no agregarlas al
repositorio, `VITE_*`, capturas o logs. Variables del backend:

| Variable | Ejemplo o función |
| --- | --- |
| `WHATSAPP_MODO` | `simulado` por defecto; `real` para Cloud API. |
| `WHATSAPP_NUMERO_NEGOCIO` | `<NUMERO_DE_PRUEBA_CON_PAIS_Y_AREA>`; arma el enlace `wa.me`. No es el phone-number-ID. |
| `WHATSAPP_PHONE_NUMBER_ID` | `<ID_DEL_NUMERO_DE_PRUEBA_META>`. |
| `WHATSAPP_TOKEN` | `<TOKEN_META_CON_WHATSAPP_BUSINESS_MESSAGING>`. |
| `WHATSAPP_APP_SECRET` | `<APP_SECRET_META>`; firma HMAC del POST del webhook. |
| `WHATSAPP_VERIFY_TOKEN` | `<VALOR_ALEATORIO_ELEGIDO_PARA_EL_HANDSHAKE>`; distinto del app secret. |
| `WHATSAPP_GRAPH_VERSION` | Versión explícita del recurso Meta; configuración inicial `v26.0`, revisable antes de probar. |
| `WHATSAPP_DESTINATARIOS_PRUEBA_SIN_9` | Lista JSON de remitentes argentinos `549...` verificados en la lista de prueba de Meta como `54...`. Vacía por defecto: `[]`. Ver el caso de formato más abajo. |
| `WHATSAPP_TRANSFERENCIA_DATOS` | Instrucciones ficticias para probar. Si está vacío, el bot deriva la consulta al personal. |
| `GEMINI_MODO` | `simulado` por defecto; `real` para interpretar con Gemini. |
| `GEMINI_API_KEY` | `<CLAVE_DE_GOOGLE_AI_STUDIO>`. |
| `GEMINI_MODELO` | `gemini-3.1-flash-lite`, configurable. |

Para Meta: crear/configurar la aplicación y WhatsApp Business Platform, obtener
el número de prueba y su phone-number-ID, y autorizar/verificar al destinatario
de prueba desde la consola. Usar un token con el permiso necesario. Exponer el
webhook del backend mediante HTTPS y registrar
`https://<HOST_HTTPS_DE_PRUEBA>/api/whatsapp/webhook` con su verify token;
suscribir los eventos de mensajes de la cuenta de prueba. El POST requiere la
firma del app secret, no el verify token. No pegar el app secret dentro del
cuerpo de un webhook ni desactivar la validación para probar.

Abrir el chat o lanzar un `wa.me` no entrega el mensaje al backend: el
destinatario debe enviarlo. Para texto libre real, primero debe existir un
mensaje del usuario dentro de las últimas 24 horas. Fuera de esa ventana Meta
exige plantillas previamente aprobadas; no están implementadas en esta etapa.
La política también exige una vía clara de atención humana. Ver la
[política oficial de WhatsApp](https://business.whatsapp.com/policy) y la
[colección oficial de mensajes de Meta](https://www.postman.com/meta/whatsapp-business-platform/folder/13382743-ba8d099d-007e-4b52-b9f2-3cf3c60e4fbc).

Para adjuntos reales, el adaptador obtiene la URL temporal por media-ID y
descarga con autorización. Solo permite HTTPS en `lookaside.fbsbx.com` o
subdominios de `fbcdn.net`, sin redirecciones, y JPEG, PNG o PDF hasta 5 MiB.
Comprueba tamaño y consistencia del MIME declarado; no analiza autenticidad del
comprobante. Las URLs temporales no son enlaces públicos permanentes. Referencia:
[recuperación de medios de Meta](https://www.postman.com/meta/whatsapp-business-platform/request/fpj02x0/retrieve-media-url).

## Desplegar en Render sin un worker de pago separado

El servicio Python existente puede ejecutar la API y el ciclo de WhatsApp en
el mismo proceso, con el pool y el apagado coordinados. El comando
`python -m scripts.serve --migrar` aplica únicamente migraciones pendientes,
sin seed ni reset, y luego inicia el servicio. Si falla una migración o cambia
el contenido de una ya aplicada, no inicia la API. La validación admite hashes
históricos LF/CRLF, conservando los registros existentes. El bloqueo de migraciones es
de sesión: usar conexión PostgreSQL directa o un pooler en modo sesión, nunca
un pooler en modo transacción para este comando.

En Settings del servicio de Render configurar:

| Campo | Valor |
| --- | --- |
| Branch | `main` (después de subir y verificar el commit del bot). |
| Root Directory | `App` (incluye `backend` y las migraciones de `db`). |
| Build Command | `pip install -r backend/requirements.txt` |
| Start Command | `cd backend && python -m scripts.serve --migrar` |
| Health Check Path | `/api/salud` |

`--migrar` autoriza la aplicación de migraciones al destino de `DATABASE_URL`:
confirmarlo antes de publicar y coordinar cualquier cambio en la base del
equipo. No agregar `--seed`, `--reset` ni credenciales al comando de arranque.
No hace falta un Pre-Deploy Command para esta configuración. Un respaldo y
la conservación del despliegue anterior permiten atender una falla; volver al
commit anterior no revierte automáticamente migraciones ni pedidos.

En Environment del backend cargar las variables WhatsApp y Gemini de la tabla
anterior con sus valores reales, no los placeholders. Mantener `DATABASE_URL`,
`JWT_SECRET` y los orígenes CORS ya configurados. El `.env` local no se sube.
Usar `DEBUG=false`, `WHATSAPP_MODO=real` y `GEMINI_MODO=real` para la prueba
con ambos proveedores. El token temporal de Meta debe seguir vigente.

El worker integrado se activa únicamente con `WHATSAPP_MODO=real`. En modo
simulado la API no procesa automáticamente ninguna salida: no convierte
mensajes reales pendientes en éxitos simulados. `--sin-worker` permite usar
el worker CLI separado si se dispone de un servicio independiente; no iniciar
ambos por rutina. Un error transitorio del ciclo se informa por su clase, sin
texto de mensajes ni secretos, y se vuelve a intentar después de dos segundos.
El servidor desactiva los access logs de Uvicorn para no registrar el verify
token del handshake dentro de la query string.

Para la instalación actual, la callback pública es:

```text
https://proyecto-seminario-integrador-2026.onrender.com/api/whatsapp/webhook
```

Después del despliegue comprobar `/api/salud` y la presencia de WhatsApp en
`/openapi.json`. Un GET del webhook sin token debe responder `403`, no `404`.
En Meta configurar la callback, el mismo `WHATSAPP_VERIFY_TOKEN` del backend y
la suscripción `messages`. Una firma inválida del POST debe seguir rechazada.
La verificación de la callback no acredita envío ni interpretación real: para
eso realizar un intercambio desde el destinatario de prueba y comprobar inbox,
outbox y entrega. No cargar pedidos ficticios masivos en la base compartida.

Render Free suspende el servicio tras 15 minutos sin tráfico entrante; al
despertarlo puede demorar alrededor de un minuto. El worker también se detiene
durante esa suspensión y retoma los registros persistidos al arrancar. Esto
sirve para la demostración académica, sin garantía de atención permanente.
No contratar otro plan ni agregar servicios para evitarlo automáticamente.
Referencias: [variables de entorno](https://render.com/docs/configure-environment-variables),
[FastAPI](https://render.com/docs/deploy-fastapi) y
[limitaciones gratuitas](https://render.com/docs/free).

### Destinatarios de prueba argentinos: diferencia entre `54...` y `549...`

En la prueba real de esta instalación, un saludo entró con `wa_id` `549...`,
pero Meta rechazó la respuesta a ese formato con `131030` (destinatario fuera
de la lista permitida). Enviar al mismo celular verificado como `54...` fue
aceptado; el callback devolvió el `wa_id` original `549...` y confirmó entrega.

Para ese caso puntual, configurar en Environment del backend de Render:

```text
WHATSAPP_DESTINATARIOS_PRUEBA_SIN_9=["5492215550000"]
```

El número del ejemplo es ficticio: reemplazarlo por el **remitente completo
que llega al webhook**, con `549`, sin `+`, espacios ni guiones. En Render,
la clave y el valor JSON van en campos separados; no rodear el JSON con
comillas adicionales. Agregar únicamente celulares propios de prueba cuya
variante sin `9` ya esté verificada en Meta. Guardar y desplegar.

La adaptación modifica solamente el campo `to` del envío. La conversación,
la ventana de atención y la conciliación de estados conservan el `wa_id`
recibido. Los demás números se envían tal como llegan. No hay un segundo
envío automático a otra variante ante errores o resultados inciertos.
No se debe activar esta excepción por rutina para números de producción.

Luego enviar un **nuevo** saludo: los mensajes cuyos tres intentos ya se
agotaron se conservan para revisión y no se reactivan al cambiar esta opción.

Si Meta rechaza una salida, buscar en los logs del backend la línea
`whatsapp_envio_http`: informa `http`, `codigo_meta` (o `None` si no se pudo
leer un código numérico) y `destino_prueba_adaptado`. No incluye teléfono,
texto, token ni cuerpo del proveedor. `destino_prueba_adaptado=True` permite
comprobar que la excepción configurada se aplicó al envío que falló. Esta
observación conserva los estados y las reglas de reintento del worker.

La misma línea incluye `emisor_id`, `version`, `revision` y `proceso_ref` para
identificar la configuración y el proceso que hizo la petición. `token_ref`
es una huella SHA-256 de 16 caracteres con el prefijo de dominio
`monuburger-whatsapp-v1:`; permite comparar la credencial efectiva con la local
sin registrar el token ni parte de él. Revisar estos campos cuando los valores
guardados en el panel coinciden pero el proceso sigue recibiendo `131005`.

## Gemini: modelo y consumo

La documentación oficial consultada el 17 de octubre de 2026 publica
`gemini-3.1-flash-lite` como estable, con llamadas a funciones y salidas
estructuradas. Su precio estándar de texto publicado es USD 0,25 por millón de
tokens de entrada y USD 1,50 por millón de salida, incluidos tokens de
razonamiento. El nivel gratuito depende de las cuotas y puede usar el contenido
para mejorar productos: las pruebas académicas usan datos ficticios.
Google anuncia su retiro para el 7 de mayo de 2027 y propone
`gemini-3.5-flash-lite` como reemplazo. Configurar el modelo evita cambiar reglas
de pedidos al migrarlo; aún se debe evaluar su interpretación con casos reales
del negocio, sin datos personales.

El adaptador hace como máximo una llamada `generateContent` por turno, sin
reintentos ni historial remoto, con hasta 256 tokens de salida. Proyecta un
contexto pequeño de catálogo y pedido, sin teléfono, dirección ni nombre del
cliente. El texto del propio turno sí puede contener datos que haya escrito la
persona; no usar información personal en la prueba. Referencias y adjuntos se
procesan de forma determinista sin consumir Gemini.

Solo admite una llamada a `datos`, `quitar_ingrediente`, `cantidad`, `confirmar`,
`consulta` o `humano`, con argumentos validados. Nunca ejecuta funciones del
modelo directamente ni usa su texto para confirmar pagos, precios o estados.
Si falla la cuota, conexión o estructura de salida, devuelve `humano` con
`motivo: "PROVEEDOR"`: el bot registra una atención para el personal y conserva
el pedido o borrador sin cambios. Un texto de más de 2000 caracteres devuelve
`motivo: "MENSAJE_LARGO"` sin llamar al proveedor; el bot pide reformularlo.
No utiliza grounding, búsquedas ni lectura de comprobantes.

Fuentes oficiales: [modelo](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite),
[precios](https://ai.google.dev/gemini-api/docs/pricing),
[límites por proyecto](https://ai.google.dev/gemini-api/docs/rate-limits),
[retiros](https://ai.google.dev/gemini-api/docs/deprecations) y
[contrato generateContent/function calling](https://ai.google.dev/gemini-api/docs/generate-content/function-calling).

## Verificación local

Con `DATABASE_URL` configurada hacia la base descartable, desde `App/backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_whatsapp_proveedores.py tests/test_whatsapp_cola.py tests/test_whatsapp_bd.py tests/test_whatsapp_regresiones.py tests/test_whatsapp_http.py tests/test_whatsapp_concurrencia.py tests/test_pedidos_whatsapp.py tests/test_stock_devoluciones.py tests/test_stock_cambios_cantidad.py tests/test_arquitectura.py -q -rs
.\.venv\Scripts\python.exe -m pytest tests/test_compra_publica.py tests/test_clientes_identidad.py tests/test_pagos_privacidad.py -q -rs
.\.venv\Scripts\python.exe -m scripts.whatsapp_demo
```

Las pruebas SQL usan transacciones revertidas; las de concurrencia confirman
filas con UUID o teléfonos aleatorios propios y las eliminan al terminar. Entre
ellas, dos pruebas retienen la interpretación con eventos explícitos mientras
otra conexión cancela y vincula pedidos o cambia el mismo pedido. La demo conserva sus datos.
Sin una base local explícita las pruebas pueden omitirse: revisar `-rs`
y reportar omitidas por separado. Ejecutar la demo no demuestra navegación,
accesibilidad ni funcionamiento con Meta/Gemini reales; esas verificaciones se
informan por separado. Para las comprobaciones generales del frontend y de CI,
seguir [DESARROLLO.md](DESARROLLO.md).

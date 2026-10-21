# WhatsApp: alcance funcional acordado

Acuerdos iniciales: 17 de octubre de 2026. Revisión de alcance: 20 de octubre de 2026.
Este documento registra decisiones de producto. La ampliación de edición y recuperación
del 20/10 está implementada localmente y aún no fue publicada en esta sesión.
El estado implementado, los contratos y sus límites se describen en la
[guía de desarrollo de WhatsApp](WHATSAPP_DESARROLLO.md).

## Objetivo y contexto

El cliente arma su pedido en la web y lo envía al WhatsApp del negocio. El bot
recibe la solicitud, reúne los datos necesarios, registra el pedido y acompaña
su evolución. La IA interpreta mensajes y modificaciones en lenguaje natural;
el backend valida y ejecuta las operaciones del negocio.

Es un proyecto académico. La integración usa WhatsApp Cloud API
directamente desde el backend Python, en entorno de prueba, conservando un modo
simulado para desarrollo y demostraciones. **n8n queda descartado del diseño.**
No se requiere publicar el sistema en producción ni habilitar el número comercial
para comenzar el desarrollo.

El alcance amplía lo planteado originalmente en el
[relevamiento reentregado](../documentos/Actividad-02-Relevamiento-y-Alcance-Reentrega.pdf):
WhatsApp participa en la recepción y modificación de pedidos, además de los avisos.
El documento académico conserva su valor histórico; la decisión vigente para esta
integración es la registrada aquí.

## Recorrido del cliente

1. Arma productos, cantidades y personalizaciones en la web.
2. Elige enviar por WhatsApp. El chat se abre con el mensaje preparado; el
   cliente debe enviarlo dentro de WhatsApp para que el bot lo reciba.
3. El bot vincula la solicitud con el borrador persistido preparado en la web;
   identificación y aislamiento se describen en la guía de desarrollo.
4. Si faltan datos, los solicita: dirección y referencias para delivery, modalidad
   de entrega, método de pago u opciones obligatorias de un producto.
5. El backend valida disponibilidad, opciones permitidas y precio. El bot comunica
   el resumen, total e identificador del pedido cuando queda registrado.
6. Continúa el flujo de pago correspondiente y avisa que informará los avances.
7. Los cambios efectivos de estado disparan los avisos de pedido en camino y
   entregado. El cliente puede plantear preguntas y solicitudes de modificación.

La mera apertura de WhatsApp no cuenta como recepción ni confirmación del pedido.
La persistencia de datos parciales y el momento de crear el pedido operativo se
describen en la guía de desarrollo.

## Modificaciones por conversación

Ejemplo: el cliente pidió una hamburguesa doble con tomate y luego solicita
"¿Le podés sacar el tomate?". El resultado esperado es que el pedido guardado y
la información que recibe cocina indiquen **doble sin tomate**.

- La IA identifica la intención, el pedido y el producto al que corresponde.
- Si hay más de un producto posible o falta información, pregunta antes de actuar.
- El backend comprueba que la modificación esté permitida y aplica el cambio.
- El bot anuncia éxito después de que la modificación se guardó efectivamente.
- Se conserva historial del cambio y una única versión vigente para cocina.

### Reglas confirmadas

| Situación | Resolución |
| --- | --- |
| Pedido todavía fuera de preparación, sin diferencia de precio | Cambio automático permitido si el backend lo valida y el producto es inequívoco. |
| Cualquier modificación desde preparación o listo, incluidos entrega y pago | La solicitud completa queda pendiente de un empleado; se conserva el pedido vigente. |
| Cambio de total antes de cocina, con o sin pagos existentes | Mostrar nuevo resumen y total; exigir confirmación explícita y revalidar antes de aplicar. Si el nuevo total queda debajo del neto cobrado, intervienen personal y caja. |
| Pedido ya pagado, modificación sin diferencia de precio y todavía fuera de preparación | Puede modificarse automáticamente si el backend lo valida. |
| Pedido o producto ambiguo | El bot solicita aclaración; mantiene el pedido vigente hasta resolverla. |

Antes de cocina, en pendiente o confirmado, se permite agregar y quitar productos,
reemplazarlos, cambiar cantidad o variante y agregar, cambiar o retirar personalizaciones
admitidas por la receta. También se pueden modificar dirección, referencias,
retiro/delivery y método acordado, consultar resumen/total y solicitar cancelación.
«Agregar una Crispy sin bacon» agrega una línea al mismo pedido; no altera otra
hamburguesa. Si faltan producto, variante, cantidad o destino del cambio, se conserva
la intención y se pide aclaración. No se inventan extras, ingredientes ni precios.
Quitar el último producto exige confirmar la cancelación; nunca deja un pedido vacío.

La entrada en preparación se comprueba también al confirmar y aplicar. La marca
`preparacion_en` conserva la protección aunque una corrección haya vuelto la etiqueta
a pendiente o confirmado. Desde cocina o listo, toda modificación se deriva de inmediato,
sin pedir primero confirmación de un cambio que el cliente ya no puede aplicar solo.
El personal recibe la solicitud persistida en la bandeja existente.

Los cambios de importe se cotizan en servidor y conservan el pedido vigente hasta
`confirmar`. El backend revalida versión, estado, cobertura, reparto, stock, precio y
dinero acreditado. Un aumento deja saldo pendiente; un cambio no acredita pagos ni
registra reintegros. Si el nuevo total es menor al neto cobrado, caja debe registrar
la devolución real antes de retomar el cambio. Las solicitudes compuestas que el
bot no puede representar de forma segura se derivan completas, sin ejecutar una parte.

La IA puede proponer hasta ocho operaciones en un mismo mensaje, combinando productos,
cantidades, variantes, personalizaciones, entrega, dirección y pago. El bot guarda el
plan completo mientras pide los datos faltantes y muestra una sola propuesta final.
`confirmar` aplica el conjunto en una transacción; no guarda partes anticipadamente.
Los índices de productos refieren a las líneas originales de esa solicitud.

Después de asignar un repartidor se coordina la modificación con el personal.
La IA no cambia estados físicos de cocina o reparto a partir del texto de un
cliente. Los recorridos de regreso y corrección manual están en
[operación de pedidos](OPERACION_PEDIDOS.md).

## Pagos

### Transferencia

1. El bot informa el importe y los datos para transferir.
2. Solicita el comprobante y lo asocia al pedido.
3. Avisa al empleado y comunica que el pago está pendiente de revisión.
4. Una persona verifica y aprueba el pago.
5. Solo después de esa aprobación se habilita el pedido para preparación.

**Recibir un comprobante no equivale a aprobar el pago.** La IA no decide si el
comprobante es verdadero ni declara el pedido pagado. Deben registrarse el resultado
de la revisión y el empleado que la realizó.

### Efectivo

El bot confirma el importe a abonar y no solicita comprobante. El pago queda
pendiente de cobro. No requiere aprobación de transferencia para que el personal
pueda pasar el pedido a preparación.

## Responsabilidades

| Actor | Responsabilidad |
| --- | --- |
| Web | Armado del pedido y paso a WhatsApp. |
| IA | Interpretar preguntas, datos y solicitudes de cambio; pedir aclaraciones ante ambigüedad. |
| Backend | Validar identidad y acceso, catálogo, precios, stock, cambios y estados; ejecutar y registrar operaciones. |
| Empleado | Revisar transferencias y resolver cambios sujetos a aprobación humana. |
| Repartidor/personal autorizado | Actualizar los estados operativos que disparan avisos. |
| Canal WhatsApp | Transportar mensajes, adjuntos y resultados de envío mediante la API oficial. |

Las respuestas sobre el pedido deben basarse en datos reales del sistema. La IA
no inventa precios, disponibilidad ni confirmaciones de operaciones que fallaron.
La derivación humana mínima está implementada como atención pendiente en la
bandeja (ver [desarrollo](WHATSAPP_DESARROLLO.md)); el alcance de las preguntas
abiertas queda por definir.

## Proveedor de IA y criterio de costo

El proveedor es **Google Gemini**. La propuesta inicial del 17/10 fue evaluar
`gemini-3.1-flash-lite`; la configuración actual usa `gemini-3.5-flash-lite` como
valor predeterminado y admite el primero como alternativo opcional. La documentación
oficial verificada el 20/10 publica llamadas a funciones y tokens estándar gratuitos
para ambos, sujetos a cuota y disponibilidad del proyecto. No se activó facturación
ni se contrató otro servicio. Que exista nivel gratuito no garantiza costo cero si
la clave pertenece a un proyecto que ya tiene facturación habilitada.

Cada interpretación tiene un presupuesto configurable de dos intentos y veinte
segundos por defecto, compartido entre modelos. Una reinterpretación por concurrencia
puede llevar una entrada a cuatro llamadas y cuarenta segundos de espera de IA.
Los comandos guiados, avisos y comprobantes no consumen Gemini. El catálogo enviado
está acotado; precios, permisos y ejecución siguen siendo autoridad del backend.

Las pruebas con el nivel gratuito usarán datos ficticios: Google indica que ese
nivel puede usar el contenido para mejorar sus productos. Credenciales solo en
backend; no registrar claves ni enviarlas al frontend. Si una cuota o el proveedor
fallan, se conserva el contexto, se registra una atención técnica recuperable y se
ofrece continuar por comandos reales (`ayuda`, `agregar`, elecciones de catálogo,
variantes, cantidades, datos y `resumen`) o por un empleado. No se presenta esa
gramática determinista como una llamada real a Gemini. Diagnósticos, herramientas,
pruebas ficticias reales y límites en la
[guía de desarrollo](WHATSAPP_DESARROLLO.md#gemini-modelo-y-consumo).

Fuentes oficiales: [modelo](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite),
[precios](https://ai.google.dev/gemini-api/docs/pricing),
[límites](https://ai.google.dev/gemini-api/docs/rate-limits) y
[llamadas a funciones](https://ai.google.dev/gemini-api/docs/function-calling).

## Trazabilidad del diseño inicial

La definición del 17/10 identificó estas áreas, cuyos contratos actuales se describen
en la guía de desarrollo; la lista no es evidencia de una nueva prueba ni publicación:

- Identificación del borrador, conversación, cliente y pedido; tratamiento de abandono.
- Estados separados de conversación, pedido, pago y notificación.
- Herramientas que la IA puede solicitar al backend y cómo se validan sus argumentos.
- Evaluación del modelo Gemini propuesto, límites de consumo y manejo de errores
  cuando el proveedor no esté disponible.
- Webhooks, autenticación, mensajes repetidos y modificaciones concurrentes.
- Adjuntos de comprobantes, acceso del empleado y recorrido de aprobación/rechazo.
- Avisos automáticos, reintentos y medición del envío respecto del evento de negocio.
- Pruebas con recursos de Meta y pruebas reproducibles con el modo simulado.

Consultar [arquitectura actual](ARQUITECTURA.md), [desarrollo](DESARROLLO.md) y las
instrucciones [AGENTS.md](../AGENTS.md). Son referencias para contrastar el diseño
con el código vigente; sus descripciones anteriores de n8n no reintroducen esa
dependencia en el alcance acordado.

## Alternativa académica desde la web (20/10/2026)

La demostración también permite continuar el carrito y conversar dentro del menú
cliente existente. Gemini interpreta realmente cuando se configura en modo real;
el transporte WhatsApp se simula y el aviso de la interfaz lo indica. Borradores,
mensajes, pedidos, cambios, comprobantes, revisiones y avisos siguen persistidos
en PostgreSQL y afectan los paneles y el stock de la base descartable.
No agrega una segunda web ni modifica las reglas de confirmación, cocina o pagos.
La sesión anónima emitida por backend aísla el historial sin autenticar por teléfono.
El modo queda desactivado por defecto. La publicación autorizada por el dueño
puede usar la base compartida mediante configuración persistida explícita; los
tests y seeds conservan la restricción a una base local descartable.
Configuración, comandos y límites implementados en
[chat web de demostración](WHATSAPP_DESARROLLO.md#chat-web-de-demostración).

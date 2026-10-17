# WhatsApp: alcance funcional acordado

Fecha: 17 de octubre de 2026.
Estado: definición funcional para preparar el diseño y el plan de desarrollo.
Este documento registra decisiones de producto; no afirma que estén implementadas.
El estado implementado, los contratos y sus límites se describen en la
[guía de desarrollo de WhatsApp](WHATSAPP_DESARROLLO.md).

## Objetivo y contexto

El cliente arma su pedido en la web y lo envía al WhatsApp del negocio. El bot
recibe la solicitud, reúne los datos necesarios, registra el pedido y acompaña
su evolución. La IA interpreta mensajes y modificaciones en lenguaje natural;
el backend valida y ejecuta las operaciones del negocio.

Es un proyecto académico. La integración se desarrollará con WhatsApp Cloud API
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
3. El bot vincula la solicitud con el pedido preparado en la web. La forma de
   conservar e identificar ese borrador se definirá en el diseño técnico.
4. Si faltan datos, los solicita: dirección y referencias para delivery, modalidad
   de entrega, método de pago u opciones obligatorias de un producto.
5. El backend valida disponibilidad, opciones permitidas y precio. El bot comunica
   el resumen, total e identificador del pedido cuando queda registrado.
6. Continúa el flujo de pago correspondiente y avisa que informará los avances.
7. Los cambios efectivos de estado disparan los avisos de pedido en camino y
   entregado. El cliente puede plantear preguntas y solicitudes de modificación.

La mera apertura de WhatsApp no cuenta como recepción ni confirmación del pedido.
La persistencia de datos parciales y el momento exacto de crear el pedido operativo
deben quedar explícitos en el diseño técnico.

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
| Pedido ya en preparación | La solicitud requiere aprobación de un empleado. |
| Pedido ya pagado y modificación que cambia el total | Siempre interviene un empleado para resolver diferencia o devolución. |
| Pedido ya pagado, modificación sin diferencia de precio y todavía fuera de preparación | Puede modificarse automáticamente si el backend lo valida. |
| Pedido o producto ambiguo | El bot solicita aclaración; mantiene el pedido vigente hasta resolverla. |

La entrada en preparación debe comprobarse al aplicar la modificación, para evitar
aceptar un cambio mientras cocina ya comenzó a trabajar con la versión anterior.
La confirmación de un nuevo total en pedidos aún no pagados se detallará en el diseño.

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

El proveedor acordado es **Google Gemini**, priorizando un costo muy bajo para
la demostración académica. Modelo inicial propuesto para evaluar:
`gemini-3.1-flash-lite`, configurable para poder cambiarlo sin modificar reglas
de pedidos o pagos. Google lo documenta como estable, con llamadas a funciones
y salidas estructuradas. Su adecuación al español del negocio y a las solicitudes
de modificación debe comprobarse con casos representativos; aún no se hicieron
pruebas reales contra Gemini.

Google anuncia el retiro de este endpoint para el 7 de mayo de 2027 y recomienda
`gemini-3.5-flash-lite` como reemplazo. El modelo debe elegirse por configuración
y revisar su disponibilidad al implementar; esta elección inicial prioriza el
costo de las pruebas académicas actuales. Ver [calendario oficial](https://ai.google.dev/gemini-api/docs/deprecations).

Precios de referencia consultados el 17 de octubre de 2026, modalidad estándar:
USD 0,25 por millón de tokens de entrada de texto y USD 1,50 por millón de tokens
de salida, incluidos tokens de razonamiento. Existe nivel gratuito sujeto a las
cuotas y disponibilidad del proyecto de Google; no se presupone uso ilimitado.
Por ejemplo, 1.000 llamadas con 2.000 tokens de entrada y 300 de salida facturada
cada una cuestan aproximadamente USD 0,95 en la modalidad paga. Es una estimación
de llamadas de IA, no de pedidos: una conversación puede necesitar varias llamadas.
No incluye cargos de WhatsApp ni infraestructura.

Para reducir consumo, el diseño enviará contexto acotado del pedido y las opciones
pertinentes, limitará salida y llamadas por turno y usará mensajes fijos para
avisos deterministas. La recepción de un comprobante lo deriva a revisión humana;
no requiere que el modelo determine su autenticidad. Las operaciones que solicite
Gemini siempre deben validarse en backend antes de ejecutarse.

Las pruebas con el nivel gratuito usarán datos ficticios: Google indica que ese
nivel puede usar el contenido para mejorar sus productos. Credenciales solo en
backend; no registrar claves ni enviarlas al frontend. Si una cuota o el proveedor
fallan, el pedido debe conservarse y ofrecer una continuación guiada o humana;
el comportamiento concreto se definirá en el diseño técnico.

Fuentes oficiales: [modelo](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite),
[precios](https://ai.google.dev/gemini-api/docs/pricing),
[límites](https://ai.google.dev/gemini-api/docs/rate-limits) y
[llamadas a funciones](https://ai.google.dev/gemini-api/docs/function-calling).

## Siguiente etapa de planificación

El diseño técnico deberá resolver, antes de escribir la implementación:

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

# Operación y corrección de pedidos

El pedido conserva su ID y número público durante toda la operación. Las
correcciones agregan historial; no se elimina una compra para volver a crearla.
El estado de cocina, el dinero recibido y el viaje son registros diferentes.

El panel muestra la siguiente acción como botón directo. Los retrocesos y la
cancelación están en «Más acciones»; editar datos, ver movimientos e historial
se despliegan cuando hacen falta. No se exige escribir un motivo: se registra
la acción elegida junto con el actor y la versión; se puede agregar una nota.
Cancelar, iniciar una nueva preparación de un cerrado, registrar una devolución
y confirmar el regreso al local conservan una confirmación contextual.

El cobro exacto usa el saldo preparado. Para cobrar otro importe o calcular
vuelto se despliegan los campos correspondientes. La transferencia sigue
requiriendo que una persona confirme el ingreso real mediante su botón;
el comprobante por sí solo no acredita dinero.

Al confirmar un cobro, el panel recibe el pedido actualizado en la misma respuesta
y habilita su siguiente acción sin esperar una recarga del detalle o del tablero.
La confirmación explícita del ingreso de una transferencia puede registrar y
conciliar en una única transacción HTTP; el alta de un comprobante mantiene su
estado pendiente por defecto. Cocina permite operar otras comandas mientras una
confirma su cambio y evita duplicar acciones sobre el mismo pedido.

Al enviar un estado, cobro, edición o acción de reparto desde el detalle, el modal
se cierra al aceptar el clic. La operación continúa en el provider de la sesión,
incluso al cambiar de sección; no se aborta al desmontar el formulario. El pedido
conserva su estado confirmado hasta recibir la respuesta de la API. Una operación
pendiente impide otra sobre la misma compra, sin bloquear las demás.
La confirmación del ingreso de una transferencia mantiene el detalle abierto:
actualiza el pago y habilita enviar a cocina con la respuesta confirmada, sin
una consulta adicional. Esto incluye transferencias nuevas y cobros pendientes
de conciliación. Si falla, el detalle conserva el error y el intento financiero;
se debe actualizar antes de reintentar con el mismo UUID.
En Cocina, marcar listo retira la tarjeta de la lista de trabajo inmediatamente;
si falla, reaparece con sus datos anteriores y queda un aviso para revisar.

Los avisos de error se conservan hasta cerrarlos y permiten volver a abrir el pedido;
no reenvían automáticamente comandos. Los intentos financieros conservan su UUID
para resolver respuestas perdidas sin duplicar cobros. Al cambiar de sesión, las
respuestas anteriores no publican datos ni inician pasos financieros con la cuenta
nueva. El trabajo en segundo plano continúa al navegar dentro de la app; cerrar o
recargar la pestaña no ofrece una garantía de ejecución persistente del navegador.

La protección SQL de preparación usa `pedido.metodo_pago_acordado` y el neto
conciliado vigente; una marca histórica del borrador de WhatsApp no acredita dinero
ni bloquea un ingreso confirmado desde el panel. Un error deja visible la acción
y permite actualizar; no se presenta como una operación que continúa guardándose.

## Cobrar y preparar

| Modalidad de pago | Acción del personal | Cocina |
| --- | --- | --- |
| Efectivo | Registrar el cobro cuando efectivamente se recibe el dinero. | Puede prepararse con saldo pendiente. |
| Transferencia | Comprobar el ingreso real y conciliar el cobro. Recibir una imagen no acredita fondos. | Requiere que el neto conciliado cubra el total vigente. |

Registrar dinero no cambia automáticamente el estado de cocina. Después de
verificar la transferencia, el personal envía el pedido a preparación. Si falta
stock, el pago permanece registrado y el pedido sigue disponible para resolver
el problema. No hay integración activa con Mercado Pago.

Los pagos pendientes no forman parte del dinero recibido ni de caja. Un
reintegro se registra como una nueva operación y no puede superar el neto
conciliado. Cambiar el método acordado afecta el cobro pendiente; conserva los
pagos anteriores y su método original.

Las operaciones de cobro y devolución usan `clave_operacion` UUID. Un reintento
conserva la misma clave y el mismo contenido. Una operación distinta usa una
clave nueva; reutilizarla con otro importe o pedido produce un conflicto.

El cierre guarda los totales y los vínculos del mismo conjunto de movimientos.
Incluye conciliados sin otro cierre hasta el final del turno y arrastra los que
quedaron sin cerrar de períodos anteriores. Una conciliación posterior al corte
se incorpora a una nueva generación pendiente o al siguiente cierre; no modifica
un cierre aprobado. El consolidado informativo consulta su ventana exacta, por
lo que puede diferir de un cierre con arrastre.

Los movimientos pendientes vinculados por el circuito histórico se separan con
auditoría al regenerar o aprobar un cierre pendiente. Si ya estaban ligados a un
cierre aprobado cuyos totales coinciden con sus conciliados, la conciliación real
separa ese vínculo y deja el ingreso disponible para el siguiente corte, sin
reescribir el cierre aprobado. Si los totales históricos aprobados ya son
inconsistentes, se rechaza la conciliación y se requiere revisión contable; este
comando no recalcula ese cierre ni registra ajustes ficticios.

## Entrega y correcciones

| Situación | Recorrido |
| --- | --- |
| Retiro listo | El personal registra la entrega en el local, sin crear un viaje. |
| Delivery listo | Asignar un repartidor, iniciar el viaje y registrar cada entrega. |
| Cambio de dirección o retiro/delivery | Editar el mismo pedido antes de tener un repartidor asignado. La API valida cobertura y recalcula envío y total. |
| Asignación incorrecta antes de salir | Desasignar el envío con un motivo; editar o asignar nuevamente. |
| Problema después de salir | Registrar el fallo y coordinar el regreso real. El fallo por sí solo no libera al repartidor ni devuelve el pedido al local. |
| Estado cargado por error | Usar una corrección con motivo y versión vigente; los permisos y la situación del envío limitan los destinos admitidos. |

Para corregir una entrega registrada por error, administración o dueño confirma
explícitamente el regreso del pedido y deja un motivo. El comando conserva el
pedido y la logística anterior en auditoría, devuelve esa compra a listo y
mantiene los otros envíos del viaje. Una nueva asignación se registra aparte.
Este recorrido también es obligatorio cuando el viaje ya finalizó: el cambio
general de estado no permite recuperar a listo una entrega que conserve su
vínculo logístico.

Si una reducción del total lo deja por debajo del dinero conciliado, primero
se registra el reintegro correspondiente. Si aumenta, queda saldo pendiente.
La API rechaza cambios sobre una versión anterior: actualizar el detalle y
revisar el cambio antes de volver a enviarlo.

## Stock y reapertura

El catálogo permite cargar varios ingredientes y cantidades propias por variante.
En «Receta» se editan las cantidades existentes; administración y dueño pueden
guardarlas, con control de versión para evitar pisar otra edición. Simple, Doble
y Triple no multiplican automáticamente todos los ingredientes: cada receta se
define expresamente. Las variantes antiguas conservan la receta base hasta que
se configuren; sus cantidades no se inventan durante la migración.

El editor acepta decimales con coma o punto y fracciones como `1/4`, `1/8` o
`3/2`. Muestra la equivalencia en la unidad real del inventario. La precisión es
de tres decimales: `2/3` muestra «Aprox. 0,667» antes de guardar. Un cuarto de un
ingrediente registrado en `GR` son 0,25 gramos; para representar piezas debe
estar registrado en `UNIDAD`. El editor de recetas no convierte ni cambia
unidades o saldos existentes.

Cada ítem fija su variante y receta al registrarse. Consumo, ajustes de cantidad,
retiro de ingredientes y reapertura usan esas cantidades guardadas, aunque se
edite el catálogo después. El contexto de WhatsApp usa la composición del mismo
pedido. El stock se descuenta al confirmar o preparar y los reintentos no lo
descuentan dos veces. Los pedidos previos a esta función se inicializan con la
receta base existente al migrar; no hay historial anterior que permita reconstruir
ediciones de recetas pasadas.

Cancelar antes de comenzar cocina devuelve la reserva consumida. Después de
comenzar la preparación se declara la merma; cambiar una etiqueta no devuelve
ingredientes utilizados al inventario.

Si se envió a cocina por error, el personal puede corregir a pendiente o
confirmado con motivo, versión y conservación explícita de insumos. También
puede deshacer una confirmación. Se conserva la fecha de preparación: una
cancelación posterior sigue requiriendo declarar la merma, y volver a preparar
no descuenta otra vez el consumo ya registrado.
Los cambios de productos posteriores siguen tratándose como cambios de cocina:
la corrección de estado no vuelve a habilitar devoluciones automáticas de
ingredientes ni elimina la revisión humana correspondiente.

Recuperar un pedido cerrado requiere administración o dueño, motivo y versión.
Una nueva preparación requiere `RECONSUMIR`. Una entrega marcada por error puede
volver a listo con `CONSERVAR`, sujeto a la situación real del reparto. Estos
tratamientos quedan registrados junto con el actor y el origen del cambio.

## WhatsApp y autoridad

Actualización local del 20/10/2026, aún sin publicar en esta sesión. La IA interpreta
intenciones; Pedidos conserva la autoridad para cotizar y ejecutar. El bot puede
agregar, quitar y reemplazar productos, cambiar cantidades/variantes y personalizaciones
admitidas, editar dirección/referencias/entrega/pago, consultar el total y solicitar
cancelación. Si faltan datos conserva la intención y pide aclaración. Quitar el último
producto propone cancelar con aceptación explícita; no deja un pedido operativo vacío.

La edición automática requiere `PENDIENTE` o `CONFIRMADO`, sin preparación iniciada
ni reparto activo. Desde `EN_PREPARACION` o `LISTO`, toda solicitud de modificación,
incluidos dirección y pago, se registra en la bandeja para un empleado y conserva el
pedido vigente. `preparacion_en` mantiene esa guarda aunque el personal retroceda la
etiqueta. El bot no pide confirmar primero una modificación que ya exige intervención.

`ServicioPedidos.cotizar_items` prepara la composición y los importes sin guardarlos;
`editar_items` revalida y aplica en la misma unidad de trabajo del pedido, historial
y ajuste de stock. Las líneas conservadas mantienen IDs y snapshots de receta/precio;
altas y reemplazos toman opciones y precios vigentes del catálogo. Se conserva el ID
y número del pedido. El stock ajusta la diferencia neta entre composiciones, permite
devolver lo consumido antes de cocina y rechaza aumentos sin insumos disponibles.

Si cambia el importe, el chat muestra el nuevo resumen y total y conserva una propuesta
persistida hasta recibir `confirmar`, incluso con pagos existentes. Al aceptar se
revalidan versión, preparación, reparto, catálogo, stock e importes. Un aumento deja
saldo pendiente: no reutiliza una aprobación de transferencia para acreditarlo. Si el
nuevo total resulta menor al neto cobrado, se deriva al personal y caja debe registrar
la devolución real antes de retomar la modificación. El bot no acredita comprobantes,
inventa reintegros ni altera estados físicos por el texto de un cliente. Las operaciones
compuestas que no puede representar de forma segura se derivan completas.

Las solicitudes compuestas representables usan `ServicioPedidos.cotizar_edicion`
y `editar_edicion`: composición, dirección, modalidad y pago se cotizan como un
resultado final y se guardan juntos con una sola versión e historial. No se encadenan
ediciones con totales intermedios. La cotización no crea direcciones ni descuenta stock;
el neto conciliado se compara con el total final. El chat conserva hasta ocho operaciones
y sus aclaraciones, muestra dirección, método y resumen final, y exige confirmar el
conjunto incluso si el importe no cambia. Los errores posteriores a la primera escritura
se propagan para revertir íntegramente el intento.

El proveedor se consulta sin mantener una transacción abierta. Antes de aplicar
una respuesta se vuelven a verificar la compra seleccionada, su versión, los
importes y el reparto. Un conflicto conserva el pedido y requiere revisar la
información vigente. La atención humana y los estados de envío de mensajes se
explican en la [guía de WhatsApp](WHATSAPP_DESARROLLO.md).

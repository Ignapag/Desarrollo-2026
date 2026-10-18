# Operación y corrección de pedidos

El pedido conserva su ID y número público durante toda la operación. Las
correcciones agregan historial; no se elimina una compra para volver a crearla.
El estado de cocina, el dinero recibido y el viaje son registros diferentes.

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

Si una reducción del total lo deja por debajo del dinero conciliado, primero
se registra el reintegro correspondiente. Si aumenta, queda saldo pendiente.
La API rechaza cambios sobre una versión anterior: actualizar el detalle y
revisar el cambio antes de volver a enviarlo.

## Stock y reapertura

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

La IA interpreta la solicitud del cliente y consume los mismos comandos de
operación que el panel. Puede proponer cambios de dirección, modalidad y método
cuando el pedido y su asignación lo permiten. No acredita comprobantes ni decide
que un pedido se cocinó, salió o se entregó por un mensaje del cliente.

El proveedor se consulta sin mantener una transacción abierta. Antes de aplicar
una respuesta se vuelven a verificar la compra seleccionada, su versión, los
importes y el reparto. Un conflicto conserva el pedido y requiere revisar la
información vigente. La atención humana y los estados de envío de mensajes se
explican en la [guía de WhatsApp](WHATSAPP_DESARROLLO.md).

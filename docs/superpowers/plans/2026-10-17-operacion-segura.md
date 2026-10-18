# Operación segura de pedidos — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development. El coordinador asigna archivos y revisiones; no se delega recursivamente.

**Goal:** Corregir la auditoría operativa y permitir correcciones manuales e IA conservando siempre pedido, número, historial y consistencia financiera/logística.

**Architecture:** Una autoridad de pedido valida estados y cambios operativos. Pagos registra dinero real sin simular acreditaciones; delivery coordina sus recursos con el pedido en la misma transacción. La IA y el panel consumen los mismos comandos.

**Tech Stack:** FastAPI, psycopg/SQL, PostgreSQL 16/17, React/Vite, Gemini/Meta existentes.

**Spec:** Revisión y seis prompts aceptados por el usuario en esta conversación. Reglas vinculantes resumidas debajo.

## Global Constraints

- Sin Mercado Pago activo. Transferencia: revisión y acreditación humanas; adjunto no acredita.
- Efectivo puede prepararse pendiente de cobro. Cobrar no inventa una operación física de cocina o entrega.
- Mismo ID y número del pedido; no borrar ni recrear para corregirlo.
- Dirección/modalidad/método modificables en pendiente/preparación/listo sin repartidor; luego requieren resolución coordinada del personal.
- Reversiones exigen motivo, actor y estado/versión esperados; las de cierre se reservan a administración/dueño.
- Conservar movimientos financieros conciliados, manejar saldo neto y no devolver insumos ya utilizados como si estuvieran disponibles.
- PostgreSQL descartable explícito para TODAS las pruebas. No cargar App/.env ni usar base compartida. Migraciones aplicadas inmutables.
- AGENTS.md por área, ui-ux-pro-max en frontend, dominio sin infraestructura, SQL parametrizado.
- No notificar éxito antes del commit. Outbox idempotente por evento, no por estado repetible.

## Review Focus

- Asignación mientras cambia dirección: solo una operación prevalece; ningún envío huérfano.
- Dos entregas simultáneas: cierre de viaje y disponibilidad coherentes.
- Cobro/reembolso concurrentes y pendientes: no inventar saldo ni exceder neto acreditado.
- Reapertura y stock: preservar consumo neto y contabilizar merma explícitamente.
- Respuesta IA/GET atrasada: no pisar cambios más recientes ni reutilizar solicitudes resueltas.

## Etapa 1 — Pagos (independiente de implementación de estados)

**Files:** modules/pagos y tests/test_pagos*, test_caja*. No editar pedidos, delivery, WhatsApp ni migraciones.
**Produces:** pagos sin endpoints activos de billetera, saldo solo CONCILIADO, cobros/devoluciones auditados, sin UPDATE de estado de pedido desde pagos.

- [x] Regresiones rojas para aprobación simulada, pendiente contado, devolución sin fondos y doble operación.
- [x] Corregir rutas/adaptador, repositorios y caja; conservar historial.
- [x] Revisión independiente aprobada tras dos rondas; 118 pruebas de área y luego 47 afectadas por la última corrección, sin skips. Reglas documentadas en operación de pedidos.

## Etapa 2 — Autoridad de pedido, stock y comandos manuales

**Files:** modules/pedidos, modules/stock, migración nueva 020 y sus tests. Dueño único de estas rutas/esquema.
**Produces:** versión y método acordado canónicos; detalle/listado/búsqueda completos; historial; comandos de estado/corrección y datos operativos; preparación con control financiero correcto; eventos de notificación.
**Consumes:** pagos CONCILIADO como única acreditación; no confirmar automáticamente por recibir archivo.

- [x] Regresiones rojas para cancelación sin devolver stock, falta de fecha de confirmación, salto delivery sin viaje y pérdida de activos tras 200.
- [x] Centralizar transiciones, correcciones con motivo/versión/actor, retiro listo→entregado y recuperación privilegiada.
- [x] Implementar cambios dirección/modalidad/método, saldo y cobertura; bloquear carrera con asignación.
- [x] Mantener fuente canónica; no duplicar consumo ni borrar cobros. Integración del consumidor WhatsApp en etapa 4.
- [x] Migraciones aditivas 020/021 y eventos por versión; DER y diccionario regenerados.
- [x] Pruebas funcionales/concurrencia y revisión independiente: 117 aprobadas, sin skips; dos P1 corregidos y re-revisados.

## Etapa 3 — Reparto (se coordina con interfaz de etapa 2)

**Files:** modules/delivery y tests/test_delivery*. No editar pedidos/stock/pagos/migraciones.
**Consumes:** autoridad de estado pública de pedidos y misma UnidadDeTrabajo.
**Produces:** asignación/salida/entrega/desasignación/recuperación reales, permisos por actor/pertenencia, cierre serializado del viaje.

- [x] Regresiones rojas de cancelado→en camino, entrega sin salida y dos entregas simultáneas.
- [x] Corregir bloqueos/orden/autoría/permisos y conectar autoridad del pedido.
- [x] Exponer asignación, desasignación, reasignación, fallo, regreso y corrección de entrega; probar errores y rollback.
- [x] Contrato comunicado al frontend; revisión independiente aprobada tras corregir tres hallazgos. 90 pruebas aprobadas sin skips en la ejecución afectada.

## Etapa 4 — WhatsApp e IA

**Files:** modules/whatsapp y tests/test_whatsapp*. Coordinador asigna implementador al liberar una plaza.
**Consumes:** comandos de etapa 2; no reimplementa reglas de pago/estado.

- [x] Regresión roja de solicitud resuelta que contamina una nueva.
- [x] Aplicar dirección/modalidad/método elegibles y derivación operable cuando no lo sean.
- [x] Conservar selección/memoria, confirmar importes y revalidar versión/asignación/fondos; IA fuera de transacción.
- [x] Mantener aprobación de comprobantes humana y estados físicos fuera de las herramientas de IA.
- [x] Múltiples turnos/pedidos, cambios de intención, reintentos y carreras: 290 aprobadas incluyendo arquitectura, sin skips; revisión independiente aprobada. Deadlock pedido/borrador reproducido y corregido.

## Etapa 5 — Interfaz operativa

**Files:** frontend fulfillment/kitchen/shared store, tests y consumidores directos.
**Consumes:** detalle, edición, historial, pagos y viajes reales.

- [x] Usar ui-ux-pro-max y conservar identidad visual.
- [x] Estados completos, número público, activos sin truncar, historia/búsqueda y detalle editable con motivo.
- [x] Sustituir entregas/asignaciones locales por operaciones persistidas y diferenciar retiro.
- [x] Dirección/teléfono/asignación/pagos reales; cocina con tiempos verdaderos.
- [x] Evitar GET obsoleto, doble clic y ceros ficticios por error; refrescar también al repartidor.
- [x] 36 pruebas operativas, 13 de portales y 3 de panel; lint/build aprobados. Tres P2 corregidos y re-revisados. Navegador no disponible, sin afirmar QA visual.

## Etapa 6 — Integración, documentación y publicación

- [x] Mapear cada hallazgo de la auditoría a cambio y regresión; matriz debajo.
- [x] Backend completo: 768 aprobadas sin skips; dos escenarios HTTP integrales adicionales aprobados. Frontend, Ruff, build y carreras verificados; CI final pendiente de su ejecución remota.
- [x] DER/diccionario regenerados y contrastados con SQL; guías de reglas/ejecución actualizadas y enlaces locales comprobados.
- [ ] Revisión independiente de conjunto y regresión de correcciones.
- [ ] Verificar CI/PR e integración autorizada. No resetear ni sembrar la base desplegada.
- [ ] Informar evidencia real, limitaciones de navegador/proveedores y decisiones tomadas.

## Cobertura de los hallazgos

| Hallazgo o requisito | Regresión y evidencia |
| --- | --- |
| Acreditación simulada de Mercado Pago | `test_pagos_operacion_segura.py`: webhook retirado y adaptador deshabilitado. |
| Pendientes contados como dinero; devoluciones sin fondos | `test_pagos_operacion_segura.py`: neto, caja, reintegro y sobreconciliación. |
| Doble clic y cobros/reintegros concurrentes | Mismo archivo: UUID, contenido original, vuelto y conexiones independientes. |
| Caja cambia entre agregado y vínculo o suplanta actor | `test_caja_seguridad.py`: corte estable, aprobación concurrente, arrastre, histórico y autoría HTTP. |
| Cancelación no devuelve reserva; corrección repone insumos usados | `test_operacion_pedidos.py` y `test_stock_cambios_cantidad.py`: reserva, merma y marca de cocina. |
| Falta fecha de confirmación al preparar directamente | `test_operacion_pedidos.py`: fecha persistida antes de reportar una entrega. |
| Activos perdidos después de 200 cierres | Mismo archivo: consulta completa y filtros SQL, relaciones por lote. |
| Etiqueta de delivery sin viaje real o cancelado resucitado | `test_delivery_bd.py` y `test_delivery_seguridad.py`: autoridad común y rollback. |
| Dos entregas dejan viaje/repartidor ocupados | `test_delivery_seguridad.py`: dos conexiones y cierre serializado. |
| Planificación roba una asignación manual | `test_delivery_revision.py`: snapshot previo al commit y escritura condicionada. |
| Fallo permite omitir regreso; entrega errónea atascada | Mismo archivo y seguridad: regreso físico, corrección privilegiada y conservación del resto del viaje. |
| Asignación o reintegro durante edición/preparación | `test_operacion_pedidos.py`: espera de bloqueo observada y nueva lectura de indicadores. |
| Solicitud humana resuelta contamina otra | `test_whatsapp_operacion_segura.py`: limpieza de intención/datos y origen propio. |
| IA usa una foto vieja o interbloquea el panel | `test_whatsapp_concurrencia.py`: proveedor fuera de transacción, versión/fondos/asignación y orden de locks. |
| Cambios de dirección/modalidad/método y nuevos importes | `test_whatsapp_operacion_segura.py`: mismo pedido, cobertura, confirmación, derivación a caja/reparto. |
| Número interno, estados ocultos, tiempos ficticios y comandos locales | `operacion-pedidos.test.js` y `operacion-ui.test.js`: contratos, roles, estados, edad real y formularios SSR. |
| GET atrasado, reintento financiero o cierre de detalle | Pruebas operativas frontend y correcciones de la revisión independiente; no equivalen a QA de navegador. |
| Recorrido completo entre capacidades con commits | `test_operacion_integral_http.py`: invitado, login real del personal, transferencia humana, cocina, fallos/regreso, retiro y cobro idempotente. |

Los archivos Python están en `App/backend/tests` y los JavaScript en
`App/frontend/tests`. La validación de proveedores reales y navegador se informa
por separado de las suites simuladas.

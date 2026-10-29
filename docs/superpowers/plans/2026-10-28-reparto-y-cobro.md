# Reparto sin límite y entrega con cobro confirmado

Objetivo solicitado: asignar varios pedidos al mismo repartidor sin límite,
mostrar su carga en hamburguesas, conservar pedidos en camino visibles/cobrables
y exigir pago completo antes de entregar tanto en retiro como en delivery.

## Implementación

- [x] Delivery y migración 031: quitar capacidad máxima, aceptar repartidores
  ocupados, agrupar asignaciones previas a salida y permitir próximas salidas;
  conservar disponibilidad correcta mientras quede trabajo abierto.
- [x] Conteo: unidades de hamburguesas vigentes asignadas, incluyendo cantidades
  explícitas de combos; excluir bebidas, acompañamientos e ítems retirados.
- [x] Pedidos: cobertura real por cobros menos devoluciones conciliados, leída
  bajo bloqueo; efectivo acordado no acredita un pago. Rechazar entrega sin
  cobertura antes de modificar pedido/envío.
- [x] Visibilidad: asignados y en camino siguen operativos; entregados históricos
  con saldo aparecen por cobrar sin falsificar su estado físico.
- [x] Frontend: selector con carga, acción cobrar en camino, entrega bloqueada
  y mensajes claros; conservar permisos, operación en segundo plano y reintentos.
- [x] TDD en PostgreSQL descartable y componentes, suite backend y pruebas
  frontend afectadas, lint/build y revisión independiente de integración.
- [x] Actualizar operación/DER/diccionario desde sus fuentes. No modificar
  migraciones anteriores, nube, credenciales ni publicar por rutina.

Se delegan backend de reparto y frontend con archivos separados. El agente
principal implementa la regla de pago en pedidos, integra y verifica el conjunto.

## Verificaci?n local (28/10/2026)

- PostgreSQL 16 descartable, migraciones 001?031 y seed: **1294 passed**, sin omisiones; una advertencia heredada de AnyIO.
- Operaci?n frontend: **125 passed**; adem?s compatibilidad focal de validaciones, privacidad y store aprobada por implementador.
- Ruff, lint, build, documentos generados y enlaces y diff aprobados. Dos advertencias heredadas de Fast Refresh.
- Revisi?n independiente sin hallazgos importantes; concurrencia mismo/distinto repartidor probada.
- Revisi?n visual en navegador sin ejecutar: no hay navegador conectado.
- Publicaci?n por el mismo flujo GitHub/Render/Pages autorizado previamente por el usuario. Sin seed ni tests contra la base compartida.

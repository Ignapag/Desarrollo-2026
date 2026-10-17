# Deuda técnica y límites conocidos

Inspección de referencia: 17 de octubre de 2026, `a62320c` más el reordenamiento
sin commit de esa fecha. Este inventario orienta futuras tareas; cada corrección
necesita alcance propio. Lo resuelto se quita de la tabla; el historial queda en Git.

| Prioridad | Área | Evidencia y consecuencia |
| --- | --- | --- |
| Alta | Transiciones de pedido fuera de `pedidos` | `pagos` confirma el pedido saldado con SQL propio (`servicio_pagos.py`: efectivo y webhook; `servicio_conciliacion.py`) y `delivery` lo pasa a en camino/entregado (`servicio_delivery.py`). Omiten `puede_transicionar` y el consumo al confirmar. La entrada por `ServicioPedidos` a preparación ahora descuenta el stock faltante también desde `CONFIRMADO`, sin duplicar consumos. Aún queda decidir qué pasa con un cobro cuando no hay stock y unificar la transacción del pago. |
| Media | Estilos de aplicación | `pedidos`, `productos`, `stock` y `reportes` reciben puertos `Protocol`; `delivery`, `pagos`, `usuarios` y `notificaciones` reciben `UnidadDeTrabajo` y repositorios SQL concretos (pagos crea `ClienteMercadoPago` por defecto). Funciona, pero sus casos de uso solo se prueban con base o con mocks del repositorio concreto. |
| Media | Estado compartido | `src/shared/store/DataContext.jsx` concentra consultas y mutaciones de varias capacidades; oxlint advierte un `setState` síncrono y una dependencia omitida en su efecto de carga (línea 246). Separarlo requiere preservar los consumidores actuales. |
| Media | Pruebas de navegador | No hay script `test` frontend ni suite end-to-end en CI. Build y lint no demuestran recorridos visuales. |
| Baja | Vistas demostrativas | `management/Analytics.jsx`, `Customers.jsx` y `AccessControl.jsx` muestran contenido de muestra. No anunciarlas como gestión real. |
| Baja | Registro y recuperación | `/register` y `/recover-password` redirigen a login. No hay vistas ni endpoints de autorregistro o recuperación. |
| Baja | Integraciones externas | El módulo anterior de notificaciones usa `EnviadorSimulado`; WhatsApp tiene adaptadores directos Meta/Gemini y demo persistente local. Faltan pruebas reales con credenciales, plantillas Meta fuera de 24 horas y resolución asistida de envíos inciertos. Mercado Pago conserva su verificación sandbox pendiente. Ver [guía de WhatsApp](WHATSAPP_DESARROLLO.md). |
| Baja | Mensaje de duplicado en usuarios | `email` también es `UNIQUE` (`001_usuarios_y_seguridad.sql`); un email repetido en el alta responde "Ese nombre de usuario ya existe" (`usuarios/infrastructure/repositorio_sql.py::crear`). |
| Baja | Omisiones en CI | Si el PostgreSQL de CI no respondiera, las pruebas con base se omitirían y el paso podría quedar verde. Revisar el conteo de omitidas en la salida del workflow. |
| Baja | Tipos de `vite.config.ts` | `npx tsc -p tsconfig.node.json` falla con TS2688: declara `types: ["node"]` sin `@types/node` instalado. No está en CI; el build no depende de ello. |
| Baja | Bundle | El build avisa un chunk de ~723 kB (> 500 kB) sin división de código. |

## Evidencia del 17 de octubre de 2026

Después del reordenamiento, en Windows con Python 3.13 del `.venv` y Node 24:

- Backend con PostgreSQL 16 descartable (contenedor `postgres:16-alpine`,
  migraciones desde cero con seed): **248 passed, 0 skipped**.
- Backend con `App/.env` hacia la base compartida: **150 passed, 98 skipped**;
  la guarda de `tests/soporte_bd.py` omitió todas las pruebas SQL/HTTP sin conectar.
  Tras sumar 5 casos de guarda (hostaddr, service, PG*): **155 passed, 98 skipped**
  sin base local. La corrida final con PostgreSQL no pudo repetirse porque los
  tests de WhatsApp en curso no importan todavía.
- `ruff check .` en `App/backend`: sin observaciones (antes: 49).
- `scripts.diccionario` y `scripts.der`: el diccionario estaba desactualizado
  respecto de las migraciones 009 y 010; se regeneró (y el generador dejó de
  emitir espacios finales para migraciones sin tablas). El DER no cambió.
- Esa evidencia es anterior al trabajo de WhatsApp que se agregó en paralelo
  (`modules/whatsapp`, migración 011), que no fue verificado en esta revisión.
- Frontend: `npm run lint` sin errores y 4 advertencias heredadas
  (`DataContext.jsx`, `AuthContext.jsx`); `npm run build` correcto.

Esto no equivale a CI aprobado ni a una verificación en navegador. El informe
[INTEGRACION_PRUEBA.md](INTEGRACION_PRUEBA.md) conserva evidencia de otra fecha.
Para actualizar esta sección, ejecutar los comandos de [DESARROLLO.md](DESARROLLO.md)
y registrar entorno, fecha y resultados por separado (aprobadas y omitidas).

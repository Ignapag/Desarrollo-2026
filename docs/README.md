# Documentación de Monu Burger

Entrá por el documento que corresponda a la tarea. El código, los manifiestos y
las pruebas definen el comportamiento vigente; los informes históricos conservan
el estado de su fecha y pueden describir trabajo que ya cambió.

| Documento | Para qué sirve |
| --- | --- |
| [AGENTS.md raíz](../AGENTS.md) | Instrucciones comunes y mapa para agentes. |
| [Arquitectura](ARQUITECTURA.md) | Componentes actuales, dependencias, flujos y puntos de extensión. |
| [Código limpio](CLEAN_CODE.md) | Convenciones Python, React, SQL y revisión. |
| [Desarrollo](DESARROLLO.md) | Preparación local, comandos y comprobaciones proporcionales. |
| [Despliegue](DESPLIEGUE.md) | Dos proyectos de Cloudflare Pages para clientes y personal, API de Render y verificación posterior. |
| [Flujo de IA](FLUJO_IA.md) | Skills, roles, delegación y uso eficiente del contexto. |
| [Alcance de WhatsApp](WHATSAPP_ALCANCE.md) | Flujo acordado de recepción de pedidos, IA, modificaciones y revisión humana de transferencias; integración directa sin n8n. |
| [Desarrollo de WhatsApp](WHATSAPP_DESARROLLO.md) | Demostración local, contratos, worker, revisión humana y conexión de recursos de prueba Meta/Gemini. |
| [Operación de pedidos](OPERACION_PEDIDOS.md) | Cobros, cocina, reparto y correcciones sin perder el pedido ni su historial. |
| [Deuda técnica](DEUDA_TECNICA.md) | Limitaciones conocidas; no es autorización para corregirlas todas. |
| [Guía del equipo](GUIA_EQUIPO.md) | Responsabilidad sobre la base compartida y colaboración con Git. |
| [DER](DER.md) | Diagrama generado del esquema SQL. |
| [Diccionario](DICCIONARIO_DATOS.md) | Tablas, campos y restricciones; generado desde SQL. |
| [Cambios del DER](CAMBIOS_DER.md) | Correcciones al modelo presentado en la actividad académica. |
| [Integración de ramas](INTEGRACION_PRUEBA.md) | Informe histórico de integración; sus resultados no prueban el estado actual. |
| [Tareas de Ignacio](TAREAS_IGNACIO.md) | Plan histórico por responsable; contrastar con la implementación. |

Los entregables académicos viven en [`documentos/`](../documentos/).
No es necesario leerlos completos para un cambio localizado.

## Mantenimiento

- Actualizar el documento dueño de cada regla; enlazarlo desde los demás.
- Arquitectura cambia con los contratos, módulos y entrypoints.
- Desarrollo cambia con comandos, configuración y CI.
- `DER.md` y `DICCIONARIO_DATOS.md` se regeneran con sus scripts, no a mano.
- Registrar fecha y evidencia de las verificaciones; distinguir ejecutado de sugerido.
- Guardar planes o decisiones solo cuando ayuden a coordinar una tarea concreta.

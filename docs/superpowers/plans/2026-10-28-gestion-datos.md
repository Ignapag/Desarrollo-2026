# Gestión de datos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** Implementar conservación operativa, auditoría automática antes/después y atribución transaccional.

**Architecture:** PostgreSQL audita mediante triggers; los repositorios filtran filas vigentes y realizan bajas lógicas. El backend propaga contexto validado por transacción, también en workers.

**Tech Stack:** PostgreSQL 16, psycopg 3, FastAPI, React/Vite, pytest.

**Spec:** [Diseño](../specs/2026-10-28-gestion-datos-design.md).

## Global Constraints

- No conectar ni aplicar migraciones en la base compartida durante este trabajo.
- Migraciones aplicadas inmutables; usar 029 para bajas y 030 para auditoría/contexto.
- No crear commits, cambiar de rama ni publicar por rutina.
- Nunca registrar secretos, hashes, tokens, cuerpos HTTP ni JSON libre sin selección.
- Conservar reglas financieras, versiones, stock, claves históricas y permisos vigentes.

## Review Focus

- Una relación revocada no concede permisos ni vuelve a descontar stock: tareas 1 y 4.
- Un rollback revierte el evento y el cambio; el actor no se filtra entre requests: tareas 2 y 3.
- La auditoría captura SQL directo, claves compuestas y cambios sensibles sin revelar valores: tarea 2.
- Los históricos y la recuperación conservan el significado del pedido y validan el estado: tareas 1 y 4.
- Las protecciones no impiden escrituras normales ni requieren una puerta de purga pública: tareas 2 y 4.

## Tarea 1: Filas vigentes y conservación de relaciones

Archivos: `App/db/migrations/029_bajas_logicas.sql`, repositorios de productos/pedidos/stock/reportes/WhatsApp y `usuarios/infrastructure/acceso_sql.py`, pruebas correspondientes.

Interfaz: `eliminado_en TIMESTAMPTZ NULL` en `pedido_item`, `producto_ingrediente`, `producto_variante_ingrediente`, `rol_permiso`. Los repositorios conservan sus contratos públicos y excluyen relaciones retiradas de todas las operaciones ordinarias.

- [x] Agregar regresiones que comprueben conservación, retirada, reactivación y filtros; observar fallo previo.
- [x] Reemplazar DELETE por UPDATE/upsert, actualizar funciones/vistas SQL y consumidores.
- [x] Verificar edición y snapshots, disponibilidad/costos, stock, reportes y autorización.

## Tarea 2: Auditoría automática SQL

Archivos: `App/db/migrations/030_auditoria_automatica.sql`, `App/backend/tests/test_auditoria_automatica_bd.py`.

Interfaz: GUC transaccionales `monu.usuario_id`, `monu.ip`, `monu.origen`, `monu.identificador_operacion`. Columnas nuevas en `auditoria`: `origen TEXT`, `identificador_operacion TEXT`. Datos automáticos: `operacion`, `clave`, `antes`, `despues`, `campos_modificados`; acciones `DATOS_INSERTADOS`, `DATOS_MODIFICADOS`, `DATOS_ELIMINADOS` si aplica mantenimiento.

- [x] Escribir pruebas de SQL directo, ambas imágenes, claves compuestas, redacción y rollback; demostrar fallo con esquema anterior.
- [x] Implementar triggers y cobertura explícita de tablas/campos, sin recursión sobre auditoría.
- [x] Incorporar protección de borrado operativo y de modificación del log, con mantenimiento únicamente administrativo, sin bypass expuesto por la aplicación.
- [x] Probar escritura normal, baja/reactivación y prohibición de operaciones destructivas.

## Tarea 3: Contexto de transacción y eventos existentes

Archivos: `core/db.py`, `core/dependencias.py`, `core/auditoria.py`, módulo de contexto propio en core si corresponde, dependencias/auth de usuarios y procesamiento/presentación de WhatsApp; esquemas de auditoría y pruebas `test_contexto_auditoria.py`.

Interfaz: configurar los cuatro GUC de tarea 2 con `set_config(..., true)` por transacción; actor validado antes de cualquier DML atribuible. Consulta de auditoría incluye las columnas nuevas.

- [x] Escribir y ejecutar pruebas de contexto HTTP, sesión, login, worker, rollback y aislamiento.
- [x] Implementar propagación de contexto sin estado global mutable compartido ni importaciones de capacidades desde core.
- [x] Hacer que eventos de negocio hereden contexto manteniendo las llamadas existentes compatibles.
- [x] Verificar arquitectura y errores HTTP.

## Tarea 4: Recuperación, filtros administrativos e integración

Archivos: casos de uso/esquemas/routers afectados de pedidos, usuarios, stock y notificaciones; consumidores administrativos existentes en frontend cuando sea necesario; tests HTTP/de servicio.

- [x] Verificar bajas/reactivaciones existentes y recuperación de ítems con el flujo versionado de edición, autorizaciones y validaciones.
- [x] Hacer que listados ordinarios excluyan inactivos y gestión los solicite explícitamente.
- [x] Mantener consulta de auditoría y acceso a imágenes/contexto; aplicar skill UI local a cambios de frontend.
- [x] Probar sin alterar ni eludir invariantes y revisar con un agente independiente el diff completo.

## Tarea 5: Verificación y documentación

- [x] Migrar base descartable vacía y verificar actualización desde 028 con datos.
- [x] Ejecutar pruebas focalizadas y suite backend; informar resultados y omisiones reales.
- [x] Ejecutar ruff, pruebas de arquitectura y, si cambia frontend, lint/build y verificación del recorrido.
- [x] Regenerar DER/diccionario; documentar cobertura, mantenimiento y despliegue en documentos dueños.
- [x] Verificar enlaces, diff y estado; no aplicar nada en nube ni hacer commit/push.

## Decisiones de ejecución

- Ejecución continua en el checkout del usuario, conservando cambios existentes; sin cambios de rama ni commits por rutina.
- Se delegan áreas sin archivos compartidos y se revisa su integración al terminar.
- Los tests que precisan PostgreSQL usan una instancia local nueva, con DATABASE_URL explícita.

## Evidencia final (28/10/2026)

- Base local nueva `monu_entrega_final`: migraciones 001?030 y seed; suite backend **1269 passed**, sin omisiones, una advertencia heredada de AnyIO.
- Frontend: **191 passed** en validaciones con concurrencia limitada; lint y build aprobados (dos advertencias heredadas de Fast Refresh).
- Revisi?n independiente sin hallazgos cr?ticos/importantes pendientes; privacidad de identificadores de demo corregida.
- DER/diccionario regenerados y contrastados con SQL; enlaces locales y diff comprobados.
- Migraci?n desde 028 con datos comprobada; no se modific? la base compartida.
- La comprobaci?n visual en un navegador real qued? sin ejecutar: el plugin no tiene navegador conectado.

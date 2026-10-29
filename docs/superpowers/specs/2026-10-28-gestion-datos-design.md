# Gestión de datos: bajas lógicas, auditoría y trazabilidad

Fecha: 28/10/2026. Estado: enfoque de auditoría automática en PostgreSQL elegido
por el usuario; implementación en curso, sin cambios aplicados a la base compartida.

## Objetivo y criterio de aceptación

Aplicar los cuatro puntos de la diapositiva del profesor a Monu Burger:
conservar registros operativos, realizar bajas recuperables, registrar automáticamente
los valores anteriores y nuevos, y poder identificar quién actuó, cuándo y desde dónde.
El pedido comprende los cuatro puntos; este documento propone cómo implementarlos.

## Evidencia actual

- `app/errores.py` y los manejadores HTTP no requieren cambios por este pedido.
- Usuarios y clientes tienen `estado`; catálogo, ingredientes, direcciones, zonas,
  puntos de encuentro, promociones y plantillas tienen banderas de actividad.
- Hay eliminaciones físicas en el reemplazo de recetas, los permisos por rol y
  la retirada de líneas de pedidos. Las migraciones existentes también contienen
  operaciones históricas de limpieza: deben permanecer inmutables.
- El catálogo aplica `solo_activos=True` por defecto. Otros listados permiten
  omitir el filtro de actividad. Esa diferencia debe resolverse de forma explícita.
- `core/auditoria.py` registra eventos en la transacción de cada caso de uso;
  cada llamador decide qué datos envía. No garantiza imágenes anteriores y nuevas.
- Permisos, roles y estados/composición de pedidos ya conservan algunos cambios.
- `auditoria` ya tiene usuario, fecha, entidad, acción, datos JSON e IP opcional.
- `core/dependencias.py` ofrece una unidad de trabajo por request. La sesión vigente
  se verifica en `usuarios/presentation/dependencias.py`. El worker de WhatsApp abre
  sus propias transacciones y también necesita contexto de auditoría.

## Enfoques considerados

1. **Backend y PostgreSQL, recomendado por el agente.** El backend mantiene reglas,
   bajas y consultas; triggers registran automáticamente los cambios confirmados en
   las tablas operativas. Incluye escrituras de scripts. Requiere migraciones nuevas,
   contexto transaccional y pruebas reales con PostgreSQL.
2. **Solo backend.** Ampliar las llamadas a auditoría en los casos de uso y reemplazar
   las eliminaciones. Menos lógica SQL, pero una escritura directa o una nueva operación
   que olvide invocar el helper queda fuera del registro automático.

El diseño corresponde al enfoque híbrido, elegido por el usuario después de explicarle
las dos opciones. Se conserva PostgreSQL con SQL directo, FastAPI y
el frontend actual; no se agrega un ORM ni se cambia la arquitectura por capacidades.

## Bajas lógicas y recuperación

- Reutilizar `activo`, `activa` y `estado` donde ya expresan la baja/reactivación.
  No agregar `deleted_at` a esas entidades solo para renombrar el mecanismo.
- Agregar `eliminado_en TIMESTAMPTZ NULL` a `pedido_item`, `producto_ingrediente`,
  `producto_variante_ingrediente` y `rol_permiso`: son las tablas que hoy se eliminan
  al editar operaciones. Las filas existentes comienzan vigentes.
- Retirar un ítem marca su fecha de baja y conserva sus opciones y snapshot de receta.
  Todas las consultas operativas de sus opciones parten de un ítem vigente.
- El reemplazo de una receta da de baja las relaciones retiradas. Las relaciones que
  permanecen se actualizan; una relación previamente retirada se reactiva mediante
  upsert sobre su clave actual. La auditoría conserva las cantidades anteriores.
- Los permisos revocados se marcan dados de baja; las concesiones usan upsert para
  reactivar la misma clave. La autorización lee únicamente concesiones vigentes.
- No convertir cancelaciones de pedidos, pagos anulados, alertas resueltas o viajes
  terminados en filas invisibles: sus estados son historial operativo y financiero.
- Recuperar un registro implica reactivar la bandera o relación mediante el caso de
  uso autorizado, con sus mismas validaciones. No se ofrece restauración arbitraria
  de JSON ni un endpoint universal que pueda eludir stock, permisos o finanzas.
- La recuperación de un ítem retirado se incorpora a la edición versionada del pedido:
  solo mientras su estado admite edición, verificando pertenencia, receta/snapshot,
  disponibilidad, totales y efectos de stock igual que una edición actual.
- Los identificadores y referencias históricas se conservan. El trabajo no reconstruye
  filas ya borradas antes de esta migración ni inventa valores anteriores inexistentes.

## Consultas y consumidores

- Los listados ordinarios usan registros vigentes por defecto. Los listados de gestión
  pueden solicitar explícitamente inactivos o todos, sujetos a permisos existentes.
- Centralizar los filtros dentro de las consultas de repositorio y funciones SQL que
  cada capacidad utiliza. No intentar reescribir SQL arbitrario desde la unidad de trabajo.
- Revisar recetas, costos/disponibilidad, stock, detalle de pedidos, edición, reportes,
  WhatsApp y autorización: una fila retirada no puede volver a contar por un JOIN.
- Las consultas de historial pueden mostrar referencias inactivas para conservar el
  significado de operaciones anteriores; no se filtra globalmente su entidad referida.
- Ajustar consumidores administrativos que dependan de recibir inactivos implícitamente.
  Conservar sus acciones de reactivación y los filtros visibles. La consulta de auditoría
  debe exponer las imágenes anterior/nueva y el contexto, manteniendo el permiso actual.
- Si faltan controles para consultar/reactivar las bajas ya gestionables, incorporarlos
  en las pantallas existentes, con etiquetas claras, teclado y mensajes de validación.
  El alcance visual se limita a esos recorridos; se aplica la skill local de UI/UX.

## Auditoría automática

- Mantener `auditoria` y los eventos de negocio actuales. Añadir `origen` e
  `identificador_operacion` opcionales, y distinguir acciones automáticas de cambios
  de fila de los eventos de negocio, para no sumar un mismo evento dos veces.
- Los cambios automáticos guardan en `datos` la operación, clave primaria completa,
  valores `antes`/`despues` y campos modificados. Las claves compuestas se representan
  estructuradamente; no se asume que toda tabla tenga una columna `id`.
- En un alta `antes` es nulo; una baja lógica es un UPDATE auditable; la reactivación
  también deja ambas imágenes. Un UPDATE sin cambios relevantes no duplica eventos.
- Triggers de fila AFTER INSERT/UPDATE registran el estado persistido en la misma
  transacción: un rollback revierte tanto el cambio como su auditoría.
- Cobertura operativa: usuarios/clientes/repartidores y datos de entrega; catálogo,
  recetas, ingredientes, movimientos y alertas; pedidos y sus relaciones e historial;
  promociones; viajes/envíos; pagos/cierres; parámetros; acceso por rol; plantillas y
  notificaciones; atención/cambios/comprobantes y borradores comerciales de WhatsApp.
- El registro automático no se aplica a `auditoria`, `schema_migrations`, archivos de
  demostración ni colas/sesiones técnicas. Las transacciones de esos procesos que
  escriban entidades operativas sí quedan auditadas en las tablas correspondientes.
- Definir una lista explícita de campos auditables por tabla. No copiar filas completas
  sin selección: excluir hashes/contraseñas, tokens, cookies, credenciales, binarios,
  cuerpos HTTP/proveedor y JSON libre que pueda transportar secretos. Registrar cambios
  de credenciales como evento sin su valor. Las pruebas comprueban estas exclusiones.
- No modificar ni borrar auditoría mediante la aplicación. Los triggers y las políticas
  de base deben impedir DELETE/TRUNCATE ordinarios de registros operativos e impedir
  alterar el log. Un propietario/superusuario puede desactivar protecciones: este diseño
  no presenta el registro como resistente a un administrador de PostgreSQL malicioso.
- Las purgas temporales o normativas son mantenimiento separado, fuera de los endpoints
  ordinarios. No crear una bandera de request que permita saltarse la conservación.

## Usuario, fecha y origen

- El backend propaga usuario validado, IP normalizada, canal y un identificador generado
  por el servidor. La sesión vigente es la autoridad; no se acepta un usuario enviado
  en un encabezado para atribuir cambios.
- Instalar contexto con `set_config(..., true)` en cada transacción antes de escribir.
  Actualizar el actor tras validar sesión o completar un login. No guardar contexto de
  usuario a nivel de conexión reutilizable ni conservarlo entre requests concurrentes.
- Registrar fecha de base con zona horaria. Identificar canales HTTP, worker WhatsApp,
  chat demostrativo y scripts. Procesos automáticos llevan usuario nulo y un origen
  identificable; una acción automática no debe atribuirse a un empleado ficticio.
- Scripts/SQL directo sin contexto de aplicación registran identidad de sesión de
  PostgreSQL y origen SQL, con usuario de aplicación nulo. Nunca heredan el actor anterior.
- La IP es opcional para procesos sin cliente HTTP. Conservar la política de proxy del
  despliegue y documentar la procedencia; una cabecera del cliente no demuestra identidad.
- El helper de eventos de negocio usa ese contexto si el llamador no pasa los datos.
  Incorporar sus nuevos campos a las respuestas y a la consulta de auditoría existente.

## Migración, verificación y entrega

- Agregar migraciones después de la última disponible (hoy `028`), sin editar las previas.
  Primero compatibilidad de esquema/contexto, luego filtros y bajas, y finalmente las
  protecciones contra borrado cuando los escritores ya no dependan de DELETE.
- Las pruebas que limpian mediante DELETE no pueden requerir desactivar protecciones
  desde el backend: usar rollback o una base/esquema descartable por ejecución. Cualquier
  limpieza administrativa de tests se limita expresamente a esa base descartable.
- Probar migración desde base vacía y actualización desde el esquema anterior con datos.
  Verificar restricciones, claves compuestas, doble baja/reactivación, concurrencia,
  idempotencia y que los privilegios revocados no se mantengan por registros históricos.
- Probar auditoría INSERT/UPDATE, baja/reactivación, ausencia de cambios, rollback,
  escrituras directas, campos sensibles y aislamiento del contexto entre conexiones.
- Probar recuperación autorizada y rechazos por estado/rol, edición de recetas y pedidos,
  totales, stock, reportes, permisos y los recorridos HTTP/worker afectados.
- Ejecutar pruebas de arquitectura, lint y suite backend con PostgreSQL descartable;
  lint/build y recorridos de navegador para los cambios administrativos que resulten necesarios.
- Regenerar `docs/DER.md` y `docs/DICCIONARIO_DATOS.md`; documentar contratos definitivos,
  cobertura/excepciones de auditoría y comandos de migración en sus documentos dueños.
- No conectar ni aplicar migraciones en la base compartida durante este trabajo.
  Preparar y verificar los cambios localmente; informar si falta un entorno descartable.
- No crear commits, cambiar de rama ni publicar por rutina. Informar pruebas efectivas,
  omisiones, migraciones pendientes y límites reales sin afirmar que la nube ya cambió.

## Referencias técnicas

- [Triggers de PostgreSQL 16: OLD, NEW y operaciones](https://www.postgresql.org/docs/16/plpgsql-trigger.html).
- [Configuración por transacción con set_config](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-ADMIN-SET).
- Arquitectura vigente: [ARQUITECTURA.md](../../ARQUITECTURA.md).
- Reglas de pedidos: [OPERACION_PEDIDOS.md](../../OPERACION_PEDIDOS.md).
- Coordinación de base compartida: [GUIA_EQUIPO.md](../../GUIA_EQUIPO.md).

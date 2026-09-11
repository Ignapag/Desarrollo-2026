# CAMBIOS — Sistema de Gestión Monu Burger

Registro de todo lo incorporado al proyecto y de las correcciones aplicadas al
modelo de datos respecto del diagrama entidad-relación entregado en
`Stack_Tecnologico_Monu_Burger.pdf`.

Última actualización: 01/09/2026 · Grupo 19 · Seminario Integrador 2026

---

El diagrama actualizado, generado del esquema real, está en
**[DER.md](DER.md)**.

## 1. Correcciones al diagrama entidad-relación

Al contrastar el ER entregado contra el alcance de la Actividad N°2 aparecieron
9 huecos que impedían implementar requisitos ya comprometidos con el cliente.
Cada uno tiene un identificador (C-xx) que está citado como comentario en el
archivo SQL donde se resuelve, para poder rastrear el cambio desde el código.

| ID | Problema detectado en el ER | Corrección aplicada | RF afectado | Archivo |
|----|-----------------------------|---------------------|-------------|---------|
| **C-01** | No existía dónde guardar los ingredientes opcionales elegidos por el cliente: `DETALLEPEDIDO` solo tenía cantidad. | Se agregan `producto_opcion` (opcionales configurables por producto, con costo adicional) y `pedido_item_opcion` (los que el cliente eligió efectivamente). | RF-03 | `002`, `003` |
| **C-02** | Stock duplicado: `PRODUCTO.stock` y `INGREDIENTE.cantidadActual` convivían sin regla de precedencia. | Se **elimina** `producto.stock`. El stock vive solo en `ingrediente`; la disponibilidad del producto se deriva con la vista `producto_disponible`. | RF-07 | `002` |
| **C-03** | Sin costo de insumos ni cantidad por receta, la rentabilidad no era calculable. | `ingrediente.costo_unitario` + `producto_ingrediente.cantidad_requerida` y `es_base`. Vista `producto_costo` con margen estimado. | RF-09 | `002` |
| **C-04** | Las zonas de cobertura eran un simple atributo texto dentro de `ENVIO`. | Nuevas entidades `zona_cobertura` (polígono GeoJSON) y `punto_encuentro`, más la función `punto_en_zona()` para validar la dirección. | RF-12 | `001` |
| **C-05** | Sin coordenadas no hay "asignación por cercanía": las direcciones eran solo calle/número/CP. | `direccion` pasa a ser entidad propia con `lat`/`lng` y zona resuelta; `repartidor` guarda su última posición; función `distancia_km()` (haversine). | RF-04, RF-12 | `001`, `004` |
| **C-06** | `ENVIO` era 1:1 con `PEDIDO`, imposible representar la regla "cada repartidor sale con 2 pedidos". | Nueva entidad `viaje` que agrupa envíos, con trigger que impone el máximo configurable (`delivery.pedidos_por_viaje`). También se agrega `movimiento_stock` para el historial de consumos y reposiciones. | RF-04, RF-07 | `004`, `002` |
| **C-07** | Solo se guardaba el estado actual del pedido; el alcance pide timestamp de **cada** cambio y el empleado que lo hizo. | Nueva tabla `pedido_estado_historial`. | RF-01, RNF-09 | `003` |
| **C-08** | `HISTORIALACTIVIDAD` guardaba solo texto libre (usuario, acción, fecha). | `auditoria` incorpora `entidad`, `entidad_id`, `datos` (jsonb) e `ip`, para poder consultar el log por objeto afectado. | RNF-09 | `001` |
| **C-09** | `CLIENTE` era una entidad suelta sin credenciales, pero el alcance exige que el cliente inicie sesión, siga su pedido y vea su historial. | `cliente` pasa a ser subtipo de `usuario` (rol `CLIENTE`), con `telefono_whatsapp` propio. Un único camino de autenticación para todos los actores. | RF-13, RNF-03 | `001` |
| **C-10** | No existía ninguna entidad de descuentos ni promociones. | Nuevas `promocion` y `pedido_promocion`. | RF-14 | `003` |
| **C-11** | Las devoluciones no tenían dónde registrarse como egreso. | `pago.tipo` (`COBRO` / `DEVOLUCION`) con referencia al pedido original, sin crear una tabla aparte. | RF-06, RF-08 | `005` |
| **C-12** | El bot no tenía plantillas configurables ni registro de envíos, exigidos por el módulo y por el RNF-10 (30 s). | Nuevas `notificacion_plantilla` y `notificacion`, más la vista `notificacion_latencia` que mide el cumplimiento del RNF-10. | RF-10, RNF-10 | `006` |

### Decisiones de modelado que conviene registrar en el informe

- **Sin PostGIS.** El stack declarado no lo incluye, así que la validación de
  zona (`punto_en_zona`, ray casting sobre GeoJSON) y la distancia
  (`distancia_km`, haversine) se resuelven con funciones SQL propias. Alcanza
  para el volumen de Ensenada / El Dique / Punta Lara.
- **Precios congelados.** `pedido_item` guarda `nombre_producto` y
  `precio_unitario` al momento de confirmar. Un cambio de precio en el menú no
  altera pedidos ni reportes históricos (el alcance exige que los períodos
  cerrados sean de solo lectura).
- **Estados del pedido.** A los cinco del alcance (pendiente, en preparación,
  listo, en camino, entregado) se suman `CONFIRMADO` —necesario para el plazo
  de cancelación de 5 minutos— y `CANCELADO`.
- **Reglas de negocio en la base.** El límite de 2 pedidos por viaje, la
  inmutabilidad del pago conciliado y la del cierre de caja aprobado se
  implementan como triggers, además de validarse en la capa de aplicación: son
  reglas que no deben poder violarse ni siquiera desde DBeaver.
- **Enums como CHECK.** Se usan restricciones `CHECK` sobre `TEXT` en lugar de
  tipos `ENUM` nativos: agregar un método de pago nuevo no requiere `ALTER TYPE`.

---

## 2. Estructura del proyecto

```
App/
├── db/
│   ├── migrations/           6 archivos .sql versionados
│   └── seed.sql              datos de desarrollo
├── backend/                  API FastAPI (monolito modular, Clean Architecture)
│   ├── app/
│   │   ├── core/             configuración, pool de BD, errores, dependencias
│   │   ├── modules/          un subpaquete por módulo del sistema
│   │   └── main.py
│   ├── scripts/              migrate.py y diccionario.py
│   └── tests/
├── docker-compose.yml
└── .env.example

docs/
├── CAMBIOS_DER.md            este documento
├── DICCIONARIO_DATOS.md      referencia del esquema (generada del SQL)
└── GUIA_EQUIPO.md            trabajo en grupo sobre la base compartida
```

Cada módulo respeta las cuatro capas del stack declarado:

| Capa | Dónde vive | Regla |
|------|-----------|-------|
| Presentación | `presentation/router.py`, `esquemas.py` | Solo traduce HTTP ↔ casos de uso. Pydantic vive acá. |
| Aplicación | `application/servicio_*.py` | Orquesta reglas y transacciones. No importa FastAPI ni psycopg. |
| Dominio | `domain/entidades.py`, `repositorios.py` | Entidades y reglas puras. Sin dependencias externas. |
| Infraestructura | `infrastructure/repositorio_sql.py` | SQL directo con psycopg. Único lugar con consultas. |

---

## 3. Lo implementado

### Base de datos (`App/db/migrations/`)

| Archivo | Contenido |
|---------|-----------|
| `001_usuarios_y_seguridad.sql` | `usuario`, `repartidor`, `cliente`, `zona_cobertura`, `punto_encuentro`, `direccion`, `auditoria`, `parametro`, función `punto_en_zona()` |
| `002_catalogo_y_stock.sql` | `categoria`, `ingrediente`, `producto`, `producto_ingrediente`, `producto_opcion`, `movimiento_stock`, `alerta_stock`, vistas `producto_costo` y `producto_disponible` |
| `003_pedidos.sql` | `pedido`, `pedido_item`, `pedido_item_opcion`, `pedido_estado_historial`, `promocion`, `pedido_promocion` |
| `004_delivery.sql` | `viaje`, `envio`, trigger de capacidad, función `distancia_km()` |
| `005_pagos_y_caja.sql` | `cierre_caja`, `pago`, triggers de inmutabilidad |
| `006_notificaciones.sql` | `notificacion_plantilla`, `notificacion`, vista `notificacion_latencia` |

El seed carga los 6 integrantes del grupo como usuarios, 2 repartidores, 1
cliente, las 3 zonas de reparto relevadas, 10 ingredientes con sus días de
reposición reales (papas los miércoles; carne y pan martes, jueves y sábados),
6 productos con receta y opcionales, y las 4 plantillas del bot.

**Contraseña de todos los usuarios de desarrollo: `Monu2026!`**
(`admin` / `ipagotto` / `jsantoro` / `erivero` / `jmartinez` / `nleguizamon` /
`taramburu` / `mdelivery` / `ldelivery` / `acliente`)

### Módulos de otros integrantes

Durante una etapa previa se prototiparon los módulos de
Usuarios y Seguridad, Control de Stock, Menú Web Dinámico y el frontend.
**Se eliminaron**: según el plan de tareas por responsable no corresponden a
mi parte del proyecto. Lo único que sobrevive de ese trabajo es el esquema de
base de datos, que sí es responsabilidad mía y da soporte a todos los módulos.

### Infraestructura

`docker-compose.yml` con PostgreSQL 16 y el backend; n8n queda en el perfil
opcional `bot` (`docker compose --profile bot up`).

### Pruebas

No hay pruebas todavía: las que existían cubrían módulos que se eliminaron.
Las próximas son las de integridad del esquema y las del algoritmo de
asignación de repartidores.

### Correcciones sobre lo entregado antes

| Qué | Por qué |
|-----|---------|
| `abrir_pool()` ya no bloquea el arranque | La API no levantaba sin PostgreSQL y moría a los 30 s. Ahora arranca y `/api/salud` informa `degradado`. |
| Timeout del pool: 30 s → 5 s (`DB_TIMEOUT_CONEXION`) | Los errores de base se manifestaban demasiado tarde. |
| Base caída devuelve **503**, no 500 | Es indisponibilidad de infraestructura, no un bug del sistema. |
| Guarda de rol declarada antes de `UoW` en la firma del endpoint | FastAPI resuelve las dependencias en orden: con el servicio primero, un request **sin sesión** igual pedía conexión a la base antes de rechazarse. Queda anotado como convención para cuando se integre el módulo de seguridad. |

---

## 4. Cómo levantar el proyecto

Ver [GUIA_EQUIPO.md](GUIA_EQUIPO.md), que explica la conexión a la base
compartida del grupo, y [App/backend/README.md](../App/backend/README.md) para
los comandos.

---

## 5. Estado de verificación

| Ítem | Estado |
|------|--------|
| Backend compila e importa; `/api/salud` responde | ✅ verificado |
| `ruff check` limpio | ✅ verificado |
| Las 6 migraciones aplicadas contra PostgreSQL real | ✅ **verificado** |
| Seed cargado | ✅ verificado |
| Pruebas de integridad del esquema (27 pruebas) | ✅ **pasan** |

El esquema se aplicó sobre **PostgreSQL 17 en Supabase** (región São Paulo),
sin un solo error. Resultado: 27 tablas, 3 vistas, 5 funciones propias, 3
triggers, 47 claves foráneas y 68 índices.

Las pruebas de `tests/test_integridad_bd.py` verifican contra la base real que
las reglas de negocio del esquema se cumplen: rechazo de roles inválidos y
duplicados, delivery sin dirección, stock negativo, precio cero, el tope de 2
pedidos por viaje, la inmutabilidad del pago conciliado y del cierre aprobado,
las funciones `punto_en_zona()` y `distancia_km()`, y las vistas de costo y
disponibilidad. Cada prueba corre en una transacción que se revierte, así que
no ensucian la base compartida.

---

## 6. Próximos pasos sugeridos

Según el plan de tareas (ver [TAREAS_IGNACIO.md](TAREAS_IGNACIO.md)):

1. **Levantar PostgreSQL** y correr las migraciones + seed.
2. **Pruebas de integridad** del esquema: constraints, FKs, triggers y vistas.
3. **Algoritmo de agrupación geográfica** (Asignación de Repartidores).
4. **Lógica de asignación automática**: elegir el repartidor disponible más
   cercano y crear el viaje.
5. **Pruebas de asignación**. Para probarlo de punta a punta hacen falta pedidos
   confirmados: coordinar con quien tenga asignado el módulo de Pedidos.
6. Actualizar el **diagrama DER del informe** con las 12 correcciones de la
   sección 1.

---

## 7. Decisiones pendientes de confirmar con el cliente

- **Cierre de caja automático a las 00:00 y 14:30**: requiere un proceso
  programado. Se puede resolver con n8n (ya está en el stack) o con un
  scheduler dentro del backend. No está definido en el alcance.
- **Costo de envío por zona**: el modelo lo contempla (`zona_cobertura.costo_envio`),
  pero el relevamiento no menciona si Monu Burger cobra el delivery. Hoy queda en 0.
- **Autorregistro de clientes**: el alcance dice que el cliente consulta su
  historial, lo que implica cuenta. Falta confirmar si se acepta pedido sin
  registro (invitado) o si la cuenta es obligatoria. Hoy es obligatoria.
- **Propinas**: se modeló el campo en `pago` porque aparece en el detalle del
  módulo de Pagos, pero no surgió en la entrevista.
- **Agrupación de envíos**: la regla relevada es "cada repartidor sale con 2
  pedidos cercanos entre sí". Falta definir qué tan cercanos: un radio en km, o
  que compartan zona de cobertura. Hoy el tope de 2 está impuesto por trigger y
  el radio queda como parámetro del algoritmo.

# Diccionario de datos — Monu Burger

Referencia del esquema para todo el grupo: nombres exactos de tablas y
columnas, tipos, obligatoriedad, relaciones y valores permitidos.

> **Generado automáticamente** con `python -m scripts.diccionario` a partir
> de `App/db/migrations/`. No editar a mano: cada vez que se agrega una
> migración, volver a generarlo. CI verifica que este al dia.

## Reglas de uso

- Los nombres van en **español** y `snake_case`. Respetarlos tal cual: si tu
  módulo inventa nombres, la integración no cierra.
- Toda consulta va **parametrizada** (`%s`). Nunca interpolar valores.
- Los montos son `NUMERIC(12,2)` y las cantidades `NUMERIC(12,3)`: en Python
  llegan como `Decimal`, no como `float`.
- Las fechas son `TIMESTAMPTZ` (con zona horaria).
- **Nadie modifica una migración ya aplicada.** Si necesitás un cambio de
  esquema, pedilo: se agrega una migración nueva numerada.

## Índice de tablas

**Usuarios y seguridad** — [`usuario`](#usuario), [`repartidor`](#repartidor), [`cliente`](#cliente), [`zona_cobertura`](#zona_cobertura), [`punto_encuentro`](#punto_encuentro), [`direccion`](#direccion), [`auditoria`](#auditoria), [`parametro`](#parametro)

**Catalogo y stock** — [`categoria`](#categoria), [`ingrediente`](#ingrediente), [`producto`](#producto), [`producto_ingrediente`](#producto_ingrediente), [`producto_opcion`](#producto_opcion), [`movimiento_stock`](#movimiento_stock), [`alerta_stock`](#alerta_stock)

**Pedidos** — [`pedido`](#pedido), [`pedido_item`](#pedido_item), [`pedido_item_opcion`](#pedido_item_opcion), [`pedido_estado_historial`](#pedido_estado_historial), [`promocion`](#promocion), [`pedido_promocion`](#pedido_promocion)

**Delivery** — [`viaje`](#viaje), [`envio`](#envio)

**Pagos y caja** — [`cierre_caja`](#cierre_caja), [`pago`](#pago)

**Notificaciones** — [`notificacion_plantilla`](#notificacion_plantilla), [`notificacion`](#notificacion)

**Parametros delivery** — sin tablas nuevas

**Funciones geo float** — sin tablas nuevas

**Menu emilio** — sin tablas nuevas

**Stock ingredientes menu** — sin tablas nuevas

**Whatsapp** — [`whatsapp_borrador`](#whatsapp_borrador), [`whatsapp_entrada`](#whatsapp_entrada), [`whatsapp_salida`](#whatsapp_salida), [`whatsapp_cambio`](#whatsapp_cambio), [`whatsapp_comprobante`](#whatsapp_comprobante)

**Whatsapp estados envio** — [`whatsapp_estado_envio`](#whatsapp_estado_envio)

**Whatsapp saldo transferencia** — sin tablas nuevas

**Whatsapp atencion** — [`whatsapp_atencion`](#whatsapp_atencion)

**Clientes sin cuenta** — sin tablas nuevas

**Contacto checkout** — sin tablas nuevas

**Whatsapp mensajes amigables** — sin tablas nuevas

**Whatsapp contexto chat** — [`whatsapp_sesion`](#whatsapp_sesion)

**Whatsapp memoria ia** — sin tablas nuevas

**Operacion segura** — sin tablas nuevas

**Mensajes operacion segura** — sin tablas nuevas

**Saldo operativo transferencia** — sin tablas nuevas

Total: **35 tablas**.

---

## 001_usuarios_y_seguridad — Usuarios y seguridad

### usuario

_usuario: unifica a TODOS los actores con credenciales del sistema. Cambio respecto del ER original: CLIENTE pasa a ser un subtipo de USUARIO (antes era una entidad suelta sin credenciales), porque el alcance exige que el cliente inicie sesion, siga su pedido y consulte su historial de pedidos. Ver CAMBIOS.md (C-09)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `nombre` | TEXT | Sí | — |
| `apellido` | TEXT | Sí | — |
| `username` | CITEXT | Sí | único |
| `email` | CITEXT | No | único |
| `telefono` | TEXT | No | — |
| `password_hash` | TEXT | Sí | — |
| `rol` | TEXT | Sí | valores: `ADMINISTRADOR`, `DUENIO`, `EMPLEADO`, `REPARTIDOR`, `CLIENTE` |
| `estado` | TEXT | Sí | valores: `ACTIVO`, `INACTIVO` · default `'ACTIVO'` |
| `fecha_alta` | TIMESTAMPTZ | Sí | default `now()` |
| `actualizado_en` | TIMESTAMPTZ | Sí | default `now()` |
| `ultimo_acceso` | TIMESTAMPTZ | No | — |

### repartidor

_repartidor: atributos propios del subtipo REPARTIDOR. Se agregan coordenadas de ultima posicion conocida para poder resolver la asignacion "por cercania" que pide RF-04. Ver CAMBIOS.md (C-05)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `usuario_id` | BIGINT | Sí | PK · FK → `usuario.id` |
| `estado` | TEXT | Sí | valores: `DISPONIBLE`, `EN_RUTA`, `FUERA_DE_SERVICIO` · default `'DISPONIBLE'` |
| `vehiculo` | TEXT | No | — |
| `ultima_lat` | NUMERIC(9,6) | No | — |
| `ultima_lng` | NUMERIC(9,6) | No | — |
| `ultima_pos_en` | TIMESTAMPTZ | No | — |

### cliente

_cliente: atributos propios del subtipo CLIENTE._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `usuario_id` | BIGINT | No | único · FK → `usuario.id` |
| `telefono_whatsapp` | TEXT | Sí | — |
| `acepta_notif_wsp` | BOOLEAN | Sí | default `TRUE` |
| `notas` | TEXT | No | — |
| `id` | BIGINT | Sí | PK · default `nextval('cliente_id_seq')` |
| `nombre` | TEXT | Sí | default `'Cliente'` |
| `estado` | TEXT | Sí | valores: `ACTIVO`, `INACTIVO` · default `'ACTIVO'` |
| `whatsapp_verificado` | TEXT | No | único |
| `telefono_contacto` | TEXT | No | — |

### zona_cobertura

_zona_cobertura: entidad nueva. El ER solo tenia un atributo "zona" dentro de ENVIO, insuficiente para validar direcciones (RF-12). El poligono se guarda como GeoJSON en jsonb para dibujarlo con Leaflet y validar el punto con punto_en_zona(). Ver CAMBIOS.md (C-04)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `nombre` | TEXT | Sí | único |
| `descripcion` | TEXT | No | — |
| `poligono` | JSONB | Sí | — |
| `centro_lat` | NUMERIC(9,6) | Sí | — |
| `centro_lng` | NUMERIC(9,6) | Sí | — |
| `costo_envio` | NUMERIC(12,2) | Sí | default `0` |
| `activa` | BOOLEAN | Sí | default `TRUE` |

### punto_encuentro

_punto_encuentro: puntos intermedios propuestos para pedidos fuera de zona, tal como opera hoy el negocio (RF-12)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `nombre` | TEXT | Sí | — |
| `referencia` | TEXT | No | — |
| `lat` | NUMERIC(9,6) | Sí | — |
| `lng` | NUMERIC(9,6) | Sí | — |
| `zona_id` | BIGINT | No | FK → `zona_cobertura.id` |
| `activo` | BOOLEAN | Sí | default `TRUE` |

### direccion

_direccion: se normaliza como entidad propia (el ER la tenia como atributo compuesto repetido en CLIENTE y en PEDIDO) y se le agregan coordenadas + zona resuelta. Ver CAMBIOS.md (C-05)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `cliente_id` | BIGINT | Sí | FK → `cliente.id` |
| `calle` | TEXT | Sí | — |
| `numero` | TEXT | Sí | — |
| `piso_depto` | TEXT | No | — |
| `codigo_postal` | TEXT | No | — |
| `localidad` | TEXT | No | — |
| `referencia` | TEXT | No | — |
| `lat` | NUMERIC(9,6) | No | — |
| `lng` | NUMERIC(9,6) | No | — |
| `zona_id` | BIGINT | No | FK → `zona_cobertura.id` |
| `es_principal` | BOOLEAN | Sí | default `FALSE` |
| `activa` | BOOLEAN | Sí | default `TRUE` |
| `creada_en` | TIMESTAMPTZ | Sí | default `now()` |

### auditoria

_auditoria: implementa HISTORIALACTIVIDAD del ER y el RNF-09. Se agregan entidad / entidad_id / datos para que el log sea consultable por objeto afectado y no solo por texto libre. Ver CAMBIOS.md (C-08)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `usuario_id` | BIGINT | No | FK → `usuario.id` |
| `accion` | TEXT | Sí | — |
| `entidad` | TEXT | Sí | — |
| `entidad_id` | TEXT | No | — |
| `datos` | JSONB | No | — |
| `ip` | INET | No | — |
| `creado_en` | TIMESTAMPTZ | Sí | default `now()` |

### parametro

_parametro: parametros globales del negocio (horarios de turno, minutos de cancelacion, umbral de notificaciones, etc.)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `clave` | TEXT | Sí | PK |
| `valor` | TEXT | Sí | — |
| `descripcion` | TEXT | No | — |
| `actualizado_en` | TIMESTAMPTZ | Sí | default `now()` |
| `actualizado_por` | BIGINT | No | FK → `usuario.id` |

**Funciones:** `punto_en_zona`

## 002_catalogo_y_stock — Catalogo y stock

### categoria

_===================================================================== 002 - Catalogo (menu) y control de stock por ingrediente =====================================================================_

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `nombre` | TEXT | Sí | único |
| `orden` | INT | Sí | default `0` |
| `activa` | BOOLEAN | Sí | default `TRUE` |

### ingrediente

_ingrediente: unica fuente de verdad del stock. Cambio respecto del ER: se elimina PRODUCTO.stock (habia stock duplicado en dos entidades) y se agrega costo_unitario, sin el cual no se puede calcular la rentabilidad de RF-09. Ver CAMBIOS.md (C-02, C-03)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `nombre` | TEXT | Sí | único |
| `unidad_medida` | TEXT | Sí | valores: `KG`, `GR`, `LT`, `ML`, `UNIDAD` |
| `cantidad_actual` | NUMERIC(12,3) | Sí | default `0` |
| `umbral_minimo` | NUMERIC(12,3) | Sí | — |
| `costo_unitario` | NUMERIC(12,2) | Sí | default `0` |
| `dias_reposicion` | TEXT[] | Sí | default `'{}'` |
| `fecha_ultima_reposicion` | TIMESTAMPTZ | No | — |
| `responsable_id` | BIGINT | No | FK → `usuario.id` |
| `activo` | BOOLEAN | Sí | default `TRUE` |

### producto

_producto: sin columna stock. Su disponibilidad se deriva del stock de sus ingredientes base (ver vista producto_disponible mas abajo)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `categoria_id` | BIGINT | Sí | FK → `categoria.id` |
| `nombre` | TEXT | Sí | — |
| `descripcion` | TEXT | No | — |
| `precio_base` | NUMERIC(12,2) | Sí | — |
| `imagen_url` | TEXT | No | — |
| `activo` | BOOLEAN | Sí | default `TRUE` |
| `orden` | INT | Sí | default `0` |
| `creado_en` | TIMESTAMPTZ | Sí | default `now()` |
| `actualizado_en` | TIMESTAMPTZ | Sí | default `now()` |
| `variantes` | JSONB | Sí | default `'[]'::jsonb` |

Únicos: `(categoria_id, nombre)`

### producto_ingrediente

_producto_ingrediente: receta. cantidad_requerida es lo que faltaba para poder descontar stock automaticamente y calcular costo/rentabilidad. es_base = TRUE significa que sin ese ingrediente el producto no se puede vender (regla de desactivacion automatica del alcance). Ver CAMBIOS.md (C-03)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `producto_id` | BIGINT | Sí | PK · FK → `producto.id` |
| `ingrediente_id` | BIGINT | Sí | PK · FK → `ingrediente.id` |
| `cantidad_requerida` | NUMERIC(12,3) | Sí | — |
| `es_base` | BOOLEAN | Sí | default `TRUE` |

### producto_opcion

_producto_opcion: ingredientes opcionales que el cliente puede agregar o quitar, con su costo adicional. Entidad ausente en el ER original; sin ella RF-03 (personalizacion) no tiene donde persistirse. Ver CAMBIOS.md (C-01)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `producto_id` | BIGINT | Sí | FK → `producto.id` |
| `ingrediente_id` | BIGINT | Sí | FK → `ingrediente.id` |
| `tipo` | TEXT | Sí | valores: `AGREGADO`, `QUITADO` · default `'AGREGADO'` |
| `costo_adicional` | NUMERIC(12,2) | Sí | default `0` |
| `cantidad_requerida` | NUMERIC(12,3) | Sí | default `1` |
| `max_por_item` | INT | Sí | default `1` |
| `activo` | BOOLEAN | Sí | default `TRUE` |

Únicos: `(producto_id, ingrediente_id, tipo)`

### movimiento_stock

_movimiento_stock: trazabilidad de cada consumo, reposicion o ajuste. El ER solo tenia la relacion REPONE sin historial. Ver CAMBIOS.md (C-06)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `ingrediente_id` | BIGINT | Sí | FK → `ingrediente.id` |
| `tipo` | TEXT | Sí | valores: `CONSUMO`, `REPOSICION`, `AJUSTE`, `DEVOLUCION`, `MERMA` |
| `cantidad` | NUMERIC(12,3) | Sí | — |
| `saldo_resultante` | NUMERIC(12,3) | Sí | — |
| `pedido_id` | BIGINT | No | FK → `pedido.id` |
| `usuario_id` | BIGINT | No | FK → `usuario.id` |
| `motivo` | TEXT | No | — |
| `creado_en` | TIMESTAMPTZ | Sí | default `now()` |

### alerta_stock

_alerta_stock: alertas de reposicion (RF-07)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `ingrediente_id` | BIGINT | Sí | FK → `ingrediente.id` |
| `nivel` | TEXT | Sí | valores: `BAJO`, `AGOTADO` |
| `cantidad_al_generar` | NUMERIC(12,3) | Sí | — |
| `estado` | TEXT | Sí | valores: `ACTIVA`, `RESUELTA` · default `'ACTIVA'` |
| `generada_en` | TIMESTAMPTZ | Sí | default `now()` |
| `resuelta_en` | TIMESTAMPTZ | No | — |
| `resuelta_por` | BIGINT | No | FK → `usuario.id` |

**Vistas:** `producto_costo`, `producto_disponible`

## 003_pedidos — Pedidos

### pedido

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `numero` | BIGINT | Sí | único · default `nextval('pedido_numero_seq')` |
| `cliente_id` | BIGINT | Sí | FK → `cliente.id` |
| `tipo_entrega` | TEXT | Sí | valores: `DELIVERY`, `RETIRO` · default `'DELIVERY'` |
| `direccion_id` | BIGINT | No | FK → `direccion.id` |
| `punto_encuentro_id` | BIGINT | No | FK → `punto_encuentro.id` |
| `canal` | TEXT | Sí | valores: `WEB`, `WHATSAPP`, `MOSTRADOR` · default `'WEB'` |
| `estado` | TEXT | Sí | valores: `PENDIENTE`, `CONFIRMADO`, `EN_PREPARACION`, `LISTO`, `EN_CAMINO`, `ENTREGADO`, `CANCELADO` · default `'PENDIENTE'` |
| `subtotal` | NUMERIC(12,2) | Sí | default `0` |
| `costo_envio` | NUMERIC(12,2) | Sí | default `0` |
| `descuento_total` | NUMERIC(12,2) | Sí | default `0` |
| `total` | NUMERIC(12,2) | Sí | default `0` |
| `observaciones` | TEXT | No | — |
| `hora_entrega_pedida` | TIMESTAMPTZ | No | — |
| `creado_en` | TIMESTAMPTZ | Sí | default `now()` |
| `confirmado_en` | TIMESTAMPTZ | No | — |
| `cancelable_hasta` | TIMESTAMPTZ | No | — |
| `entregado_en` | TIMESTAMPTZ | No | — |
| `cancelado_en` | TIMESTAMPTZ | No | — |
| `motivo_cancelacion` | TEXT | No | — |
| `version` | INT | Sí | default `1` |
| `metodo_pago_acordado` | TEXT | Sí | valores: `EFECTIVO`, `TRANSFERENCIA` · default `'EFECTIVO'` |
| `preparacion_en` | TIMESTAMPTZ | No | — |
| `listo_en` | TIMESTAMPTZ | No | — |

### pedido_item

_pedido_item: los precios se congelan al confirmar (snapshot), para que un cambio de precio en el menu no altere pedidos ni reportes historicos._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `pedido_id` | BIGINT | Sí | FK → `pedido.id` |
| `producto_id` | BIGINT | Sí | FK → `producto.id` |
| `nombre_producto` | TEXT | Sí | — |
| `cantidad` | INT | Sí | — |
| `precio_unitario` | NUMERIC(12,2) | Sí | — |
| `costo_opciones` | NUMERIC(12,2) | Sí | default `0` |
| `subtotal` | NUMERIC(12,2) | Sí | — |
| `aclaraciones` | TEXT | No | — |

### pedido_item_opcion

_pedido_item_opcion: personalizacion efectiva de cada item (RF-03). Entidad nueva. Ver CAMBIOS.md (C-01)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `pedido_item_id` | BIGINT | Sí | FK → `pedido_item.id` |
| `producto_opcion_id` | BIGINT | No | FK → `producto_opcion.id` |
| `ingrediente_id` | BIGINT | Sí | FK → `ingrediente.id` |
| `nombre_opcion` | TEXT | Sí | — |
| `tipo` | TEXT | Sí | valores: `AGREGADO`, `QUITADO` |
| `cantidad` | INT | Sí | default `1` |
| `costo_adicional` | NUMERIC(12,2) | Sí | default `0` |

### pedido_estado_historial

_pedido_estado_historial: el alcance exige timestamp de CADA cambio de estado y el usuario que lo hizo; el ER solo guardaba el estado actual. Ver CAMBIOS.md (C-07)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `pedido_id` | BIGINT | Sí | FK → `pedido.id` |
| `estado_anterior` | TEXT | No | — |
| `estado_nuevo` | TEXT | Sí | — |
| `usuario_id` | BIGINT | No | FK → `usuario.id` |
| `observacion` | TEXT | No | — |
| `creado_en` | TIMESTAMPTZ | Sí | default `now()` |
| `origen` | TEXT | Sí | default `'HISTORICO'` |
| `version` | INT | No | — |
| `cambios` | JSONB | No | — |
| `tratamiento_stock` | TEXT | No | — |

### promocion

_promocion / pedido_promocion: RF-14. Entidades ausentes en el ER. Ver CAMBIOS.md (C-10)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `nombre` | TEXT | Sí | — |
| `codigo` | CITEXT | No | único |
| `tipo` | TEXT | Sí | valores: `PORCENTAJE`, `MONTO_FIJO` |
| `valor` | NUMERIC(12,2) | Sí | — |
| `monto_minimo` | NUMERIC(12,2) | Sí | default `0` |
| `vigencia_desde` | DATE | No | — |
| `vigencia_hasta` | DATE | No | — |
| `activa` | BOOLEAN | Sí | default `TRUE` |
| `creada_por` | BIGINT | No | FK → `usuario.id` |
| `creada_en` | TIMESTAMPTZ | Sí | default `now()` |

### pedido_promocion

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `pedido_id` | BIGINT | Sí | PK · FK → `pedido.id` |
| `promocion_id` | BIGINT | Sí | PK · FK → `promocion.id` |
| `monto_descontado` | NUMERIC(12,2) | Sí | — |
| `aplicada_por` | BIGINT | No | FK → `usuario.id` |
| `aplicada_en` | TIMESTAMPTZ | Sí | default `now()` |

## 004_delivery — Delivery

### viaje

_===================================================================== 004 - Delivery: viajes (salidas) y envios ===================================================================== viaje: entidad nueva. La regla del negocio dice que cada repartidor sale con hasta 2 pedidos cercanos entre si; el ER tenia ENVIO 1:1 con PEDIDO y no podia representar esa agrupacion. Ver CAMBIOS.md (C-06)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `repartidor_id` | BIGINT | Sí | FK → `repartidor.usuario_id` |
| `estado` | TEXT | Sí | valores: `PLANIFICADO`, `EN_RUTA`, `FINALIZADO`, `CANCELADO` · default `'PLANIFICADO'` |
| `creado_en` | TIMESTAMPTZ | Sí | default `now()` |
| `salida_en` | TIMESTAMPTZ | No | — |
| `retorno_en` | TIMESTAMPTZ | No | — |
| `asignado_por` | BIGINT | No | FK → `usuario.id` |
| `asignacion_auto` | BOOLEAN | Sí | default `TRUE` |

### envio

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `pedido_id` | BIGINT | Sí | único · FK → `pedido.id` |
| `viaje_id` | BIGINT | No | FK → `viaje.id` |
| `zona_id` | BIGINT | No | FK → `zona_cobertura.id` |
| `punto_encuentro_id` | BIGINT | No | FK → `punto_encuentro.id` |
| `orden_en_viaje` | INT | Sí | default `1` |
| `estado` | TEXT | Sí | valores: `PENDIENTE`, `ASIGNADO`, `EN_CAMINO`, `ENTREGADO`, `FALLIDO` · default `'PENDIENTE'` |
| `distancia_km` | NUMERIC(8,3) | No | — |
| `asignado_en` | TIMESTAMPTZ | No | — |
| `en_camino_en` | TIMESTAMPTZ | No | — |
| `entregado_en` | TIMESTAMPTZ | No | — |
| `observaciones` | TEXT | No | — |

**Funciones:** `valida_capacidad_viaje`, `distancia_km`

**Triggers:** `envio_capacidad_trg`

## 005_pagos_y_caja — Pagos y caja

### cierre_caja

_===================================================================== 005 - Pagos, cierre de caja y conciliacion Modulo que resuelve el problema CRITICO relevado (cierre de caja manual) =====================================================================_

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `fecha` | DATE | Sí | — |
| `turno` | TEXT | Sí | valores: `MEDIODIA`, `NOCHE` |
| `abierto_en` | TIMESTAMPTZ | Sí | default `now()` |
| `cerrado_en` | TIMESTAMPTZ | No | — |
| `total_efectivo` | NUMERIC(12,2) | Sí | default `0` |
| `total_billeteras` | NUMERIC(12,2) | Sí | default `0` |
| `total_devoluciones` | NUMERIC(12,2) | Sí | default `0` |
| `total_general` | NUMERIC(12,2) | Sí | default `0` |
| `cantidad_pedidos` | INT | Sí | default `0` |
| `estado` | TEXT | Sí | valores: `ABIERTO`, `PENDIENTE_APROBACION`, `APROBADO` · default `'ABIERTO'` |
| `generado_por` | BIGINT | No | FK → `usuario.id` |
| `aprobado_por` | BIGINT | No | FK → `usuario.id` |
| `aprobado_en` | TIMESTAMPTZ | No | — |
| `observaciones` | TEXT | No | — |

Únicos: `(fecha, turno)`

### pago

_pago: se agrega tipo (COBRO / DEVOLUCION) para registrar el egreso con referencia al pedido original, como pide el alcance, sin crear una tabla aparte. Ver CAMBIOS.md (C-11)._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `pedido_id` | BIGINT | Sí | FK → `pedido.id` |
| `cierre_caja_id` | BIGINT | No | FK → `cierre_caja.id` |
| `tipo` | TEXT | Sí | valores: `COBRO`, `DEVOLUCION` · default `'COBRO'` |
| `metodo_pago` | TEXT | Sí | valores: `EFECTIVO`, `MERCADO_PAGO`, `CUENTA_DNI`, `NARANJA_X`, `OTRA_BILLETERA`, `TRANSFERENCIA` |
| `monto` | NUMERIC(12,2) | Sí | — |
| `propina` | NUMERIC(12,2) | Sí | default `0` |
| `estado` | TEXT | Sí | valores: `PENDIENTE`, `CONCILIADO`, `ANULADO` · default `'PENDIENTE'` |
| `referencia_externa` | TEXT | No | — |
| `registrado_por` | BIGINT | No | FK → `usuario.id` |
| `registrado_en` | TIMESTAMPTZ | Sí | default `now()` |
| `conciliado_en` | TIMESTAMPTZ | No | — |
| `motivo` | TEXT | No | — |
| `clave_operacion` | UUID | No | único |
| `datos_operacion` | JSONB | No | — |

**Funciones:** `protege_pago_conciliado`, `protege_cierre_aprobado`

**Triggers:** `pago_conciliado_trg`, `cierre_aprobado_trg`

## 006_notificaciones — Notificaciones

### notificacion_plantilla

_===================================================================== 006 - Notificaciones de WhatsApp (integracion n8n) Entidades ausentes en el ER: el modulo del bot exige plantillas configurables y timestamp de cada notificacion enviada (RNF-10: 30 s). Ver CAMBIOS.md (C-12). =====================================================================_

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `clave` | TEXT | Sí | único · valores: `BIENVENIDA`, `PEDIDO_CONFIRMADO`, `EN_CAMINO`, `ENTREGADO`, `ALERTA_STOCK`, `CIERRE_CAJA` |
| `nombre` | TEXT | Sí | — |
| `cuerpo` | TEXT | Sí | — |
| `activa` | BOOLEAN | Sí | default `TRUE` |
| `actualizado_por` | BIGINT | No | FK → `usuario.id` |
| `actualizado_en` | TIMESTAMPTZ | Sí | default `now()` |

### notificacion

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `plantilla_id` | BIGINT | No | FK → `notificacion_plantilla.id` |
| `clave` | TEXT | Sí | — |
| `destinatario` | TEXT | Sí | — |
| `cliente_id` | BIGINT | No | FK → `cliente.id` |
| `pedido_id` | BIGINT | No | FK → `pedido.id` |
| `cuerpo_renderizado` | TEXT | Sí | — |
| `canal` | TEXT | Sí | valores: `WHATSAPP`, `EMAIL`, `PANEL` · default `'WHATSAPP'` |
| `estado` | TEXT | Sí | valores: `PENDIENTE`, `ENVIADA`, `FALLIDA`, `DESCARTADA` · default `'PENDIENTE'` |
| `intentos` | INT | Sí | default `0` |
| `error` | TEXT | No | — |
| `creada_en` | TIMESTAMPTZ | Sí | default `now()` |
| `enviada_en` | TIMESTAMPTZ | No | — |

**Vistas:** `notificacion_latencia`

## 007_parametros_delivery — Parametros delivery

## 008_funciones_geo_float — Funciones geo float

**Funciones:** `distancia_km`, `punto_en_zona`

## 009_menu_emilio — Menu emilio

## 010_stock_ingredientes_menu — Stock ingredientes menu

## 011_whatsapp — Whatsapp

### whatsapp_borrador

_Borradores separados del pedido operativo y colas transaccionales del bot._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `referencia_hash` | TEXT | Sí | PK |
| `cliente_id` | BIGINT | No | FK → `cliente.id` |
| `telefono` | TEXT | No | — |
| `items` | JSONB | Sí | — |
| `tipo_entrega` | TEXT | No | valores: `RETIRO`, `DELIVERY` |
| `metodo_pago` | TEXT | No | valores: `EFECTIVO`, `TRANSFERENCIA` |
| `direccion` | JSONB | No | — |
| `estado` | TEXT | Sí | valores: `BORRADOR`, `VINCULADO`, `CREADO`, `HUMANO` · default `'BORRADOR'` |
| `estado_pago` | TEXT | Sí | valores: `PENDIENTE`, `APROBADO`, `RECHAZADO` · default `'PENDIENTE'` |
| `pedido_id` | BIGINT | No | único · FK → `pedido.id` |
| `version` | INT | Sí | default `1` |
| `propuesta` | JSONB | No | — |
| `creado_en` | TIMESTAMPTZ | Sí | default `now()` |
| `expira_en` | TIMESTAMPTZ | Sí | default `now() + interval '30 minutes'` |
| `ultimo_mensaje_en` | TIMESTAMPTZ | No | — |
| `contacto` | JSONB | Sí | default `'{}'::jsonb` |
| `inicio_hash` | TEXT | No | único |
| `contexto_chat` | JSONB | Sí | default `'{}'::jsonb` |

### whatsapp_entrada

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | TEXT | Sí | PK |
| `telefono` | TEXT | Sí | — |
| `texto` | TEXT | Sí | — |
| `media_id` | TEXT | No | — |
| `referencia_hash` | TEXT | No | FK → `whatsapp_borrador.referencia_hash` |
| `estado` | TEXT | Sí | valores: `PENDIENTE`, `PROCESADO` · default `'PENDIENTE'` |
| `respuesta` | TEXT | No | — |
| `creado_en` | TIMESTAMPTZ | Sí | default `now()` |
| `nombre_remitente` | TEXT | No | — |
| `memoria_ia` | JSONB | No | — |
| `orden_recibido` | BIGINT | No | autonumérico |

### whatsapp_salida

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `clave` | TEXT | Sí | único |
| `telefono` | TEXT | Sí | — |
| `texto` | TEXT | Sí | — |
| `estado` | TEXT | Sí | valores: `PENDIENTE`, `ENVIANDO`, `ACEPTADO`, `ENTREGADO`, `FALLIDO`, `INCIERTO`, `SIMULADO` · default `'PENDIENTE'` |
| `proveedor_id` | TEXT | No | único |
| `intentos` | INT | Sí | default `0` |
| `proximo_intento_en` | TIMESTAMPTZ | Sí | default `now()` |
| `actualizado_en` | TIMESTAMPTZ | Sí | default `now()` |
| `creado_en` | TIMESTAMPTZ | Sí | default `now()` |
| `atencion_id` | BIGINT | No | FK → `whatsapp_atencion.id` |
| `enviado_por` | BIGINT | No | FK → `usuario.id` |

### whatsapp_cambio

_Cambios propuestos, aplicados o derivados. La cocina lee pedido_item vigente._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `pedido_id` | BIGINT | Sí | FK → `pedido.id` |
| `version` | INT | Sí | — |
| `accion` | JSONB | Sí | — |
| `anterior` | JSONB | Sí | — |
| `posterior` | JSONB | No | — |
| `estado` | TEXT | Sí | valores: `APLICADO`, `PENDIENTE_EMPLEADO`, `RECHAZADO` |
| `revisado_por` | BIGINT | No | FK → `usuario.id` |
| `revisado_en` | TIMESTAMPTZ | No | — |
| `creado_en` | TIMESTAMPTZ | Sí | default `now()` |

### whatsapp_comprobante

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `entrada_id` | TEXT | Sí | único · FK → `whatsapp_entrada.id` |
| `pedido_id` | BIGINT | Sí | FK → `pedido.id` |
| `media_id` | TEXT | Sí | — |
| `estado` | TEXT | Sí | valores: `PENDIENTE`, `APROBADO`, `RECHAZADO` · default `'PENDIENTE'` |
| `revisado_por` | BIGINT | No | FK → `usuario.id` |
| `revisado_en` | TIMESTAMPTZ | No | — |
| `motivo` | TEXT | No | — |
| `creado_en` | TIMESTAMPTZ | Sí | default `now()` |

**Triggers:** `whatsapp_estado_trg`

## 012_whatsapp_estados_envio — Whatsapp estados envio

### whatsapp_estado_envio

_Los callbacks pueden adelantarse a la persistencia de la respuesta HTTP de Meta._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `proveedor_id` | TEXT | Sí | PK |
| `telefono` | TEXT | Sí | PK |
| `estado` | TEXT | Sí | PK · valores: `sent`, `delivered`, `read`, `failed` |
| `recibido_en` | TIMESTAMPTZ | Sí | default `now()` |

## 013_whatsapp_saldo_transferencia — Whatsapp saldo transferencia

**Triggers:** `whatsapp_saldo_transferencia_trg`

## 014_whatsapp_atencion — Whatsapp atencion

### whatsapp_atencion

_Derivaciones a personal: visibles en la bandeja hasta que un empleado las resuelve. Una conversación tiene a lo sumo una atención pendiente; mientras exista, el bot no crea ni modifica el pedido. El mensaje que la originó y la resolución quedan registrados con el empleado responsable._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `id` | BIGINT | Sí | PK · autonumérico |
| `referencia_hash` | TEXT | Sí | FK → `whatsapp_borrador.referencia_hash` |
| `entrada_id` | TEXT | Sí | FK → `whatsapp_entrada.id` |
| `motivo` | TEXT | Sí | valores: `SOLICITUD`, `PROVEEDOR` |
| `estado` | TEXT | Sí | valores: `PENDIENTE`, `RESUELTA` · default `'PENDIENTE'` |
| `resolucion` | TEXT | No | — |
| `resuelta_por` | BIGINT | No | FK → `usuario.id` |
| `resuelta_en` | TIMESTAMPTZ | No | — |
| `creado_en` | TIMESTAMPTZ | Sí | default `now()` |

## 015_clientes_sin_cuenta — Clientes sin cuenta

## 016_contacto_checkout — Contacto checkout

## 017_whatsapp_mensajes_amigables — Whatsapp mensajes amigables

**Funciones:** `whatsapp_evento_estado`

## 018_whatsapp_contexto_chat — Whatsapp contexto chat

### whatsapp_sesion

_Foco y pregunta de selección por remitente; no almacena credenciales ni historial de IA._

| Columna | Tipo | Obligatoria | Notas |
|---------|------|-------------|-------|
| `telefono` | TEXT | Sí | PK |
| `referencia_hash` | TEXT | No | FK → `whatsapp_borrador.referencia_hash` |
| `solicitud_id` | TEXT | No | FK → `whatsapp_entrada.id` |
| `opciones` | JSONB | Sí | default `'[]'::jsonb` |
| `version` | INT | Sí | default `1` |
| `expira_en` | TIMESTAMPTZ | Sí | default `now() + interval '30 minutes'` |

## 019_whatsapp_memoria_ia — Whatsapp memoria ia

## 020_operacion_segura — Operacion segura

**Funciones:** `whatsapp_evento_estado`

## 021_mensajes_operacion_segura — Mensajes operacion segura

**Funciones:** `whatsapp_evento_estado`

## 022_saldo_operativo_transferencia — Saldo operativo transferencia

**Funciones:** `whatsapp_validar_saldo_transferencia`

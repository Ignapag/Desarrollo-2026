# Diagrama Entidad-Relación — Monu Burger

Modelo de datos **tal como está implementado** en la base.

> **Generado automáticamente** con `python -m scripts.der` a partir de
> `App/db/migrations/`. No editar a mano: al derivarse del SQL, no puede
> quedar desactualizado respecto del esquema real. CI verifica que
> este al dia.

**27 entidades · 46 relaciones.**

Este diagrama reemplaza al entregado en la Actividad N°2: las diferencias
están explicadas una por una en [CAMBIOS_DER.md](CAMBIOS_DER.md) (C-01 a C-12).

## Cómo leer la notación

| Símbolo | Significado |
|---------|-------------|
| `\|\|--o{` | uno a muchos (la relación es obligatoria) |
| `o\|--o{` | uno a muchos (la clave foránea admite nulos) |
| `\|\|--\|\|` | uno a uno |
| `PK` | clave primaria · `FK` clave foránea · `UK` valor único |

---

## Diagrama general

Entidades y relaciones, sin atributos.

```mermaid
erDiagram
    USUARIO ||--|| REPARTIDOR : usuario_id
    USUARIO ||--|| CLIENTE : usuario_id
    ZONA_COBERTURA o|--o{ PUNTO_ENCUENTRO : zona_id
    CLIENTE ||--o{ DIRECCION : cliente_id
    ZONA_COBERTURA o|--o{ DIRECCION : zona_id
    USUARIO o|--o{ AUDITORIA : usuario_id
    USUARIO o|--o{ PARAMETRO : actualizado_por
    USUARIO o|--o{ INGREDIENTE : responsable_id
    CATEGORIA ||--o{ PRODUCTO : categoria_id
    PRODUCTO ||--o{ PRODUCTO_INGREDIENTE : producto_id
    INGREDIENTE ||--o{ PRODUCTO_INGREDIENTE : ingrediente_id
    PRODUCTO ||--o{ PRODUCTO_OPCION : producto_id
    INGREDIENTE ||--o{ PRODUCTO_OPCION : ingrediente_id
    INGREDIENTE ||--o{ MOVIMIENTO_STOCK : ingrediente_id
    USUARIO o|--o{ MOVIMIENTO_STOCK : usuario_id
    INGREDIENTE ||--o{ ALERTA_STOCK : ingrediente_id
    USUARIO o|--o{ ALERTA_STOCK : resuelta_por
    CLIENTE ||--o{ PEDIDO : cliente_id
    DIRECCION o|--o{ PEDIDO : direccion_id
    PUNTO_ENCUENTRO o|--o{ PEDIDO : punto_encuentro_id
    PEDIDO ||--o{ PEDIDO_ITEM : pedido_id
    PRODUCTO ||--o{ PEDIDO_ITEM : producto_id
    PEDIDO_ITEM ||--o{ PEDIDO_ITEM_OPCION : pedido_item_id
    PRODUCTO_OPCION o|--o{ PEDIDO_ITEM_OPCION : producto_opcion_id
    INGREDIENTE ||--o{ PEDIDO_ITEM_OPCION : ingrediente_id
    PEDIDO ||--o{ PEDIDO_ESTADO_HISTORIAL : pedido_id
    USUARIO o|--o{ PEDIDO_ESTADO_HISTORIAL : usuario_id
    USUARIO o|--o{ PROMOCION : creada_por
    PEDIDO ||--o{ PEDIDO_PROMOCION : pedido_id
    PROMOCION ||--o{ PEDIDO_PROMOCION : promocion_id
    USUARIO o|--o{ PEDIDO_PROMOCION : aplicada_por
    REPARTIDOR ||--o{ VIAJE : repartidor_id
    USUARIO o|--o{ VIAJE : asignado_por
    PEDIDO ||--|| ENVIO : pedido_id
    VIAJE o|--o{ ENVIO : viaje_id
    ZONA_COBERTURA o|--o{ ENVIO : zona_id
    PUNTO_ENCUENTRO o|--o{ ENVIO : punto_encuentro_id
    USUARIO o|--o{ CIERRE_CAJA : generado_por
    USUARIO o|--o{ CIERRE_CAJA : aprobado_por
    PEDIDO ||--o{ PAGO : pedido_id
    CIERRE_CAJA o|--o{ PAGO : cierre_caja_id
    USUARIO o|--o{ PAGO : registrado_por
    USUARIO o|--o{ NOTIFICACION_PLANTILLA : actualizado_por
    NOTIFICACION_PLANTILLA o|--o{ NOTIFICACION : plantilla_id
    CLIENTE o|--o{ NOTIFICACION : cliente_id
    PEDIDO o|--o{ NOTIFICACION : pedido_id
```

---

## Diagramas por módulo

### Usuarios y seguridad

```mermaid
erDiagram
    USUARIO ||--|| REPARTIDOR : usuario_id
    USUARIO ||--|| CLIENTE : usuario_id
    ZONA_COBERTURA o|--o{ PUNTO_ENCUENTRO : zona_id
    CLIENTE ||--o{ DIRECCION : cliente_id
    ZONA_COBERTURA o|--o{ DIRECCION : zona_id
    USUARIO o|--o{ AUDITORIA : usuario_id
    USUARIO o|--o{ PARAMETRO : actualizado_por
    USUARIO {
        bigint id PK
        text nombre
        text apellido
        citext username UK
        citext email UK
        text telefono
        text password_hash
        text rol
        text estado
        timestamptz fecha_alta
        timestamptz actualizado_en
        timestamptz ultimo_acceso
    }
    REPARTIDOR {
        bigint usuario_id PK
        text estado
        text vehiculo
        numeric ultima_lat
        numeric ultima_lng
        timestamptz ultima_pos_en
    }
    CLIENTE {
        bigint usuario_id PK
        text telefono_whatsapp
        boolean acepta_notif_wsp
        text notas
    }
    ZONA_COBERTURA {
        bigint id PK
        text nombre UK
        text descripcion
        jsonb poligono
        numeric centro_lat
        numeric centro_lng
        numeric costo_envio
        boolean activa
    }
    PUNTO_ENCUENTRO {
        bigint id PK
        text nombre
        text referencia
        numeric lat
        numeric lng
        bigint zona_id FK
        boolean activo
    }
    DIRECCION {
        bigint id PK
        bigint cliente_id FK
        text calle
        text numero
        text piso_depto
        text codigo_postal
        text localidad
        text referencia
        numeric lat
        numeric lng
        bigint zona_id FK
        boolean es_principal
        boolean activa
        timestamptz creada_en
    }
    AUDITORIA {
        bigint id PK
        bigint usuario_id FK
        text accion
        text entidad
        text entidad_id
        jsonb datos
        inet ip
        timestamptz creado_en
    }
    PARAMETRO {
        text clave PK
        text valor
        text descripcion
        timestamptz actualizado_en
        bigint actualizado_por FK
    }
```

### Catalogo y stock

```mermaid
erDiagram
    CATEGORIA ||--o{ PRODUCTO : categoria_id
    PRODUCTO ||--o{ PRODUCTO_INGREDIENTE : producto_id
    INGREDIENTE ||--o{ PRODUCTO_INGREDIENTE : ingrediente_id
    PRODUCTO ||--o{ PRODUCTO_OPCION : producto_id
    INGREDIENTE ||--o{ PRODUCTO_OPCION : ingrediente_id
    INGREDIENTE ||--o{ MOVIMIENTO_STOCK : ingrediente_id
    INGREDIENTE ||--o{ ALERTA_STOCK : ingrediente_id
    CATEGORIA {
        bigint id PK
        text nombre UK
        int orden
        boolean activa
    }
    INGREDIENTE {
        bigint id PK
        text nombre UK
        text unidad_medida
        numeric cantidad_actual
        numeric umbral_minimo
        numeric costo_unitario
        text[] dias_reposicion
        timestamptz fecha_ultima_reposicion
        bigint responsable_id FK
        boolean activo
    }
    PRODUCTO {
        bigint id PK
        bigint categoria_id FK
        text nombre
        text descripcion
        numeric precio_base
        text imagen_url
        boolean activo
        int orden
        timestamptz creado_en
        timestamptz actualizado_en
    }
    PRODUCTO_INGREDIENTE {
        bigint producto_id PK
        bigint ingrediente_id PK
        numeric cantidad_requerida
        boolean es_base
    }
    PRODUCTO_OPCION {
        bigint id PK
        bigint producto_id FK
        bigint ingrediente_id FK
        text tipo
        numeric costo_adicional
        numeric cantidad_requerida
        int max_por_item
        boolean activo
    }
    MOVIMIENTO_STOCK {
        bigint id PK
        bigint ingrediente_id FK
        text tipo
        numeric cantidad
        numeric saldo_resultante
        bigint pedido_id
        bigint usuario_id FK
        text motivo
        timestamptz creado_en
    }
    ALERTA_STOCK {
        bigint id PK
        bigint ingrediente_id FK
        text nivel
        numeric cantidad_al_generar
        text estado
        timestamptz generada_en
        timestamptz resuelta_en
        bigint resuelta_por FK
    }
```

### Pedidos

```mermaid
erDiagram
    PEDIDO ||--o{ PEDIDO_ITEM : pedido_id
    PEDIDO_ITEM ||--o{ PEDIDO_ITEM_OPCION : pedido_item_id
    PEDIDO ||--o{ PEDIDO_ESTADO_HISTORIAL : pedido_id
    PEDIDO ||--o{ PEDIDO_PROMOCION : pedido_id
    PROMOCION ||--o{ PEDIDO_PROMOCION : promocion_id
    PEDIDO {
        bigint id PK
        bigint numero UK
        bigint cliente_id FK
        text tipo_entrega
        bigint direccion_id FK
        bigint punto_encuentro_id FK
        text canal
        text estado
        numeric subtotal
        numeric costo_envio
        numeric descuento_total
        numeric total
        text observaciones
        timestamptz hora_entrega_pedida
        timestamptz creado_en
        timestamptz confirmado_en
        timestamptz cancelable_hasta
        timestamptz entregado_en
        timestamptz cancelado_en
        text motivo_cancelacion
    }
    PEDIDO_ITEM {
        bigint id PK
        bigint pedido_id FK
        bigint producto_id FK
        text nombre_producto
        int cantidad
        numeric precio_unitario
        numeric costo_opciones
        numeric subtotal
        text aclaraciones
    }
    PEDIDO_ITEM_OPCION {
        bigint id PK
        bigint pedido_item_id FK
        bigint producto_opcion_id FK
        bigint ingrediente_id FK
        text nombre_opcion
        text tipo
        int cantidad
        numeric costo_adicional
    }
    PEDIDO_ESTADO_HISTORIAL {
        bigint id PK
        bigint pedido_id FK
        text estado_anterior
        text estado_nuevo
        bigint usuario_id FK
        text observacion
        timestamptz creado_en
    }
    PROMOCION {
        bigint id PK
        text nombre
        citext codigo UK
        text tipo
        numeric valor
        numeric monto_minimo
        date vigencia_desde
        date vigencia_hasta
        boolean activa
        bigint creada_por FK
        timestamptz creada_en
    }
    PEDIDO_PROMOCION {
        bigint pedido_id PK
        bigint promocion_id PK
        numeric monto_descontado
        bigint aplicada_por FK
        timestamptz aplicada_en
    }
```

### Delivery

```mermaid
erDiagram
    VIAJE o|--o{ ENVIO : viaje_id
    VIAJE {
        bigint id PK
        bigint repartidor_id FK
        text estado
        timestamptz creado_en
        timestamptz salida_en
        timestamptz retorno_en
        bigint asignado_por FK
        boolean asignacion_auto
    }
    ENVIO {
        bigint id PK
        bigint pedido_id FK
        bigint viaje_id FK
        bigint zona_id FK
        bigint punto_encuentro_id FK
        int orden_en_viaje
        text estado
        numeric distancia_km
        timestamptz asignado_en
        timestamptz en_camino_en
        timestamptz entregado_en
        text observaciones
    }
```

### Pagos y caja

```mermaid
erDiagram
    CIERRE_CAJA o|--o{ PAGO : cierre_caja_id
    CIERRE_CAJA {
        bigint id PK
        date fecha
        text turno
        timestamptz abierto_en
        timestamptz cerrado_en
        numeric total_efectivo
        numeric total_billeteras
        numeric total_devoluciones
        numeric total_general
        int cantidad_pedidos
        text estado
        bigint generado_por FK
        bigint aprobado_por FK
        timestamptz aprobado_en
        text observaciones
    }
    PAGO {
        bigint id PK
        bigint pedido_id FK
        bigint cierre_caja_id FK
        text tipo
        text metodo_pago
        numeric monto
        numeric propina
        text estado
        text referencia_externa
        bigint registrado_por FK
        timestamptz registrado_en
        timestamptz conciliado_en
        text motivo
    }
```

### Notificaciones

```mermaid
erDiagram
    NOTIFICACION_PLANTILLA o|--o{ NOTIFICACION : plantilla_id
    NOTIFICACION_PLANTILLA {
        bigint id PK
        text clave UK
        text nombre
        text cuerpo
        boolean activa
        bigint actualizado_por FK
        timestamptz actualizado_en
    }
    NOTIFICACION {
        bigint id PK
        bigint plantilla_id FK
        text clave
        text destinatario
        bigint cliente_id FK
        bigint pedido_id FK
        text cuerpo_renderizado
        text canal
        text estado
        int intentos
        text error
        timestamptz creada_en
        timestamptz enviada_en
    }
```

---

## Relaciones en detalle

| Desde | Clave foránea | Hacia | Cardinalidad | Obligatoria |
|-------|---------------|-------|--------------|-------------|
| `alerta_stock` | `ingrediente_id` | `ingrediente` | 1 : N | Sí |
| `alerta_stock` | `resuelta_por` | `usuario` | 1 : N | No |
| `auditoria` | `usuario_id` | `usuario` | 1 : N | No |
| `cierre_caja` | `aprobado_por` | `usuario` | 1 : N | No |
| `cierre_caja` | `generado_por` | `usuario` | 1 : N | No |
| `cliente` | `usuario_id` | `usuario` | 1 : 1 | Sí |
| `direccion` | `cliente_id` | `cliente` | 1 : N | Sí |
| `direccion` | `zona_id` | `zona_cobertura` | 1 : N | No |
| `envio` | `pedido_id` | `pedido` | 1 : 1 | Sí |
| `envio` | `punto_encuentro_id` | `punto_encuentro` | 1 : N | No |
| `envio` | `viaje_id` | `viaje` | 1 : N | No |
| `envio` | `zona_id` | `zona_cobertura` | 1 : N | No |
| `ingrediente` | `responsable_id` | `usuario` | 1 : N | No |
| `movimiento_stock` | `ingrediente_id` | `ingrediente` | 1 : N | Sí |
| `movimiento_stock` | `usuario_id` | `usuario` | 1 : N | No |
| `notificacion` | `cliente_id` | `cliente` | 1 : N | No |
| `notificacion` | `plantilla_id` | `notificacion_plantilla` | 1 : N | No |
| `notificacion` | `pedido_id` | `pedido` | 1 : N | No |
| `notificacion_plantilla` | `actualizado_por` | `usuario` | 1 : N | No |
| `pago` | `cierre_caja_id` | `cierre_caja` | 1 : N | No |
| `pago` | `pedido_id` | `pedido` | 1 : N | Sí |
| `pago` | `registrado_por` | `usuario` | 1 : N | No |
| `parametro` | `actualizado_por` | `usuario` | 1 : N | No |
| `pedido` | `cliente_id` | `cliente` | 1 : N | Sí |
| `pedido` | `direccion_id` | `direccion` | 1 : N | No |
| `pedido` | `punto_encuentro_id` | `punto_encuentro` | 1 : N | No |
| `pedido_estado_historial` | `pedido_id` | `pedido` | 1 : N | Sí |
| `pedido_estado_historial` | `usuario_id` | `usuario` | 1 : N | No |
| `pedido_item` | `pedido_id` | `pedido` | 1 : N | Sí |
| `pedido_item` | `producto_id` | `producto` | 1 : N | Sí |
| `pedido_item_opcion` | `ingrediente_id` | `ingrediente` | 1 : N | Sí |
| `pedido_item_opcion` | `pedido_item_id` | `pedido_item` | 1 : N | Sí |
| `pedido_item_opcion` | `producto_opcion_id` | `producto_opcion` | 1 : N | No |
| `pedido_promocion` | `pedido_id` | `pedido` | 1 : N | Sí |
| `pedido_promocion` | `promocion_id` | `promocion` | 1 : N | Sí |
| `pedido_promocion` | `aplicada_por` | `usuario` | 1 : N | No |
| `producto` | `categoria_id` | `categoria` | 1 : N | Sí |
| `producto_ingrediente` | `ingrediente_id` | `ingrediente` | 1 : N | Sí |
| `producto_ingrediente` | `producto_id` | `producto` | 1 : N | Sí |
| `producto_opcion` | `ingrediente_id` | `ingrediente` | 1 : N | Sí |
| `producto_opcion` | `producto_id` | `producto` | 1 : N | Sí |
| `promocion` | `creada_por` | `usuario` | 1 : N | No |
| `punto_encuentro` | `zona_id` | `zona_cobertura` | 1 : N | No |
| `repartidor` | `usuario_id` | `usuario` | 1 : 1 | Sí |
| `viaje` | `repartidor_id` | `repartidor` | 1 : N | Sí |
| `viaje` | `asignado_por` | `usuario` | 1 : N | No |

---

## Para el informe

Los diagramas de arriba se renderizan solos en GitHub. Para pegarlos en el
documento de la entrega, copiar el bloque `mermaid` correspondiente en
[mermaid.live](https://mermaid.live) y exportarlo como PNG o SVG.

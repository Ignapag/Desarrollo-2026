-- La identidad comercial y el acceso autenticado tienen ciclos de vida distintos.
-- Preservamos los IDs históricos para no renumerar pedidos ni otros vínculos.
ALTER TABLE cliente ADD COLUMN id BIGINT;
UPDATE cliente SET id = usuario_id;

CREATE SEQUENCE cliente_id_seq OWNED BY cliente.id;
SELECT setval('cliente_id_seq', COALESCE(MAX(id), 0) + 1, false) FROM cliente;
ALTER TABLE cliente ALTER COLUMN id SET DEFAULT nextval('cliente_id_seq');
ALTER TABLE cliente ALTER COLUMN id SET NOT NULL;

ALTER TABLE pedido DROP CONSTRAINT pedido_cliente_id_fkey;
ALTER TABLE direccion DROP CONSTRAINT direccion_cliente_id_fkey;
ALTER TABLE notificacion DROP CONSTRAINT notificacion_cliente_id_fkey;
ALTER TABLE whatsapp_borrador DROP CONSTRAINT whatsapp_borrador_cliente_id_fkey;
ALTER TABLE cliente DROP CONSTRAINT cliente_pkey;
ALTER TABLE cliente ALTER COLUMN usuario_id DROP NOT NULL;
ALTER TABLE cliente ADD CONSTRAINT cliente_pkey PRIMARY KEY (id);
ALTER TABLE cliente ADD CONSTRAINT cliente_usuario_id_key UNIQUE (usuario_id);

ALTER TABLE pedido ADD CONSTRAINT pedido_cliente_id_fkey
    FOREIGN KEY (cliente_id) REFERENCES cliente (id) ON DELETE RESTRICT;
ALTER TABLE direccion ADD CONSTRAINT direccion_cliente_id_fkey
    FOREIGN KEY (cliente_id) REFERENCES cliente (id) ON DELETE CASCADE;
ALTER TABLE notificacion ADD CONSTRAINT notificacion_cliente_id_fkey
    FOREIGN KEY (cliente_id) REFERENCES cliente (id) ON DELETE SET NULL;
ALTER TABLE whatsapp_borrador ADD CONSTRAINT whatsapp_borrador_cliente_id_fkey
    FOREIGN KEY (cliente_id) REFERENCES cliente (id);

ALTER TABLE cliente
    ADD COLUMN nombre TEXT NOT NULL DEFAULT 'Cliente',
    ADD COLUMN estado TEXT NOT NULL DEFAULT 'ACTIVO',
    ADD COLUMN whatsapp_verificado TEXT,
    ADD CONSTRAINT cliente_nombre_chk CHECK (length(btrim(nombre)) > 0),
    ADD CONSTRAINT cliente_estado_chk CHECK (estado IN ('ACTIVO', 'INACTIVO')),
    ADD CONSTRAINT cliente_whatsapp_verificado_chk
        CHECK (whatsapp_verificado ~ '^[0-9]{11,15}$'),
    ADD CONSTRAINT cliente_whatsapp_verificado_key UNIQUE (whatsapp_verificado);
UPDATE cliente c SET nombre = concat_ws(' ', u.nombre, u.apellido), estado = u.estado
FROM usuario u WHERE u.id = c.usuario_id;
-- telefono_whatsapp es un dato declarado histórico, no acredita control del número.
-- whatsapp_verificado se completa únicamente desde un remitente firmado del webhook.

ALTER TABLE whatsapp_borrador
    ALTER COLUMN cliente_id DROP NOT NULL,
    ALTER COLUMN telefono DROP NOT NULL,
    ADD CONSTRAINT whatsapp_borrador_identidad_chk
        CHECK ((cliente_id IS NULL) = (telefono IS NULL));
ALTER TABLE whatsapp_entrada ADD COLUMN nombre_remitente TEXT;

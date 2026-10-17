-- Borradores separados del pedido operativo y colas transaccionales del bot.
CREATE TABLE whatsapp_borrador (
    referencia_hash TEXT PRIMARY KEY,
    cliente_id BIGINT NOT NULL REFERENCES cliente (usuario_id),
    telefono TEXT NOT NULL,
    items JSONB NOT NULL,
    tipo_entrega TEXT CHECK (tipo_entrega IN ('RETIRO','DELIVERY')),
    metodo_pago TEXT CHECK (metodo_pago IN ('EFECTIVO','TRANSFERENCIA')),
    direccion JSONB,
    estado TEXT NOT NULL DEFAULT 'BORRADOR' CHECK (estado IN ('BORRADOR','VINCULADO','CREADO','HUMANO')),
    estado_pago TEXT NOT NULL DEFAULT 'PENDIENTE' CHECK (estado_pago IN ('PENDIENTE','APROBADO','RECHAZADO')),
    pedido_id BIGINT UNIQUE REFERENCES pedido (id),
    version INT NOT NULL DEFAULT 1 CHECK (version > 0),
    propuesta JSONB,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_en TIMESTAMPTZ NOT NULL DEFAULT now() + interval '30 minutes',
    ultimo_mensaje_en TIMESTAMPTZ,
    CHECK (telefono ~ '^[0-9]{11,15}$')
);
CREATE INDEX whatsapp_conversacion_idx ON whatsapp_borrador (telefono, ultimo_mensaje_en DESC);

CREATE TABLE whatsapp_entrada (
    id TEXT PRIMARY KEY,
    telefono TEXT NOT NULL,
    texto TEXT NOT NULL,
    media_id TEXT,
    referencia_hash TEXT REFERENCES whatsapp_borrador (referencia_hash),
    estado TEXT NOT NULL DEFAULT 'PENDIENTE' CHECK (estado IN ('PENDIENTE','PROCESADO')),
    respuesta TEXT,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE whatsapp_salida (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    clave TEXT NOT NULL UNIQUE,
    telefono TEXT NOT NULL,
    texto TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'PENDIENTE' CHECK (estado IN
        ('PENDIENTE','ENVIANDO','ACEPTADO','ENTREGADO','FALLIDO','INCIERTO','SIMULADO')),
    proveedor_id TEXT UNIQUE,
    intentos INT NOT NULL DEFAULT 0,
    proximo_intento_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX whatsapp_envio_pendiente_idx ON whatsapp_salida (proximo_intento_en)
    WHERE estado IN ('PENDIENTE','FALLIDO');

-- Cambios propuestos, aplicados o derivados. La cocina lee pedido_item vigente.
CREATE TABLE whatsapp_cambio (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pedido_id BIGINT NOT NULL REFERENCES pedido (id),
    version INT NOT NULL,
    accion JSONB NOT NULL,
    anterior JSONB NOT NULL,
    posterior JSONB,
    estado TEXT NOT NULL CHECK (estado IN ('APLICADO','PENDIENTE_EMPLEADO','RECHAZADO')),
    revisado_por BIGINT REFERENCES usuario (id),
    revisado_en TIMESTAMPTZ,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE whatsapp_comprobante (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entrada_id TEXT NOT NULL UNIQUE REFERENCES whatsapp_entrada (id),
    pedido_id BIGINT NOT NULL REFERENCES pedido (id),
    media_id TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'PENDIENTE' CHECK (estado IN ('PENDIENTE','APROBADO','RECHAZADO')),
    revisado_por BIGINT REFERENCES usuario (id),
    revisado_en TIMESTAMPTZ,
    motivo TEXT,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- También cubre productores históricos de estados (pagos y delivery con SQL propio).
CREATE FUNCTION whatsapp_evento_estado() RETURNS TRIGGER LANGUAGE plpgsql AS $func$
DECLARE contacto TEXT;
BEGIN
    IF NEW.estado = OLD.estado THEN RETURN NEW; END IF;
    SELECT telefono INTO contacto FROM whatsapp_borrador WHERE pedido_id = NEW.id;
    IF contacto IS NULL THEN RETURN NEW; END IF;
    IF NEW.estado = 'EN_PREPARACION' AND EXISTS (
        SELECT 1 FROM whatsapp_borrador WHERE pedido_id = NEW.id
        AND metodo_pago = 'TRANSFERENCIA' AND estado_pago <> 'APROBADO'
    ) THEN
        RAISE EXCEPTION 'La transferencia requiere revision humana' USING ERRCODE = 'check_violation';
    END IF;
    INSERT INTO whatsapp_salida (clave, telefono, texto)
    VALUES ('estado:' || NEW.id || ':' || NEW.estado, contacto,
        'Pedido #' || NEW.numero || ': ' || replace(NEW.estado, '_', ' ') || '.')
    ON CONFLICT (clave) DO NOTHING;
    RETURN NEW;
END;
$func$;
CREATE TRIGGER whatsapp_estado_trg AFTER UPDATE OF estado ON pedido
    FOR EACH ROW EXECUTE FUNCTION whatsapp_evento_estado();

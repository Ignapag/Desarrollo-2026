-- Adaptador web de demostración. Las reglas e inbox/outbox siguen siendo del bot.
CREATE TABLE chat_demo_sesion (
    token_hash TEXT PRIMARY KEY,
    telefono TEXT NOT NULL UNIQUE CHECK (telefono ~ '^000[0-9]{12}$'),
    cliente_id BIGINT NOT NULL REFERENCES cliente (id),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_en TIMESTAMPTZ NOT NULL DEFAULT now() + interval '7 days'
);

CREATE TABLE chat_demo_operacion (
    sesion_hash TEXT NOT NULL REFERENCES chat_demo_sesion (token_hash),
    solicitud_id UUID NOT NULL,
    huella TEXT NOT NULL,
    entrada_id TEXT NOT NULL UNIQUE REFERENCES whatsapp_entrada (id),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (sesion_hash, solicitud_id)
);
CREATE INDEX chat_demo_operacion_fecha_idx ON chat_demo_operacion (creado_en);

-- BYTEA permite persistencia atómica y acceso privado sin otro servicio/volumen.
CREATE TABLE chat_demo_archivo (
    media_id TEXT PRIMARY KEY,
    sesion_hash TEXT NOT NULL REFERENCES chat_demo_sesion (token_hash),
    entrada_id TEXT NOT NULL UNIQUE REFERENCES whatsapp_entrada (id),
    mime TEXT NOT NULL CHECK (mime IN ('image/png','image/jpeg','application/pdf')),
    contenido BYTEA NOT NULL CHECK (octet_length(contenido) BETWEEN 1 AND 2097152)
);

-- Foco y pregunta de selección por remitente; no almacena credenciales ni historial de IA.
CREATE TABLE whatsapp_sesion (
    telefono TEXT PRIMARY KEY CHECK (telefono ~ '^[0-9]{11,15}$'),
    referencia_hash TEXT REFERENCES whatsapp_borrador (referencia_hash) ON DELETE CASCADE,
    solicitud_id TEXT REFERENCES whatsapp_entrada (id) ON DELETE CASCADE,
    opciones JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(opciones) = 'array'),
    version INT NOT NULL DEFAULT 1 CHECK (version > 0),
    expira_en TIMESTAMPTZ NOT NULL DEFAULT now() + interval '30 minutes',
    CHECK ((referencia_hash IS NOT NULL AND solicitud_id IS NULL AND opciones = '[]'::jsonb)
        OR (referencia_hash IS NULL AND solicitud_id IS NOT NULL AND jsonb_array_length(opciones) > 0))
);

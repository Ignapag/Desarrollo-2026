-- Contacto declarado en la web; nunca reemplaza al remitente verificado por Meta.
ALTER TABLE whatsapp_borrador
    ADD COLUMN contacto JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD CONSTRAINT whatsapp_borrador_contacto_objeto
        CHECK (jsonb_typeof(contacto) = 'object');

ALTER TABLE cliente
    ADD COLUMN telefono_contacto TEXT,
    ADD CONSTRAINT cliente_telefono_contacto_formato
        CHECK (telefono_contacto ~ '^[0-9]{11,15}$');

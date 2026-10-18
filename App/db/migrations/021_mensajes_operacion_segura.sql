-- Conserva mensajes y modalidad con un evento distinto por cada version.
CREATE OR REPLACE FUNCTION whatsapp_evento_estado() RETURNS TRIGGER
LANGUAGE plpgsql AS $func$
DECLARE
    contacto TEXT;
    mensaje TEXT;
BEGIN
    IF NEW.estado = OLD.estado THEN RETURN NEW; END IF;
    SELECT telefono INTO contacto FROM whatsapp_borrador WHERE pedido_id = NEW.id;
    IF contacto IS NULL THEN RETURN NEW; END IF;
    mensaje := CASE NEW.estado
        WHEN 'PENDIENTE' THEN '🍔 *Pedido #' || NEW.numero || '* recibido. ¡Gracias por elegir Monu Burger!'
        WHEN 'CONFIRMADO' THEN '✅ *Pedido #' || NEW.numero || '* confirmado. Te avisamos cuando empecemos a prepararlo.'
        WHEN 'EN_PREPARACION' THEN '👨‍🍳 ¡Ya estamos preparando tu *Pedido #' || NEW.numero || '*! Te avisamos cuando esté listo. 🍔'
        WHEN 'LISTO' THEN CASE WHEN NEW.tipo_entrega = 'RETIRO'
            THEN '🛍️ ¡Tu *Pedido #' || NEW.numero || '* está listo para retirar! Te esperamos en el local. 🍔'
            ELSE '🍔 ¡Tu *Pedido #' || NEW.numero || '* está listo! Te avisamos cuando salga para tu dirección.' END
        WHEN 'EN_CAMINO' THEN CASE WHEN NEW.tipo_entrega = 'RETIRO'
            THEN '🛍️ Tu *Pedido #' || NEW.numero || '* está listo para retirar. ¡Te esperamos!'
            ELSE '🛵 ¡Tu *Pedido #' || NEW.numero || '* está en camino! Si necesitás indicarnos algo para la entrega, escribinos por acá. 📍' END
        WHEN 'ENTREGADO' THEN '💚 ¡Gracias por elegirnos! Tu *Pedido #' || NEW.numero || '* figura como entregado. ¡Que lo disfrutes! 🍔'
        WHEN 'CANCELADO' THEN 'Tu *Pedido #' || NEW.numero || '* fue cancelado. Si ya habías pagado, escribinos para que el equipo revise el reintegro. 💬'
        ELSE '🍔 Tenemos una novedad sobre tu *Pedido #' || NEW.numero || '*. Escribinos y te ayudamos. 💬'
    END;
    INSERT INTO whatsapp_salida (clave, telefono, texto)
    VALUES ('estado:' || NEW.id || ':v' || NEW.version, contacto, mensaje)
    ON CONFLICT (clave) DO NOTHING;
    RETURN NEW;
END;
$func$;

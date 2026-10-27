import { apiFetch } from '../shared/api/http';

function normalizeWhatsAppPhone(phone) {
  if (!/^[+0-9()\s.-]+$/.test(phone)) return '';
  let number = phone.replace(/\D/g, '');
  if (/^54(?:9)?[1-9][0-9]{9}$/.test(number)) number = number.slice(-10);
  if (/^0[1-9][0-9]{9}$/.test(number)) number = number.slice(1);
  return /^[1-9][0-9]{9}$/.test(number) ? `549${number}` : '';
}

export function buildWhatsAppDraftPayload({ cart, delivery, payment, address, number, zone, contact }) {
  return {
    tipo_entrega: delivery,
    metodo_pago: payment,
    contacto: contact ? {
      nombre: contact.nombre.trim(),
      apellido: contact.apellido.trim(),
      telefono: normalizeWhatsAppPhone(contact.telefono),
    } : null,
    direccion_nueva: delivery === 'DELIVERY'
      ? { calle: address.trim(), numero: number.trim(), localidad: zone }
      : null,
    items: cart.map((item) => ({
      producto_id: Number(String(item.id).split('-')[0]),
      cantidad: item.quantity,
      variante: item.variant || null,
      aclaraciones: item.notes || null,
    })),
  };
}

export async function createWhatsAppDraft(payload) {
  const result = await apiFetch('/api/whatsapp/borradores', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (typeof result?.referencia !== 'string' || !result.referencia.trim() || typeof result.mensaje !== 'string' || !result.mensaje.trim() || !Number.isFinite(Date.parse(result.expira_en))) {
    throw new Error('No se pudo confirmar el mensaje preparado. Volvé a preparar el pedido.');
  }
  return result;
}

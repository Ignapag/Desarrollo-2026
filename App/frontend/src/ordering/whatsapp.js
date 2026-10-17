import { apiFetch } from '../shared/api/http';

export function buildWhatsAppDraftPayload({ cart, phone, delivery, payment, address, number, zone }) {
  return {
    telefono: phone.replace(/\D/g, ''),
    tipo_entrega: delivery,
    metodo_pago: payment,
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

export function createWhatsAppDraft(payload) {
  return apiFetch('/api/whatsapp/borradores', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// Pages Functions mantiene la API y sus cookies HttpOnly bajo cada dominio de Pages.
// Proxy de Cloudflare Pages: reenvía toda petición /api/* al backend (API_ORIGIN o
// el backend de desarrollo en Render) conservando método, cuerpo y cookies, y
// marca la respuesta como no cacheable porque contiene datos de sesión.
// IP confiable: X-Monu-IP-Cliente (CF-Connecting-IP) viaja junto a X-Monu-Proxy-Secreto
// solo si hay PROXY_IP_SECRETO; los X-Monu-* del visitante siempre se descartan.
export async function onRequest({ request, env }) {
  const origen = new URL(env.API_ORIGIN || 'https://monu-burger-desarrollo.onrender.com');
  const destino = new URL(request.url);
  destino.protocol = origen.protocol;
  destino.host = origen.host;
  const reenviada = new Request(destino, request);
  reenviada.headers.delete('host');
  reenviada.headers.delete('X-Monu-IP-Cliente');
  reenviada.headers.delete('X-Monu-Proxy-Secreto');
  const ipCliente = request.headers.get('CF-Connecting-IP');
  if (typeof env.PROXY_IP_SECRETO === 'string' && env.PROXY_IP_SECRETO && ipCliente) {
    reenviada.headers.set('X-Monu-IP-Cliente', ipCliente);
    reenviada.headers.set('X-Monu-Proxy-Secreto', env.PROXY_IP_SECRETO);
  }
  // No reenviar credenciales a un segundo origen si el backend responde un redirect.
  const respuesta = await fetch(reenviada, { redirect: 'manual' });
  const salida = new Response(respuesta.body, respuesta);
  salida.headers.set('Cache-Control', 'private, no-store');
  return salida;
}

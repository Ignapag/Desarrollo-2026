// Pages Functions mantiene la API y su cookie HttpOnly bajo el dominio del personal.
export async function onRequest({ request, env }) {
  const origen = new URL(env.API_ORIGIN || 'https://proyecto-seminario-integrador-2026.onrender.com');
  const destino = new URL(request.url);
  destino.protocol = origen.protocol;
  destino.host = origen.host;
  const reenviada = new Request(destino, request);
  reenviada.headers.delete('host');
  // No reenviar credenciales a un segundo origen si el backend responde un redirect.
  const respuesta = await fetch(reenviada, { redirect: 'manual' });
  const salida = new Response(respuesta.body, respuesta);
  salida.headers.set('Cache-Control', 'private, no-store');
  return salida;
}

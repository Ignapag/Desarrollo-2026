import { useEffect, useState } from 'react';
import { can } from '../auth/permissions';
import { apiFetch } from '../shared/api/http';

// La identidad se comprueba también al renderizar, antes del cleanup del efecto.
export function useAnalyticsReports(user, consulta, refreshSession) {
  const [estado, setEstado] = useState(null);
  const habilitado = can(user, 'reportes.ver');
  const financieros = habilitado && can(user, 'reportes.financieros');
  useEffect(() => {
    if (!habilitado || !consulta) return undefined;
    let vigente = true;
    const controller = new AbortController();
    const query = new URLSearchParams({ fecha_desde: consulta.desde, fecha_hasta: consulta.hasta });
    async function cargar() {
      try {
        const opciones = { signal: controller.signal };
        const respuestas = await Promise.allSettled([
          apiFetch(`/api/reportes/dashboard?${query}`, opciones),
          apiFetch(`/api/reportes/ventas?${query}&agrupacion=DIA`, opciones),
          ...(financieros ? [apiFetch(`/api/reportes/rentabilidad?${query}`, opciones)] : []),
        ]);
        if (!vigente) return;
        const fallo = respuestas.find((respuesta) => respuesta.status === 'rejected');
        if (fallo) throw fallo.reason;
        const [resumen, ventas, rentabilidad] = respuestas.map((respuesta) => respuesta.value);
        setEstado({ user, consulta, datos: { resumen, ventas, rentabilidad }, error: '' });
      } catch (error) {
        if (!vigente) return;
        setEstado({ user, consulta, datos: null, error: error.message || 'No se pudieron cargar los reportes.' });
        if ([401, 403].includes(error.status)) void refreshSession?.();
      }
    }
    void cargar();
    return () => { vigente = false; controller.abort(); };
  }, [user, consulta, habilitado, financieros, refreshSession]);
  const actual = habilitado && consulta && estado?.user === user && estado?.consulta === consulta ? estado : null;
  return { datos: actual?.datos, error: actual?.error, cargando: habilitado && Boolean(consulta) && !actual, financieros };
}

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, CalendarDays, CalendarRange, RefreshCw, ShoppingBag } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { can, canVisit } from '../auth/permissions';
import { useAuth } from '../auth/AuthContext';
import { apiFetch } from '../shared/api/http';
import { periodoPanel, unidadesPorDia } from './datosPanel';

const cantidad = new Intl.NumberFormat('es-AR');
const moneda = new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 });
const hora = new Intl.DateTimeFormat('es-AR', { timeZone: 'America/Argentina/Buenos_Aires', hour: '2-digit', minute: '2-digit' });
const tarjeta = 'bg-monu-bone rounded-2xl p-6 shadow-sm border border-monu-green/10 min-w-0';

function useReportes(user, refreshSession) {
  const [estado, setEstado] = useState(null);
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    if (!can(user, 'reportes.ver')) return undefined;
    let activo = true;
    let pendiente = false;
    let ultimoInicio = 0;
    const controller = new AbortController();

    async function cargar(forzar = false) {
      if (pendiente || document.visibilityState === 'hidden') return;
      if (!forzar && Date.now() - ultimoInicio < 10000) return;
      pendiente = true;
      ultimoInicio = Date.now();
      setEstado((anterior) => ({ owner: user, datos: anterior?.owner === user ? anterior.datos : null, error: '', cargando: true }));
      const periodo = periodoPanel();
      const query = new URLSearchParams({ fecha_desde: periodo.desde, fecha_hasta: periodo.hasta });
      try {
        const respuestas = await Promise.allSettled([
          apiFetch(`/api/reportes/dashboard?${query}`, { signal: controller.signal }),
          apiFetch(`/api/reportes/ventas?${query}&agrupacion=DIA`, { signal: controller.signal }),
        ]);
        const fallida = respuestas.find((respuesta) => respuesta.status === 'rejected');
        if (fallida) throw fallida.reason;
        const [resumen, ventas] = respuestas.map((respuesta) => respuesta.value);
        if (activo) {
          setEstado({ owner: user, datos: { resumen, serie: unidadesPorDia(periodo.dias, ventas) }, error: '', cargando: false });
        }
      } catch (fallo) {
        if (activo) {
          const sinAcceso = [401, 403].includes(fallo.status);
          setEstado((anterior) => ({ owner: user, datos: !sinAcceso && anterior?.owner === user ? anterior.datos : null, error: fallo.message || 'No se pudo cargar el panel.', cargando: false }));
          if (sinAcceso) void refreshSession?.();
        }
      } finally {
        pendiente = false;
      }
    }

    cargar(true);
    const refrescar = () => cargar();
    const intervalo = window.setInterval(refrescar, 45000);
    window.addEventListener('focus', refrescar);
    document.addEventListener('visibilitychange', refrescar);
    return () => {
      activo = false;
      controller.abort();
      window.clearInterval(intervalo);
      window.removeEventListener('focus', refrescar);
      document.removeEventListener('visibilitychange', refrescar);
    };
  }, [user, intento, refreshSession]);

  const habilitado = can(user, 'reportes.ver');
  const actual = habilitado && estado?.owner === user ? estado : null;
  return { datos: actual?.datos, error: actual?.error || '', cargando: habilitado && (actual?.cargando ?? true), recargar: () => setIntento((anterior) => anterior + 1) };
}

export default function ControlPanel() {
  const { user, refreshSession } = useAuth();
  const habilitado = can(user, 'reportes.ver');
  const { datos, error, cargando, recargar } = useReportes(user, refreshSession);
  const resumen = datos?.resumen;
  const ranking = resumen?.ranking_productos.slice(0, 5) || [];
  const stats = resumen ? [
    { label: 'Pedidos hoy', value: resumen.pedidos_dia, icon: ShoppingBag },
    { label: 'Pedidos esta semana', value: resumen.pedidos_semana, icon: CalendarDays },
    { label: 'Pedidos este mes', value: resumen.pedidos_mes, icon: CalendarRange },
    { label: 'Alertas de stock', value: resumen.alertas_stock.length, icon: AlertTriangle },
  ] : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between items-end gap-4">
        <div>
          <h1 className="text-3xl font-extrabold font-heading text-monu-dark mb-1">Panel de Control</h1>
          <p className="text-monu-text/70">Métricas y resumen operativo general.</p>
        </div>
        {habilitado && (
          <button type="button" onClick={recargar} disabled={cargando} className="min-h-11 inline-flex items-center gap-2 rounded-xl border border-monu-green/20 bg-monu-bone px-4 text-sm font-bold text-monu-dark hover:bg-monu-green/10 disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-monu-green">
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            {cargando ? 'Actualizando…' : 'Actualizar'}
          </button>
        )}
      </div>

      {!habilitado ? (
        <section className={tarjeta}>
          <h2 className="font-bold text-lg text-monu-dark">Todo listo para trabajar</h2>
          <p className="mt-2 text-monu-text/70">Consultá los pedidos y la cocina. Las métricas están disponibles para administración y el dueño.</p>
          <div className="mt-4 flex flex-wrap gap-3">
            <AllowedLink to="/dashboard/orders" className="min-h-11 inline-flex items-center rounded-xl bg-monu-green px-4 font-bold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-monu-green">Ver pedidos</AllowedLink>
            <AllowedLink to="/dashboard/kitchen" className="min-h-11 inline-flex items-center rounded-xl border border-monu-green/20 px-4 font-bold text-monu-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-monu-green">Ir a cocina</AllowedLink>
          </div>
        </section>
      ) : (
        <>
          {error && (
            <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">
              <p className="font-bold">No pudimos actualizar las métricas.</p>
              <p className="text-sm mt-1">{error} {datos ? 'Se muestran los últimos datos recibidos.' : 'Todavía no hay datos disponibles.'}</p>
              <button type="button" onClick={recargar} disabled={cargando} className="mt-2 min-h-11 font-bold underline focus-visible:outline-2 focus-visible:outline-offset-2">Reintentar</button>
            </div>
          )}
          <p role="status" className="text-sm text-monu-text/70">
            {!datos ? (cargando ? 'Cargando métricas…' : 'No se pudieron obtener las métricas.') : `Actualizado a las ${hora.format(new Date(resumen.actualizado_en))} · Hora Argentina${cargando ? ' · Actualizando…' : ''}`}
          </p>
          <div aria-busy={cargando} className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-6">
            {resumen ? stats.map(({ label, value, icon: Icon }) => (
              <article key={label} className={tarjeta}>
                <div className="mb-4 w-fit rounded-xl bg-monu-green/10 p-3"><Icon aria-hidden="true" className="h-6 w-6 text-monu-green" /></div>
                <p className="text-3xl font-extrabold text-monu-dark mb-1">{cantidad.format(value)}</p>
                <h2 className="text-sm font-bold text-monu-text/70">{label}</h2>
              </article>
            )) : ['Pedidos hoy', 'Pedidos esta semana', 'Pedidos este mes', 'Alertas de stock'].map((label) => (
              <article key={label} className={`${tarjeta} min-h-44`}><p className="text-3xl text-monu-text/40 mb-4">—</p><h2 className="text-sm font-bold text-monu-text/70">{label}</h2></article>
            ))}
          </div>
          {resumen && (
            <>
              <p className="text-sm text-monu-text/70">Pedidos confirmados, sin cancelados. Semana desde el lunes y mes calendario. Los gráficos abarcan los últimos 7 días, incluido hoy.</p>
              {can(user, 'reportes.financieros') && resumen.ingreso_neto_confirmado != null && (
                <section className={tarjeta}>
                  <h2 className="text-sm font-bold text-monu-text/70">Ingreso neto confirmado · Últimos 7 días</h2>
                  <p className="mt-2 text-3xl font-extrabold text-monu-dark">{moneda.format(Number(resumen.ingreso_neto_confirmado))}</p>
                  <p className="mt-1 text-sm text-monu-text/70">Cobros conciliados menos devoluciones conciliadas.</p>
                </section>
              )}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <section className={tarjeta}>
                  <h2 className="font-bold text-monu-dark mb-6">Unidades vendidas · Últimos 7 días</h2>
                  {datos.serie.some((dia) => dia.unidades > 0) ? (
                    <>
                      <div className="h-64 min-w-0" aria-hidden="true">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={datos.serie} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-monu-cream)" />
                            <XAxis dataKey="nombre" axisLine={false} tickLine={false} tick={{ fontSize: 12 }} />
                            <YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fontSize: 12 }} />
                            <Tooltip formatter={(value) => [cantidad.format(value), 'Unidades']} />
                            <Area type="linear" dataKey="unidades" stroke="var(--color-monu-green)" strokeWidth={3} fill="var(--color-monu-green)" fillOpacity={0.12} isAnimationActive={false} />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                      <details className="mt-3 text-sm text-monu-dark">
                        <summary className="cursor-pointer min-h-11 py-3 focus-visible:outline-2 focus-visible:outline-offset-2">Ver datos por día</summary>
                        <table className="w-full text-left"><caption className="sr-only">Unidades vendidas por día</caption><thead><tr><th scope="col" className="py-2">Día</th><th scope="col">Unidades</th></tr></thead><tbody>{datos.serie.map((dia) => <tr key={dia.fecha}><th scope="row" className="py-2 font-normal">{dia.nombre}</th><td>{cantidad.format(dia.unidades)}</td></tr>)}</tbody></table>
                      </details>
                    </>
                  ) : <EstadoVacio texto="Todavía no hay ventas confirmadas en estos 7 días." />}
                </section>
                <section className={tarjeta}>
                  <h2 className="font-bold text-monu-dark mb-6">Productos más vendidos · Últimos 7 días</h2>
                  {ranking.length ? (
                    <ol className="space-y-5">
                      {ranking.map((producto) => (
                        <li key={producto.producto_id}>
                          <div className="flex justify-between gap-4 text-sm mb-2"><span className="font-bold text-monu-dark break-words min-w-0">{producto.producto}</span><span className="shrink-0 text-monu-text/70">{cantidad.format(producto.cantidad_vendida)} uds.</span></div>
                          <div aria-hidden="true" className="h-2 rounded-full bg-monu-cream overflow-hidden"><div className="h-full bg-monu-orange rounded-full" style={{ width: `${producto.cantidad_vendida / ranking[0].cantidad_vendida * 100}%` }} /></div>
                        </li>
                      ))}
                    </ol>
                  ) : <EstadoVacio texto="Cuando se confirmen pedidos, verás acá los productos más vendidos." />}
                </section>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

function EstadoVacio({ texto }) {
  return <div className="min-h-64 flex flex-col items-center justify-center text-center gap-4"><ShoppingBag aria-hidden="true" className="h-9 w-9 text-monu-green/60" /><p className="max-w-xs text-monu-text/70">{texto}</p><AllowedLink to="/dashboard/orders" className="min-h-11 inline-flex items-center font-bold text-monu-green underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-monu-green">Ver pedidos</AllowedLink></div>;
}

function AllowedLink({ to, children, ...props }) {
  const { user } = useAuth();
  return canVisit(user, to) ? <Link to={to} {...props}>{children}</Link> : null;
}

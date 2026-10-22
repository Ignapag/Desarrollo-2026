import { useEffect, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { can } from '../auth/permissions';
import { useAnalyticsReports } from './useAnalyticsReports';
import { AnalyticsReports } from './AnalyticsReports';
import { fecha, tarjeta, periodoInicial, validarFechas } from './analyticsModel';

export default function Analytics() {
  const { user, refreshSession } = useAuth();
  const [periodo, setPeriodo] = useState(periodoInicial);
  const [consulta, setConsulta] = useState(periodo);
  const [validacion, setValidacion] = useState('');
  const errorFiltro = useRef(null);
  useEffect(() => { if (validacion) errorFiltro.current?.focus(); }, [validacion]);
  const { datos, error, cargando, financieros } = useAnalyticsReports(user, consulta, refreshSession);
  const habilitado = can(user, 'reportes.ver');
  function editar(campo, valor) {
    setPeriodo((anterior) => ({ ...anterior, [campo]: valor }));
    setConsulta(null);
    setValidacion('');
  }
  function consultar(event) {
    event.preventDefault();
    const problema = validarFechas(periodo);
    setValidacion(problema);
    if (problema) return;
    setConsulta({ ...periodo });
  }

  return (
    <div className="space-y-6 min-w-0">
      <header>
        <h1 className="text-3xl font-extrabold font-heading text-monu-dark">Reportes y Analítica</h1>
        <p className="mt-2 text-monu-text/80">Ventas y productos más vendidos por período.</p>
      </header>
      {!habilitado ? <p role="alert" className={tarjeta}>No tenés permiso para consultar reportes.</p> : <>
        <form onSubmit={consultar} noValidate className={tarjeta} aria-label="Período de los reportes">
          {validacion && <p ref={errorFiltro} tabIndex={-1} id="error-periodo" role="alert" className="mb-4 text-red-800 font-bold focus-visible:outline-2">{validacion} <a href="#reporte-desde" className="underline">Revisar fechas</a></p>}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_auto] gap-4 items-end">
            {['desde', 'hasta'].map((campo) => <div key={campo} className="min-w-0">
              <label htmlFor={`reporte-${campo}`} className="block mb-2 font-bold text-monu-dark">{campo === 'desde' ? 'Desde' : 'Hasta'}</label>
              <input id={`reporte-${campo}`} name={campo} type="date" required value={periodo[campo]} onChange={(event) => editar(campo, event.target.value)} aria-invalid={Boolean(validacion)} aria-describedby={validacion ? 'error-periodo periodo-ayuda' : 'periodo-ayuda'} className="min-h-11 w-full min-w-0 rounded-xl border border-monu-green/60 bg-white px-3 text-monu-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-monu-green" />
            </div>)}
            <button type="submit" disabled={cargando} className="min-h-11 flex justify-center items-center gap-2 rounded-xl bg-monu-green px-5 font-bold text-white hover:bg-monu-dark disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-monu-green">
              <RefreshCw aria-hidden="true" className="w-4 h-4" />{cargando ? 'Consultando…' : 'Consultar período'}
            </button>
          </div>
          <p id="periodo-ayuda" className="mt-3 text-sm text-monu-text/80">Ambas fechas incluidas · Hora Argentina. Inicio: últimos 30 días, incluido hoy.</p>
        </form>
        <div role="status" aria-live="polite" className="text-sm text-monu-text/80">
          {!consulta ? 'Aplicá las fechas con «Consultar período» para ver los resultados.' : cargando ? 'Cargando reportes del período…' : `Período consultado: ${fecha(consulta.desde)} al ${fecha(consulta.hasta)}.`}
        </div>
        {error && <section role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-5 text-red-800">
          <h2 className="font-bold">No pudimos cargar los reportes de este período.</h2>
          <p className="mt-2 break-words">{error}</p>
          <button type="button" onClick={() => setConsulta({ ...periodo })} className="mt-3 min-h-11 px-3 font-bold underline focus-visible:outline-2 focus-visible:outline-offset-2">Reintentar</button>
        </section>}
        <div aria-busy={cargando}>{datos && <AnalyticsReports datos={datos} financieros={financieros} />}</div>
      </>}
    </div>
  );
}

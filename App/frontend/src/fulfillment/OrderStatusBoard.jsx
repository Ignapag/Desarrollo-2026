import { AlertTriangle, ArrowUp, Bike, Clock, Store } from 'lucide-react';
import { buttonClass } from './operationUi';
import { money } from './orderModel';
import { CLOSED_STATES, closedAt, countLabel, formatWait, isLongWait, itemsSummary, orderAlerts, shortDateTime, stateSummaryLabel, waitMinutes } from './orderBoard';

const toneClass = {
  info: 'bg-monu-green/10 text-monu-dark',
  warning: 'bg-monu-yellow/25 text-monu-burnt',
  danger: 'bg-red-100 text-red-800',
};

// Sólo queda fija cuando entra en una fila; en pantallas angostas taparía el contenido enfocado.
export function StatusBar({ options, groups, known, current, onSelect, controls, selectedRef }) {
  return <div role="group" aria-label="Pedidos por estado" className="xl:sticky xl:top-16 z-[5] -mx-1 px-1 py-2 bg-monu-cream">
    <div className="grid grid-cols-2 sm:grid-cols-3 xl:flex xl:flex-wrap gap-2 xl:gap-1.5">
      {options.map(([id, label]) => {
        const summary = groups[id];
        const pressed = current === id;
        return <button key={id} type="button" ref={pressed ? selectedRef : undefined} aria-pressed={pressed} aria-controls={controls} aria-label={stateSummaryLabel(label, summary, known)} onClick={() => onSelect(id)}
          className={`min-h-11 px-3 xl:px-2.5 py-2 rounded-xl border text-sm font-bold text-left min-w-0 inline-flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5 transition-colors motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-monu-green ${pressed ? 'bg-monu-dark text-white border-monu-dark' : 'bg-white text-monu-dark border-monu-green/30 hover:bg-monu-green/10'}`}>
          <span>{label}</span>
          <span className="ml-auto inline-flex items-center gap-1.5">
            <span className="tabular-nums text-base">{known ? summary.count : '—'}</span>
            {known && summary.longWait > 0 && <span className="inline-flex items-center gap-0.5 rounded-full bg-red-100 px-1.5 text-xs text-red-800"><AlertTriangle aria-hidden="true" className="h-3.5 w-3.5" />{summary.longWait}</span>}
          </span>
        </button>;
      })}
    </div>
  </div>;
}

function WaitTag({ id, order, now }) {
  if (CLOSED_STATES.includes(order.estado)) {
    return <span id={id} className="text-xs text-monu-text/75"><span className="sr-only">Cerrado: </span>{shortDateTime(closedAt(order))}</span>;
  }
  const wait = waitMinutes(order, now);
  const long = isLongWait(wait);
  const Icon = long ? AlertTriangle : Clock;
  return <span id={id} className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-bold ${long ? 'bg-red-100 text-red-800' : 'bg-monu-cream text-monu-dark'}`}>
    <Icon aria-hidden="true" className="h-3.5 w-3.5" /><span className="sr-only">Espera: </span>{formatWait(wait)}{long && <span className="sr-only"> (espera alta)</span>}
  </span>;
}

function OrderCard({ order, now, pending, compact, onOpen, registerOpener }) {
  // La espera alta ya se muestra en su etiqueta; aquí van los demás avisos.
  const alerts = orderAlerts(order, { now, pending }).filter((alert) => alert.id !== 'wait');
  const saldo = Number(order.saldo_pendiente);
  const pickup = order.tipo_entrega === 'RETIRO';
  const Delivery = pickup ? Store : Bike;
  const titleId = `order-card-${order.id}`;
  return <article aria-labelledby={titleId} className={`relative rounded-xl border border-monu-green/20 bg-white p-3 text-sm space-y-1 transition-colors motion-reduce:transition-none ${pending ? 'opacity-75' : 'hover:border-monu-green'}`}>
    <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
      <h3 id={titleId} className="text-base font-extrabold text-monu-dark">
        {/* Se extiende sobre toda la tarjeta: un destino táctil y una parada de teclado. Sigue enfocable
            mientras opera para que el foco pueda volver a ella al cerrar el detalle. */}
        <button ref={(node) => registerOpener(order.id, node)} type="button" aria-disabled={pending} aria-describedby={`${titleId}-espera ${titleId}-datos`} onClick={() => { if (!pending) onOpen(order.id); }}
          className="text-left after:absolute after:inset-0 after:rounded-xl after:content-[''] focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-monu-green">
          <span className="sr-only">Abrir pedido </span>#{order.number}
        </button>
      </h3>
      <WaitTag id={`${titleId}-espera`} order={order} now={now} />
    </div>
    <div id={`${titleId}-datos`} className="space-y-1">
      <p className="font-bold truncate">{order.client}</p>
      <p className="flex items-start gap-1.5 text-monu-text/80"><Delivery aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" /><span className="line-clamp-2 break-words">{!pickup && <span className="sr-only">Envío a </span>}{order.address}</span></p>
      <p className="truncate text-monu-text/80">{itemsSummary(order, compact)}</p>
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 pt-1">
        <span><span className="text-monu-text/75">Total </span><strong className="text-monu-dark">{money(order.total)}</strong></span>
        {saldo > 0 ? <span className="rounded-full bg-monu-yellow/25 px-2 py-0.5 text-xs font-bold text-monu-burnt">Saldo {money(saldo)}</span>
          : Number.isFinite(saldo) && order.saldo_pendiente != null ? <span className="text-xs font-bold text-monu-green">Pagado</span>
            : <span className="text-xs text-monu-text/75">Saldo no disponible</span>}
      </div>
      {alerts.length > 0 && <ul aria-label="Alertas" className="flex flex-wrap gap-1 pt-1">
        {alerts.map((alert) => <li key={alert.id} className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-bold ${toneClass[alert.tone]}`}>{alert.tone !== 'info' && <AlertTriangle aria-hidden="true" className="h-3.5 w-3.5" />}{alert.label}</li>)}
      </ul>}
    </div>
  </article>;
}

// `column` es la columna de alto fijo del tablero; `panel` es la vista de un estado enfocado.
// Las listas no cortan el desplazamiento: al llegar al final, la rueda sigue con la página.
export function OrderList({ id, label, group, known, emptyMessage, layout, now, pending, onOpen, registerOpener, onBackToStates }) {
  const headingId = `orders-state-${id}`;
  const column = layout === 'column';
  return <section aria-labelledby={headingId} className={`min-w-0 rounded-2xl border border-monu-green/20 bg-monu-bone ${column ? 'flex flex-col h-[calc(100dvh-11rem)] min-h-96' : 'p-3 md:p-4 space-y-3'}`}>
    <h2 id={headingId} className={`font-extrabold leading-tight text-monu-dark flex items-start justify-between gap-2 ${column ? 'px-3 py-3 border-b border-monu-green/15' : 'text-lg'}`}>
      <span>{label}<span className="sr-only">{known ? `, ${countLabel(group.count)}` : ', cantidad sin consultar'}</span></span>
      <span aria-hidden="true" className="rounded-full bg-monu-dark px-2.5 py-0.5 text-sm text-white tabular-nums">{known ? group.count : '—'}</span>
    </h2>
    {group.count > 0 ? <ul className={column ? 'flex-1 overflow-y-auto p-2 space-y-2' : 'grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 md:max-h-[calc(100dvh-15rem)] md:overflow-y-auto md:p-1'}>
      {group.orders.map((order) => <li key={order.id}><OrderCard order={order} now={now} pending={pending(order.id)} compact={column} onOpen={onOpen} registerOpener={registerOpener} /></li>)}
    </ul> : <p className={`text-sm text-monu-text/80 ${column ? 'p-3' : ''}`}>{emptyMessage}</p>}
    {/* En celular la lista usa el scroll de la página: este atajo evita volver a subir a mano. */}
    {!column && group.count > 3 && onBackToStates && <button type="button" onClick={onBackToStates} className={`${buttonClass} md:hidden w-full inline-flex items-center justify-center gap-2`}><ArrowUp aria-hidden="true" className="h-4 w-4" />Volver a los estados</button>}
  </section>;
}

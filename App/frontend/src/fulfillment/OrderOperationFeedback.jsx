// Avisos flotantes del resultado de las operaciones de pedidos (éxito o error)
// y apertura del detalle del pedido para revisar uno que falló.
import { lazy, Suspense, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useData } from '../shared/store/DataContext';
import { buttonClass } from './operationUi';

// El detalle se carga solo cuando hace falta revisar un pedido.
const OrderDetail = lazy(() => import('./OrderDetail'));

/** Pila de avisos de operaciones de pedidos y diálogo de recuperación del pedido elegido. */
export default function OrderOperationFeedback() {
  const { user } = useAuth();
  const { orderOperations = [], dismissOrderOperation } = useData();
  const [recovery, setRecovery] = useState(null);
  return <>
    <aside aria-label="Acciones de pedidos" className="fixed bottom-4 right-4 z-40 w-[calc(100%_-_2rem)] max-w-sm max-h-[40dvh] overflow-y-auto space-y-2 pointer-events-none">
      {/* Un aviso por operación terminada (las silenciosas solo si fallaron) */}
      {orderOperations.filter((entry) => entry.status !== 'pending' && (!entry.silent || entry.status === 'error')).map((entry) => <div key={entry.id} role={entry.status === 'error' ? 'alert' : 'status'} className={`pointer-events-auto rounded-xl border p-3 shadow-md text-sm ${entry.status === 'error' ? 'border-red-200 bg-red-50 text-red-900' : 'border-monu-green/20 bg-monu-bone text-monu-dark'}`}>
        <p className="font-bold">Pedido #{entry.number || entry.id}</p><p className="break-words">{entry.message}</p>
        {entry.status !== 'pending' && <div className="flex gap-2 mt-2">
          {entry.status === 'error' && <button type="button" onClick={() => setRecovery({ id: entry.id, owner: user })} className={buttonClass}>Revisar pedido</button>}
          <button type="button" onClick={() => dismissOrderOperation(entry.id)} className={buttonClass} aria-label={`Cerrar aviso del pedido #${entry.number || entry.id}`}>Cerrar aviso</button>
        </div>}
      </div>)}
    </aside>
    {/* Detalle para revisar el pedido; solo si sigue siendo el mismo usuario que lo pidió */}
    {recovery?.owner === user && recovery?.id && <Suspense fallback={<p role="status" className="fixed bottom-4 left-4 z-40 rounded-xl bg-monu-bone p-3">Abriendo pedido...</p>}><OrderDetail key={recovery.id} id={recovery.id} requireFresh onClose={() => setRecovery(null)} /></Suspense>}
  </>;
}

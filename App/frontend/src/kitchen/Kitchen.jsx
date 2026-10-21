import { useEffect, useState } from 'react';
import { Clock, CheckCircle } from 'lucide-react';
import { useData } from '../shared/store/DataContext';
import { ageMinutes, dateTime } from '../fulfillment/orderModel';
import { createOrderCommands } from '../fulfillment/orderCommands';
import { apiFetch } from '../shared/api/http';
import { buttonClass, DataError } from '../fulfillment/operationUi';
import OrderDetail from '../fulfillment/OrderDetail';
const commands = createOrderCommands(apiFetch);

export default function Kitchen() {
  const { state, startOrderOperation, orderOperationPending, refreshOrders, watchOrders } = useData();
  useEffect(() => watchOrders?.(), [watchOrders]);
  const [now, setNow] = useState(() => Date.now());
  const [selected, setSelected] = useState(null);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(timer); }, []);
  const orders = state.orders.filter((order) => ['CONFIRMADO', 'EN_PREPARACION'].includes(order.estado))
    .sort((a, b) => Date.parse(a.preparacion_en || a.confirmado_en || a.date) - Date.parse(b.preparacion_en || b.confirmado_en || b.date));
  const markReady = (order) => startOrderOperation({ id: order.id, number: order.number,
    operation: () => commands.state(order, { estado: 'LISTO' }, 'Cocina confirma preparación terminada'),
    optimisticOrder: { ...order.detail, estado: 'LISTO' },
    success: order.tipo_entrega === 'RETIRO' ? 'Listo para retirar.' : 'Listo para reparto.',
  });
  return <div className="space-y-6">
    <div className="flex flex-wrap justify-between items-start gap-3"><div><h1 className="text-3xl font-extrabold font-heading text-monu-dark">Cocina / KDS</h1><p className="text-monu-text/80">Comandas confirmadas y en preparación, ordenadas por su fecha real.</p></div><button type="button" onClick={() => { void refreshOrders(undefined, true).catch(() => undefined); }} className={buttonClass}>Actualizar cocina</button></div>
    <DataError message={state.ordersError} />
    {state.ordersStatus === 'loading' && <p role="status">Consultando comandas...</p>}
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
      {orders.map((order) => { const age = ageMinutes(order.preparacion_en || order.confirmado_en, now); return <article key={order.id} className="bg-white rounded-2xl shadow-monu overflow-hidden border border-monu-green/20">
        <div className="p-4 bg-monu-dark text-white space-y-2"><h2 className="font-extrabold text-xl">Pedido #{order.number}</h2><p className="flex items-center gap-2 text-sm"><Clock aria-hidden="true" className="w-4 h-4" />{order.estado === 'CONFIRMADO' ? 'Confirmado: pendiente de iniciar cocina' : 'En preparación'} · {age == null ? 'Sin fecha registrada' : `${age} min`}</p><p className="text-sm">{dateTime(order.preparacion_en || order.confirmado_en)}</p></div>
        <div className="p-5 space-y-4"><p className="font-bold">{order.tipo_entrega === 'RETIRO' ? 'Retiro en local' : 'Delivery'}</p><ul className="space-y-3 font-bold">{order.items.map((item, index) => <li key={index} className="border-b border-monu-green/10 pb-2 break-words">{item}</li>)}</ul>{order.observaciones && <p className="text-sm break-words">{order.observaciones}</p>}
          <button type="button" disabled={orderOperationPending(order.id)} onClick={() => setSelected(order.id)} className={`${buttonClass} w-full`}>Detalle y acciones</button>
          {order.estado === 'EN_PREPARACION' && <button type="button" disabled={orderOperationPending(order.id)} onClick={() => { markReady(order); }} className={`${buttonClass} w-full bg-monu-green text-white flex gap-2 items-center justify-center`}><CheckCircle aria-hidden="true" className="w-5 h-5" />{order.tipo_entrega === 'RETIRO' ? 'Listo para retirar' : 'Listo para reparto'}</button>}
        </div>
      </article>; })}
    </div>
    {orders.length === 0 && state.ordersStatus === 'ready' && <p className="text-center py-12">No hay comandas confirmadas ni en preparación.</p>}
    {selected && <OrderDetail key={selected} id={selected} onClose={() => setSelected(null)} />}
  </div>;
}

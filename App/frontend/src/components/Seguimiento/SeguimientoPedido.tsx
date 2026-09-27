// src/components/Seguimiento/SeguimientoPedido.tsx
import type { Pedido } from "../../types/order";

interface SeguimientoPedidoProps {
    pedido: Pedido;
}

export function SeguimientoPedido({ pedido }: SeguimientoPedidoProps) {
    return (
    <div className="flex flex-col gap-5">
        <div>
        <p className="font-inter text-xs text-stone-400">
            {new Date(pedido.fechaHora).toLocaleString("es-AR")}
        </p>
        </div>

        <section>
        <h3 className="font-jakarta font-semibold text-sm text-stone-800 mb-2">Productos</h3>
        <ul className="flex flex-col gap-2">
            {pedido.items.map((item) => (
            <li key={item.id} className="flex justify-between text-sm font-inter text-stone-600">
                <span>{item.cantidad}x {item.producto.nombre}</span>
              <span>${(item.precioUnitario * item.cantidad).toLocaleString("es-AR")}</span>
            </li>
            ))}
        </ul>
        </section>

        <section className="flex justify-between text-sm font-inter text-stone-600">
        <span>Método de pago</span>
        <span className="font-medium text-stone-800">{pedido.metodoPago}</span>
        </section>

        <section className="flex justify-between items-start text-sm font-inter text-stone-600 gap-4">
        <span className="shrink-0">Entrega</span>
        <span className="font-medium text-stone-800 text-right">
            {pedido.entrega.puntoEncuentro ?? pedido.entrega.direccionOriginal}
        </span>
        </section>

        <div className="flex justify-between items-center pt-3 border-t border-stone-100">
        <span className="font-inter text-stone-500 text-sm">Total</span>
        <span className="font-jakarta font-bold text-lg text-stone-900">
            ${pedido.total.toLocaleString("es-AR")}
        </span>
        </div>

        <section>
        <h3 className="font-jakarta font-semibold text-sm text-stone-800 mb-3">Seguimiento</h3>
        <ol className="flex flex-col gap-3">
            {pedido.historial.map((paso, idx) => (
            <li key={idx} className="flex items-start gap-3">
                <span className="w-2.5 h-2.5 rounded-full bg-verde-monu mt-1 shrink-0" />
                <div>
                <p className="font-inter text-sm font-medium text-stone-800">{paso.estado}</p>
                <p className="font-inter text-xs text-stone-400">
                    {new Date(paso.fechaHora).toLocaleString("es-AR")}
                </p>
                </div>
            </li>
            ))}
        </ol>
        </section>
    </div>
    );
}
// src/components/Seguimiento/MisPedidosDrawer.tsx
import { useState } from "react";
import { createPortal } from "react-dom";
import { usePedidos } from "../../context/PedidosContext";
import { Modal } from "../ui/Modal";
import { SeguimientoPedido } from "./SeguimientoPedido";
import type { Pedido } from "../../types/order";

interface MisPedidosDrawerProps {
    abierto: boolean;
    onCerrar: () => void;
}

export function MisPedidosDrawer({ abierto, onCerrar }: MisPedidosDrawerProps) {
    const { pedidos } = usePedidos();
    const [pedidoSeleccionado, setPedidoSeleccionado] = useState<Pedido | null>(null);

    if (!abierto) return null;

    return (
    <>
        {createPortal(
        <div className="fixed inset-0 z-50 flex justify-end">
            <div className="absolute inset-0 bg-carbon/60 backdrop-blur-sm" onClick={onCerrar} />

            <div className="relative w-full sm:max-w-md bg-white h-full shadow-xl flex flex-col">
            <div className="flex items-center justify-between px-5 pt-5 pb-3 shrink-0 border-b border-stone-100">
                <h2 className="font-jakarta font-bold text-lg text-stone-900">Mis pedidos</h2>
                <button
                type="button"
                onClick={onCerrar}
                className="w-8 h-8 flex items-center justify-center rounded-full bg-stone-100 hover:bg-stone-200 transition-colors"
                aria-label="Cerrar"
                >
                <svg className="w-4 h-4 text-stone-500" viewBox="0 0 16 16" fill="none">
                    <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
                </button>
            </div>

            <div className="overflow-y-auto flex-1 px-5 py-4">
                {pedidos.length === 0 ? (
                <p className="font-inter text-sm text-stone-400 text-center mt-10">
                    Todavía no hiciste ningún pedido.
                </p>
                ) : (
                <ul className="flex flex-col gap-2">
                    {pedidos.map((pedido) => (
                    <li key={pedido.numeroPedido}>
                        <button
                        type="button"
                        onClick={() => setPedidoSeleccionado(pedido)}
                        className="w-full flex items-center justify-between px-4 py-3 rounded-2xl border border-stone-200 hover:border-stone-300 transition-colors text-left"
                        >
                        <div>
                            <p className="font-jakarta font-semibold text-sm text-stone-900">
                            Pedido #{pedido.numeroPedido}
                            </p>
                            <p className="font-inter text-xs text-stone-400">
                            {new Date(pedido.fechaHora).toLocaleString("es-AR")}
                            </p>
                        </div>
                        <span className="font-inter text-xs font-medium text-verde-monu bg-verde-monu/10 px-2 py-1 rounded-full">
                            {pedido.estado}
                        </span>
                        </button>
                    </li>
                    ))}
                </ul>
                )}
            </div>
            </div>
        </div>,
        document.body
        )}

        <Modal
        abierto={pedidoSeleccionado !== null}
        onCerrar={() => setPedidoSeleccionado(null)}
        titulo={pedidoSeleccionado ? `Pedido #${pedidoSeleccionado.numeroPedido}` : ""}
        >
        {pedidoSeleccionado && <SeguimientoPedido pedido={pedidoSeleccionado} />}
        </Modal>
    </>
    );
}
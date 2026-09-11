// src/context/PedidosContext.tsx
import { createContext, useContext, useState } from "react";
import type { ReactNode } from "react";
import type { Pedido } from "../types/order";

interface PedidosContextValue {
    pedidos: Pedido[];
    agregarPedido: (pedido: Pedido) => void;
}

const PedidosContext = createContext<PedidosContextValue | undefined>(undefined);

export function PedidosProvider({ children }: { children: ReactNode }) {
    const [pedidos, setPedidos] = useState<Pedido[]>([]);

    const agregarPedido = (pedido: Pedido) => {
    setPedidos((prev) => [pedido, ...prev]);
    };

    return (
    <PedidosContext.Provider value={{ pedidos, agregarPedido }}>
        {children}
    </PedidosContext.Provider>
    );
}

export function usePedidos() {
    const context = useContext(PedidosContext);
    if (!context) {
    throw new Error("usePedidos debe usarse dentro de un PedidosProvider");
    }
    return context;
}
// src/context/CarritoContext.tsx
import { createContext, useContext, useReducer } from "react";
import type { ReactNode } from "react";
import type { Producto, PersonalizacionPayload } from "../types/product";
import type { CarritoItem } from "../types/cart";

type CarritoAction =
    | {
        type: "AGREGAR_ITEM";
        producto: Producto;
        personalizacion: PersonalizacionPayload;
        precioUnitario: number;
        cantidad: number;
    }
    | { type: "QUITAR_ITEM"; id: string }
    | { type: "ACTUALIZAR_CANTIDAD"; id: string; cantidad: number }
    | { type: "VACIAR_CARRITO" };

interface CarritoState {
    items: CarritoItem[];
}

function carritoReducer(state: CarritoState, action: CarritoAction): CarritoState {
    switch (action.type) {
    case "AGREGAR_ITEM": {
        const nuevoItem: CarritoItem = {
        id: crypto.randomUUID(),
        producto: action.producto,
        cantidad: action.cantidad,
        personalizacion: action.personalizacion,
        precioUnitario: action.precioUnitario,
        };
        return { items: [...state.items, nuevoItem] };
    }
    case "QUITAR_ITEM":
        return { items: state.items.filter((item) => item.id !== action.id) };
    case "ACTUALIZAR_CANTIDAD":
        return {
        items: state.items.map((item) =>
            item.id === action.id
            ? { ...item, cantidad: Math.max(1, action.cantidad) }
            : item
        ),
        };
    case "VACIAR_CARRITO":
        return { items: [] };
    default:
        return state;
    }
}

interface CarritoContextValue {
    items: CarritoItem[];
    agregarItem: (
    producto: Producto,
    personalizacion: PersonalizacionPayload,
    precioUnitario: number,
    cantidad?: number
    ) => void;
    quitarItem: (id: string) => void;
    actualizarCantidad: (id: string, cantidad: number) => void;
    vaciarCarrito: () => void;
    total: number;
    cantidadTotal: number;
}

const CarritoContext = createContext<CarritoContextValue | undefined>(undefined);

export function CarritoProvider({ children }: { children: ReactNode }) {
    const [state, dispatch] = useReducer(carritoReducer, { items: [] });

    const agregarItem = (
    producto: Producto,
    personalizacion: PersonalizacionPayload,
    precioUnitario: number,
    cantidad: number = 1
    ) => {
    dispatch({ type: "AGREGAR_ITEM", producto, personalizacion, precioUnitario, cantidad });
    };

    const quitarItem = (id: string) => dispatch({ type: "QUITAR_ITEM", id });

    const actualizarCantidad = (id: string, cantidad: number) =>
    dispatch({ type: "ACTUALIZAR_CANTIDAD", id, cantidad });

    const vaciarCarrito = () => dispatch({ type: "VACIAR_CARRITO" });

    const total = state.items.reduce(
    (acc, item) => acc + item.precioUnitario * item.cantidad,
    0
    );
    const cantidadTotal = state.items.reduce((acc, item) => acc + item.cantidad, 0);

    return (
    <CarritoContext.Provider
        value={{ items: state.items, agregarItem, quitarItem, actualizarCantidad, vaciarCarrito, total, cantidadTotal }}
    >
        {children}
    </CarritoContext.Provider>
    );
}

export function useCarrito() {
    const context = useContext(CarritoContext);
    if (!context) {
    throw new Error("useCarrito debe usarse dentro de un CarritoProvider");
    }
    return context;
}
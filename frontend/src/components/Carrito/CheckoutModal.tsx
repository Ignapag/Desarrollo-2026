// src/components/Carrito/CheckoutModal.tsx
import { useState } from "react";
import { Modal } from "../ui/Modal";
import { useCarrito } from "../../context/CarritoContext";
import { validarZonaCobertura } from "../../utils/zonas";
import { registrarPedido } from "../../services/pedidos";
import type { MetodoPago, Pedido, ZonaResultado } from "../../types/order";

interface CheckoutModalProps {
    abierto: boolean;
    onCerrar: () => void;
}

const METODOS_PAGO: MetodoPago[] = ["Efectivo", "Mercado Pago", "Cuenta DNI", "Naranja X"];

// TODO backend/Delivery: cuando exista el módulo real, este punto vendría
// calculado por el sistema (CU_DEL_02); por ahora es un valor fijo de ejemplo.
const PUNTO_ENCUENTRO_SUGERIDO = "Kiosco Don Pepe, esquina 12 y 60";

type Paso = "formulario" | "confirmando" | "exito";

export function CheckoutModal({ abierto, onCerrar }: CheckoutModalProps) {
    const { items, total, vaciarCarrito } = useCarrito();

    const [direccion, setDireccion] = useState("");
    const [zona, setZona] = useState<ZonaResultado | null>(null);
    const [puntoEncuentroAceptado, setPuntoEncuentroAceptado] = useState(false);
    const [metodoPago, setMetodoPago] = useState<MetodoPago | null>(null);
    const [paso, setPaso] = useState<Paso>("formulario");
    const [pedido, setPedido] = useState<Pedido | null>(null);

    const direccionValidada =
    zona !== null && zona !== "Fuera de zona" ? true : zona === "Fuera de zona" && puntoEncuentroAceptado;

    const puedeConfirmar = direccion.trim().length > 0 && direccionValidada && metodoPago !== null;

    const handleValidarDireccion = () => {
    const resultado = validarZonaCobertura(direccion);
    setZona(resultado);
    setPuntoEncuentroAceptado(false);
    };

    const handleConfirmar = async () => {
    if (!puedeConfirmar || !metodoPago || !zona) return;

    setPaso("confirmando");

    const nuevoPedido = await registrarPedido({
        items,
        total,
        metodoPago,
        entrega: {
        direccionOriginal: direccion,
        zona,
        puntoEncuentro: zona === "Fuera de zona" ? PUNTO_ENCUENTRO_SUGERIDO : undefined,
        direccionValidada,
        },
    });

    setPedido(nuevoPedido);
    setPaso("exito");
    vaciarCarrito();
    };

    const handleCerrar = () => {
    setDireccion("");
    setZona(null);
    setPuntoEncuentroAceptado(false);
    setMetodoPago(null);
    setPaso("formulario");
    setPedido(null);
    onCerrar();
    };

    if (paso === "exito" && pedido) {
    return (
        <Modal abierto={abierto} onCerrar={handleCerrar} titulo="¡Pedido confirmado!">
        <div className="flex flex-col items-center text-center gap-3 py-4">
            <div className="w-14 h-14 rounded-full bg-verde-monu/10 flex items-center justify-center">
            <svg className="w-7 h-7 text-verde-monu" viewBox="0 0 24 24" fill="none">
                <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            </div>
            <p className="font-inter text-sm text-stone-500">Tu pedido quedó registrado</p>
            <p className="font-jakarta font-bold text-2xl text-stone-900">#{pedido.numeroPedido}</p>
            <p className="font-inter text-sm text-stone-500">
            Total: <span className="font-semibold text-stone-800">${pedido.total.toLocaleString("es-AR")}</span>
            </p>
            <button
            type="button"
            onClick={handleCerrar}
            className="w-full mt-4 bg-naranja hover:bg-naranja/90 text-white font-inter font-semibold py-3 rounded-2xl transition-colors"
            >
            Listo
            </button>
        </div>
        </Modal>
    );
    }

    return (
    <Modal abierto={abierto} onCerrar={handleCerrar} titulo="Finalizar pedido">
        <div className="flex flex-col gap-5">
        <section>
            <label className="font-jakarta font-semibold text-sm text-stone-800 block mb-2">
            Dirección de entrega
            </label>
            <div className="flex gap-2">
            <input
                type="text"
                value={direccion}
                onChange={(e) => {
                setDireccion(e.target.value);
                setZona(null);
                setPuntoEncuentroAceptado(false);
                }}
                placeholder="Calle y número, barrio"
                className="flex-1 border border-stone-200 rounded-xl px-3 py-2 font-inter text-sm text-stone-700 focus:outline-none focus:border-naranja"
            />
            <button
                type="button"
                onClick={handleValidarDireccion}
                disabled={direccion.trim().length === 0}
                className="px-4 rounded-xl bg-stone-100 hover:bg-stone-200 disabled:opacity-50 font-inter text-sm font-medium text-stone-700 transition-colors"
            >
                Validar
            </button>
            </div>

            {zona && zona !== "Fuera de zona" && (
            <p className="font-inter text-xs text-verde-monu mt-2">
                ✓ Dentro de zona de cobertura ({zona})
            </p>
            )}

            {zona === "Fuera de zona" && !puntoEncuentroAceptado && (
            <div className="mt-3 bg-naranja/10 border border-naranja/30 rounded-2xl p-3 flex flex-col gap-2">
                <p className="font-inter text-xs text-stone-600">
                Tu dirección está fuera de la zona de cobertura. Te proponemos este punto de encuentro:
                </p>
                <p className="font-inter text-sm font-semibold text-stone-800">{PUNTO_ENCUENTRO_SUGERIDO}</p>
                <div className="flex gap-2 mt-1">
                <button
                    type="button"
                    onClick={() => setPuntoEncuentroAceptado(true)}
                    className="flex-1 bg-naranja text-white text-xs font-inter font-semibold py-2 rounded-xl"
                >
                    Aceptar punto
                </button>
                <button
                    type="button"
                    onClick={() => {
                    setDireccion("");
                    setZona(null);
                    }}
                    className="flex-1 bg-white border border-stone-200 text-stone-600 text-xs font-inter font-semibold py-2 rounded-xl"
                >
                    Probar otra dirección
                </button>
                </div>
            </div>
            )}

            {zona === "Fuera de zona" && puntoEncuentroAceptado && (
            <p className="font-inter text-xs text-verde-monu mt-2">
                ✓ Punto de encuentro aceptado: {PUNTO_ENCUENTRO_SUGERIDO}
            </p>
            )}
        </section>

        <section>
            <label className="font-jakarta font-semibold text-sm text-stone-800 block mb-2">
            Método de pago
            </label>
            <div className="grid grid-cols-2 gap-2">
            {METODOS_PAGO.map((metodo) => (
                <button
                key={metodo}
                type="button"
                onClick={() => setMetodoPago(metodo)}
                className={`px-3 py-2 rounded-xl border text-sm font-inter transition-colors ${
                    metodoPago === metodo
                    ? "bg-naranja/10 border-naranja text-naranja font-semibold"
                    : "bg-white border-stone-200 text-stone-600"
                }`}
                >
                {metodo}
                </button>
            ))}
            </div>
        </section>

        <div className="flex justify-between items-center pt-2 border-t border-stone-100">
            <span className="font-inter text-stone-500 text-sm">Total a pagar</span>
            <span className="font-jakarta font-bold text-xl text-stone-900">
            ${total.toLocaleString("es-AR")}
            </span>
        </div>

        <button
            type="button"
            onClick={handleConfirmar}
            disabled={!puedeConfirmar || paso === "confirmando"}
            className="w-full bg-naranja hover:bg-naranja/90 disabled:opacity-40 disabled:cursor-not-allowed text-white font-inter font-semibold py-3.5 rounded-2xl transition-colors"
        >
            {paso === "confirmando" ? "Confirmando..." : "Confirmar pedido"}
        </button>
        </div>
    </Modal>
    );
}
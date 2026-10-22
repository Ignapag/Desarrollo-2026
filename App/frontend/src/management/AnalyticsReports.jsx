import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { unidadesPorDia } from './datosPanel';
import { fecha, tarjeta } from './analyticsModel';

const cantidad = new Intl.NumberFormat('es-AR');
const moneda = new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS' });
const porcentaje = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 2 });
const pesos = (valor) => moneda.format(Number(valor));
const celda = 'py-3 px-2 align-top border-b border-monu-green/10';

function Tabla({ titulo, columnas, filas }) {
  return <div role="region" aria-label={titulo} tabIndex={0} className="overflow-x-auto rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-monu-green">
    <table className="w-full text-left text-sm">
      <caption className="sr-only">{titulo}</caption>
      <thead><tr>{columnas.map((columna) => <th key={columna} scope="col" className={`${celda} font-bold text-monu-dark`}>{columna}</th>)}</tr></thead>
      <tbody>{filas.map(({ id, valores }) => <tr key={id}>{valores.map((valor, indice) => indice === 0 ? <th key={indice} scope="row" className={`${celda} font-medium`}>{valor}</th> : <td key={indice} className={`${celda} tabular-nums`}>{valor}</td>)}</tr>)}</tbody>
    </table>
  </div>;
}

export function AnalyticsReports({ datos: { resumen, ventas, rentabilidad }, financieros }) {
  // Los días sin filas no se interpolan: el gráfico describe solo días con ventas.
  const dias = [...new Set(ventas.map((venta) => venta.periodo))].sort().map((dia) => ({ fecha: dia, nombre: fecha(dia) }));
  const serie = unidadesPorDia(dias, ventas);
  const unidades = serie.reduce((total, dia) => total + dia.unidades, 0);
  const pedidosProducto = new Map();
  for (const venta of ventas) {
    if (venta.cantidad_pedidos != null) pedidosProducto.set(venta.producto_id, (pedidosProducto.get(venta.producto_id) || 0) + venta.cantidad_pedidos);
  }
  const ranking = resumen.ranking_productos;
  const hayPedidos = !financieros && ventas.length > 0 && ventas.every((venta) => venta.cantidad_pedidos != null);
  return <div className="space-y-6 text-monu-text">
    <p className="text-sm text-monu-text/80">Ventas: pedidos confirmados, sin cancelados, según su fecha de confirmación. Las unidades suman las cantidades de sus productos.</p>
    <div className="grid gap-4 sm:grid-cols-2">
      <article className={tarjeta}><h2 className="text-sm font-bold text-monu-dark">Unidades vendidas</h2><p className="mt-2 text-3xl font-extrabold text-monu-dark tabular-nums">{cantidad.format(unidades)}</p><p className="mt-2 text-sm text-monu-text/80">En el período consultado.</p></article>
      {financieros && resumen.ingreso_neto_confirmado != null && <article className={tarjeta}>
        <h2 className="text-sm font-bold text-monu-dark">Cobros netos conciliados</h2><p className="mt-2 text-3xl font-extrabold text-monu-dark break-words tabular-nums">{pesos(resumen.ingreso_neto_confirmado)}</p>
        <p className="mt-2 text-sm text-monu-text/80">Cobros menos devoluciones, por fecha de conciliación. Excluye propinas; puede diferir de las ventas.</p>
        {resumen.ingresos_por_metodo.length > 0 && <dl className="mt-4 space-y-2">{resumen.ingresos_por_metodo.map((metodo) => <div key={metodo.metodo_pago} className="flex flex-wrap justify-between gap-x-4 text-sm"><dt>{metodo.metodo_pago}</dt><dd className="tabular-nums">{pesos(metodo.ingreso_neto)}</dd></div>)}</dl>}
      </article>}
    </div>
    {!ventas.length && <p role="status" className={tarjeta}>No hay ventas confirmadas en este período. Podés consultar otras fechas.</p>}
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <section className={tarjeta} aria-labelledby="ventas-titulo">
        <h2 id="ventas-titulo" className="font-bold text-lg text-monu-dark">Ventas en el tiempo · Unidades</h2>
        {serie.length ? <>
          <p className="mt-2 text-sm text-monu-text/80">Se muestran los días con ventas. Los valores se pueden consultar en la tabla.</p>
          <div aria-hidden="true" className="h-64 mt-4 min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart accessibilityLayer={false} data={serie} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-monu-cream)" />
                <XAxis dataKey="nombre" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip formatter={(valor) => [cantidad.format(valor), 'Unidades']} />
                <Area type="linear" dataKey="unidades" stroke="var(--color-monu-green)" fill="var(--color-monu-green)" fillOpacity={0.12} strokeWidth={3} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <details className="mt-4"><summary className="min-h-11 py-3 font-bold text-monu-green">Ver tabla diaria</summary>
            <Tabla titulo="Unidades vendidas por día" columnas={['Fecha de confirmación', 'Unidades']} filas={serie.map((dia) => ({ id: dia.fecha, valores: [dia.nombre, cantidad.format(dia.unidades)] }))} />
          </details>
        </> : <p className="mt-4 text-monu-text/80">Sin unidades vendidas para graficar.</p>}
      </section>
      <section className={tarjeta} aria-labelledby="ranking-titulo">
        <h2 id="ranking-titulo" className="font-bold text-lg text-monu-dark">Productos más vendidos</h2>
        {ranking.length ? <>
          <p className="my-3 text-sm text-monu-text/80">Ordenados por unidades vendidas en todo el período.</p>
          <Tabla titulo="Ranking de productos más vendidos" columnas={['Producto', 'Unidades', ...(hayPedidos ? ['Pedidos con este producto'] : [])]} filas={ranking.map((producto) => ({ id: producto.producto_id, valores: [<span key="producto" className="break-words">{producto.ranking}. {producto.producto}<span aria-hidden="true" className="block mt-2 h-1.5 rounded-full bg-monu-cream"><span className="block h-full rounded-full bg-monu-orange" style={{ width: `${ranking[0].cantidad_vendida ? producto.cantidad_vendida / ranking[0].cantidad_vendida * 100 : 0}%` }} /></span></span>, cantidad.format(producto.cantidad_vendida), ...(hayPedidos ? [pedidosProducto.has(producto.producto_id) ? cantidad.format(pedidosProducto.get(producto.producto_id)) : '—'] : [])] }))} />
          {hayPedidos && <p className="mt-3 text-sm text-monu-text/80">Un pedido puede incluir varios productos. Estos conteos por producto no se suman para obtener pedidos únicos.</p>}
        </> : <p className="mt-4 text-monu-text/80">Sin productos vendidos en este período.</p>}
      </section>
    </div>
    {financieros && <>
      <section className={tarjeta} aria-labelledby="importes-titulo">
        <h2 id="importes-titulo" className="font-bold text-lg text-monu-dark">Importes de ventas por producto y día</h2>
        <p className="my-3 text-sm text-monu-text/80">Subtotales de ítems de pedidos confirmados a precios históricos. No representan cobros; no incluyen envío ni propinas. Importes en pesos argentinos (ARS).</p>
        {ventas.length ? <Tabla titulo="Importes vendidos por producto y día" columnas={['Fecha de confirmación', 'Producto', 'Unidades', 'Importe vendido']} filas={ventas.map((venta) => ({ id: `${venta.periodo}-${venta.producto_id}`, valores: [fecha(venta.periodo), venta.producto, cantidad.format(venta.cantidad_vendida), venta.monto_total != null ? pesos(venta.monto_total) : 'No disponible'] }))} /> : <p>Sin importes de ventas en este período.</p>}
      </section>
      <section className={tarjeta} aria-labelledby="rentabilidad-titulo">
        <h2 id="rentabilidad-titulo" className="font-bold text-lg text-monu-dark">Rentabilidad estimada</h2>
        <p className="my-3 text-sm text-monu-text/80">Precios históricos de venta y costos actuales de insumos de la receta. No es ganancia histórica exacta ni incluye otros gastos. Un costo cero puede corresponder a un costo sin cargar. Importes en ARS.</p>
        {rentabilidad?.length ? <Tabla titulo="Rentabilidad estimada por producto" columnas={['Producto', 'Unidades', 'Ingreso estimado', 'Costo estimado', 'Margen estimado', 'Margen (%)']} filas={rentabilidad.map((fila) => ({ id: fila.producto_id, valores: [fila.producto, cantidad.format(fila.unidades_vendidas), pesos(fila.ingreso_estimado), pesos(fila.costo_estimado), pesos(fila.margen_estimado), `${porcentaje.format(Number(fila.porcentaje_margen))} %`] }))} /> : <p>Sin resultados de rentabilidad estimada en este período.</p>}
      </section>
    </>}
  </div>;
}

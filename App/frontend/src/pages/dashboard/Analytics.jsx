import { BarChart2, PieChart, TrendingUp } from 'lucide-react';
export default function Analytics() {
  return (
    <div className='space-y-6'>
      <h1 className='text-3xl font-extrabold font-heading text-monu-dark'>Reportes y Analítica</h1>
      <p className='text-monu-text/70'>Rendimiento de ventas y métricas clave.</p>
      <div className='grid grid-cols-1 md:grid-cols-2 gap-6'>
        <div className='bg-white p-6 rounded-2xl shadow-sm border border-monu-green/10 h-64 flex flex-col justify-center items-center text-monu-text/50'>
          <BarChart2 className='w-12 h-12 mb-4 opacity-50'/>
          <p>Gráfico de Ventas Mensuales</p>
        </div>
        <div className='bg-white p-6 rounded-2xl shadow-sm border border-monu-green/10 h-64 flex flex-col justify-center items-center text-monu-text/50'>
          <PieChart className='w-12 h-12 mb-4 opacity-50'/>
          <p>Productos más vendidos</p>
        </div>
      </div>
    </div>
  );
}

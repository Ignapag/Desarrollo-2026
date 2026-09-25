import { DollarSign, TrendingUp, Users, ShoppingBag } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';

const dataVentas = [
  { name: 'Lun', total: 150000 },
  { name: 'Mar', total: 180000 },
  { name: 'Mié', total: 120000 },
  { name: 'Jue', total: 245500 },
  { name: 'Vie', total: 310000 },
  { name: 'Sáb', total: 450000 },
  { name: 'Dom', total: 380000 },
];

const dataProductos = [
  { name: 'Monu Clásica', ventas: 145 },
  { name: 'Doble Cheddar', ventas: 210 },
  { name: 'Smash Onion', ventas: 110 },
  { name: 'Papas Monu', ventas: 280 },
];

export default function ControlPanel() {
  const stats = [
    { label: 'Ventas del Día', value: '$245.500', trend: '+12.5%', icon: DollarSign, color: 'text-monu-green', bg: 'bg-monu-green/10' },
    { label: 'Pedidos Completados', value: '48', trend: '+5.2%', icon: ShoppingBag, color: 'text-monu-orange', bg: 'bg-monu-orange/10' },
    { label: 'Nuevos Clientes', value: '12', trend: '+18.1%', icon: Users, color: 'text-monu-dark', bg: 'bg-monu-dark/10' },
    { label: 'Crecimiento', value: '+24%', trend: 'Mensual', icon: TrendingUp, color: 'text-monu-burnt', bg: 'bg-monu-burnt/10' }
  ];

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-extrabold font-heading text-monu-dark mb-1">Panel de Control</h1>
          <p className="text-monu-text/70">Métricas y resumen operativo general.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat, i) => (
          <div key={i} className="bg-monu-bone rounded-2xl p-6 shadow-sm border border-monu-green/5">
            <div className="flex justify-between items-start mb-4">
              <div className={`p-3 rounded-xl ${stat.bg}`}>
                <stat.icon className={`w-6 h-6 ${stat.color}`} />
              </div>
              <span className={`text-sm font-bold ${stat.trend.startsWith('+') ? 'text-monu-green' : 'text-monu-text/70'}`}>
                {stat.trend}
              </span>
            </div>
            <h3 className="text-3xl font-extrabold text-monu-dark mb-1">{stat.value}</h3>
            <p className="text-sm font-bold text-monu-text/70">{stat.label}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-monu-bone rounded-2xl p-6 shadow-sm border border-monu-green/5 h-[400px] flex flex-col">
          <h3 className="font-bold text-monu-dark mb-6">Gráfico de Ventas (Última Semana)</h3>
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={dataVentas} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#1C5A3F" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#1C5A3F" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#6b7280' }} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#6b7280' }} tickFormatter={(value) => `$${value/1000}k`} />
                <Tooltip 
                  contentStyle={{ borderRadius: '1rem', border: 'none', boxShadow: '0 10px 25px -5px rgba(0,0,0,0.1)' }}
                  formatter={(value) => [`$${value.toLocaleString()}`, 'Ventas']}
                />
                <Area type="monotone" dataKey="total" stroke="#1C5A3F" strokeWidth={3} fillOpacity={1} fill="url(#colorTotal)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-monu-bone rounded-2xl p-6 shadow-sm border border-monu-green/5 h-[400px] flex flex-col">
          <h3 className="font-bold text-monu-dark mb-6">Productos Más Vendidos</h3>
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dataProductos} layout="vertical" margin={{ top: 0, right: 0, left: 20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e5e7eb" />
                <XAxis type="number" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#6b7280' }} />
                <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#191C1A', fontWeight: 'bold' }} width={100} />
                <Tooltip 
                  cursor={{ fill: '#f3f4f6' }}
                  contentStyle={{ borderRadius: '1rem', border: 'none', boxShadow: '0 10px 25px -5px rgba(0,0,0,0.1)' }}
                />
                <Bar dataKey="ventas" fill="#E85D2C" radius={[0, 4, 4, 0]} barSize={24} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}

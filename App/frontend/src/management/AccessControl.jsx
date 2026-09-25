import { ShieldCheck, Users, Key } from 'lucide-react';
export default function AccessControl() {
  return (
    <div className='space-y-6'>
      <h1 className='text-3xl font-extrabold font-heading text-monu-dark'>Control de Acceso</h1>
      <p className='text-monu-text/70'>Administración de roles y permisos del sistema.</p>
      <div className='bg-white p-6 rounded-2xl shadow-sm border border-monu-green/10'>
        <div className='flex items-center gap-4 mb-4 pb-4 border-b border-monu-green/10'>
          <div className='w-12 h-12 bg-monu-green/10 rounded-xl flex items-center justify-center'><Users className='text-monu-green'/></div>
          <div><h3 className='font-bold text-monu-dark'>Usuarios Activos</h3><p className='text-sm text-monu-text/70'>3 Administradores, 12 Repartidores</p></div>
        </div>
        <div className='flex items-center gap-4'>
          <div className='w-12 h-12 bg-monu-orange/10 rounded-xl flex items-center justify-center'><Key className='text-monu-orange'/></div>
          <div><h3 className='font-bold text-monu-dark'>Roles del Sistema</h3><p className='text-sm text-monu-text/70'>Configuración de permisos por módulo</p></div>
        </div>
      </div>
    </div>
  );
}

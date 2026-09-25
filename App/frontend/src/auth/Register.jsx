import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useAuth } from './AuthContext';
import { Eye, EyeOff, ArrowRight } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

const schema = z.object({
  name: z.string().min(2, { message: "Ingres� tu nombre" }),
  email: z.string().email({ message: "Correo inv�lido" }),
  password: z.string().min(6, { message: "Al menos 6 caracteres" })
});

export default function Register() {
  const { register: registerUser } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const { register, handleSubmit, formState: { errors } } = useForm({
    resolver: zodResolver(schema)
  });

  const onSubmit = (data) => {
    registerUser(data.name, data.email, data.password);
  };

  return (
    <div className="min-h-screen bg-[#eadecd] flex items-center justify-center p-4">
      <div className="bg-white max-w-[348px] w-full rounded-3xl shadow-monu overflow-hidden">
        
        {/* Header simple */}
        <div className="w-full h-[80px] bg-[#f4e6b1] flex items-center justify-center border-b-4 border-b-[#F6B42C]">
            <h1 className="text-3xl font-extrabold font-heading text-[#003c30]">
              REGISTRO
            </h1>
        </div>

        <div className="px-8 pb-8 pt-6">
          <div className="text-center mb-6">
            <h2 className="text-xl font-extrabold text-[#003c30] mb-1">
              Cre� tu cuenta
            </h2>
            <p className="text-[13px] text-gray-500">Complet� tus datos para empezar a pedir.</p>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="block text-[13px] font-bold text-[#003c30] mb-1.5">Nombre Completo</label>
              <input 
                type="text" 
                {...register('name')}
                className={`w-full px-4 py-2.5 rounded-xl bg-white border ${errors.name ? 'border-red-500' : 'border-gray-200'} focus:outline-none focus:border-[#d95123] transition-all text-sm`}
                placeholder="Juan P�rez"
              />
              {errors.name && <p className="text-red-500 text-xs mt-1 font-medium">{errors.name.message}</p>}
            </div>

            <div>
              <label className="block text-[13px] font-bold text-[#003c30] mb-1.5">Correo Electr�nico</label>
              <input 
                type="email" 
                {...register('email')}
                className={`w-full px-4 py-2.5 rounded-xl bg-white border ${errors.email ? 'border-red-500' : 'border-gray-200'} focus:outline-none focus:border-[#d95123] transition-all text-sm`}
                placeholder="juan@ejemplo.com"
              />
              {errors.email && <p className="text-red-500 text-xs mt-1 font-medium">{errors.email.message}</p>}
            </div>

            <div>
              <label className="block text-[13px] font-bold text-[#003c30] mb-1.5">Contrase�a</label>
              <div className="relative">
                <input 
                  type={showPassword ? "text" : "password"} 
                  {...register('password')}
                  className={`w-full pl-4 pr-10 py-2.5 rounded-xl bg-white border ${errors.password ? 'border-red-500' : 'border-gray-200'} focus:outline-none focus:border-[#d95123] transition-all text-sm`}
                  placeholder="��������"
                />
                <button 
                  type="button" 
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-3 text-gray-400 hover:text-gray-600 transition"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {errors.password && <p className="text-red-500 text-xs mt-1 font-medium">{errors.password.message}</p>}
            </div>

            <button 
              type="submit" 
              className="w-full bg-[#e85d2c] hover:bg-[#d95123] text-white py-3 rounded-xl font-bold text-[15px] flex items-center justify-center gap-2 transition-all shadow-sm group mt-6"
            >
              Crear Cuenta <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </button>
          </form>

          <div className="mt-5 text-center text-[13px]">
            <p className="text-gray-600">
              �Ya ten�s cuenta? <Link to="/login" className="text-[#a83311] font-bold hover:underline">Inici� Sesi�n</Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

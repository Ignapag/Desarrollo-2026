import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useAuth } from '../../context/AuthContext';
import { Eye, EyeOff, ArrowRight } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

const schema = z.object({
  email: z.string().email({ message: "Correo inválido" }),
  password: z.string().min(6, { message: "La contraseña debe tener al menos 6 caracteres" })
});

export default function Login() {
  const { login } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const { register, handleSubmit, formState: { errors } } = useForm({
    resolver: zodResolver(schema)
  });

  const onSubmit = (data) => {
    login(data.email, data.password);
  };

  return (
    <div className="min-h-screen bg-[#eadecd] flex items-center justify-center p-4">
      <div className="bg-white max-w-[348px] w-full rounded-3xl shadow-monu overflow-hidden">
        
        {/* Header con imagen exacta cortada */}
        <div className="w-full h-[155px] overflow-hidden relative bg-[#f4e6b1]">
          <img 
            src="/login-original.png" 
            alt="Login Header" 
            className="absolute top-[-18px] left-[-16px] w-[378px] max-w-none"
            style={{ objectFit: 'cover' }}
          />
        </div>

        <div className="px-8 pb-8 pt-4">
          <div className="text-center mb-6">
            <h2 className="text-xl font-extrabold text-[#003c30] mb-1">
              Bienvenido
            </h2>
            <p className="text-[13px] text-gray-500">Introducí tus credenciales para continuar.</p>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="block text-[13px] font-bold text-[#003c30] mb-1.5">Correo Electrónico</label>
              <input 
                type="email" 
                {...register('email')}
                className={`w-full px-4 py-2.5 rounded-xl bg-white border ${errors.email ? 'border-red-500' : 'border-gray-200'} focus:outline-none focus:border-[#d95123] transition-all text-sm`}
                placeholder="admin@monuburger.com"
              />
              {errors.email && <p className="text-red-500 text-xs mt-1 font-medium">{errors.email.message}</p>}
            </div>

            <div>
              <label className="block text-[13px] font-bold text-[#003c30] mb-1.5">Contraseña</label>
              <div className="relative">
                <input 
                  type={showPassword ? "text" : "password"} 
                  {...register('password')}
                  className={`w-full pl-4 pr-10 py-2.5 rounded-xl bg-white border ${errors.password ? 'border-red-500' : 'border-gray-200'} focus:outline-none focus:border-[#d95123] transition-all text-sm`}
                  placeholder="••••••••"
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

            <div className="flex justify-between items-center text-[12px] pt-1">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" className="w-3.5 h-3.5 rounded border-gray-300 text-[#d95123] focus:ring-[#d95123]" />
                <span className="text-gray-600">Recordarme</span>
              </label>
              <Link to="/recover-password" className="text-[#a83311] hover:text-[#d95123] transition font-bold">¿Olvidaste tu contraseña?</Link>
            </div>

            <button 
              type="submit" 
              className="w-full bg-[#e85d2c] hover:bg-[#d95123] text-white py-3 rounded-xl font-bold text-[15px] flex items-center justify-center gap-2 transition-all shadow-sm group mt-4"
            >
              Iniciar Sesión <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </button>
          </form>

          <div className="mt-5 text-center text-[13px]">
            <p className="text-gray-600">
              ¿No tenés cuenta? <Link to="/register" className="text-[#a83311] font-bold hover:underline">Registrate</Link>
            </p>
          </div>

          <div className="mt-6 pt-5 border-t border-gray-100 flex justify-center gap-4 text-[11px] font-bold text-gray-500">
            <a href="#" className="hover:text-gray-800 transition">Términos</a>
            <a href="#" className="hover:text-gray-800 transition">Privacidad</a>
            <a href="#" className="hover:text-gray-800 transition">Soporte Técnico</a>
          </div>
        </div>
      </div>
    </div>
  );
}

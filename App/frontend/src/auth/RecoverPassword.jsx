import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CheckCircle } from 'lucide-react';

const schema = z.object({
  email: z.string().email({ message: "Correo inválido" })
});

export default function RecoverPassword() {
  const [isSent, setIsSent] = useState(false);
  const { register, handleSubmit, formState: { errors } } = useForm({
    resolver: zodResolver(schema)
  });

  const onSubmit = (data) => {
    // Simulated recovery
    setIsSent(true);
  };

  return (
    <div className="min-h-screen bg-[#eadecd] flex items-center justify-center p-4">
      <div className="bg-white max-w-[348px] w-full rounded-3xl shadow-monu overflow-hidden">
        
        {/* Header simple */}
        <div className="w-full h-[80px] bg-[#f4e6b1] flex items-center justify-center border-b-4 border-b-[#F6B42C]">
            <h1 className="text-2xl font-extrabold font-heading text-[#003c30]">
              RECUPERAR CLAVE
            </h1>
        </div>

        <div className="px-8 pb-8 pt-6">
          {isSent ? (
            <div className="text-center animate-in fade-in duration-300">
              <CheckCircle className="w-16 h-16 text-[#1C5A3F] mx-auto mb-4" />
              <h2 className="text-xl font-extrabold text-[#003c30] mb-2">¡Correo Enviado!</h2>
              <p className="text-[13px] text-gray-500 mb-6">Revisá tu bandeja de entrada o spam para restablecer tu contraseña.</p>
              <Link to="/login" className="w-full bg-[#003c30] hover:bg-[#1C5A3F] text-white py-3 rounded-xl font-bold text-[15px] flex items-center justify-center transition-all shadow-sm">
                Volver al Login
              </Link>
            </div>
          ) : (
            <>
              <div className="text-center mb-6">
                <h2 className="text-xl font-extrabold text-[#003c30] mb-1">
                  ¿Te olvidaste?
                </h2>
                <p className="text-[13px] text-gray-500">Ingresá tu correo y te enviaremos las instrucciones.</p>
              </div>

              <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                <div>
                  <label className="block text-[13px] font-bold text-[#003c30] mb-1.5">Correo Electrónico</label>
                  <input 
                    type="email" 
                    {...register('email')}
                    className={`w-full px-4 py-2.5 rounded-xl bg-white border ${errors.email ? 'border-red-500' : 'border-gray-200'} focus:outline-none focus:border-[#d95123] transition-all text-sm`}
                    placeholder="juan@ejemplo.com"
                  />
                  {errors.email && <p className="text-red-500 text-xs mt-1 font-medium">{errors.email.message}</p>}
                </div>

                <button 
                  type="submit" 
                  className="w-full bg-[#e85d2c] hover:bg-[#d95123] text-white py-3 rounded-xl font-bold text-[15px] flex items-center justify-center gap-2 transition-all shadow-sm group mt-6"
                >
                  Enviar Instrucciones <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </button>
              </form>

              <div className="mt-5 text-center text-[13px]">
                <p className="text-gray-600">
                  <Link to="/login" className="text-[#a83311] font-bold hover:underline">Volver al Login</Link>
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../components/Button";
import { Input } from "../components/Input";
import { toast } from "react-toastify";
import { Mail, KeyRound } from "lucide-react";
import { AuthLayout } from "../components/AuthLayout";
import {
  authBotao, authCabecalhoTexto, authCampo, authEspacoCampos, authRodape, authTitulo,
} from "../features/auth/estilosAuth";
import { authService } from "../api/auth";
import { getErrorMessage } from "../api/axios";

export const EsqueciSenhaPage = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) {
      toast.error("Por favor, informe seu e-mail.");
      return;
    }

    setLoading(true);
    try {
      await authService.esqueciSenha(email.trim());
      setSent(true);
    } catch (error) {
      toast.error(getErrorMessage(error, "Não foi possível enviar agora. Tente novamente."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      onVoltar={() => navigate(-1)}
      rotacao='-rotate-6'
      icone={<KeyRound className='size-[clamp(2.5rem,8dvh,3.75rem)] text-brand-blue' strokeWidth={1.5} />}
    >
      {!sent ? (
        <div className='flex-1 flex flex-col justify-center'>
          <div className={authCabecalhoTexto}>
            <h1 className={authTitulo}>
              Recuperar
              <br />
              Senha
            </h1>
            <p className='text-gray-400 text-sm font-medium mt-3 px-2'>
              Informe seu e-mail para receber as instruções de recuperação
            </p>
          </div>

          <form onSubmit={handleSubmit} className={`w-full ${authEspacoCampos}`}>
            <div className='relative group shadow-sm'>
              <div className='absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-brand-blue transition-colors'>
                <Mail size={20} />
              </div>
              <Input
                type='email'
                autoComplete='email'
                placeholder='Seu e-mail'
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={authCampo}
              />
            </div>

            <div className='pt-[clamp(0.25rem,1.5dvh,1rem)]'>
              <Button type='submit' isLoading={loading} className={authBotao}>
                ENVIAR E-MAIL
              </Button>
            </div>
          </form>
        </div>
      ) : (
        <div className='flex-1 flex flex-col items-center justify-center text-center animate-fade-in'>
          <div className='size-[clamp(3.5rem,10dvh,5rem)] bg-green-100 text-green-600 rounded-full flex items-center justify-center mb-[clamp(1rem,3dvh,1.5rem)] shadow-inner'>
            <Mail size={36} />
          </div>
          <h2 className='text-[clamp(1.25rem,3.5dvh,1.5rem)] font-black text-brand-navy mb-[clamp(0.5rem,2dvh,1rem)]'>
            Confira seu e-mail
          </h2>
          <p className='text-gray-500 text-[clamp(0.875rem,2.6dvh,1rem)] mb-[clamp(1rem,4dvh,2.5rem)] px-2'>
            Se houver uma conta com <b>{email.trim()}</b>, enviamos um link para
            criar uma nova senha. Ele vale por 30 minutos. Não chegou? Veja a
            pasta de spam ou tente de novo daqui a alguns minutos.
          </p>
          <Button
            onClick={() => navigate("/login")}
            className='text-white! max-w-[200px]'
          >
            VOLTAR AO LOGIN
          </Button>
        </div>
      )}

      <div className={authRodape}>
        <button
          type='button'
          onClick={() => navigate("/login")}
          className='text-brand-navy text-[15px] font-bold opacity-60 hover:opacity-100 transition-opacity'
        >
          Lembrei minha senha
        </button>
      </div>
    </AuthLayout>
  );
};

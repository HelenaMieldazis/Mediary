import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/useAuthStore";
import { Button } from "../components/Button";
import { Input } from "../components/Input";
import { toast } from "react-toastify";
import { loginSchema } from "../features/auth/authSchema";
import { getErrorMessage } from "../api/axios";
import { ZodError } from "zod";
import { Mail, Lock, Eye, EyeOff } from "lucide-react";
import { AuthLayout } from "../components/AuthLayout";
import { LogoMediary } from "../components/LogoMediary";
import {
  authBotao, authCabecalhoTexto, authCampo, authEspacoCampos, authRodape, authTitulo,
} from "../features/auth/estilosAuth";

export const LoginPage = () => {
  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      loginSchema.parse({ email, senha });
      await login(email, senha);
      toast.success("Bem-vindo de volta!");
      navigate("/");
    } catch (error: any) {
      if (error instanceof ZodError) {
        toast.error("Por favor, verifique seus dados.");
      } else {
        toast.error(getErrorMessage(error, "Erro ao fazer login"));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout icone={<LogoMediary className='size-[clamp(2.75rem,9dvh,4.5rem)] text-brand-blue' />}>
      {/* Em telas altas, título e formulário ficam centralizados no cartão. */}
      <div className='flex-1 flex flex-col justify-center'>
        <div className={authCabecalhoTexto}>
          <h1 className={authTitulo}>Login</h1>
        </div>

        <form onSubmit={handleLogin} className={`w-full ${authEspacoCampos}`}>
          <div className='relative group shadow-sm'>
            <div className='absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-brand-blue transition-colors'>
              <Mail size={20} />
            </div>
            <Input
              type='email'
              autoComplete='email'
              placeholder='E-mail'
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={authCampo}
            />
          </div>

          <div className='relative group shadow-sm'>
            <div className='absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-brand-blue transition-colors'>
              <Lock size={20} />
            </div>
            <Input
              type={showPassword ? "text" : "password"}
              autoComplete='current-password'
              placeholder='Senha'
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              className={`${authCampo} pr-12`}
            />
            <button
              type='button'
              onClick={() => setShowPassword(!showPassword)}
              aria-label={showPassword ? "Esconder senha" : "Mostrar senha"}
              className='absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-brand-navy transition-colors'
            >
              {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
            </button>
          </div>

          <div className='flex justify-end w-full px-1'>
            <button
              type='button'
              onClick={() => navigate("/esqueci-senha")}
              className='text-sm text-brand-teal-light font-bold hover:text-brand-blue transition-colors'
            >
              Esqueci minha senha
            </button>
          </div>

          <div className='pt-[clamp(0.25rem,1.5dvh,1rem)]'>
            <Button type='submit' isLoading={loading} className={authBotao}>
              ENTRAR
            </Button>
          </div>
        </form>
      </div>

      <div className={authRodape}>
        <p className='text-brand-navy text-[15px] font-medium opacity-80'>
          Ainda não tem uma conta?{" "}
          <button
            type='button'
            onClick={() => navigate("/cadastro")}
            className='text-brand-blue font-black hover:underline underline-offset-4'
          >
            Cadastre-se
          </button>
        </p>
      </div>
    </AuthLayout>
  );
};

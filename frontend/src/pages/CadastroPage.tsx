import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/useAuthStore";
import { Button } from "../components/Button";
import { Input } from "../components/Input";
import { PasswordRequirements, isPasswordValid, requisitosFaltando } from "../components/PasswordRequirements";
import { toast } from "react-toastify";
import { registerSchema } from "../features/auth/authSchema";
import { getErrorMessage } from "../api/axios";
import { ZodError } from "zod";
import { AuthLayout } from "../components/AuthLayout";
import {
  authBotao, authCabecalhoTexto, authCampo, authEspacoCampos, authRodape, authSubtitulo, authTitulo,
} from "../features/auth/estilosAuth";
import {
  User,
  Mail,
  Lock,
  Eye,
  EyeOff,
  UserPlus,
} from "lucide-react";

export const CadastroPage = () => {
  const navigate = useNavigate();
  const cadastro = useAuthStore((state) => state.cadastro);
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [confirmarSenha, setConfirmarSenha] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!isPasswordValid(senha)) {
      const faltando = requisitosFaltando(senha);
      toast.error(`Sua senha ainda precisa de: ${faltando.join(", ")}.`);
      return;
    }

    if (senha !== confirmarSenha) {
      toast.error("As senhas não coincidem.");
      return;
    }

    setLoading(true);

    try {
      registerSchema.parse({ nome, email, senha, confirmarSenha });
      await cadastro(nome, email, senha);
      toast.success("Conta criada com sucesso! Faça login para continuar.");
      navigate("/login");
    } catch (error: any) {
      if (error instanceof ZodError) {
        const primeiraMsg = error.issues[0]?.message;
        toast.error(primeiraMsg || "Por favor, preencha todos os campos corretamente.");
      } else {
        toast.error(getErrorMessage(error, "Erro ao criar conta"));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      onVoltar={() => navigate(-1)}
      rotacao='rotate-3'
      icone={<UserPlus className='size-[clamp(2.25rem,7.5dvh,3.25rem)] text-brand-blue' strokeWidth={1.5} />}
    >
      <div className='flex-1 flex flex-col justify-center'>
        <div className={authCabecalhoTexto}>
          <h1 className={authTitulo}>Cadastro</h1>
          <p className={authSubtitulo}>Crie sua conta para começar</p>
        </div>

        <form onSubmit={handleRegister} className={`w-full ${authEspacoCampos}`}>
          <div className='relative group shadow-sm'>
            <div className='absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-brand-blue transition-colors'>
              <User size={20} />
            </div>
            <Input
              type='text'
              autoComplete='name'
              placeholder='Nome Completo'
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              className={authCampo}
            />
          </div>
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
              autoComplete='new-password'
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

          {senha && <PasswordRequirements senha={senha} className='-mt-2' />}

          <div className='relative group shadow-sm'>
            <div className='absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-brand-blue transition-colors'>
              <Lock size={20} />
            </div>
            <Input
              type={showConfirmPassword ? "text" : "password"}
              autoComplete='new-password'
              placeholder='Confirmar Senha'
              value={confirmarSenha}
              onChange={(e) => setConfirmarSenha(e.target.value)}
              className={`${authCampo} pr-12`}
            />
            <button
              type='button'
              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
              aria-label={showConfirmPassword ? "Esconder senha" : "Mostrar senha"}
              className='absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-brand-navy transition-colors'
            >
              {showConfirmPassword ? <EyeOff size={20} /> : <Eye size={20} />}
            </button>
          </div>
          {confirmarSenha && confirmarSenha !== senha && (
            <p className='text-xs text-brand-danger font-bold -mt-2 ml-1'>
              As senhas não coincidem
            </p>
          )}

          <div className='pt-[clamp(0.25rem,1.5dvh,1rem)]'>
            <Button type='submit' isLoading={loading} className={authBotao}>
              CRIAR CONTA
            </Button>
          </div>
        </form>
      </div>

      <div className={authRodape}>
        <p className='text-brand-navy text-[15px] font-medium opacity-80'>
          Já possui uma conta?{" "}
          <button
            type='button'
            onClick={() => navigate("/login")}
            className='text-brand-blue font-black hover:underline underline-offset-4'
          >
            Fazer Login
          </button>
        </p>
      </div>
    </AuthLayout>
  );
};

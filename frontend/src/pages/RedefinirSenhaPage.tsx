import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { KeyRound } from "lucide-react";
import { toast } from "react-toastify";
import { Input } from "../components/Input";
import { Button } from "../components/Button";
import {
  PasswordRequirements,
  isPasswordValid,
  requisitosFaltando,
} from "../components/PasswordRequirements";
import { authService } from "../api/auth";
import { getErrorMessage } from "../api/axios";

/** Lê o token do link do e-mail (sem efeitos colaterais: o React pode chamar duas vezes). */
function lerTokenDaUrl(): string {
  return new URLSearchParams(window.location.search).get("token") || "";
}

export const RedefinirSenhaPage = () => {
  const navigate = useNavigate();
  const [token] = useState(lerTokenDaUrl);
  const [novaSenha, setNovaSenha] = useState("");
  const [confirmarSenha, setConfirmarSenha] = useState("");
  const [loading, setLoading] = useState(false);

  // Tira o token da barra de endereço e do histórico do navegador.
  useEffect(() => {
    if (window.location.search) {
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isPasswordValid(novaSenha)) {
      toast.error(`Sua nova senha ainda precisa de: ${requisitosFaltando(novaSenha).join(", ")}.`, {
        position: "top-center",
      });
      return;
    }
    if (novaSenha !== confirmarSenha) {
      toast.error("As senhas não coincidem.", { position: "top-center" });
      return;
    }
    setLoading(true);
    try {
      const r = await authService.redefinirSenha(token, novaSenha);
      toast.success(r.message || "Senha alterada!", { position: "top-center" });
      navigate("/login", { replace: true });
    } catch (error) {
      toast.error(getErrorMessage(error, "Não foi possível alterar a senha."), {
        position: "top-center",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className='flex flex-col h-full min-h-screen bg-brand-blue overflow-hidden'>
      <div className='flex-[0.3] flex flex-col justify-center items-center py-4 px-6'>
        <div className='bg-brand-navy p-5 rounded-3xl shadow-2xl transform rotate-[-5deg] flex items-center justify-center border-4 border-white/10 scale-90'>
          <KeyRound size={60} className='text-brand-blue' strokeWidth={1.5} />
        </div>
      </div>

      <div className='flex-[0.7] bg-gray-50 rounded-t-[40px] shadow-2xl px-8 pt-12 pb-6 flex flex-col animate-slide-up relative z-20'>
        <div className='text-center mb-8'>
          <h1 className='text-2xl font-black text-brand-navy tracking-widest uppercase leading-tight'>
            Nova
            <br />
            Senha
          </h1>
        </div>

        {!token ? (
          <div className='flex-1 flex flex-col items-center text-center'>
            <p className='text-gray-500 mb-8 px-4'>
              Este link está incompleto. Abra de novo o link do e-mail ou peça um novo.
            </p>
            <Button onClick={() => navigate("/esqueci-senha")} className='text-white! max-w-[260px]'>
              PEDIR NOVO LINK
            </Button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className='w-full space-y-4 max-w-sm mx-auto flex-1 flex flex-col'>
            <Input
              label='Nova Senha'
              type='password'
              autoComplete='new-password'
              value={novaSenha}
              onChange={(e) => setNovaSenha(e.target.value)}
              placeholder='Mínimo 8 caracteres, com maiúscula, número e símbolo'
            />
            {novaSenha && <PasswordRequirements senha={novaSenha} />}
            <Input
              label='Confirmar Nova Senha'
              type='password'
              autoComplete='new-password'
              value={confirmarSenha}
              onChange={(e) => setConfirmarSenha(e.target.value)}
              placeholder='Repita a nova senha'
            />
            {confirmarSenha && confirmarSenha !== novaSenha && (
              <p className='text-xs text-brand-danger font-bold ml-1'>As senhas não coincidem</p>
            )}
            <div className='pt-4'>
              <Button type='submit' isLoading={loading} className='text-white! w-full'>
                SALVAR NOVA SENHA
              </Button>
            </div>
          </form>
        )}

        <div className='mt-auto pt-6 text-center'>
          <button
            type='button'
            onClick={() => navigate("/login")}
            className='text-brand-navy text-[15px] font-bold opacity-60 hover:opacity-100 transition-opacity'
          >
            Voltar ao login
          </button>
        </div>
      </div>
    </div>
  );
};

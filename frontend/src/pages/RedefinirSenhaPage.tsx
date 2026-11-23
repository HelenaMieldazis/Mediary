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
import { AuthLayout } from "../components/AuthLayout";
import {
  authBotao, authCabecalhoTexto, authEspacoCampos, authRodape, authTitulo,
} from "../features/auth/estilosAuth";
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
    <AuthLayout
      rotacao='-rotate-6'
      icone={<KeyRound className='size-[clamp(2.5rem,8dvh,3.75rem)] text-brand-blue' strokeWidth={1.5} />}
    >
      <div className='flex-1 flex flex-col justify-center'>
        <div className={authCabecalhoTexto}>
          <h1 className={authTitulo}>
            Nova
            <br />
            Senha
          </h1>
        </div>

        {!token ? (
          <div className='flex flex-col items-center text-center'>
            <p className='text-gray-500 mb-8 px-2'>
              Este link está incompleto. Abra de novo o link do e-mail ou peça um novo.
            </p>
            <Button onClick={() => navigate("/esqueci-senha")} className='text-white! max-w-[260px]'>
              PEDIR NOVO LINK
            </Button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className={`w-full ${authEspacoCampos}`}>
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
            <div className='pt-[clamp(0.25rem,1.5dvh,1rem)]'>
              <Button type='submit' isLoading={loading} className={`${authBotao} w-full`}>
                SALVAR NOVA SENHA
              </Button>
            </div>
          </form>
        )}
      </div>

      <div className={authRodape}>
        <button
          type='button'
          onClick={() => navigate("/login")}
          className='text-brand-navy text-[15px] font-bold opacity-60 hover:opacity-100 transition-opacity'
        >
          Voltar ao login
        </button>
      </div>
    </AuthLayout>
  );
};

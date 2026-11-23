import { useNavigate } from "react-router-dom";
import { Avatar } from "../components/Avatar";
import { ChevronLeft, ChevronRight, LogOut, FileDown, Sparkles } from "lucide-react";
import { useAuthStore } from "../store/useAuthStore";
import { useEffect, useState } from "react";
import { toast } from "react-toastify";
import { sintomasService } from "../api/sintomas";
import { iaService } from "../api/ia";
import { getErrorMessage } from "../api/axios";

// Componente auxiliar para os Toggles de Notificação
const Toggle = ({
  enabled,
  onChange,
}: {
  enabled: boolean;
  onChange: () => void;
}) => {
  return (
    <div
      onClick={onChange}
      className={`w-12 h-6 flex items-center rounded-full p-1 cursor-pointer transition-colors duration-300 ${enabled ? "bg-brand-navy" : "bg-gray-300"}`}
    >
      <div
        className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform duration-300 ${enabled ? "translate-x-6" : "translate-x-0"}`}
      />
    </div>
  );
};

export const ConfiguracoesPage = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();

  const [updatesEnabled, setUpdatesEnabled] = useState(true);
  const [exportando, setExportando] = useState(false);
  const [ia, setIa] = useState<{ disponivel: boolean; consentido: boolean } | null>(null);

  useEffect(() => {
    iaService.status().then(setIa).catch(() => setIa(null));
  }, []);

  const alternarIa = async () => {
    if (!ia) return;
    // Para ativar, o consentimento é pedido na própria tela da IA; aqui só é possível desativar.
    if (!ia.consentido) {
      navigate("/resumo-ia");
      return;
    }
    try {
      await iaService.consentimento(false);
      setIa({ ...ia, consentido: false });
      toast.success("IA desativada. Nenhum dado será enviado.");
    } catch (error) {
      toast.error(getErrorMessage(error, "Não foi possível alterar agora."));
    }
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const handleExportarPdf = async () => {
    setExportando(true);
    try {
      const blob = await sintomasService.exportarRelatorioPdf();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      const dataAtual = new Date().toISOString().slice(0, 10);
      link.href = url;
      link.download = `mediary_relatorio_${dataAtual}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Relatório gerado com sucesso!");
    } catch (error) {
      toast.error(
        getErrorMessage(error, "Não foi possível gerar o relatório em PDF no momento.")
      );
    } finally {
      setExportando(false);
    }
  };

  return (
    <div className='flex flex-col min-h-screen bg-gray-50 relative'>
      {/* Header com Fundo Azul */}
      <div className='bg-brand-blue pt-12 pb-16 px-6 rounded-b-[40px] shadow-sm'>
        <div className='flex items-center relative w-full h-10'>
          <button
            onClick={() => navigate("/")}
            className='absolute left-0 w-10 h-10 bg-white/20 flex items-center justify-center rounded-full text-brand-navy active:scale-95 transition-transform'
          >
            <ChevronLeft size={24} strokeWidth={2.5} />
          </button>
          <h1 className='flex-1 text-center text-xl font-black text-brand-navy tracking-widest uppercase'>
            Configurações
          </h1>
        </div>
      </div>

      {/* Perfil (Sobreposto ao header) */}
      <div className='px-6 -mt-16 flex flex-col items-center mb-8'>
        <div className='w-32 h-32 bg-white rounded-full p-1 shadow-lg mb-4'>
          <Avatar />
        </div>
        <h2 className='text-2xl font-black text-brand-navy'>
          {user?.nome || "Usuário"}
        </h2>
        <p className='text-gray-500 font-medium'>
          {user?.email || ""}
        </p>
      </div>

      <div className='flex-1 px-6 pb-10 space-y-8'>
        {/* Configurações da Conta */}
        <section>
          <h3 className='text-sm font-black text-brand-navy mb-3 ml-2 uppercase opacity-60'>
            Configurações da Conta
          </h3>
          <div className='bg-white rounded-3xl shadow-sm border border-gray-100 overflow-hidden'>
            <button
              onClick={() => navigate("/editar-perfil")}
              className='w-full flex items-center justify-between p-4 border-b border-gray-100 active:bg-gray-50 transition-colors'
            >
              <span className='font-bold text-brand-navy'>Editar Perfil</span>
              <ChevronRight size={20} className='text-gray-400' />
            </button>
            <button
              onClick={() => navigate("/mudar-senha")}
              className='w-full flex items-center justify-between p-4 border-b border-gray-100 active:bg-gray-50 transition-colors'
            >
              <span className='font-bold text-brand-navy'>Mudar sua Senha</span>
              <ChevronRight size={20} className='text-gray-400' />
            </button>
            <button
              onClick={() => navigate("/seguranca")}
              className='w-full flex items-center justify-between p-4 active:bg-gray-50 transition-colors'
            >
              <span className='font-bold text-brand-navy'>
                Segurança e Privacidade
              </span>
              <ChevronRight size={20} className='text-gray-400' />
            </button>
          </div>
        </section>

        {/* Meus Dados */}
        <section>
          <h3 className='text-sm font-black text-brand-navy mb-3 ml-2 uppercase opacity-60'>
            Meus Dados
          </h3>
          <div className='bg-white rounded-3xl shadow-sm border border-gray-100 overflow-hidden'>
            {ia?.disponivel && (
              <>
                <button
                  onClick={() => navigate("/resumo-ia")}
                  className='w-full flex items-center justify-between p-4 border-b border-gray-100 active:bg-gray-50 transition-colors'
                >
                  <span className='flex items-center gap-3 font-bold text-brand-navy'>
                    <Sparkles size={20} className='text-brand-blue' />
                    Resumo com IA para a consulta
                  </span>
                  <ChevronRight size={20} className='text-gray-400' />
                </button>
                <div className='w-full flex items-center justify-between p-4 border-b border-gray-100'>
                  <span className='font-bold text-brand-navy'>Usar IA no app</span>
                  <Toggle enabled={ia.consentido} onChange={alternarIa} />
                </div>
              </>
            )}
            <button
              onClick={handleExportarPdf}
              disabled={exportando}
              className='w-full flex items-center justify-between p-4 active:bg-gray-50 transition-colors disabled:opacity-60'
            >
              <span className='flex items-center gap-3 font-bold text-brand-navy'>
                <FileDown size={20} className='text-brand-teal' />
                {exportando ? "Gerando PDF..." : "Exportar Relatório em PDF"}
              </span>
              <ChevronRight size={20} className='text-gray-400' />
            </button>
          </div>
        </section>

        {/* Configurações de Notificação */}
        <section>
          <h3 className='text-sm font-black text-brand-navy mb-3 ml-2 uppercase opacity-60'>
            Configurações de Notificação
          </h3>
          <div className='bg-white rounded-3xl shadow-sm border border-gray-100 overflow-hidden'>
            <div className='w-full flex items-center justify-between p-4'>
              <span className='font-bold text-brand-navy'>
                Atualizações do App
              </span>
              <Toggle
                enabled={updatesEnabled}
                onChange={() => setUpdatesEnabled(!updatesEnabled)}
              />
            </div>
          </div>
        </section>

        {/* Botão de Logout */}
        <div className='pt-4'>
          <button
            onClick={handleLogout}
            className='w-full py-4 bg-red-50 text-brand-danger font-black rounded-full flex items-center justify-center gap-2 hover:bg-red-100 active:scale-95 transition-all shadow-sm'
          >
            <LogOut size={20} strokeWidth={2.5} />
            SAIR DA CONTA
          </button>
        </div>
      </div>
    </div>
  );
};

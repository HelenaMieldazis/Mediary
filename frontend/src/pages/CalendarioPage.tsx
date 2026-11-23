import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSintomasStore } from "../store/useSintomasStore";
import { useAuthStore } from "../store/useAuthStore";
import { Calendar as CalendarIcon, User, Plus, Sparkles, FileText } from "lucide-react";
import { Calendar } from "../components/Calendar";
import { BottomSheetAddSintoma } from "../components/BottomSheetAddSintoma";
import { ModalViewSintomas } from "../components/ModalViewSintomas";
import { AssistenteIA } from "../components/AssistenteIA";
import { iaService } from "../api/ia";

export const CalendarioPage = () => {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const { setSelectedDate } = useSintomasStore();

  const [isAddOpen, setIsAddOpen] = useState(false);
  const [isViewOpen, setIsViewOpen] = useState(false);
  const [isIaOpen, setIsIaOpen] = useState(false);
  const [iaDisponivel, setIaDisponivel] = useState(false);

  // O atalho da IA só aparece se o servidor tiver a IA configurada.
  useEffect(() => {
    iaService
      .status()
      .then((s) => setIaDisponivel(s.disponivel))
      .catch(() => setIaDisponivel(false));
  }, []);

  // const sintomasDoDia = sintomas.filter((s) => {
  //   const sDate = new Date(s.inicio);
  //   return (
  //     sDate.getDate() === selectedDate.getDate() &&
  //     sDate.getMonth() === selectedDate.getMonth() &&
  //     sDate.getFullYear() === selectedDate.getFullYear()
  //   );
  // });

  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return "Bom dia";
    if (hour < 18) return "Boa tarde";
    return "Boa noite";
  };

  return (
    // h-dvh: exatamente a altura visível do celular (já descontando a barra do
    // navegador). Só em telas muito baixas (celular deitado) a página rola.
    <div className='flex flex-col h-dvh min-h-[34rem] bg-brand-blue relative overflow-hidden'>
      {/* Header */}
      <div className='pt-[calc(env(safe-area-inset-top)+clamp(0.75rem,3dvh,2rem))] px-6 pb-[clamp(0.25rem,1.5dvh,1rem)] flex flex-col gap-[clamp(0.5rem,2dvh,1rem)] animate-fade-in shrink-0'>
        <div className='flex justify-between items-center'>
          <button
            onClick={() => setSelectedDate(new Date())}
            className='w-11 h-11 border-2 border-white/20 rounded-2xl flex items-center justify-center bg-white/10 text-white active:scale-90 transition-all shadow-lg backdrop-blur-sm group'
            title='Ir para hoje'
          >
            <CalendarIcon
              size={22}
              strokeWidth={2}
              className='group-hover:scale-110 transition-transform'
            />
          </button>

          <div className='flex items-center gap-2'>
            {iaDisponivel && (
              <button
                onClick={() => navigate("/resumo-ia")}
                aria-label='Resumo para a consulta'
                title='Resumo para a consulta'
                className='w-11 h-11 border-2 border-white/20 rounded-2xl flex items-center justify-center bg-white/10 text-white active:scale-90 transition-all shadow-lg backdrop-blur-sm'
              >
                <FileText size={22} strokeWidth={2} />
              </button>
            )}
            <button
              onClick={() => navigate("/configuracoes")}
              className='w-11 h-11 bg-brand-navy rounded-2xl flex items-center justify-center text-brand-blue active:scale-90 transition-all shadow-xl border-2 border-brand-blue-dark/30'
            >
              <User size={22} strokeWidth={2.5} />
            </button>
          </div>
        </div>

        <div className='flex flex-col gap-0.5'>
          <h1 className='text-white text-xl font-black flex items-center gap-2'>
            {getGreeting()},{" "}
            <span className='text-brand-navy underline decoration-brand-blue-dark decoration-4 underline-offset-4'>
              {user?.nome?.split(" ")[0] || "Paciente"}
            </span>
            !
          </h1>
          <p className='text-white/70 text-xs font-bold flex items-center gap-2'>
            <span className='w-1.5 h-1.5 bg-brand-navy rounded-full animate-pulse'></span>
            Como você está se sentindo hoje?
          </p>
        </div>
      </div>

      {/* O calendário ocupa o espaço que sobrar; em telas altas, no máximo 36rem (o espaçamento do design original). */}
      <div className='flex-1 min-h-0 px-[clamp(0.75rem,5vw,1.5rem)] flex flex-col justify-center'>
        <div className='w-full h-full max-h-[36rem] min-h-0'>
          <Calendar onDayClick={() => setIsViewOpen(true)} />
        </div>
      </div>

      {/* Bottom Area with + */}
      <div className='bg-gray-50 rounded-t-[40px] pt-2 pb-[calc(env(safe-area-inset-bottom)+clamp(0.5rem,2dvh,1.5rem))] flex flex-row items-center justify-center gap-4 w-full shrink-0 relative z-10 shadow-[0_-10px_20px_rgba(0,0,0,0.05)]'>
        {iaDisponivel && (
          <button
            onClick={() => setIsIaOpen(true)}
            className='flex items-center gap-2 bg-brand-navy text-white text-sm font-black rounded-full px-5 py-2.5 shadow-md active:scale-95 transition-transform'
          >
            <Sparkles size={16} className='text-brand-blue' />
            Registrar com IA
          </button>
        )}
        <button
          onClick={() => setIsAddOpen(true)}
          aria-label='Adicionar sintoma'
          className='text-brand-blue flex items-center justify-center active:scale-95 transition-transform'
        >
          <Plus className='size-[clamp(3rem,8dvh,4rem)]' strokeWidth={1.5} />
        </button>
      </div>

      <BottomSheetAddSintoma
        isOpen={isAddOpen}
        onClose={() => setIsAddOpen(false)}
      />

      <AssistenteIA isOpen={isIaOpen} onClose={() => setIsIaOpen(false)} />

      <ModalViewSintomas
        isOpen={isViewOpen}
        onClose={() => setIsViewOpen(false)}
      />
    </div>
  );
};

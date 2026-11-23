import React from "react";
import { ChevronLeft } from "lucide-react";

interface Props {
  /** Ícone dentro do quadrado azul-escuro do topo. */
  icone: React.ReactNode;
  /** Inclinação do quadrado (ex.: "-rotate-2", "rotate-3"). */
  rotacao?: string;
  /** Mostra o botão de voltar no topo. */
  onVoltar?: () => void;
  children: React.ReactNode;
}

/**
 * Esqueleto das telas de entrada. A altura do topo e os espaçamentos seguem a
 * altura da tela (dvh): em celulares baixos tudo cabe sem rolar; em telas altas
 * o formulário fica centralizado. Com o teclado aberto, a página rola
 * normalmente (min-h, não altura fixa). Respeita o entalhe e a barra de gestos.
 */
export const AuthLayout: React.FC<Props> = ({ icone, rotacao = "-rotate-2", onVoltar, children }) => (
  <div className='flex flex-col min-h-dvh bg-brand-blue'>
    <div className='relative shrink-0 pt-[env(safe-area-inset-top)] h-[calc(env(safe-area-inset-top)+clamp(5.5rem,calc(30dvh_-_4rem),15rem))] flex items-center justify-center px-6'>
      {onVoltar && (
        <button
          type='button'
          onClick={onVoltar}
          aria-label='Voltar'
          className='absolute left-[clamp(1rem,5vw,1.5rem)] top-[calc(env(safe-area-inset-top)+clamp(0.75rem,2.5dvh,1.5rem))] w-10 h-10 flex items-center justify-center rounded-2xl bg-white/20 text-white backdrop-blur-md hover:bg-white/30 transition-all z-30'
        >
          <ChevronLeft size={24} />
        </button>
      )}
      <div
        className={`bg-brand-navy p-[clamp(0.75rem,2.2dvh,1.25rem)] rounded-3xl shadow-2xl ${rotacao} flex items-center justify-center border-4 border-white/10`}
      >
        {icone}
      </div>
    </div>

    <div className='flex-1 flex flex-col bg-gray-50 rounded-t-[40px] shadow-2xl px-[clamp(1.25rem,7vw,2rem)] pt-[clamp(1.25rem,4.5dvh,3rem)] pb-[calc(env(safe-area-inset-bottom)+clamp(0.75rem,2.5dvh,1.5rem))] animate-slide-up relative z-20'>
      <div className='w-full max-w-sm mx-auto flex-1 flex flex-col'>{children}</div>
    </div>
  </div>
);

AuthLayout.displayName = "AuthLayout";

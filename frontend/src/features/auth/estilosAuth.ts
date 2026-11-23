/**
 * Medidas das telas de entrada (login, cadastro, esqueci/nova senha).
 * Tudo cresce e encolhe com a altura da tela (dvh), dentro de limites:
 * em celulares baixos fica compacto; em telas altas, volta ao tamanho do design.
 */
export const authTitulo =
  "text-[clamp(1.5rem,4.2dvh,1.875rem)] font-black text-brand-navy tracking-[0.2em] uppercase leading-tight";
export const authSubtitulo = "text-gray-400 text-sm font-medium mt-1";
export const authCabecalhoTexto = "text-center mb-[clamp(1rem,3.5dvh,2rem)]";
export const authEspacoCampos = "space-y-[clamp(0.75rem,2.2dvh,1.5rem)]";
export const authCampo =
  "pl-12 bg-white! shadow-lg! border-none py-[clamp(0.625rem,1.9dvh,1rem)]! text-base";
export const authBotao =
  "text-white! py-[clamp(0.75rem,2.3dvh,1.25rem)]! shadow-[0_8px_0_0_var(--color-brand-blue-dark)] active:translate-y-[8px] active:shadow-none transition-all";
export const authRodape = "mt-auto pt-[clamp(0.75rem,2.5dvh,1.5rem)] text-center";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Loader2, Mic, Send, Sparkles, Square, X } from "lucide-react";
import { toast } from "react-toastify";
import { iaService } from "../api/ia";
import { getErrorMessage } from "../api/axios";
import { useSintomasStore } from "../store/useSintomasStore";
import { useReconhecimentoVoz } from "../hooks/useReconhecimentoVoz";
import { ConsentimentoIA } from "./ConsentimentoIA";
import { dataHoraBr, ROTULO_TIPO } from "../features/ia/formatar";
import type { RascunhoIA, SintomaProntoIA, TurnoConversa } from "../types/ia";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

type Fase = "carregando" | "consentimento" | "conversa";

const BOAS_VINDAS =
  "Oi! Me conte o que você sentiu, por texto ou por voz. Por exemplo: \"ontem à noite tive dor de cabeça por umas duas horas\".";

/** Cada abertura monta uma sessão nova: a conversa nunca sobra de uma abertura para outra. */
export const AssistenteIA: React.FC<Props> = ({ isOpen, onClose }) =>
  isOpen ? <SessaoAssistente onClose={onClose} /> : null;

const SessaoAssistente: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const { adicionarSintoma, fetchCalendarioInfo } = useSintomasStore();

  const [fase, setFase] = useState<Fase>("carregando");
  const [turnos, setTurnos] = useState<TurnoConversa[]>([]);
  const [rascunho, setRascunho] = useState<RascunhoIA | null>(null);
  const [pronto, setPronto] = useState<SintomaProntoIA | null>(null);
  const [alerta, setAlerta] = useState<string | null>(null);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const fimRef = useRef<HTMLDivElement>(null);
  // onClose geralmente é uma função nova a cada render do pai; guardamos numa ref
  // para não reiniciar a conversa por causa disso.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  // Ao abrir: verifica se a IA está disponível e se a pessoa já consentiu.
  useEffect(() => {
    let ativo = true;
    iaService
      .status()
      .then((s) => {
        if (!ativo) return;
        if (!s.disponivel) {
          toast.info("O assistente com IA não está disponível agora.");
          onCloseRef.current();
          return;
        }
        setFase(s.consentido ? "conversa" : "consentimento");
      })
      .catch((e) => {
        if (!ativo) return;
        toast.error(getErrorMessage(e, "Não foi possível abrir o assistente."));
        onCloseRef.current();
      });
    return () => {
      ativo = false;
    };
  }, []);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turnos, pronto, enviando]);

  const enviar = useCallback(
    async (mensagem: string) => {
      const limpa = mensagem.trim();
      if (!limpa || enviando) return;
      const historico = turnos;
      setTurnos([...historico, { papel: "paciente", texto: limpa }]);
      setTexto("");
      setPronto(null);
      setEnviando(true);
      try {
        const r = await iaService.interpretar(limpa, rascunho, historico);
        setRascunho(r.rascunho);
        setAlerta(r.alerta);
        if (r.status === "completo" && r.sintoma) {
          setPronto(r.sintoma);
          setTurnos((t) => [...t, { papel: "assistente", texto: "Entendi! Confira abaixo e confirme se está certo." }]);
        } else {
          setTurnos((t) => [...t, { papel: "assistente", texto: r.pergunta || "Pode me contar mais um pouco?" }]);
        }
      } catch (e) {
        const resp = (e as { response?: { status?: number; data?: { codigo?: string } } }).response;
        if (resp?.status === 403 && resp.data?.codigo === "consentimento_necessario") {
          setFase("consentimento");
        } else {
          toast.error(getErrorMessage(e, "Não consegui entender agora. Tente novamente."));
        }
        // devolve a mensagem para a caixa de texto para a pessoa não perder o que escreveu
        setTurnos(historico);
        setTexto(limpa);
      } finally {
        setEnviando(false);
      }
    },
    [enviando, turnos, rascunho]
  );

  const voz = useReconhecimentoVoz({ aoTerminar: enviar });

  const fechar = () => {
    voz.cancelar();
    onClose();
  };

  const aceitar = async () => {
    try {
      await iaService.consentimento(true);
      setFase("conversa");
    } catch (e) {
      toast.error(getErrorMessage(e, "Não foi possível salvar sua escolha."));
    }
  };

  const salvar = async () => {
    if (!pronto) return;
    setSalvando(true);
    try {
      await adicionarSintoma(pronto);
      const d = new Date(pronto.inicio.replace(" ", "T"));
      fetchCalendarioInfo(d.getFullYear(), d.getMonth() + 1);
      toast.success("Sintoma registrado!");
      fechar();
    } catch (e) {
      toast.error(getErrorMessage(e, "Erro ao salvar sintoma"));
    } finally {
      setSalvando(false);
    }
  };

  const corrigir = () => {
    setPronto(null);
    setTurnos((t) => [...t, { papel: "assistente", texto: "Sem problema! O que você quer corrigir?" }]);
  };

  return (
    <div className='fixed inset-0 z-50 flex items-end justify-center bg-black/50 animate-fade-in'>
      <div className='absolute inset-0' onClick={fechar} />
      <div className='relative w-full max-w-md bg-white rounded-t-[32px] shadow-2xl flex flex-col max-h-[92vh] h-[85vh] animate-slide-up'>
        {/* Cabeçalho */}
        <div className='flex items-center justify-between px-5 pt-5 pb-3 border-b border-gray-100'>
          <div className='flex items-center gap-2 text-brand-navy font-black'>
            <Sparkles size={20} className='text-brand-blue' />
            Registrar com IA
          </div>
          <button
            onClick={fechar}
            aria-label='Fechar'
            className='w-9 h-9 rounded-full bg-gray-100 text-gray-500 flex items-center justify-center active:scale-90 transition-transform'
          >
            <X size={18} />
          </button>
        </div>

        {fase === "carregando" && (
          <div className='flex-1 flex items-center justify-center text-brand-blue'>
            <Loader2 className='animate-spin' size={32} />
          </div>
        )}

        {fase === "consentimento" && <ConsentimentoIA onAceitar={aceitar} onRecusar={fechar} />}

        {fase === "conversa" && (
          <>
            <div className='flex-1 overflow-y-auto px-5 py-4 space-y-3'>
              {alerta && (
                <div role='alert' className='flex gap-2 bg-red-50 border border-red-200 text-red-700 rounded-2xl p-3 text-sm font-semibold'>
                  <AlertTriangle size={18} className='shrink-0 mt-0.5' />
                  <span>{alerta}</span>
                </div>
              )}

              <Balao papel='assistente' texto={BOAS_VINDAS} />
              {turnos.map((t, i) => (
                <Balao key={i} papel={t.papel} texto={t.texto} />
              ))}
              {voz.ouvindo && <Balao papel='paciente' texto={voz.parcial || "Estou ouvindo..."} suave />}
              {enviando && (
                <div className='flex items-center gap-2 text-gray-400 text-sm'>
                  <Loader2 size={16} className='animate-spin' /> Pensando...
                </div>
              )}

              {pronto && (
                <div className='bg-brand-blue/10 border border-brand-blue/30 rounded-3xl p-4 space-y-2'>
                  <div className='text-xs font-black uppercase tracking-widest text-brand-teal'>Vou registrar</div>
                  <div className='text-brand-navy font-black text-lg'>
                    {ROTULO_TIPO[pronto.tipo] || pronto.tipo}
                    {pronto.subtipo ? ` — ${pronto.subtipo.charAt(0) + pronto.subtipo.slice(1).toLowerCase()}` : ""}
                  </div>
                  <div className='text-sm text-gray-700'>
                    <b>Início:</b> {dataHoraBr(pronto.inicio)}
                  </div>
                  {pronto.fim && (
                    <div className='text-sm text-gray-700'>
                      <b>Fim:</b> {dataHoraBr(pronto.fim)}
                    </div>
                  )}
                  {pronto.descricao && (
                    <div className='text-sm text-gray-700'>
                      <b>Observação:</b> {pronto.descricao}
                    </div>
                  )}
                  <div className='flex gap-2 pt-2'>
                    <button
                      onClick={salvar}
                      disabled={salvando}
                      className='flex-1 flex items-center justify-center gap-2 bg-brand-navy text-white font-black rounded-2xl py-3 active:scale-95 transition-transform disabled:opacity-60'
                    >
                      {salvando ? <Loader2 size={18} className='animate-spin' /> : <Check size={18} />}
                      Salvar
                    </button>
                    <button
                      onClick={corrigir}
                      disabled={salvando}
                      className='px-4 bg-white text-brand-navy font-bold rounded-2xl border border-gray-200 active:scale-95 transition-transform'
                    >
                      Corrigir
                    </button>
                  </div>
                </div>
              )}
              <div ref={fimRef} />
            </div>

            {/* Entrada */}
            <div className='px-4 pb-5 pt-3 border-t border-gray-100'>
              {voz.erro && <p className='text-xs text-brand-danger font-semibold mb-2 px-1'>{voz.erro}</p>}
              <form
                className='flex items-end gap-2'
                onSubmit={(e) => {
                  e.preventDefault();
                  void enviar(texto);
                }}
              >
                {voz.suportado && (
                  <button
                    type='button'
                    onClick={voz.ouvindo ? voz.parar : voz.iniciar}
                    disabled={enviando}
                    aria-label={voz.ouvindo ? "Parar de gravar" : "Falar"}
                    className={`w-12 h-12 shrink-0 rounded-full flex items-center justify-center text-white active:scale-90 transition-all disabled:opacity-50 ${
                      voz.ouvindo ? "bg-brand-danger animate-pulse" : "bg-brand-blue-dark"
                    }`}
                  >
                    {voz.ouvindo ? <Square size={18} fill='currentColor' /> : <Mic size={22} />}
                  </button>
                )}
                <textarea
                  value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void enviar(texto);
                    }
                  }}
                  maxLength={600}
                  rows={1}
                  placeholder={voz.ouvindo ? "Ouvindo..." : "Escreva aqui o que sentiu"}
                  disabled={enviando || voz.ouvindo}
                  className='flex-1 resize-none rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 text-brand-navy font-medium focus:outline-none focus:border-brand-blue max-h-32'
                />
                <button
                  type='submit'
                  disabled={enviando || !texto.trim()}
                  aria-label='Enviar'
                  className='w-12 h-12 shrink-0 rounded-full bg-brand-navy text-white flex items-center justify-center active:scale-90 transition-transform disabled:opacity-40'
                >
                  <Send size={20} />
                </button>
              </form>
              {!voz.suportado && (
                <p className='text-[11px] text-gray-400 mt-2 px-1'>
                  Seu navegador não permite falar com o app. Use o texto ou abra no Chrome.
                </p>
              )}
              <p className='text-[11px] text-gray-400 mt-2 px-1'>
                A IA pode errar. Confira antes de salvar. Não substitui avaliação médica.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

const Balao = ({ papel, texto, suave }: { papel: "paciente" | "assistente"; texto: string; suave?: boolean }) => (
  <div className={`flex ${papel === "paciente" ? "justify-end" : "justify-start"}`}>
    <div
      className={`max-w-[85%] rounded-3xl px-4 py-2.5 text-sm font-medium whitespace-pre-wrap break-words ${
        papel === "paciente"
          ? "bg-brand-navy text-white rounded-br-lg"
          : "bg-gray-100 text-brand-navy rounded-bl-lg"
      } ${suave ? "opacity-60" : ""}`}
    >
      {texto}
    </div>
  </div>
);

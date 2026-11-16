import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, FileDown, Loader2, Sparkles, X, Plus } from "lucide-react";
import { toast } from "react-toastify";
import { iaService, type PeriodoIA } from "../api/ia";
import { getErrorMessage } from "../api/axios";
import { Button } from "../components/Button";
import { ConsentimentoIA } from "../components/ConsentimentoIA";
import { baixarBlob, dataBr, diasAtrasIso, hojeIso, horasBr } from "../features/ia/formatar";
import type { ResumoIA } from "../types/ia";

type Atalho = "30" | "90" | "tudo" | "custom";

export const ResumoIAPage = () => {
  const navigate = useNavigate();
  const [consentido, setConsentido] = useState<boolean | null>(null);
  const [disponivel, setDisponivel] = useState(true);
  const [atalho, setAtalho] = useState<Atalho>("30");
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [gerando, setGerando] = useState(false);
  const [baixando, setBaixando] = useState(false);
  const [dados, setDados] = useState<ResumoIA | null>(null);
  const [resumo, setResumo] = useState("");
  const [destaques, setDestaques] = useState<string[]>([]);
  const [perguntas, setPerguntas] = useState<string[]>([]);
  const [periodoUsado, setPeriodoUsado] = useState<PeriodoIA>({});

  useEffect(() => {
    iaService
      .status()
      .then((s) => {
        setDisponivel(s.disponivel);
        setConsentido(s.consentido);
      })
      .catch((e) => {
        toast.error(getErrorMessage(e, "Não foi possível abrir esta tela."));
        navigate("/");
      });
  }, [navigate]);

  const periodo = (): PeriodoIA => {
    if (atalho === "30") return { data_inicio: diasAtrasIso(30), data_fim: hojeIso() };
    if (atalho === "90") return { data_inicio: diasAtrasIso(90), data_fim: hojeIso() };
    if (atalho === "tudo") return {};
    return { data_inicio: inicio || undefined, data_fim: fim || undefined };
  };

  const gerar = async () => {
    if (atalho === "custom" && inicio && fim && fim < inicio) {
      toast.error("A data final não pode ser anterior à inicial.");
      return;
    }
    const p = periodo();
    setGerando(true);
    try {
      const r = await iaService.gerarResumo(p);
      setDados(r);
      setResumo(r.resumo);
      setDestaques(r.destaques);
      setPerguntas(r.perguntas);
      setPeriodoUsado(p);
    } catch (e) {
      const resp = (e as { response?: { status?: number; data?: { codigo?: string } } }).response;
      if (resp?.status === 403 && resp.data?.codigo === "consentimento_necessario") setConsentido(false);
      else toast.error(getErrorMessage(e, "Não foi possível gerar o resumo agora."));
    } finally {
      setGerando(false);
    }
  };

  const baixar = async () => {
    if (!resumo.trim()) {
      toast.error("O resumo não pode ficar vazio.");
      return;
    }
    setBaixando(true);
    try {
      const blob = await iaService.baixarRelatorio(periodoUsado, {
        resumo: resumo.trim(),
        destaques: destaques.map((d) => d.trim()).filter(Boolean),
        perguntas: perguntas.map((q) => q.trim()).filter(Boolean),
      });
      baixarBlob(blob, `mediary_resumo_${hojeIso()}.pdf`);
      toast.success("PDF gerado!");
    } catch (e) {
      toast.error(getErrorMessage(e, "Não foi possível gerar o PDF agora."));
    } finally {
      setBaixando(false);
    }
  };

  const aceitar = async () => {
    try {
      await iaService.consentimento(true);
      setConsentido(true);
    } catch (e) {
      toast.error(getErrorMessage(e, "Não foi possível salvar sua escolha."));
    }
  };

  const editarLista = (lista: string[], set: (v: string[]) => void, i: number, valor: string) =>
    set(lista.map((x, j) => (j === i ? valor : x)));

  const est = dados?.estatisticas;
  const chips: { id: Atalho; label: string }[] = [
    { id: "30", label: "30 dias" },
    { id: "90", label: "90 dias" },
    { id: "tudo", label: "Tudo" },
    { id: "custom", label: "Período" },
  ];

  return (
    <div className='flex flex-col min-h-screen bg-gray-50'>
      <div className='bg-brand-blue pt-12 pb-10 px-6 rounded-b-[40px] shadow-sm'>
        <div className='flex items-center relative w-full h-10'>
          <button
            onClick={() => navigate("/")}
            aria-label='Voltar'
            className='absolute left-0 w-10 h-10 bg-white/20 flex items-center justify-center rounded-full text-brand-navy active:scale-95 transition-transform'
          >
            <ChevronLeft size={24} strokeWidth={2.5} />
          </button>
          <h1 className='flex-1 px-12 text-center text-base leading-tight font-black text-brand-navy tracking-widest uppercase'>
            Resumo para a consulta
          </h1>
        </div>
      </div>

      <div className='px-5 py-6 space-y-5 max-w-md w-full mx-auto'>
        {consentido === null && (
          <div className='flex justify-center py-10 text-brand-blue'>
            <Loader2 className='animate-spin' size={32} />
          </div>
        )}

        {consentido !== null && !disponivel && (
          <div className='bg-white rounded-3xl p-5 border border-gray-100 text-gray-600 font-medium'>
            O resumo com IA não está disponível agora. Você ainda pode exportar o relatório simples em
            Configurações.
          </div>
        )}

        {consentido === false && disponivel && (
          <div className='bg-white rounded-3xl border border-gray-100 shadow-sm'>
            <ConsentimentoIA onAceitar={aceitar} onRecusar={() => navigate("/")} />
          </div>
        )}

        {consentido && disponivel && (
          <>
            <section className='bg-white rounded-3xl p-5 border border-gray-100 shadow-sm space-y-4'>
              <p className='text-sm text-gray-600 font-medium'>
                A IA lê os sintomas que você registrou e escreve um resumo com padrões, datas e horários
                para você levar ao médico em PDF.
              </p>
              <div className='flex flex-wrap gap-2'>
                {chips.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setAtalho(c.id)}
                    className={`px-4 py-2 rounded-full text-sm font-black transition-colors ${
                      atalho === c.id ? "bg-brand-navy text-white" : "bg-gray-100 text-brand-navy"
                    }`}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
              {atalho === "custom" && (
                <div className='grid grid-cols-2 gap-3'>
                  <label className='text-xs font-bold text-gray-500'>
                    De
                    <input
                      type='date'
                      value={inicio}
                      max={hojeIso()}
                      onChange={(e) => setInicio(e.target.value)}
                      className='mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-brand-navy'
                    />
                  </label>
                  <label className='text-xs font-bold text-gray-500'>
                    Até
                    <input
                      type='date'
                      value={fim}
                      max={hojeIso()}
                      onChange={(e) => setFim(e.target.value)}
                      className='mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-brand-navy'
                    />
                  </label>
                </div>
              )}
              <Button onClick={gerar} isLoading={gerando} className='!mb-0'>
                <Sparkles size={20} className='mr-2' />
                Gerar resumo
              </Button>
            </section>

            {dados && est && (
              <>
                <div className='grid grid-cols-3 gap-3'>
                  <Card titulo='Registros' valor={String(est.total)} />
                  <Card titulo='Dias' valor={String(est.dias_com_sintoma)} />
                  <Card titulo='Mais comum' valor={est.por_tipo[0]?.rotulo.split(" — ")[0] ?? "-"} pequeno />
                </div>
                <p className='text-xs text-gray-500 font-semibold text-center'>
                  {dataBr(est.primeiro_registro)} a {dataBr(est.ultimo_registro)}
                  {est.duracao ? ` · duração média ${horasBr(est.duracao.media_horas)}` : ""}
                </p>

                <div className='bg-amber-50 border border-amber-200 text-amber-800 rounded-2xl p-3 text-xs font-semibold'>
                  Texto gerado por IA. Revise e edite antes de levar ao médico: a IA pode errar. Os números
                  do PDF (tabelas) são calculados pelo app, não pela IA.
                </div>

                <section className='bg-white rounded-3xl p-5 border border-gray-100 shadow-sm space-y-2'>
                  <h2 className='font-black text-brand-navy'>Resumo do período</h2>
                  <textarea
                    value={resumo}
                    onChange={(e) => setResumo(e.target.value)}
                    maxLength={1800}
                    rows={7}
                    className='w-full rounded-2xl border border-gray-200 bg-gray-50 p-3 text-sm text-brand-navy font-medium focus:outline-none focus:border-brand-blue'
                  />
                </section>

                <Lista
                  titulo='Pontos observados'
                  itens={destaques}
                  onChange={(i, v) => editarLista(destaques, setDestaques, i, v)}
                  onRemover={(i) => setDestaques(destaques.filter((_, j) => j !== i))}
                  onAdicionar={destaques.length < 6 ? () => setDestaques([...destaques, ""]) : undefined}
                />
                <Lista
                  titulo='Perguntas para levar à consulta'
                  itens={perguntas}
                  onChange={(i, v) => editarLista(perguntas, setPerguntas, i, v)}
                  onRemover={(i) => setPerguntas(perguntas.filter((_, j) => j !== i))}
                  onAdicionar={perguntas.length < 5 ? () => setPerguntas([...perguntas, ""]) : undefined}
                />

                <Button onClick={baixar} isLoading={baixando}>
                  <FileDown size={20} className='mr-2' />
                  Baixar PDF
                </Button>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
};

const Card = ({ titulo, valor, pequeno }: { titulo: string; valor: string; pequeno?: boolean }) => (
  <div className='bg-white rounded-2xl border border-gray-100 shadow-sm p-3 text-center'>
    <div className='text-[10px] uppercase font-black tracking-widest text-gray-400'>{titulo}</div>
    <div className={`font-black text-brand-navy mt-1 ${pequeno ? "text-sm leading-tight" : "text-2xl"}`}>{valor}</div>
  </div>
);

interface ListaProps {
  titulo: string;
  itens: string[];
  onChange: (i: number, v: string) => void;
  onRemover: (i: number) => void;
  onAdicionar?: () => void;
}

const Lista = ({ titulo, itens, onChange, onRemover, onAdicionar }: ListaProps) => (
  <section className='bg-white rounded-3xl p-5 border border-gray-100 shadow-sm space-y-3'>
    <h2 className='font-black text-brand-navy'>{titulo}</h2>
    {itens.map((item, i) => (
      <div key={i} className='flex items-start gap-2'>
        <textarea
          value={item}
          onChange={(e) => onChange(i, e.target.value)}
          maxLength={220}
          rows={2}
          className='flex-1 rounded-2xl border border-gray-200 bg-gray-50 p-3 text-sm text-brand-navy font-medium focus:outline-none focus:border-brand-blue resize-none'
        />
        <button
          onClick={() => onRemover(i)}
          aria-label='Remover'
          className='w-8 h-8 mt-1 shrink-0 rounded-full bg-gray-100 text-gray-500 flex items-center justify-center active:scale-90'
        >
          <X size={16} />
        </button>
      </div>
    ))}
    {onAdicionar && (
      <button onClick={onAdicionar} className='flex items-center gap-1 text-sm font-black text-brand-blue-dark'>
        <Plus size={16} /> Adicionar
      </button>
    )}
  </section>
);

import React, { useState } from "react";
import { ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "./Button";

interface Props {
  onAceitar: () => Promise<void>;
  onRecusar: () => void;
}

/** Aviso e consentimento antes do primeiro uso da IA (dados de saúde). */
export const ConsentimentoIA: React.FC<Props> = ({ onAceitar, onRecusar }) => {
  const [carregando, setCarregando] = useState(false);

  const aceitar = async () => {
    setCarregando(true);
    try {
      await onAceitar();
    } finally {
      setCarregando(false);
    }
  };

  return (
    <div className='flex flex-col gap-4 p-6 overflow-y-auto'>
      <div className='flex items-center gap-3'>
        <div className='w-12 h-12 rounded-2xl bg-brand-blue/15 text-brand-blue-dark flex items-center justify-center'>
          <Sparkles size={26} />
        </div>
        <h2 className='text-xl font-black text-brand-navy leading-tight'>
          Assistente com IA do Mediary
        </h2>
      </div>

      <p className='text-sm text-gray-600 font-medium'>
        Para ajudar você a registrar sintomas e a montar o resumo para a consulta, o Mediary usa
        inteligência artificial. Antes de começar, saiba como seus dados são tratados:
      </p>

      <ul className='text-sm text-gray-700 space-y-2 list-disc pl-5'>
        <li>
          O que você escreve ou fala, e os sintomas que você registrou, são enviados para a{" "}
          <b>Anthropic</b>, empresa responsável pelo modelo de IA, apenas para gerar a resposta.
        </li>
        <li>
          Seu <b>nome e e-mail não são enviados</b>.
        </li>
        <li>A conversa não fica guardada no Mediary. Só o sintoma que você confirmar é salvo.</li>
        <li>
          Ao <b>falar</b>, o áudio é transcrito pelo seu navegador. No Chrome, isso é feito por um
          serviço do Google.
        </li>
        <li>
          A IA <b>não faz diagnóstico</b> e pode errar. Confira sempre o que ela entendeu antes de
          salvar e revise o resumo antes de levar ao médico.
        </li>
        <li>Em caso de emergência, ligue 192 (SAMU).</li>
        <li>Você pode desativar a IA quando quiser, em Configurações.</li>
      </ul>

      <div className='flex items-start gap-2 text-xs text-gray-500 bg-gray-50 rounded-2xl p-3'>
        <ShieldCheck size={16} className='shrink-0 mt-0.5 text-brand-teal' />
        <span>
          Você só usa a IA se concordar. Sem ela, o app continua funcionando normalmente.
        </span>
      </div>

      <div className='pt-2'>
        <Button onClick={aceitar} isLoading={carregando}>
          Aceito e quero usar
        </Button>
        <Button variant='ghost' onClick={onRecusar} disabled={carregando}>
          Agora não
        </Button>
      </div>
    </div>
  );
};

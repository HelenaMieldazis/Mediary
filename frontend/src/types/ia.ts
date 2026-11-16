export interface IaStatus {
  disponivel: boolean;
  consentido: boolean;
}

/** Rascunho do sintoma que o servidor devolve a cada passo da conversa. */
export type RascunhoIA = Record<string, string | boolean>;

export interface SintomaProntoIA {
  tipo: string;
  subtipo: string | null;
  descricao: string | null;
  inicio: string;
  fim: string | null;
}

export interface TurnoConversa {
  papel: "paciente" | "assistente";
  texto: string;
}

export interface InterpretacaoIA {
  status: "completo" | "incompleto";
  rascunho: RascunhoIA;
  pergunta: string;
  alerta: string | null;
  sintoma: SintomaProntoIA | null;
}

export interface TipoEstatistica {
  rotulo: string;
  total: number;
  primeiro: string;
  ultimo: string;
  com_duracao: number;
  duracao_media_horas: number | null;
}

export interface EstatisticasIA {
  total: number;
  dias_com_sintoma: number;
  primeiro_registro: string;
  ultimo_registro: string;
  por_tipo: TipoEstatistica[];
  por_dia_semana: { dia: string; total: number }[];
  por_periodo: { periodo: string; faixa: string; total: number }[];
  combinacoes_no_mesmo_dia: { sintomas: [string, string]; dias: number }[];
  duracao: { com_termino: number; media_horas: number; maxima_horas: number } | null;
}

export interface ResumoIA {
  estatisticas: EstatisticasIA;
  resumo: string;
  destaques: string[];
  perguntas: string[];
}

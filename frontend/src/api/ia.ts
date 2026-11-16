import api from "./axios";
import type { IaStatus, InterpretacaoIA, RascunhoIA, ResumoIA, TurnoConversa } from "../types/ia";

function agoraLocal(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export interface PeriodoIA {
  data_inicio?: string;
  data_fim?: string;
}

export const iaService = {
  status: async (): Promise<IaStatus> => (await api.get("/api/ia/status")).data,

  consentimento: async (aceito: boolean): Promise<{ consentido: boolean }> =>
    (await api.post("/api/ia/consentimento", { aceito })).data,

  interpretar: async (
    mensagem: string,
    rascunho: RascunhoIA | null,
    historico: TurnoConversa[]
  ): Promise<InterpretacaoIA> =>
    (
      await api.post("/api/ia/sintoma/interpretar", {
        mensagem,
        rascunho,
        historico,
        agora_local: agoraLocal(),
      })
    ).data,

  gerarResumo: async (periodo: PeriodoIA): Promise<ResumoIA> =>
    (await api.post("/api/ia/resumo", periodo)).data,

  baixarRelatorio: async (
    periodo: PeriodoIA,
    texto: { resumo: string; destaques: string[]; perguntas: string[] }
  ): Promise<Blob> =>
    (await api.post("/api/ia/relatorio/pdf", { ...periodo, ...texto }, { responseType: "blob" }))
      .data as Blob,
};

import api from "./axios";
import type { CreateSintomaDTO, UpdateSintomaDTO } from "../types/sintoma";

export const sintomasService = {
  getSintomasMes: async (ano: number, mes: number) => {
    const response = await api.get(`/api/sintomas/mes/${ano}/${mes}`);
    return response.data;
  },
  getCalendarioInfo: async (ano: number, mes: number) => {
    const response = await api.get(`/api/sintomas/calendario`, {
      params: { ano, mes },
    });
    return response.data;
  },
  getSintomasDia: async (data: string) => {
    const response = await api.get(`/api/sintomas/dia`, {
      params: { data },
    });
    return response.data;
  },
  adicionar: async (dto: CreateSintomaDTO) => {
    const response = await api.post("/api/sintomas", dto);
    return response.data;
  },
  atualizar: async (id: number, dto: UpdateSintomaDTO) => {
    const response = await api.put(`/api/sintomas/${id}`, dto);
    return response.data;
  },
  excluir: async (id: number) => {
    const response = await api.delete(`/api/sintomas/${id}`);
    return response.data;
  },
  /**
   * Baixa o relatório em PDF dos sintomas do usuário autenticado.
   * Datas (opcionais) no formato YYYY-MM-DD.
   */
  exportarRelatorioPdf: async (dataInicio?: string, dataFim?: string) => {
    const response = await api.get("/api/sintomas/relatorio/pdf", {
      params: {
        data_inicio: dataInicio || undefined,
        data_fim: dataFim || undefined,
      },
      responseType: "blob",
    });
    return response.data as Blob;
  },
};

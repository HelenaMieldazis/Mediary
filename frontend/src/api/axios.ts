import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || '';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Anexa o token JWT em toda requisição, se existir
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('mediary_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Se o token expirar/for inválido, limpa e força novo login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('mediary_token');
    }
    return Promise.reject(error);
  }
);

/**
 * Converte um erro do axios em uma mensagem amigável para o usuário,
 * nunca expondo códigos de status, erros de rede ou detalhes internos
 * do servidor/banco de dados.
 */
export function getErrorMessage(
  error: unknown,
  fallback = "Ocorreu um erro. Tente novamente."
): string {
  const err = error as {
    response?: { status?: number; data?: { error?: unknown } };
    request?: unknown;
  };

  // Sem resposta do servidor: problema de rede/conexão.
  if (!err?.response) {
    return "Não foi possível conectar ao servidor. Verifique sua internet e tente novamente.";
  }

  const status = err.response.status;

  // 503 pode trazer uma mensagem amigável do backend (ex.: IA indisponível).
  if (status === 503) {
    const m = err.response.data?.error;
    if (typeof m === "string" && m.trim() && m.length < 200) return m;
  }

  // Erros de servidor (5xx) nunca mostram detalhes internos.
  if (status && status >= 500) {
    return "Ocorreu um erro no servidor. Tente novamente em instantes.";
  }

  const backendMsg = err.response.data?.error;
  if (typeof backendMsg === "string" && backendMsg.trim().length > 0 && backendMsg.length < 200) {
    return backendMsg;
  }

  if (status === 401) {
    return "Sessão expirada ou credenciais inválidas. Faça login novamente.";
  }

  return fallback;
}

export default api;

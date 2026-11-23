import { create } from 'zustand';
import type { User } from '../features/auth/authSchema';
import { authService } from '../api/auth';
import { limparCacheApi } from '../utils/limparCacheApi';

interface AuthState {
  user: User | null;
  /** URL local (blob:) da foto de perfil, ou null se não houver. */
  fotoUrl: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  
  login: (email: string, senha: string) => Promise<void>;
  cadastro: (nome: string, email: string, senha: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  updatePerfil: (nome: string, email: string) => Promise<void>;
  updateSenha: (senhaAtual: string, novaSenha: string) => Promise<void>;
  carregarFoto: () => Promise<void>;
  enviarFoto: (foto: Blob) => Promise<void>;
  removerFoto: () => Promise<void>;
}

function trocarFotoUrl(antiga: string | null, nova: string | null): string | null {
  if (antiga) URL.revokeObjectURL(antiga);
  return nova;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  fotoUrl: null,
  isAuthenticated: false,
  isLoading: true,

  login: async (email, senha) => {
    const data = await authService.login(email, senha);
    set({ user: data.user, isAuthenticated: true });
    void get().carregarFoto();
  },

  cadastro: async (nome, email, senha) => {
    await authService.cadastro(nome, email, senha);
  },

  logout: async () => {
    try {
      await authService.logout();
    } finally {
      set((s) => ({ user: null, isAuthenticated: false, fotoUrl: trocarFotoUrl(s.fotoUrl, null) }));
      await limparCacheApi();
    }
  },

  checkAuth: async () => {
    set({ isLoading: true });
    try {
      const data = await authService.me();
      set({ user: data, isAuthenticated: true });
      if (data.tem_foto) void get().carregarFoto();
    } catch (error) {
      set({ user: null, isAuthenticated: false });
    } finally {
      set({ isLoading: false });
    }
  },

  updatePerfil: async (nome, email) => {
    const data = await authService.updatePerfil(nome, email);
    set((state) => ({
      user: state.user ? { ...state.user, nome: data.nome, email: data.email } : null
    }));
  },

  updateSenha: async (senhaAtual, novaSenha) => {
    await authService.updateSenha(senhaAtual, novaSenha);
  },

  carregarFoto: async () => {
    try {
      const blob = await authService.baixarFoto();
      set((s) => ({ fotoUrl: trocarFotoUrl(s.fotoUrl, URL.createObjectURL(blob)) }));
    } catch {
      // 404 = sem foto; qualquer outro erro: mostra a inicial do nome.
      set((s) => ({ fotoUrl: trocarFotoUrl(s.fotoUrl, null) }));
    }
  },

  enviarFoto: async (foto) => {
    await authService.enviarFoto(foto);
    set((s) => ({ user: s.user ? { ...s.user, tem_foto: true } : null }));
    await get().carregarFoto();
  },

  removerFoto: async () => {
    await authService.removerFoto();
    set((s) => ({
      user: s.user ? { ...s.user, tem_foto: false } : null,
      fotoUrl: trocarFotoUrl(s.fotoUrl, null),
    }));
  }
}));

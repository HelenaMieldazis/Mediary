import { z } from 'zod';

export const userSchema = z.object({
  id: z.number(),
  nome: z.string(),
  email: z.string().email(),
  criado_em: z.string()
});

export type User = z.infer<typeof userSchema>;

// Login: não reforçamos a nova política de senha aqui, pois contas antigas
// podem ter senhas criadas antes dessa regra existir. Só exigimos que não
// esteja vazia — quem valida a senha de fato é o backend, no login.
export const loginSchema = z.object({
  email: z.string().email('E-mail inválido'),
  senha: z.string().min(1, 'Informe sua senha')
});

export type LoginForm = z.infer<typeof loginSchema>;

// Regra de senha para novas contas e trocas de senha:
// mínimo 8 caracteres, 1 maiúscula, 1 minúscula, 1 número e 1 caractere especial.
export const PASSWORD_REGEX =
  /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$/;

export const registerSchema = z
  .object({
    nome: z.string().min(2, 'O nome deve ter pelo menos 2 caracteres'),
    email: z.string().email('E-mail inválido'),
    senha: z
      .string()
      .regex(PASSWORD_REGEX, 'A senha não atende aos requisitos mínimos'),
    confirmarSenha: z.string()
  })
  .refine((data) => data.senha === data.confirmarSenha, {
    message: 'As senhas não coincidem',
    path: ['confirmarSenha']
  });

export type RegisterForm = z.infer<typeof registerSchema>;

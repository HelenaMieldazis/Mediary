import React from "react";
import { Check, X } from "lucide-react";

interface Requisito {
  label: string;
  test: (senha: string) => boolean;
}

export const REQUISITOS_SENHA: Requisito[] = [
  { label: "Pelo menos 8 caracteres", test: (s) => s.length >= 8 },
  { label: "Uma letra maiúscula", test: (s) => /[A-Z]/.test(s) },
  { label: "Uma letra minúscula", test: (s) => /[a-z]/.test(s) },
  { label: "Um número", test: (s) => /[0-9]/.test(s) },
  {
    label: "Um caractere especial (ex: ! @ # $ %)",
    test: (s) => /[^A-Za-z0-9]/.test(s),
  },
];

export const isPasswordValid = (senha: string): boolean =>
  REQUISITOS_SENHA.every((req) => req.test(senha));

/** Retorna a lista de requisitos que a senha ainda não atende. */
export const requisitosFaltando = (senha: string): string[] =>
  REQUISITOS_SENHA.filter((req) => !req.test(senha)).map((req) => req.label);

interface Props {
  senha: string;
  className?: string;
}

/**
 * Checklist visual dos requisitos de senha, atualizado em tempo real
 * conforme o usuário digita.
 */
export const PasswordRequirements: React.FC<Props> = ({ senha, className = "" }) => {
  return (
    <ul className={`space-y-1 px-1 ${className}`}>
      {REQUISITOS_SENHA.map((req) => {
        const atendido = req.test(senha);
        return (
          <li
            key={req.label}
            className={`flex items-center gap-1.5 text-xs font-bold transition-colors ${
              atendido ? "text-green-600" : "text-gray-400"
            }`}
          >
            {atendido ? (
              <Check size={14} strokeWidth={3} />
            ) : (
              <X size={14} strokeWidth={3} />
            )}
            {req.label}
          </li>
        );
      })}
    </ul>
  );
};

import React from "react";
import { useAuthStore } from "../store/useAuthStore";

interface Props {
  /** Classes de tamanho/forma do círculo (ex.: "w-full h-full", "w-11 h-11"). */
  className?: string;
  /** Classes do texto da inicial, quando não há foto. */
  classeInicial?: string;
}

/** Foto de perfil da pessoa logada; sem foto, mostra a inicial do nome. */
export const Avatar: React.FC<Props> = ({ className = "w-full h-full", classeInicial = "text-4xl" }) => {
  const user = useAuthStore((s) => s.user);
  const fotoUrl = useAuthStore((s) => s.fotoUrl);
  const inicial = user?.nome?.trim().charAt(0).toUpperCase() || "U";
  return (
    <div className={`${className} bg-brand-teal rounded-full overflow-hidden flex items-center justify-center`}>
      {fotoUrl ? (
        <img src={fotoUrl} alt='Foto de perfil' className='w-full h-full object-cover' draggable={false} />
      ) : (
        <span className={`text-white font-black ${classeInicial}`}>{inicial}</span>
      )}
    </div>
  );
};

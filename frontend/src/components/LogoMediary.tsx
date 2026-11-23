import React from "react";

/** Logo do Mediary (calendário com a cruz), no mesmo desenho do ícone do app.
 *  Usa currentColor: a cor vem da classe de texto de quem usa. */
export const LogoMediary: React.FC<{ className?: string }> = ({ className = "" }) => (
  <svg viewBox="120 100 272 292" className={className} aria-hidden="true">
    <g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
      <rect x="136" y="150" width="240" height="226" rx="38" strokeWidth="26" />
      <line x1="136" y1="214" x2="376" y2="214" strokeWidth="22" />
      <line x1="200" y1="116" x2="200" y2="176" strokeWidth="26" />
      <line x1="312" y1="116" x2="312" y2="176" strokeWidth="26" />
    </g>
    <g fill="currentColor">
      <rect x="236" y="244" width="40" height="110" rx="9" />
      <rect x="201" y="279" width="110" height="40" rx="9" />
    </g>
  </svg>
);

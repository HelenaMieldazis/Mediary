export function dataBr(iso: string | null | undefined): string {
  if (!iso) return "-";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return a && m && d ? `${d}/${m}/${a}` : "-";
}

export function horasBr(h: number | null | undefined): string {
  if (h === null || h === undefined) return "-";
  if (h < 1) return `${Math.round(h * 60)} min`;
  return `${h.toFixed(1).replace(".", ",")} h`;
}

export function baixarBlob(blob: Blob, nome: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export function hojeIso(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function diasAtrasIso(dias: number): string {
  const d = new Date();
  d.setDate(d.getDate() - dias);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export const ROTULO_TIPO: Record<string, string> = {
  DOR: "Dor",
  NAUSEA: "Náusea",
  FADIGA: "Fadiga",
  VERTIGEM: "Vertigem",
  FALTA_DE_AR: "Falta de ar",
  TOSSE: "Tosse",
  DIARREIA: "Diarreia",
  CONSTIPACAO: "Constipação",
  COCEIRA: "Coceira",
  OUTRO: "Outro",
};

/** "2026-11-15 20:00:00" -> "15/11/2026 às 20:00" */
export function dataHoraBr(valor: string | null | undefined): string {
  if (!valor) return "";
  const [d, h] = valor.split(" ");
  return `${dataBr(d)}${h ? ` às ${h.slice(0, 5)}` : ""}`;
}

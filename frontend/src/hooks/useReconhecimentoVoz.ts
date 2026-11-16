import { useCallback, useEffect, useRef, useState } from "react";

// Tipos mínimos da Web Speech API (não vêm no lib.dom do TypeScript).
interface RecAlternativa {
  transcript: string;
}
interface RecResultado {
  isFinal: boolean;
  0: RecAlternativa;
}
interface RecEvento {
  resultIndex: number;
  results: ArrayLike<RecResultado>;
}
interface RecErro {
  error: string;
}
interface Reconhecedor {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: RecEvento) => void) | null;
  onerror: ((e: RecErro) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}
type Construtor = new () => Reconhecedor;

function obterConstrutor(): Construtor | null {
  const w = window as unknown as {
    SpeechRecognition?: Construtor;
    webkitSpeechRecognition?: Construtor;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

const ERROS: Record<string, string> = {
  "not-allowed": "Permita o uso do microfone no navegador para falar.",
  "service-not-allowed": "Permita o uso do microfone no navegador para falar.",
  "no-speech": "Não ouvi nada. Toque no microfone e tente de novo.",
  "audio-capture": "Não encontrei um microfone neste aparelho.",
  network: "Sem conexão para reconhecer a voz. Você pode digitar.",
};

interface Opcoes {
  /** Chamado com o texto final quando a pessoa termina de falar. */
  aoTerminar: (texto: string) => void;
}

export function useReconhecimentoVoz({ aoTerminar }: Opcoes) {
  const [suportado] = useState(() => obterConstrutor() !== null);
  const [ouvindo, setOuvindo] = useState(false);
  const [parcial, setParcial] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  const rec = useRef<Reconhecedor | null>(null);
  const final = useRef("");
  const cancelado = useRef(false);
  const callback = useRef(aoTerminar);

  useEffect(() => {
    callback.current = aoTerminar;
  }, [aoTerminar]);

  useEffect(() => () => rec.current?.abort(), []);

  const iniciar = useCallback(() => {
    const C = obterConstrutor();
    if (!C) return;
    setErro(null);
    setParcial("");
    final.current = "";
    cancelado.current = false;

    const r = new C();
    r.lang = "pt-BR";
    r.continuous = false;
    r.interimResults = true;
    r.onresult = (e) => {
      let interino = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const trecho = e.results[i][0].transcript;
        if (e.results[i].isFinal) final.current += trecho + " ";
        else interino += trecho;
      }
      setParcial((final.current + interino).trim());
    };
    r.onerror = (e) => {
      if (e.error === "aborted") return;
      cancelado.current = true;
      setErro(ERROS[e.error] || "Não consegui entender. Tente de novo ou digite.");
    };
    r.onend = () => {
      setOuvindo(false);
      const texto = final.current.trim();
      setParcial("");
      if (!cancelado.current && texto) callback.current(texto);
      rec.current = null;
    };
    rec.current = r;
    try {
      r.start();
      setOuvindo(true);
    } catch {
      setErro("Não foi possível iniciar o microfone.");
    }
  }, []);

  const parar = useCallback(() => rec.current?.stop(), []);

  const cancelar = useCallback(() => {
    cancelado.current = true;
    rec.current?.abort();
  }, []);

  return { suportado, ouvindo, parcial, erro, iniciar, parar, cancelar };
}

"""
Teste rápido da integração com a IA, usando a SUA chave de verdade.
Não usa banco de dados e não grava nada.

Como rodar (dentro da pasta backend/, com o ANTHROPIC_API_KEY no .env):
    python testar_ia.py

Se aparecer "OK" nas duas etapas, a IA está funcionando.
"""
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

import ia_service  # noqa: E402


def main():
    if not ia_service.ia_configurada():
        print("Falta o ANTHROPIC_API_KEY no arquivo backend/.env")
        return 1

    agora = datetime.now()
    ontem = agora - timedelta(days=1)

    print("1) Cadastro por texto...")
    try:
        r = ia_service.interpretar_mensagem(
            "ontem à noite tive uma dor de cabeça forte por umas duas horas e tomei dipirona",
            rascunho=None, historico=[], agora=agora)
        print("   status:", r["status"])
        print("   rascunho:", r["rascunho"])
        if r["pergunta"]:
            print("   pergunta da IA:", r["pergunta"])
        print("   sintoma pronto:", r["sintoma"])
        print("   OK")
    except Exception as e:
        print("   FALHOU:", type(e).__name__, "- veja a mensagem acima nos logs")
        return 1

    print("2) Resumo para a consulta...")
    exemplo = [
        {"tipo": "DOR", "subtipo": "CABEÇA", "inicio": ontem.replace(hour=20, minute=0),
         "fim": ontem.replace(hour=22, minute=0), "descricao": "forte, tomei dipirona"},
        {"tipo": "NAUSEA", "subtipo": None, "inicio": ontem.replace(hour=21, minute=0),
         "fim": None, "descricao": None},
        {"tipo": "DOR", "subtipo": "CABEÇA", "inicio": agora - timedelta(days=8),
         "fim": None, "descricao": "pela manhã"},
    ]
    try:
        r = ia_service.gerar_resumo(exemplo)
        print("   resumo:", r["resumo"])
        for d in r["destaques"]:
            print("   -", d)
        print("   OK")
    except Exception as e:
        print("   FALHOU:", type(e).__name__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

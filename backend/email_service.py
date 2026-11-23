"""
Envio de e-mails do Mediary (hoje só o de redefinição de senha), pelo Amazon SES.

Configuração (variáveis de ambiente):
  EMAIL_REMETENTE   ex.: "Mediary <nao-responda@seudominio.com.br>". Sem ela, o envio
                    fica desligado: em desenvolvimento o link aparece no log local;
                    em produção só registramos que o e-mail não foi enviado.
  SES_REGIAO        região do SES (padrão: AWS_REGION ou sa-east-1).

As credenciais da AWS vêm do papel IAM da instância (nunca de chaves no código).
O conteúdo do e-mail e o link nunca são registrados em log em produção.
"""
import logging
import os
from html import escape

logger = logging.getLogger("mediary.email")


class EmailNaoEnviado(Exception):
    """O provedor recusou ou falhou ao enviar."""


def remetente():
    return (os.environ.get("EMAIL_REMETENTE") or "").strip()


def email_configurado():
    return bool(remetente())


def _em_producao():
    return os.environ.get("AMBIENTE", "").strip().lower() in ("producao", "production", "prod")


_cliente = None


def _cliente_ses():
    global _cliente
    if _cliente is None:
        import boto3
        regiao = os.environ.get("SES_REGIAO") or os.environ.get("AWS_REGION") or "sa-east-1"
        _cliente = boto3.client("sesv2", region_name=regiao)
    return _cliente


def _enviar(destinatario, assunto, texto, html):
    if not email_configurado():
        if _em_producao():
            logger.error("E-mail não enviado: EMAIL_REMETENTE não configurado.")
        else:
            # Só em desenvolvimento: permite testar o fluxo sem SES.
            logger.warning("[DEV] E-mail não enviado (sem EMAIL_REMETENTE). Conteúdo:\n%s", texto)
        return
    try:
        _cliente_ses().send_email(
            FromEmailAddress=remetente(),
            Destination={"ToAddresses": [destinatario]},
            Content={"Simple": {
                "Subject": {"Data": assunto, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": texto, "Charset": "UTF-8"},
                         "Html": {"Data": html, "Charset": "UTF-8"}},
            }},
        )
    except Exception as e:
        # Sem o endereço do destinatário nem o link no log.
        codigo = getattr(e, "response", {}).get("Error", {}).get("Code") if hasattr(e, "response") else None
        logger.error("Falha ao enviar e-mail pelo SES: %s (%s)", type(e).__name__, codigo)
        raise EmailNaoEnviado(type(e).__name__) from e


def enviar_redefinicao_senha(destinatario, nome, link, minutos_validade):
    primeiro_nome = (nome or "").split(" ")[0] or "Olá"
    assunto = "Mediary: redefinição de senha"
    texto = (
        f"{primeiro_nome}, recebemos um pedido para redefinir a senha da sua conta no Mediary.\n\n"
        f"Para criar uma nova senha, abra o link abaixo (válido por {minutos_validade} minutos, uma única vez):\n"
        f"{link}\n\n"
        "Se não foi você, ignore este e-mail: sua senha continua a mesma.\n\n"
        "Mediary - seu diário de sintomas"
    )
    html = f"""<!doctype html><html lang="pt-BR"><body style="font-family:Arial,sans-serif;color:#173B5E;background:#f5f7fa;padding:24px">
<div style="max-width:480px;margin:auto;background:#fff;border-radius:16px;padding:28px">
<h2 style="margin-top:0">Redefinição de senha</h2>
<p>{escape(primeiro_nome)}, recebemos um pedido para redefinir a senha da sua conta no Mediary.</p>
<p style="text-align:center;margin:28px 0"><a href="{escape(link, quote=True)}"
 style="background:#21A9BC;color:#fff;text-decoration:none;font-weight:bold;padding:14px 24px;border-radius:12px;display:inline-block">Criar nova senha</a></p>
<p style="font-size:13px;color:#555">O link vale por {minutos_validade} minutos e só pode ser usado uma vez.
Se não foi você, ignore este e-mail: sua senha continua a mesma.</p>
<p style="font-size:12px;color:#888;word-break:break-all">Se o botão não funcionar, copie no navegador:<br>{escape(link)}</p>
</div></body></html>"""
    _enviar(destinatario, assunto, texto, html)

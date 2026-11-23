"""Envio de e-mail (SES) sem rede: o cliente do SES é substituído por um falso."""
import os
import unittest
from unittest import mock

import email_service as es


class EmailService(unittest.TestCase):
    def tearDown(self):
        es._cliente = None

    def test_monta_chamada_do_ses(self):
        falso = mock.Mock()
        with mock.patch.dict(os.environ, {"EMAIL_REMETENTE": "Mediary <nao-responda@exemplo.com.br>"}), \
             mock.patch.object(es, "_cliente_ses", return_value=falso):
            es.enviar_redefinicao_senha("ana@exemplo.com", "Ana <b>Maria</b>",
                                        "https://app.exemplo.com.br/redefinir-senha?token=abc&x=1", 30)
        kw = falso.send_email.call_args.kwargs
        self.assertEqual(kw["FromEmailAddress"], "Mediary <nao-responda@exemplo.com.br>")
        self.assertEqual(kw["Destination"], {"ToAddresses": ["ana@exemplo.com"]})
        corpo = kw["Content"]["Simple"]
        self.assertIn("redefinição", corpo["Subject"]["Data"])
        self.assertIn("token=abc&x=1", corpo["Body"]["Text"]["Data"])
        html = corpo["Body"]["Html"]["Data"]
        self.assertIn("token=abc&amp;x=1", html)        # link escapado no HTML
        self.assertNotIn("<b>Maria</b>", html)           # nome escapado
        self.assertIn("30 minutos", html)

    def test_falha_do_ses_vira_excecao_sem_dados(self):
        falso = mock.Mock()
        falso.send_email.side_effect = RuntimeError("ana@exemplo.com rejeitado")
        with mock.patch.dict(os.environ, {"EMAIL_REMETENTE": "x@exemplo.com.br"}), \
             mock.patch.object(es, "_cliente_ses", return_value=falso), \
             self.assertLogs("mediary.email", level="ERROR") as logs:
            with self.assertRaises(es.EmailNaoEnviado):
                es.enviar_redefinicao_senha("ana@exemplo.com", "Ana", "https://x/redefinir-senha?token=t", 30)
        self.assertNotIn("ana@exemplo.com", "\n".join(logs.output))

    def test_sem_remetente_nao_chama_ses(self):
        with mock.patch.dict(os.environ, {"EMAIL_REMETENTE": "", "AMBIENTE": "producao"}), \
             mock.patch.object(es, "_cliente_ses") as cli, \
             self.assertLogs("mediary.email", level="ERROR") as logs:
            es.enviar_redefinicao_senha("a@b.com", "A", "https://x/redefinir-senha?token=segredo", 30)
        cli.assert_not_called()
        self.assertNotIn("segredo", "\n".join(logs.output))  # em produção o link não vai para o log


if __name__ == "__main__":
    unittest.main()

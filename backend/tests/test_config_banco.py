"""Leitura da DATABASE_URL do MySQL (sem precisar de banco)."""
import os
import unittest
from datetime import datetime, timezone
from urllib.parse import quote

os.environ.setdefault("MEDIARY_PULAR_INIT_DB", "1")
import app  # noqa: E402


class ConfigBanco(unittest.TestCase):
    def test_url_simples(self):
        c = app._config_banco("mysql://usuario:senha@db.exemplo:3306/mediary", senha="")
        self.assertEqual((c["host"], c["port"], c["user"], c["password"], c["database"]),
                         ("db.exemplo", 3306, "usuario", "senha", "mediary"))
        self.assertEqual((c["charset"], c["collation"]), ("utf8mb4", "utf8mb4_unicode_ci"))
        self.assertNotIn("ssl", c)

    def test_porta_padrao_e_driver_explicito(self):
        c = app._config_banco("mysql+pymysql://u:p@host/banco", senha="")
        self.assertEqual(c["port"], 3306)

    def test_senha_com_caracteres_especiais_codificada(self):
        senha = "S3nh@/c0m?#especiais:%"
        c = app._config_banco(f"mysql://u:{quote(senha, safe='')}@h:3306/b", senha="")
        self.assertEqual(c["password"], senha)

    def test_senha_com_arroba_e_dois_pontos_sem_codificar(self):
        c = app._config_banco("mysql://u:a:b@c@h:3306/b", senha="")
        self.assertEqual((c["user"], c["password"], c["host"]), ("u", "a:b@c", "h"))

    def test_database_password_tem_prioridade(self):
        c = app._config_banco("mysql://u:velha@h/b", senha="nova/#?@")
        self.assertEqual(c["password"], "nova/#?@")

    def test_ssl_ca_na_url(self):
        c = app._config_banco("mysql://u:p@h/b?ssl_ca=/certs/ca.pem", senha="")
        self.assertEqual(c["ssl"], {"ca": "/certs/ca.pem"})

    def test_rejeita_postgres(self):
        with self.assertRaises(ValueError):
            app._config_banco("postgresql://u:p@h/b", senha="")


class DatasEFuso(unittest.TestCase):
    def test_dia_da_cota_em_sao_paulo(self):
        # 02:30 UTC de 16/11 ainda é 23:30 de 15/11 em Brasília.
        self.assertEqual(str(app.dia_local_cota(datetime(2026, 11, 16, 2, 30, tzinfo=timezone.utc))),
                         "2026-11-15")
        self.assertEqual(str(app.dia_local_cota(datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc))),
                         "2026-11-16")

    def test_parse_data_hora(self):
        self.assertEqual(app._parse_data_hora("2026-11-15 20:00:00"), datetime(2026, 11, 15, 20, 0))
        self.assertEqual(app._parse_data_hora("2026-11-15 20:00"), datetime(2026, 11, 15, 20, 0))
        # Como o Postgres fazia numa coluna TIMESTAMP: o fuso do texto é ignorado.
        self.assertEqual(app._parse_data_hora("2026-11-15T20:00:00.123Z"), datetime(2026, 11, 15, 20, 0))
        for ruim in ("ontem", "", None, "2026-13-01 10:00"):
            with self.assertRaises(ValueError):
                app._parse_data_hora(ruim)

    def test_json_de_datas_sem_gmt(self):
        with app.app.app_context():
            self.assertEqual(app.app.json.dumps({"d": datetime(2026, 11, 15, 20, 0)}),
                             '{"d": "2026-11-15T20:00:00"}')


if __name__ == "__main__":
    unittest.main()

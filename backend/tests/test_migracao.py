"""Teste do script de migração Postgres -> MySQL, com os dois bancos de verdade.

Cria na origem as tabelas exatamente como o init_db ANTIGO (Postgres) criava, com
dados acentuados, emoji, TIMESTAMP com microssegundos e um usuário sem consentimento;
exporta, importa e confere contagens e conteúdo. Bancos DESCARTÁVEIS ('teste' no nome).

    MEDIARY_TEST_PG_URL="postgresql://postgres:SENHA@127.0.0.1:5433/origem_teste" \\
    MEDIARY_TEST_MIGRACAO_MYSQL_URL="mysql://root:SENHA@127.0.0.1:3307/migracao_teste" \\
        python -m unittest tests.test_migracao -v
"""
import gzip
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, date
from unittest import mock

PG = os.environ.get("MEDIARY_TEST_PG_URL", "")
MY = os.environ.get("MEDIARY_TEST_MIGRACAO_MYSQL_URL", "")

ESQUEMA_ANTIGO = [
    """CREATE TABLE IF NOT EXISTS Usuarios (id SERIAL PRIMARY KEY, nome TEXT NOT NULL,
       email TEXT NOT NULL UNIQUE, senha_hash TEXT NOT NULL, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS Sintomas (id SERIAL PRIMARY KEY, usuario_id INTEGER NOT NULL,
       tipo TEXT NOT NULL, subtipo TEXT, descricao TEXT, inicio TIMESTAMP NOT NULL, fim TIMESTAMP,
       criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP, atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       FOREIGN KEY (usuario_id) REFERENCES Usuarios(id) ON DELETE CASCADE)""",
    "ALTER TABLE Usuarios ADD COLUMN IF NOT EXISTS ia_consentimento_em TIMESTAMP",
    """CREATE TABLE IF NOT EXISTS IaUso (usuario_id INTEGER NOT NULL REFERENCES Usuarios(id) ON DELETE CASCADE,
       dia DATE NOT NULL, recurso TEXT NOT NULL, total INTEGER NOT NULL DEFAULT 0,
       PRIMARY KEY (usuario_id, dia, recurso))""",
]


@unittest.skipUnless(PG and MY, "defina MEDIARY_TEST_PG_URL e MEDIARY_TEST_MIGRACAO_MYSQL_URL")
class Migracao(unittest.TestCase):
    def setUp(self):
        assert "teste" in PG.rsplit("/", 1)[-1] and "teste" in MY.rsplit("/", 1)[-1]
        import psycopg2
        self.pg = psycopg2.connect(PG)
        with self.pg.cursor() as c:
            c.execute("DROP TABLE IF EXISTS iauso, sintomas, usuarios CASCADE")
            for sql in ESQUEMA_ANTIGO:
                c.execute(sql)
            c.execute("""INSERT INTO Usuarios (id, nome, email, senha_hash, criado_em, ia_consentimento_em) VALUES
                (1, 'Maria da Conceição', 'maria@exemplo.com', 'scrypt:hash1', '2026-01-02 03:04:05.678901', '2026-02-01 10:00:00'),
                (7, 'João Ninguém', 'joao@exemplo.com', 'scrypt:hash2', '2026-03-01 00:00:00', NULL)""")
            c.execute("SELECT setval('usuarios_id_seq', 7)")
            c.execute("""INSERT INTO Sintomas (id, usuario_id, tipo, subtipo, descricao, inicio, fim) VALUES
                (10, 1, 'DOR', 'CABEÇA', 'latejante 😣 — piora à noite', '2026-10-01 20:00:00', '2026-10-01 22:30:00'),
                (11, 1, 'NAUSEA', NULL, NULL, '2026-10-02 08:00:00', NULL),
                (12, 7, 'OUTRO', NULL, 'formigamento <b>&</b>', '2026-10-03 23:59:59.900', NULL)""")
            c.execute("INSERT INTO IaUso VALUES (1, '2026-10-02', 'interpretar', 4)")
        self.pg.commit()
        self.env = mock.patch.dict(os.environ, {"PG_DATABASE_URL": PG, "DATABASE_URL": MY,
                                                "DATABASE_PASSWORD": "", "MEDIARY_PULAR_INIT_DB": "1"})
        self.env.start()
        import app
        self.app = app
        conn = app.get_db()
        with conn.cursor() as c:
            for t in ("FotoPerfil", "RedefinicaoSenha", "IaUso", "Sintomas", "Usuarios"):
                c.execute(f"DROP TABLE IF EXISTS `{t}`")
        conn.commit()
        conn.close()
        self.tmp = tempfile.mkdtemp()
        self.arquivo = os.path.join(self.tmp, "dump.json.gz")

    def tearDown(self):
        self.env.stop()
        self.pg.close()

    def rodar(self, *args):
        from scripts import migrar_postgres_para_mysql as m
        saida = io.StringIO()
        with redirect_stdout(saida):
            m.main(list(args))
        return saida.getvalue()

    def test_exportar_importar_e_conferir(self):
        saida = self.rodar("exportar", "--arquivo", self.arquivo)
        self.assertIn("Nada foi alterado no Postgres", saida)
        self.assertEqual(oct(os.stat(self.arquivo).st_mode & 0o777), "0o600")
        self.assertNotIn("maria@exemplo.com", saida)  # o script só imprime contagens
        with gzip.open(self.arquivo, "rt", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["contagens"], {"Usuarios": 2, "Sintomas": 3, "IaUso": 1})

        saida = self.rodar("importar", "--arquivo", self.arquivo, "--simular")
        self.assertIn("Simulação OK", saida)
        conn = self.app.get_db()
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM Usuarios")
            self.assertEqual(c.fetchone()[0], 0)
        conn.close()

        saida = self.rodar("importar", "--arquivo", self.arquivo)
        self.assertIn("Contagens conferem", saida)

        conn = self.app.get_db()
        with conn.cursor() as c:
            c.execute("SELECT id, nome, email, senha_hash, criado_em, ia_consentimento_em FROM Usuarios ORDER BY id")
            self.assertEqual(c.fetchall(), (
                (1, "Maria da Conceição", "maria@exemplo.com", "scrypt:hash1", datetime(2026, 1, 2, 3, 4, 5),
                 datetime(2026, 2, 1, 10, 0)),
                (7, "João Ninguém", "joao@exemplo.com", "scrypt:hash2", datetime(2026, 3, 1), None)))
            c.execute("SELECT id, usuario_id, tipo, subtipo, descricao, inicio, fim FROM Sintomas ORDER BY id")
            linhas = c.fetchall()
            self.assertEqual(linhas[0], (10, 1, "DOR", "CABEÇA", "latejante 😣 — piora à noite",
                                         datetime(2026, 10, 1, 20, 0), datetime(2026, 10, 1, 22, 30)))
            # Microssegundos são truncados (não arredondados para o dia seguinte).
            self.assertEqual(linhas[2][5], datetime(2026, 10, 3, 23, 59, 59))
            c.execute("SELECT usuario_id, dia, recurso, total FROM IaUso")
            self.assertEqual(c.fetchall(), ((1, date(2026, 10, 2), "interpretar", 4),))
            # Novos cadastros continuam a numeração depois do maior id migrado.
            c.execute("INSERT INTO Usuarios (nome, email, senha_hash) VALUES ('Novo', 'novo@x.com', 'h')")
            self.assertEqual(c.lastrowid, 8)
        conn.rollback()
        conn.close()

        # Rodar de novo é recusado: não duplica dados.
        with self.assertRaises(SystemExit):
            self.rodar("importar", "--arquivo", self.arquivo)

        # A origem continua intacta.
        with self.pg.cursor() as c:
            c.execute("SELECT (SELECT COUNT(*) FROM usuarios), (SELECT COUNT(*) FROM sintomas), "
                      "(SELECT COUNT(*) FROM iauso)")
            self.assertEqual(c.fetchone(), (2, 3, 1))

        saida = self.rodar("contar")
        self.assertEqual(saida.count("Usuarios   2"), 2)
        self.assertEqual(saida.count("Sintomas   3"), 2)

    def test_conexao_de_origem_e_somente_leitura(self):
        from scripts import migrar_postgres_para_mysql as m
        conn = m.conectar_postgres()
        import psycopg2
        with self.assertRaises(psycopg2.errors.ReadOnlySqlTransaction):
            with conn.cursor() as c:
                c.execute("DELETE FROM sintomas")
        conn.close()

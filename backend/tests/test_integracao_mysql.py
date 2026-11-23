"""Testes de integração com um MySQL 8 de verdade (e um servidor falso da Anthropic).

Precisa de um banco DESCARTÁVEL: os testes apagam e recriam as tabelas dele.
Por segurança, o nome do banco tem que conter "teste".

Rodar (dentro de backend/), com um MySQL no Docker:
    docker run -d --name mediary-mysql-teste -e MYSQL_ROOT_PASSWORD=root \\
        -e MYSQL_DATABASE=mediary_teste -p 127.0.0.1:3307:3306 mysql:8.4
    MEDIARY_TEST_DATABASE_URL="mysql://root:root@127.0.0.1:3307/mediary_teste" \\
        python -m unittest discover -s tests -t . -v

Sem MEDIARY_TEST_DATABASE_URL estes testes são pulados.
"""
import io
import os
import threading
import unittest
from datetime import datetime, timedelta
from unittest import mock
from urllib.parse import urlsplit

URL_TESTE = os.environ.get("MEDIARY_TEST_DATABASE_URL", "")

if URL_TESTE:
    os.environ["DATABASE_URL"] = URL_TESTE
    os.environ["DATABASE_PASSWORD"] = ""
os.environ["MEDIARY_PULAR_INIT_DB"] = "1"

import app as mediary  # noqa: E402
import ia_service  # noqa: E402
from tests.fake_anthropic import ServidorFalsoAnthropic  # noqa: E402

SENHA = "Senha#Forte1"
HOJE = datetime.now().replace(second=0, microsecond=0)


def _dt(dias_atras, hora=10, minuto=0):
    return (HOJE - timedelta(days=dias_atras)).replace(hour=hora, minute=minuto)


def _txt(d):
    return d.strftime("%Y-%m-%d %H:%M:%S")


def _texto_pdf(dados):
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(dados)).pages)


@unittest.skipUnless(URL_TESTE, "defina MEDIARY_TEST_DATABASE_URL para rodar com MySQL real")
class IntegracaoMySQL(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        nome_banco = urlsplit(URL_TESTE).path.lstrip("/")
        assert "teste" in nome_banco, "use um banco descartável com 'teste' no nome"
        cls.fake = ServidorFalsoAnthropic().__enter__()
        cls._env = mock.patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "chave-falsa-de-teste",
            "ANTHROPIC_BASE_URL": cls.fake.url,
            "IA_LIMITE_DIARIO_INTERPRETAR": "3",
            "IA_LIMITE_DIARIO_RESUMO": "2",
        })
        cls._env.start()
        ia_service._resetar_cliente()
        conn = mediary.get_db()
        with conn.cursor() as cur:
            for t in ("RedefinicaoSenha", "IaUso", "Sintomas", "Usuarios"):
                cur.execute(f"DROP TABLE IF EXISTS `{t}`")
        conn.commit()
        conn.close()
        mediary.init_db()
        mediary.init_db()  # idempotente
        cls.client = mediary.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls._env.stop()
        cls.fake.__exit__(None, None, None)
        ia_service._resetar_cliente()

    def setUp(self):
        self.fake.limpar()

    # ── utilidades ──
    def _sql(self, query, params=()):
        conn = mediary.get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                linhas = cur.fetchall()
            conn.commit()
            return linhas
        finally:
            conn.close()

    def _novo_usuario(self, nome, email):
        r = self.client.post("/api/cadastro", json={"nome": nome, "email": email, "senha": SENHA})
        self.assertEqual(r.status_code, 201, r.get_json())
        r = self.client.post("/api/login", json={"email": email, "senha": SENHA})
        self.assertEqual(r.status_code, 200)
        dados = r.get_json()
        return {"Authorization": f"Bearer {dados['token']}"}, dados["user"]["id"]

    def _sintoma(self, h, **campos):
        r = self.client.post("/api/sintomas", json=campos, headers=h)
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()["id"]

    # ── esquema ──
    def test_00_esquema_utf8mb4_e_coluna_da_ia(self):
        linhas = self._sql("""SELECT TABLE_NAME, TABLE_COLLATION, ENGINE FROM information_schema.TABLES
                              WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME""")
        self.assertEqual({l[0] for l in linhas}, {"IaUso", "RedefinicaoSenha", "Sintomas", "Usuarios"})
        for _, coll, engine in linhas:
            self.assertEqual((coll, engine), ("utf8mb4_unicode_ci", "InnoDB"))
        # ADD COLUMN idempotente: remove a coluna e o init_db a recria.
        self._sql("ALTER TABLE Usuarios DROP COLUMN ia_consentimento_em")
        mediary.init_db()
        self.assertTrue(self._sql("""SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE()
                                     AND TABLE_NAME='Usuarios' AND COLUMN_NAME='ia_consentimento_em'"""))

    # ── cadastro e login ──
    def test_cadastro_login_e_perfil(self):
        r = self.client.post("/api/cadastro", json={"nome": "José da Conceição Ção",
                                                    "email": " Jose.Cadastro@Exemplo.com ", "senha": SENHA})
        self.assertEqual(r.status_code, 201)
        r = self.client.post("/api/cadastro", json={"nome": "Outro", "email": "jose.cadastro@exemplo.com",
                                                    "senha": SENHA})
        self.assertEqual((r.status_code, r.get_json()["error"]), (400, "E-mail já cadastrado"))
        r = self.client.post("/api/cadastro", json={"nome": "X", "email": "fraca@exemplo.com", "senha": "abc"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.post("/api/login", json={"email": "jose.cadastro@exemplo.com",
                                                              "senha": "Errada#123"}).status_code, 401)
        r = self.client.post("/api/login", json={"email": "JOSE.CADASTRO@exemplo.com", "senha": SENHA})
        self.assertEqual(r.status_code, 200)
        h = {"Authorization": f"Bearer {r.get_json()['token']}"}
        self.assertEqual(self.client.get("/api/me", headers=h).get_json()["nome"], "José da Conceição Ção")
        self.assertEqual(self.client.get("/api/me").status_code, 401)
        self.assertEqual(self.client.get("/api/me", headers={"Authorization": "Bearer lixo"}).status_code, 401)
        # Senha guardada com hash, nunca em texto.
        hash_ = self._sql("SELECT senha_hash FROM Usuarios WHERE email=%s", ("jose.cadastro@exemplo.com",))[0][0]
        self.assertNotIn(SENHA, hash_)
        self.assertTrue(hash_.startswith(("scrypt:", "pbkdf2:")))

        # Troca de e-mail com maiúsculas continua permitindo login (bug corrigido).
        r = self.client.put("/api/usuario", json={"nome": "José", "email": "Novo.Email@Exemplo.com"}, headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.post("/api/login", json={"email": "novo.email@exemplo.com",
                                                              "senha": SENHA}).status_code, 200)
        # Trocar a senha.
        r = self.client.put("/api/usuario/senha", json={"senha_atual": SENHA, "senha_nova": "Outra#Senha2"},
                            headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.post("/api/login", json={"email": "novo.email@exemplo.com",
                                                              "senha": "Outra#Senha2"}).status_code, 200)
        # E-mail de outra pessoa.
        self._novo_usuario("Ocupado", "ocupado@exemplo.com")
        r = self.client.put("/api/usuario", json={"nome": "José", "email": "ocupado@exemplo.com"}, headers=h)
        self.assertEqual(r.status_code, 400)

    # ── sintomas, calendário e isolamento ──
    def test_crud_calendario_e_isolamento(self):
        ha, _ = self._novo_usuario("Ana", "ana.crud@exemplo.com")
        hb, _ = self._novo_usuario("Bruno", "bruno.crud@exemplo.com")
        d1 = _dt(3, 20)
        id_a = self._sintoma(ha, tipo="DOR", subtipo="CABEÇA", descricao="latejante, tomei dipirona 😣",
                             inicio=_txt(d1), fim=_txt(d1 + timedelta(hours=2)))
        # Formato ISO com Z (usado em AdicionarSintomasPage) também é aceito.
        self._sintoma(ha, tipo="NAUSEA", subtipo=None, descricao=None,
                      inicio=d1.replace(hour=21).strftime("%Y-%m-%dT%H:%M:%S.000Z"), fim=None)
        id_b = self._sintoma(hb, tipo="TOSSE", subtipo=None, descricao="segredo do Bruno", inicio=_txt(d1), fim=None)

        dia = d1.strftime("%Y-%m-%d")
        lista = self.client.get(f"/api/sintomas/dia?data={dia}", headers=ha).get_json()
        self.assertEqual([s["tipo"] for s in lista], ["DOR", "NAUSEA"])
        self.assertEqual(lista[0]["descricao"], "latejante, tomei dipirona 😣")
        self.assertEqual(lista[0]["inicio"], d1.strftime("%Y-%m-%dT%H:%M:%S"))
        self.assertEqual(self.client.get("/api/sintomas/dia?data=ontem", headers=ha).status_code, 400)

        mes = self.client.get(f"/api/sintomas/mes/{d1.year}/{d1.month}", headers=ha).get_json()
        self.assertEqual({s["id"] for s in mes} >= {id_a}, True)
        self.assertEqual(mes[0]["tipo"] in ("DOR", "NAUSEA"), True)  # dicts de verdade, não {"id": "id"}
        cal = self.client.get(f"/api/sintomas/calendario?ano={d1.year}&mes={d1.month}", headers=ha).get_json()
        self.assertEqual(cal.get(dia), 2)
        self.assertEqual(self.client.get("/api/sintomas/calendario?ano=x&mes=1", headers=ha).status_code, 400)

        # Isolamento: B não vê, não edita e não apaga o que é de A.
        lista_b = self.client.get(f"/api/sintomas/dia?data={dia}", headers=hb).get_json()
        self.assertEqual([s["id"] for s in lista_b], [id_b])
        cal_b = self.client.get(f"/api/sintomas/calendario?ano={d1.year}&mes={d1.month}", headers=hb).get_json()
        self.assertEqual(cal_b.get(dia), 1)
        self.assertEqual(self.client.put(f"/api/sintomas/{id_a}", json={"descricao": "hack"},
                                         headers=hb).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/sintomas/{id_a}", headers=hb).status_code, 404)
        self.assertEqual(self._sql("SELECT descricao FROM Sintomas WHERE id=%s", (id_a,))[0][0],
                         "latejante, tomei dipirona 😣")

        # Edição pelo dono (formato enviado pelo ModalViewSintomas).
        r = self.client.put(f"/api/sintomas/{id_a}", headers=ha, json={
            "tipo": "DOR", "subtipo": "COSTAS", "descricao": "melhorou à tarde",
            "inicio": _txt(d1.replace(hour=19)), "fim": None})
        self.assertEqual(r.status_code, 200)
        linha = self._sql("SELECT subtipo, descricao, inicio, fim FROM Sintomas WHERE id=%s", (id_a,))[0]
        self.assertEqual(linha, ("COSTAS", "melhorou à tarde", d1.replace(hour=19), None))
        r = self.client.put(f"/api/sintomas/{id_a}", headers=ha, json={
            "inicio": _txt(d1), "fim": _txt(d1 - timedelta(hours=1))})
        self.assertEqual(r.status_code, 400)

        # Validações do cadastro de sintoma.
        for ruim in ({"tipo": "DOR", "inicio": _txt(HOJE + timedelta(days=2))},
                     {"tipo": "DOR", "inicio": _txt(HOJE - timedelta(days=400))},
                     {"tipo": "DOR", "inicio": "ontem"},
                     {"tipo": "DOR", "inicio": _txt(d1), "fim": _txt(d1 - timedelta(hours=1))},
                     {"inicio": _txt(d1)}):
            self.assertEqual(self.client.post("/api/sintomas", json=ruim, headers=ha).status_code, 400, ruim)

        # Exclusão pelo dono.
        self.assertEqual(self.client.delete(f"/api/sintomas/{id_a}", headers=ha).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/sintomas/{id_a}", headers=ha).status_code, 404)

    def test_sintoma_de_varios_dias_no_calendario(self):
        h, _ = self._novo_usuario("Carla", "carla.cal@exemplo.com")
        ini = _dt(40, 22)
        fim = ini + timedelta(days=2)
        self._sintoma(h, tipo="FADIGA", inicio=_txt(ini), fim=_txt(fim))
        contagem = {}
        for d in (ini, ini + timedelta(days=1), fim):
            cal = self.client.get(f"/api/sintomas/calendario?ano={d.year}&mes={d.month}", headers=h).get_json()
            contagem[d.strftime("%Y-%m-%d")] = cal.get(d.strftime("%Y-%m-%d"))
        self.assertEqual(list(contagem.values()), [1, 1, 1])
        meio = (ini + timedelta(days=1)).strftime("%Y-%m-%d")
        self.assertEqual(len(self.client.get(f"/api/sintomas/dia?data={meio}", headers=h).get_json()), 1)

    # ── relatório PDF ──
    def test_relatorio_pdf_e_isolamento(self):
        ha, _ = self._novo_usuario("Débora Relatório", "debora.pdf@exemplo.com")
        hb, _ = self._novo_usuario("Eduardo", "eduardo.pdf@exemplo.com")
        self._sintoma(ha, tipo="DOR", subtipo="ABDOMINAL", descricao="pior após café <b>forte</b> & leite",
                      inicio=_txt(_dt(5, 9)), fim=None)
        self._sintoma(hb, tipo="TOSSE", descricao="SEGREDO_DO_EDUARDO", inicio=_txt(_dt(5, 9)), fim=None)
        r = self.client.get("/api/sintomas/relatorio/pdf", headers=ha)
        self.assertEqual((r.status_code, r.mimetype), (200, "application/pdf"))
        self.assertTrue(r.data.startswith(b"%PDF"))
        texto = _texto_pdf(r.data)
        if texto is not None:
            self.assertIn("café <b>forte</b> & leite", texto)
            self.assertNotIn("SEGREDO_DO_EDUARDO", texto)
        hoje = HOJE.strftime("%Y-%m-%d")
        r = self.client.get(f"/api/sintomas/relatorio/pdf?data_inicio={_dt(10).strftime('%Y-%m-%d')}&data_fim={hoje}",
                            headers=ha)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/sintomas/relatorio/pdf?data_inicio=31/12/2026",
                                         headers=ha).status_code, 400)
        self.assertEqual(self.client.get("/api/sintomas/relatorio/pdf").status_code, 401)

    # ── IA: consentimento, cota e rotas (com servidor falso) ──
    def _resposta_interpretacao(self, **extra):
        d = _dt(1, 20)
        base = {"tipo": "DOR", "subtipo": "CABEÇA", "outro_descricao": "", "inicio_data": d.strftime("%Y-%m-%d"),
                "inicio_hora": "20:00", "fim_data": "", "fim_hora": "", "observacao": "forte",
                "urgencia": False, "pergunta": ""}
        base.update(extra)
        return base

    def _total_uso(self, uid, recurso):
        linhas = self._sql("SELECT dia, total FROM IaUso WHERE usuario_id=%s AND recurso=%s", (uid, recurso))
        return linhas[0] if linhas else (None, 0)

    def test_ia_interpretar_consentimento_e_cota(self):
        h, uid = self._novo_usuario("Fernanda Sigilo", "fernanda.ia@exemplo.com")
        self.assertEqual(self.client.get("/api/ia/status", headers=h).get_json(),
                         {"disponivel": True, "consentido": False})
        corpo = {"mensagem": "tive dor de cabeça ontem à noite", "rascunho": None, "historico": [],
                 "agora_local": HOJE.strftime("%Y-%m-%dT%H:%M")}
        r = self.client.post("/api/ia/sintoma/interpretar", json=corpo, headers=h)
        self.assertEqual((r.status_code, r.get_json()["codigo"]), (403, "consentimento_necessario"))
        self.assertEqual(self.fake.requisicoes, [])  # nada saiu para a IA sem consentimento

        self.assertEqual(self.client.post("/api/ia/consentimento", json={"aceito": True}, headers=h).status_code, 200)
        self.assertTrue(self.client.get("/api/ia/status", headers=h).get_json()["consentido"])

        self.fake.responder_json(self._resposta_interpretacao())
        r = self.client.post("/api/ia/sintoma/interpretar", json=corpo, headers=h)
        self.assertEqual(r.status_code, 200, r.get_json())
        dados = r.get_json()
        self.assertEqual(dados["status"], "completo")
        self.assertEqual(dados["sintoma"]["tipo"], "DOR")
        # A IA não grava nada: nenhum sintoma foi criado.
        self.assertEqual(self._sql("SELECT COUNT(*) FROM Sintomas WHERE usuario_id=%s", (uid,))[0][0], 0)
        # O app grava pela rota normal depois da confirmação do paciente.
        self.assertEqual(self.client.post("/api/sintomas", json=dados["sintoma"], headers=h).status_code, 201)

        # O que foi enviado à API: formato atual e nada de nome/e-mail.
        req = self.fake.requisicoes[-1]
        self.assertEqual(req["path"], "/v1/messages")
        body = req["body"]
        self.assertEqual(body["model"], "claude-haiku-5-5")
        self.assertEqual(body["output_config"]["effort"], "low")
        self.assertEqual(body["output_config"]["format"]["type"], "json_schema")
        for proibido in ("temperature", "top_p", "top_k"):
            self.assertNotIn(proibido, body)
        bruto = str(body)
        self.assertNotIn("Fernanda", bruto)
        self.assertNotIn("fernanda.ia@exemplo.com", bruto)

        dia, total = self._total_uso(uid, "interpretar")
        self.assertEqual((dia, total), (mediary.dia_local_cota(), 1))

        # Falha da IA (500): o uso é devolvido.
        self.fake.responder_erro(500)
        r = self.client.post("/api/ia/sintoma/interpretar", json=corpo, headers=h)
        self.assertEqual(r.status_code, 503)
        self.assertEqual(self._total_uso(uid, "interpretar")[1], 1)
        # Saída inválida do modelo (não é JSON): 422 e uso devolvido.
        self.fake.responder_json("isto não é json")
        r = self.client.post("/api/ia/sintoma/interpretar", json=corpo, headers=h)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self._total_uso(uid, "interpretar")[1], 1)

        # Limite = 3 por dia.
        for _ in range(2):
            self.fake.responder_json(self._resposta_interpretacao())
            self.assertEqual(self.client.post("/api/ia/sintoma/interpretar", json=corpo, headers=h).status_code, 200)
        n_req = len(self.fake.requisicoes)
        r = self.client.post("/api/ia/sintoma/interpretar", json=corpo, headers=h)
        self.assertEqual(r.status_code, 429)
        self.assertEqual(len(self.fake.requisicoes), n_req)  # bloqueado antes de chamar a IA
        self.assertEqual(self._total_uso(uid, "interpretar")[1], 3)

        # Revogar o consentimento bloqueia de novo.
        self.client.post("/api/ia/consentimento", json={"aceito": False}, headers=h)
        self.assertEqual(self.client.post("/api/ia/sintoma/interpretar", json=corpo, headers=h).status_code, 403)
        self.assertIsNone(self._sql("SELECT ia_consentimento_em FROM Usuarios WHERE id=%s", (uid,))[0][0])

    def test_ia_cota_e_atomica_com_concorrencia(self):
        _, uid = self._novo_usuario("Gabriel", "gabriel.cota@exemplo.com")
        resultados = []
        barreira = threading.Barrier(25)

        def tentar():
            barreira.wait()
            resultados.append(mediary.reservar_uso_ia(uid, "concorrencia", 5))

        threads = [threading.Thread(target=tentar) for _ in range(25)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sum(1 for r in resultados if r), 5)
        self.assertEqual(self._total_uso(uid, "concorrencia")[1], 5)
        # Devolver nunca deixa negativo e libera exatamente uma vaga.
        dia = mediary.dia_local_cota()
        mediary.liberar_uso_ia(uid, "concorrencia", dia)
        self.assertEqual(mediary.reservar_uso_ia(uid, "concorrencia", 5), dia)
        self.assertIsNone(mediary.reservar_uso_ia(uid, "concorrencia", 5))
        for _ in range(10):
            mediary.liberar_uso_ia(uid, "concorrencia", dia)
        self.assertEqual(self._total_uso(uid, "concorrencia")[1], 0)
        # Limite zero = IA desligada para o recurso.
        self.assertIsNone(mediary.reservar_uso_ia(uid, "zero", 0))
        # Dias diferentes têm contadores separados.
        ontem = dia - timedelta(days=1)
        self.assertEqual(mediary.reservar_uso_ia(uid, "concorrencia", 1, dia=ontem), ontem)

    def test_ia_resumo_e_pdf(self):
        ha, uid = self._novo_usuario("Helena Privada", "helena.resumo@exemplo.com")
        hb, _ = self._novo_usuario("Igor", "igor.resumo@exemplo.com")
        self._sintoma(ha, tipo="DOR", subtipo="CABEÇA", descricao="tomei dipirona", inicio=_txt(_dt(6, 8)),
                      fim=_txt(_dt(6, 10)))
        self._sintoma(ha, tipo="NAUSEA", inicio=_txt(_dt(6, 20)))
        self._sintoma(hb, tipo="TOSSE", descricao="DADO_DO_IGOR", inicio=_txt(_dt(6, 9)))
        self.client.post("/api/ia/consentimento", json={"aceito": True}, headers=ha)

        self.fake.responder_json({"resumo": "O paciente registrou 2 sintomas no período.",
                                  "destaques": ["Dor de cabeça com 2 h de duração."],
                                  "perguntas": ["O que devo observar nas próximas crises?"]})
        r = self.client.post("/api/ia/resumo", json={}, headers=ha)
        self.assertEqual(r.status_code, 200, r.get_json())
        dados = r.get_json()
        self.assertEqual(dados["estatisticas"]["total"], 2)
        body = self.fake.requisicoes[-1]["body"]
        self.assertEqual((body["model"], body["output_config"]["effort"]), ("claude-sonnet-5-5", "medium"))
        bruto = str(body)
        for proibido in ("Helena", "helena.resumo@exemplo.com", "DADO_DO_IGOR"):
            self.assertNotIn(proibido, bruto)
        self.assertIn("tomei dipirona", bruto)

        # Resposta cortada (max_tokens) vira 422 e devolve a cota.
        self.fake.responder_json({"resumo": "x", "destaques": [], "perguntas": []}, stop_reason="max_tokens")
        self.assertEqual(self.client.post("/api/ia/resumo", json={}, headers=ha).status_code, 422)
        self.assertEqual(self._total_uso(uid, "resumo")[1], 1)

        # Período sem registros e datas inválidas.
        r = self.client.post("/api/ia/resumo", json={"data_inicio": "2020-01-01", "data_fim": "2020-01-31"},
                             headers=ha)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.post("/api/ia/resumo", json={"data_inicio": "x"}, headers=ha).status_code, 400)

        # PDF com o texto revisado pelo paciente (não chama a IA; texto escapado).
        n_req = len(self.fake.requisicoes)
        r = self.client.post("/api/ia/relatorio/pdf", headers=ha, json={
            "resumo": "Resumo editado: <script>alert(1)</script> & dores à noite",
            "destaques": ["Destaque com acentuação ção"], "perguntas": ["Pergunta?"]})
        self.assertEqual((r.status_code, r.mimetype), (200, "application/pdf"))
        self.assertEqual(len(self.fake.requisicoes), n_req)
        texto = _texto_pdf(r.data)
        if texto is not None:
            self.assertIn("<script>alert(1)</script> & dores à noite", texto)
            self.assertNotIn("DADO_DO_IGOR", texto)
        self.assertEqual(self.client.post("/api/ia/relatorio/pdf", json={}, headers=ha).status_code, 400)

        # Quem não consentiu não usa o resumo.
        self.assertEqual(self.client.post("/api/ia/resumo", json={}, headers=hb).status_code, 403)

    # ── esqueci minha senha ──
    def test_esqueci_e_redefinir_senha(self):
        _, uid = self._novo_usuario("Laura Senha", "laura.senha@exemplo.com")
        enviados = []
        with mock.patch.object(mediary, "_em_segundo_plano", side_effect=lambda f, *a: f(*a)), \
             mock.patch.object(mediary.email_service, "enviar_redefinicao_senha",
                               side_effect=lambda dest, nome, link, minutos: enviados.append((dest, nome, link))), \
             mock.patch.dict(os.environ, {"APP_URL": "https://mediary.exemplo.com.br"}):
            # E-mail inexistente: mesma resposta, nada enviado (não revela quem tem conta).
            r_inexistente = self.client.post("/api/senha/esqueci", json={"email": "ninguem@exemplo.com"})
            r = self.client.post("/api/senha/esqueci", json={"email": " Laura.Senha@Exemplo.com "})
            self.assertEqual((r.status_code, r_inexistente.status_code), (200, 200))
            self.assertEqual(r.get_json(), r_inexistente.get_json())
            self.assertEqual(len(enviados), 1)
            dest, nome, link = enviados[0]
            self.assertEqual((dest, nome), ("laura.senha@exemplo.com", "Laura Senha"))
            self.assertTrue(link.startswith("https://mediary.exemplo.com.br/redefinir-senha?token="))
            token = link.split("token=", 1)[1]
            # O banco guarda só o hash do token.
            linhas = self._sql("SELECT token_hash FROM RedefinicaoSenha WHERE usuario_id=%s", (uid,))
            self.assertEqual(len(linhas), 1)
            self.assertNotIn(token, str(linhas))
            self.assertEqual(linhas[0][0], mediary._hash_token(token))

            # Validações.
            self.assertEqual(self.client.post("/api/senha/esqueci", json={"email": "sem-arroba"}).status_code, 400)
            self.assertEqual(self.client.post("/api/senha/redefinir",
                                              json={"token": token, "senha_nova": "fraca"}).status_code, 400)
            self.assertEqual(self.client.post("/api/senha/redefinir",
                                              json={"token": "x" * 43, "senha_nova": "Nova#Senha9"}).status_code, 400)

            # Redefinir funciona uma vez só.
            r = self.client.post("/api/senha/redefinir", json={"token": token, "senha_nova": "Nova#Senha9"})
            self.assertEqual(r.status_code, 200, r.get_json())
            self.assertEqual(self.client.post("/api/senha/redefinir",
                                              json={"token": token, "senha_nova": "Outra#Senha9"}).status_code, 400)
            self.assertEqual(self.client.post("/api/login", json={"email": "laura.senha@exemplo.com",
                                                                  "senha": SENHA}).status_code, 401)
            self.assertEqual(self.client.post("/api/login", json={"email": "laura.senha@exemplo.com",
                                                                  "senha": "Nova#Senha9"}).status_code, 200)

            # Pedido novo invalida o anterior; link expirado não vale.
            self.client.post("/api/senha/esqueci", json={"email": "laura.senha@exemplo.com"})
            token_velho = enviados[-1][2].split("token=", 1)[1]
            self.client.post("/api/senha/esqueci", json={"email": "laura.senha@exemplo.com"})
            token_novo = enviados[-1][2].split("token=", 1)[1]
            self.assertEqual(self.client.post("/api/senha/redefinir", json={
                "token": token_velho, "senha_nova": "Velha#Senha9"}).status_code, 400)
            self._sql("UPDATE RedefinicaoSenha SET expira_em = UTC_TIMESTAMP() - INTERVAL 1 MINUTE "
                      "WHERE token_hash=%s", (mediary._hash_token(token_novo),))
            self.assertEqual(self.client.post("/api/senha/redefinir", json={
                "token": token_novo, "senha_nova": "Expirada#9"}).status_code, 400)

            # Limite: no máximo 3 pedidos por hora por conta (já foram 3).
            n = len(enviados)
            r = self.client.post("/api/senha/esqueci", json={"email": "laura.senha@exemplo.com"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(len(enviados), n)

    def test_esqueci_senha_falha_no_envio_nao_vaza(self):
        self._novo_usuario("Marina", "marina.falha@exemplo.com")
        with mock.patch.object(mediary, "_em_segundo_plano", side_effect=lambda f, *a: f(*a)), \
             mock.patch.object(mediary.email_service, "enviar_redefinicao_senha",
                               side_effect=mediary.email_service.EmailNaoEnviado("MessageRejected")):
            with self.assertLogs("mediary", level="ERROR") as logs:
                r = self.client.post("/api/senha/esqueci", json={"email": "marina.falha@exemplo.com"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("marina.falha", "\n".join(logs.output))
        self.assertNotIn("token=", "\n".join(logs.output))

    def test_ia_desligada_sem_chave(self):
        h, _ = self._novo_usuario("Júlia", "julia.semchave@exemplo.com")
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            self.assertFalse(self.client.get("/api/ia/status", headers=h).get_json()["disponivel"])
            r = self.client.post("/api/ia/sintoma/interpretar", json={"mensagem": "oi"}, headers=h)
            self.assertEqual(r.status_code, 503)

    def test_erro_de_banco_nao_vaza_detalhes(self):
        h, _ = self._novo_usuario("Karina", "karina.erro@exemplo.com")
        with mock.patch.object(mediary, "get_db", side_effect=mediary.pymysql.err.OperationalError(
                2003, "Can't connect to MySQL server on 'host-secreto'")):
            with self.assertLogs("mediary", level="ERROR") as logs:
                r = self.client.get("/api/me", headers=h)
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("host-secreto", r.get_data(as_text=True))
        self.assertNotIn("host-secreto", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()

import os
import re
import time
import jwt
import logging
import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv
from flask import Flask
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from functools import wraps
from datetime import datetime, date, timedelta, timezone
from urllib.parse import urlsplit, unquote, parse_qs
from zoneinfo import ZoneInfo
from flask import request, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash

import ia_service
from relatorio_pdf import gerar_pdf_relatorio

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.environ.get("SECRET_KEY")
# "producao" endurece o app: exige SECRET_KEY e não libera localhost no CORS.
EM_PRODUCAO = os.environ.get("AMBIENTE", "").strip().lower() in ("producao", "production", "prod")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mediary")

if not DATABASE_URL:
    logger.warning("DATABASE_URL não definida. Configure a variável de ambiente antes de usar em produção.")

if not SECRET_KEY and EM_PRODUCAO:
    raise RuntimeError("SECRET_KEY é obrigatória com AMBIENTE=producao.")

if not SECRET_KEY:
    # Em desenvolvimento local, usamos uma chave fixa (não aleatória) para não travar o app
    # quando SECRET_KEY não está configurada. Precisa ser fixa — e não gerada com os.urandom() —
    # porque o servidor roda com múltiplos processos (gunicorn --workers 2): se cada processo
    # sorteasse sua própria chave, um token emitido por um worker seria rejeitado pelo outro,
    # causando erros 401 aleatórios e intermitentes mesmo para logins corretos.
    # Isso NUNCA deve acontecer em produção — sempre defina SECRET_KEY no seu .env.
    logger.warning(
        "SECRET_KEY não definida em variável de ambiente. Usando uma chave fixa de "
        "desenvolvimento (INSEGURA) — defina SECRET_KEY no .env antes de ir para produção."
    )
    import hashlib
    SECRET_KEY = hashlib.sha256(b"mediary-dev-fallback-key-do-not-use-in-production").hexdigest()

class _JSONProvider(DefaultJSONProvider):
    """Datas saem em ISO sem fuso ('2026-11-15T20:00:00'), que o navegador lê como
    hora local. O padrão do Flask ('Sun, 15 Nov 2026 20:00:00 GMT') fazia o
    navegador converter de GMT para o fuso do Brasil e mostrar 3 h a menos."""
    @staticmethod
    def default(o):
        if isinstance(o, datetime):
            return o.replace(tzinfo=None).isoformat(timespec="seconds")
        if isinstance(o, date):
            return o.isoformat()
        return DefaultJSONProvider.default(o)


app = Flask(__name__)
app.json = _JSONProvider(app)
app.config["SECRET_KEY"] = SECRET_KEY

# Mensagem genérica usada sempre que um erro interno não pode ser exposto ao usuário.
MSG_ERRO_INTERNO = "Ocorreu um erro inesperado. Tente novamente em instantes."
MSG_ERRO_BANCO = "Não foi possível completar a operação no momento. Tente novamente mais tarde."


def log_erro(contexto, excecao):
    """Loga o erro no servidor sem nunca expor detalhes internos ao cliente.
    Para erros do banco registramos só o tipo e o código: a mensagem do MySQL pode
    conter dados (ex.: "Duplicate entry 'fulano@email' ..."), que não vão para o log."""
    if isinstance(excecao, pymysql.MySQLError):
        codigo = excecao.args[0] if excecao.args else "?"
        logger.error("Erro em %s: %s (código MySQL %s)", contexto, type(excecao).__name__, codigo)
    else:
        logger.error("Erro em %s: %s: %s", contexto, type(excecao).__name__, str(excecao)[:300])


def validar_senha(senha: str):
    """Valida a força da senha. Retorna None se válida, ou uma mensagem de erro."""
    if not senha or len(senha) < 8:
        return "A senha deve ter pelo menos 8 caracteres"
    if not re.search(r"[A-Z]", senha):
        return "A senha deve conter pelo menos uma letra maiúscula"
    if not re.search(r"[a-z]", senha):
        return "A senha deve conter pelo menos uma letra minúscula"
    if not re.search(r"[0-9]", senha):
        return "A senha deve conter pelo menos um número"
    if not re.search(r"[^A-Za-z0-9]", senha):
        return "A senha deve conter pelo menos um caractere especial"
    return None

_frontend_url = os.environ.get("FRONTEND_URL", "")
_allowed_origins = [o.strip() for o in _frontend_url.split(",") if o.strip()]
if not EM_PRODUCAO:
    _allowed_origins += ["http://localhost", "http://localhost:80", "http://127.0.0.1",
                         "http://localhost:5173"]

CORS(
    app,
    resources={r"/api/*": {"origins": _allowed_origins}},
    supports_credentials=True,
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
)


# ── Tratamento genérico de erros ───────────────────────────────────────────────
# Rede de segurança: garante que nenhuma exceção não tratada vaze detalhes
# internos (stack trace, string de conexão, erro do driver do banco, etc.)
# para quem está usando a API.

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Recurso não encontrado"}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Método não permitido"}), 405


@app.errorhandler(Exception)
def handle_uncaught_exception(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return jsonify({"error": e.description or "Erro na requisição"}), e.code
    log_erro("exceção não tratada", e)
    return jsonify({"error": MSG_ERRO_INTERNO}), 500

# ── DB (MySQL 8) ──────────────────────────────────────────────────────────────

def _config_banco(url=None, senha=None):
    """Lê DATABASE_URL no formato mysql://usuario:senha@host:3306/banco.

    * Caracteres especiais na senha devem vir codificados na URL (ex.: '@' -> %40,
      '/' -> %2F, '#' -> %23). Use urllib.parse.quote(senha, safe='').
    * Alternativa: deixe a senha fora da URL e defina DATABASE_PASSWORD, que tem
      prioridade e é usada sem nenhuma codificação.
    * Opcional: ?ssl_ca=/caminho/ca.pem na URL ou DATABASE_SSL_CA para exigir TLS
      (ex.: certificado da AWS RDS).
    """
    url = url if url is not None else (os.environ.get("DATABASE_URL") or "")
    partes = urlsplit(url)
    if partes.scheme not in ("mysql", "mysql+pymysql"):
        raise ValueError("DATABASE_URL deve começar com mysql://")
    query = parse_qs(partes.query)
    senha = senha if senha is not None else os.environ.get("DATABASE_PASSWORD")
    cfg = {
        "host": partes.hostname or "localhost",
        "port": partes.port or 3306,
        "user": unquote(partes.username or ""),
        "password": senha if senha else unquote(partes.password or ""),
        "database": unquote(partes.path.lstrip("/")),
        "charset": "utf8mb4",
        "collation": "utf8mb4_unicode_ci",
        "connect_timeout": 10,
        "autocommit": False,
        # A sessão usa UTC, como o Postgres do Supabase: NOW()/CURRENT_TIMESTAMP
        # gravam o mesmo horário de antes. O "dia" da cota da IA é calculado à parte,
        # em America/Sao_Paulo.
        "init_command": "SET time_zone = '+00:00'",
    }
    ca = (query.get("ssl_ca") or [None])[0] or os.environ.get("DATABASE_SSL_CA")
    if ca:
        cfg["ssl"] = {"ca": ca}
    return cfg


def get_db():
    return pymysql.connect(**_config_banco())


ERRO_MYSQL_COLUNA_DUPLICADA = 1060


def _coluna_existe(cursor, tabela, coluna):
    cursor.execute("""
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
    """, (tabela, coluna))
    return cursor.fetchone() is not None


def _adicionar_coluna(cursor, tabela, coluna, definicao):
    """ALTER TABLE ... ADD COLUMN idempotente (o MySQL 8 não tem ADD COLUMN IF NOT EXISTS)."""
    if _coluna_existe(cursor, tabela, coluna):
        return
    try:
        cursor.execute(f"ALTER TABLE `{tabela}` ADD COLUMN `{coluna}` {definicao}")
    except pymysql.err.OperationalError as e:
        # Dois workers do gunicorn podem tentar ao mesmo tempo: o segundo recebe 1060.
        if e.args and e.args[0] == ERRO_MYSQL_COLUNA_DUPLICADA:
            return
        raise


_OPCOES_TABELA = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"


def init_db():
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS Usuarios (
                id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL,
                senha_hash VARCHAR(255) NOT NULL,
                criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_usuarios_email (email)
            ) {_OPCOES_TABELA}
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS Sintomas (
                id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                usuario_id INT NOT NULL,
                tipo VARCHAR(100) NOT NULL,
                subtipo VARCHAR(100) NULL,
                descricao TEXT NULL,
                inicio DATETIME NOT NULL,
                fim DATETIME NULL,
                criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
                atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
                KEY ix_sintomas_usuario_inicio (usuario_id, inicio),
                CONSTRAINT fk_sintomas_usuario FOREIGN KEY (usuario_id)
                    REFERENCES Usuarios(id) ON DELETE CASCADE
            ) {_OPCOES_TABELA}
        """)
        # ── IA ──
        # Consentimento do usuário para enviar os dados ao serviço de IA (NULL = não consentiu).
        _adicionar_coluna(cursor, "Usuarios", "ia_consentimento_em", "DATETIME NULL")
        # Contador diário de uso da IA por usuário (limita custo e abuso). Não guarda conteúdo.
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS IaUso (
                usuario_id INT NOT NULL,
                dia DATE NOT NULL,
                recurso VARCHAR(40) NOT NULL,
                total INT NOT NULL DEFAULT 0,
                PRIMARY KEY (usuario_id, dia, recurso),
                CONSTRAINT fk_iauso_usuario FOREIGN KEY (usuario_id)
                    REFERENCES Usuarios(id) ON DELETE CASCADE
            ) {_OPCOES_TABELA}
        """)
        conn.commit()
    finally:
        conn.close()


def _init_db_com_tentativas(tentativas=5, espera=3):
    """O banco pode ainda estar subindo (docker compose, reinício da instância)."""
    for n in range(1, tentativas + 1):
        try:
            init_db()
            return True
        except Exception as e:
            log_erro(f"init_db (tentativa {n}/{tentativas})", e)
            if n < tentativas:
                time.sleep(espera)
    return False


if DATABASE_URL and os.environ.get("MEDIARY_PULAR_INIT_DB") != "1":
    _init_db_com_tentativas()

# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_token(usuario_id, nome):
    payload = {
        "usuario_id": usuario_id,
        "nome": nome,
        "exp": datetime.now(timezone.utc) + timedelta(days=30)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def get_current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1]
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Não autorizado"}), 401
        request.current_user = user
        return f(*args, **kwargs)
    return decorated

# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route("/api/me", methods=["GET"])
@login_required
def me():
    try:
        conn = get_db()
        cursor = conn.cursor(DictCursor)
        cursor.execute("SELECT id, nome, email FROM Usuarios WHERE id = %s",
                       (request.current_user["usuario_id"],))
        row = cursor.fetchone()
        conn.close()
        if row:
            return jsonify({"id": row["id"], "nome": row["nome"], "email": row["email"]})
        return jsonify({"error": "Usuário não encontrado"}), 404
    except Exception as e:
        log_erro("me", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    senha = data.get("senha", "")
    if not email or not senha:
        return jsonify({"error": "Informe e-mail e senha"}), 400
    try:
        conn = get_db()
        cursor = conn.cursor(DictCursor)
        cursor.execute("SELECT id, nome, email, senha_hash FROM Usuarios WHERE email = %s", (email,))
        row = cursor.fetchone()
        conn.close()
        if row and check_password_hash(row["senha_hash"], senha):
            token = create_token(row["id"], row["nome"])
            return jsonify({
                "message": "Login realizado com sucesso",
                "token": token,
                "user": {"id": row["id"], "nome": row["nome"], "email": row["email"]}
            })
        return jsonify({"error": "E-mail ou senha incorretos"}), 401
    except Exception as e:
        log_erro("login", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500


@app.route("/api/cadastro", methods=["POST"])
def cadastro():
    data = request.json or {}
    nome  = data.get("nome", "").strip()
    email = data.get("email", "").strip().lower()
    senha = data.get("senha", "")
    if not nome or not email or not senha:
        return jsonify({"error": "Preencha todos os campos"}), 400
    erro_senha = validar_senha(senha)
    if erro_senha:
        return jsonify({"error": erro_senha}), 400
    try:
        conn = get_db()
        cursor = conn.cursor(DictCursor)
        cursor.execute("INSERT INTO Usuarios (nome, email, senha_hash) VALUES (%s, %s, %s)",
                       (nome, email, generate_password_hash(senha)))
        conn.commit()
        conn.close()
        return jsonify({"message": "Conta criada com sucesso!"}), 201
    except pymysql.err.IntegrityError:
        return jsonify({"error": "E-mail já cadastrado"}), 400
    except Exception as e:
        log_erro("cadastro", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500


@app.route("/api/usuario", methods=["PUT"])
@login_required
def update_usuario():
    data = request.json or {}
    nome = (data.get("nome") or "").strip()
    # Mesmo tratamento do cadastro/login: sem isso, quem trocava o e-mail para
    # "Fulano@X.com" não conseguia mais entrar (o login procura em minúsculas).
    email = (data.get("email") or "").strip().lower()
    if not nome or not email:
        return jsonify({"error": "Nome e e-mail são obrigatórios"}), 400
    try:
        conn = get_db()
        cursor = conn.cursor(DictCursor)
        cursor.execute("UPDATE Usuarios SET nome=%s, email=%s WHERE id=%s",
                       (nome, email, request.current_user["usuario_id"]))
        conn.commit()
        conn.close()
        return jsonify({"message": "Perfil atualizado com sucesso", "nome": nome, "email": email})
    except pymysql.err.IntegrityError:
        return jsonify({"error": "Este e-mail já está em uso por outro usuário"}), 400
    except Exception as e:
        log_erro("update_usuario", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500


@app.route("/api/usuario/senha", methods=["PUT"])
@login_required
def update_senha():
    data = request.json or {}
    senha_atual = data.get("senha_atual")
    senha_nova = data.get("senha_nova")
    if not senha_atual or not senha_nova:
        return jsonify({"error": "Preencha todos os campos"}), 400
    erro_senha = validar_senha(senha_nova)
    if erro_senha:
        return jsonify({"error": erro_senha}), 400
    try:
        conn = get_db()
        cursor = conn.cursor(DictCursor)
        cursor.execute("SELECT senha_hash FROM Usuarios WHERE id = %s",
                       (request.current_user["usuario_id"],))
        row = cursor.fetchone()
        if row and check_password_hash(row["senha_hash"], senha_atual):
            cursor.execute("UPDATE Usuarios SET senha_hash=%s WHERE id=%s",
                           (generate_password_hash(senha_nova), request.current_user["usuario_id"]))
            conn.commit()
            conn.close()
            return jsonify({"message": "Senha atualizada com sucesso"})
        conn.close()
        return jsonify({"error": "Senha atual incorreta"}), 401
    except Exception as e:
        log_erro("update_senha", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500


@app.route("/api/logout")
def logout():
    return jsonify({"message": "Logout realizado com sucesso"})


# ── Sintomas ──────────────────────────────────────────────────────────────────

def _intervalo_mes(ano, mes):
    """[primeiro dia do mês, primeiro dia do mês seguinte) como datetime."""
    inicio = datetime(ano, mes, 1)
    fim = datetime(ano + 1, 1, 1) if mes == 12 else datetime(ano, mes + 1, 1)
    return inicio, fim


def _ano_mes_validos(ano, mes):
    return 1900 <= ano <= 9999 and 1 <= mes <= 12


def _parse_data_hora(valor):
    """Aceita 'AAAA-MM-DD HH:MM[:SS]' (formato do app) ou ISO 8601 com 'T' (e 'Z' ou
    fuso opcionais). Devolve datetime SEM fuso, guardando a hora exatamente como veio,
    igual o Postgres fazia numa coluna TIMESTAMP (ele ignorava o fuso do texto).
    Lança ValueError se o formato for inválido."""
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None)
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError("data vazia")
    v = valor.strip()
    if "T" in v:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None, microsecond=0)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    raise ValueError("formato inválido")


@app.route("/api/sintomas/calendario")
@login_required
def api_calendario_info():
    try:
        ano = int(request.args.get("ano", date.today().year))
        mes = int(request.args.get("mes", date.today().month))
    except ValueError:
        return jsonify({"error": "Mês ou ano inválido"}), 400
    if not _ano_mes_validos(ano, mes):
        return jsonify({"error": "Mês ou ano inválido"}), 400
    ini_mes, prox_mes = _intervalo_mes(ano, mes)
    try:
        conn = get_db()
        cursor = conn.cursor(DictCursor)
        # Mesma regra de antes (TO_CHAR(inicio,'YYYY-MM') <= mês e fim >= mês),
        # escrita com intervalos para usar o índice (usuario_id, inicio).
        cursor.execute("""
            SELECT inicio, fim FROM Sintomas
            WHERE usuario_id = %s
            AND inicio < %s
            AND (fim IS NULL OR fim >= %s)
        """, (request.current_user["usuario_id"], prox_mes, ini_mes))
        rows = cursor.fetchall()
        conn.close()
        calendario = {}
        for row in rows:
            ini_dt = row["inicio"].date()
            fim_dt = row["fim"].date() if row["fim"] else ini_dt
            curr = max(ini_dt, ini_mes.date())
            while curr <= fim_dt and curr < prox_mes.date():
                d_str = curr.strftime("%Y-%m-%d")
                calendario[d_str] = calendario.get(d_str, 0) + 1
                curr += timedelta(days=1)
        return jsonify(calendario)
    except Exception as e:
        log_erro("api_calendario_info", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500


@app.route("/api/sintomas/dia")
@login_required
def api_sintomas_dia():
    data_sel = request.args.get("data")
    if not data_sel:
        return jsonify({"error": "Data não informada"}), 400
    try:
        dia = datetime.strptime(data_sel.strip(), "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Data inválida. Use o formato AAAA-MM-DD."}), 400
    dia_seguinte = dia + timedelta(days=1)
    try:
        conn = get_db()
        cursor = conn.cursor(DictCursor)
        cursor.execute("""
            SELECT id, tipo, subtipo, descricao, inicio, fim FROM Sintomas
            WHERE usuario_id = %s
            AND ((fim IS NULL AND inicio >= %s AND inicio < %s)
                OR (fim IS NOT NULL AND inicio < %s AND fim >= %s))
            ORDER BY inicio
        """, (request.current_user["usuario_id"], dia, dia_seguinte, dia_seguinte, dia))
        sintomas = cursor.fetchall()
        conn.close()
        return jsonify(sintomas)
    except Exception as e:
        log_erro("api_sintomas_dia", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500


@app.route("/api/sintomas", methods=["POST"])
@login_required
def api_adicionar_sintoma():
    data = request.json or {}
    tipo      = data.get("tipo", "")
    subtipo   = data.get("subtipo")
    descricao = data.get("descricao")
    inicio    = data.get("inicio")
    fim       = data.get("fim")
    if not tipo or not inicio:
        return jsonify({"error": "Tipo e início são obrigatórios"}), 400
    try:
        agora = datetime.now()
        um_ano_atras = agora - timedelta(days=365)
        try:
            ini_dt = _parse_data_hora(inicio)
        except ValueError:
            return jsonify({"error": "Formato de data de início inválido"}), 400
        if ini_dt > agora + timedelta(minutes=5):
            return jsonify({"error": "A data de início não pode ser futura"}), 400
        if ini_dt < um_ano_atras:
            return jsonify({"error": "O registro é limitado a no máximo 1 ano atrás"}), 400
        fim_dt = None
        if fim:
            try:
                fim_dt = _parse_data_hora(fim)
            except ValueError:
                return jsonify({"error": "Formato de data de fim inválido"}), 400
            if fim_dt < ini_dt:
                return jsonify({"error": "A data de término não pode ser anterior à de início"}), 400
        conn = get_db()
        cursor = conn.cursor(DictCursor)
        cursor.execute(
            "INSERT INTO Sintomas (usuario_id, tipo, subtipo, descricao, inicio, fim) VALUES (%s, %s, %s, %s, %s, %s)",
            (request.current_user["usuario_id"], tipo, subtipo, descricao, ini_dt, fim_dt))
        novo_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return jsonify({"message": "Sintoma adicionado com sucesso", "id": novo_id}), 201
    except Exception as e:
        log_erro("api_adicionar_sintoma", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500


@app.route("/api/sintomas/<int:sintoma_id>", methods=["PUT", "DELETE"])
@login_required
def api_sintoma_detail(sintoma_id):
    uid = request.current_user["usuario_id"]
    if request.method == "DELETE":
        try:
            conn = get_db()
            cursor = conn.cursor(DictCursor)
            cursor.execute("DELETE FROM Sintomas WHERE id=%s AND usuario_id=%s", (sintoma_id, uid))
            excluido = cursor.rowcount > 0
            conn.commit()
            conn.close()
            if not excluido:
                return jsonify({"error": "Sintoma não encontrado"}), 404
            return jsonify({"message": "Sintoma excluído"})
        except Exception as e:
            log_erro("api_sintoma_detail (DELETE)", e)
            return jsonify({"error": MSG_ERRO_BANCO}), 500
    data = request.json or {}
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor(DictCursor)
        cursor.execute("SELECT * FROM Sintomas WHERE id=%s AND usuario_id=%s", (sintoma_id, uid))
        sintoma_atual = cursor.fetchone()
        if not sintoma_atual:
            return jsonify({"error": "Sintoma não encontrado"}), 404
        tipo      = data.get("tipo") or sintoma_atual["tipo"]
        subtipo   = data.get("subtipo", sintoma_atual["subtipo"])
        descricao = data.get("descricao", sintoma_atual["descricao"])
        try:
            inicio = _parse_data_hora(data.get("inicio") or sintoma_atual["inicio"])
        except ValueError:
            return jsonify({"error": "Formato de data de início inválido"}), 400
        fim = data.get("fim", sintoma_atual["fim"])
        try:
            fim = _parse_data_hora(fim) if fim else None
        except ValueError:
            return jsonify({"error": "Formato de data de fim inválido"}), 400
        if fim and fim < inicio:
            return jsonify({"error": "A data de término não pode ser anterior à de início"}), 400
        cursor.execute("""UPDATE Sintomas SET tipo=%s, subtipo=%s, descricao=%s,
                         inicio=%s, fim=%s, atualizado_em=CURRENT_TIMESTAMP
                         WHERE id=%s AND usuario_id=%s""",
                       (tipo, subtipo, descricao, inicio, fim, sintoma_id, uid))
        conn.commit()
        return jsonify({"message": "Sintoma atualizado"})
    except Exception as e:
        log_erro("api_sintoma_detail (PUT)", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500
    finally:
        if conn is not None:
            conn.close()


@app.route("/api/sintomas/mes/<int:ano>/<int:mes>")
@login_required
def api_sintomas_mes(ano, mes):
    if not _ano_mes_validos(ano, mes):
        return jsonify({"error": "Mês ou ano inválido"}), 400
    ini_mes, prox_mes = _intervalo_mes(ano, mes)
    try:
        conn = get_db()
        cursor = conn.cursor(DictCursor)
        cursor.execute("""
            SELECT id, tipo, subtipo, descricao, inicio, fim FROM Sintomas
            WHERE usuario_id = %s
            AND inicio < %s
            AND (fim IS NULL OR fim >= %s)
            ORDER BY inicio
        """, (request.current_user["usuario_id"], prox_mes, ini_mes))
        # Antes: dict(zip(colunas, row)) sobre um RealDictRow devolvia {"id": "id", ...}.
        data = cursor.fetchall()
        conn.close()
        return jsonify(data)
    except Exception as e:
        log_erro("api_sintomas_mes", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500


# ── Relatório em PDF ──────────────────────────────────────────────────────────

def parse_data_param(valor):
    """'AAAA-MM-DD' -> date; vazio -> None; inválido -> ValueError."""
    if not valor:
        return None
    return datetime.strptime(str(valor).strip(), "%Y-%m-%d").date()


def buscar_sintomas_usuario(uid, data_inicio=None, data_fim=None, limite=5000):
    """Dados do usuário e seus sintomas em ordem cronológica.
    Sempre filtra por usuario_id: ninguém acessa registros de outro usuário."""
    conn = get_db()
    try:
        cursor = conn.cursor(DictCursor)
        cursor.execute("SELECT nome, email FROM Usuarios WHERE id = %s", (uid,))
        usuario = cursor.fetchone()
        if not usuario:
            return None, []
        query = "SELECT id, tipo, subtipo, descricao, inicio, fim FROM Sintomas WHERE usuario_id = %s"
        params = [uid]
        if data_inicio:
            query += " AND inicio >= %s"
            params.append(data_inicio)
        if data_fim:
            query += " AND inicio < %s"
            params.append(data_fim + timedelta(days=1))
        query += " ORDER BY inicio LIMIT %s"
        params.append(limite)
        cursor.execute(query, tuple(params))
        return usuario, cursor.fetchall()
    finally:
        conn.close()


def _enviar_pdf(buffer):
    nome_arquivo = f"mediary_relatorio_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=nome_arquivo)


def _periodo_da_requisicao(origem):
    """Lê data_inicio/data_fim (AAAA-MM-DD) de args ou JSON. Retorna (inicio, fim) como date/None."""
    return parse_data_param(origem.get("data_inicio")), parse_data_param(origem.get("data_fim"))


MSG_DATA_INVALIDA = "Data inválida. Use o formato AAAA-MM-DD."


@app.route("/api/sintomas/relatorio/pdf")
@login_required
def api_relatorio_pdf():
    """PDF com os sintomas do usuário autenticado (sem IA)."""
    uid = request.current_user["usuario_id"]
    try:
        data_inicio, data_fim = _periodo_da_requisicao(request.args)
    except ValueError:
        return jsonify({"error": MSG_DATA_INVALIDA}), 400

    try:
        usuario, sintomas = buscar_sintomas_usuario(uid, data_inicio, data_fim)
    except Exception as e:
        log_erro("api_relatorio_pdf (consulta)", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500
    if not usuario:
        return jsonify({"error": "Usuário não encontrado"}), 404

    try:
        pdf = gerar_pdf_relatorio(usuario, sintomas,
                                  data_inicio.isoformat() if data_inicio else None,
                                  data_fim.isoformat() if data_fim else None)
    except Exception as e:
        log_erro("api_relatorio_pdf (geração do PDF)", e)
        return jsonify({"error": "Não foi possível gerar o relatório em PDF no momento."}), 500
    return _enviar_pdf(pdf)


# ── IA: consentimento, limite diário e rotas ──────────────────────────────────

def _limite_ia(nome_env, padrao):
    try:
        return int(os.environ.get(nome_env, padrao))
    except ValueError:
        return padrao


def usuario_consentiu_ia(uid):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ia_consentimento_em FROM Usuarios WHERE id = %s", (uid,))
        row = cursor.fetchone()
        return bool(row and row[0])
    finally:
        conn.close()


FUSO_COTA_IA = ZoneInfo("America/Sao_Paulo")


def dia_local_cota(agora_utc=None):
    """Dia da cota da IA no fuso de São Paulo (vira à meia-noite de Brasília).
    Calculado em Python para não depender das tabelas de fuso do MySQL."""
    agora_utc = agora_utc or datetime.now(ZoneInfo("UTC"))
    return agora_utc.astimezone(FUSO_COTA_IA).date()


def reservar_uso_ia(uid, recurso, limite, dia=None):
    """Conta +1 uso no dia, de forma atômica. Devolve o dia reservado (date) ou None
    se o limite diário já foi atingido.

    Um único INSERT ... ON DUPLICATE KEY UPDATE trava a linha (usuario_id, dia,
    recurso) no InnoDB, então duas requisições simultâneas nunca passam do limite.
    O 'rowcount' diz o que aconteceu (sem a flag CLIENT.FOUND_ROWS, que o PyMySQL
    não liga): 1 = linha criada, 2 = total incrementado, 0 = já estava no limite.
    """
    if limite <= 0:
        return None
    dia = dia or dia_local_cota()
    conn = get_db()
    try:
        cursor = conn.cursor()
        afetadas = cursor.execute("""
            INSERT INTO IaUso (usuario_id, dia, recurso, total)
            VALUES (%s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE total = IF(total < %s, total + 1, total)
        """, (uid, dia, recurso, limite))
        conn.commit()
        return dia if afetadas in (1, 2) else None
    finally:
        conn.close()


def liberar_uso_ia(uid, recurso, dia=None):
    """Devolve o uso reservado quando a falha foi nossa (a IA não respondeu).
    Usa o mesmo dia da reserva, mesmo que a chamada tenha atravessado a meia-noite."""
    try:
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE IaUso SET total = GREATEST(total - 1, 0)
                WHERE usuario_id = %s AND dia = %s AND recurso = %s
            """, (uid, dia or dia_local_cota(), recurso))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        log_erro("liberar_uso_ia", e)


def _bloqueio_ia(uid, recurso, limite):
    """(None, dia_reservado) se pode usar a IA agora; senão (resposta de erro, None)."""
    if not ia_service.ia_configurada():
        return (jsonify({"error": "O assistente de IA não está disponível no momento."}), 503), None
    if not usuario_consentiu_ia(uid):
        return (jsonify({
            "error": "Para usar a IA, aceite primeiro o envio dos seus registros ao assistente.",
            "codigo": "consentimento_necessario",
        }), 403), None
    dia = reservar_uso_ia(uid, recurso, limite)
    if not dia:
        return (jsonify({"error": "Você atingiu o limite diário de uso da IA. Tente novamente amanhã."}), 429), None
    return None, dia


@app.route("/api/ia/status")
@login_required
def api_ia_status():
    try:
        consentido = usuario_consentiu_ia(request.current_user["usuario_id"])
    except Exception as e:
        log_erro("api_ia_status", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500
    return jsonify({"disponivel": ia_service.ia_configurada(), "consentido": consentido})


@app.route("/api/ia/consentimento", methods=["POST"])
@login_required
def api_ia_consentimento():
    """Registra (aceito=true) ou revoga (aceito=false) o consentimento para usar a IA."""
    data = request.get_json(silent=True) or {}
    aceito = data.get("aceito") is True
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE Usuarios SET ia_consentimento_em = IF(%s, CURRENT_TIMESTAMP, NULL) WHERE id = %s",
            (aceito, request.current_user["usuario_id"]))
        conn.commit()
        conn.close()
        return jsonify({"consentido": aceito})
    except Exception as e:
        log_erro("api_ia_consentimento", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500


@app.route("/api/ia/sintoma/interpretar", methods=["POST"])
@login_required
def api_ia_interpretar():
    """Um passo da conversa de cadastro por texto/voz. NÃO grava nada: devolve o
    rascunho/pergunta e, quando completo, o payload que o app envia ao POST /api/sintomas."""
    uid = request.current_user["usuario_id"]
    data = request.get_json(silent=True) or {}

    mensagem = data.get("mensagem")
    if not isinstance(mensagem, str) or not mensagem.strip():
        return jsonify({"error": "Escreva ou fale o que você está sentindo."}), 400
    if len(mensagem) > ia_service.MAX_MENSAGEM:
        return jsonify({"error": "A mensagem ficou muito longa. Conte de forma mais resumida."}), 400

    historico = data.get("historico")
    turnos = sum(1 for h in historico if isinstance(h, dict) and h.get("papel") == "paciente") \
        if isinstance(historico, list) else 0
    if turnos >= ia_service.MAX_TURNOS_PACIENTE:
        return jsonify({"error": "A conversa ficou longa. Use o botão + para completar o registro manualmente."}), 400

    agora = ia_service.parse_agora_local(data.get("agora_local"), datetime.now())
    limite = _limite_ia("IA_LIMITE_DIARIO_INTERPRETAR", 40)

    try:
        bloqueio, dia_reservado = _bloqueio_ia(uid, "interpretar", limite)
    except Exception as e:
        log_erro("api_ia_interpretar (bloqueio)", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500
    if bloqueio:
        return bloqueio

    try:
        resultado = ia_service.interpretar_mensagem(mensagem, data.get("rascunho"), historico, agora)
    except ia_service.IAIndisponivel:
        liberar_uso_ia(uid, "interpretar", dia_reservado)
        return jsonify({"error": "O assistente de IA está indisponível agora. Tente de novo em instantes ou use o botão + para registrar manualmente."}), 503
    except ia_service.IASaidaInvalida:
        liberar_uso_ia(uid, "interpretar", dia_reservado)
        return jsonify({"error": "Não consegui entender essa mensagem. Pode contar de outro jeito?"}), 422
    except Exception as e:
        liberar_uso_ia(uid, "interpretar", dia_reservado)
        log_erro("api_ia_interpretar", e)
        return jsonify({"error": MSG_ERRO_INTERNO}), 500
    return jsonify(resultado)


@app.route("/api/ia/resumo", methods=["POST"])
@login_required
def api_ia_resumo():
    """Gera o resumo por IA dos sintomas do próprio usuário no período."""
    uid = request.current_user["usuario_id"]
    data = request.get_json(silent=True) or {}
    try:
        data_inicio, data_fim = _periodo_da_requisicao(data)
    except ValueError:
        return jsonify({"error": MSG_DATA_INVALIDA}), 400

    try:
        usuario, sintomas = buscar_sintomas_usuario(uid, data_inicio, data_fim)
    except Exception as e:
        log_erro("api_ia_resumo (consulta)", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500
    if not usuario:
        return jsonify({"error": "Usuário não encontrado"}), 404
    if not sintomas:
        return jsonify({"error": "Nenhum sintoma encontrado no período escolhido."}), 400

    limite = _limite_ia("IA_LIMITE_DIARIO_RESUMO", 10)
    try:
        bloqueio, dia_reservado = _bloqueio_ia(uid, "resumo", limite)
    except Exception as e:
        log_erro("api_ia_resumo (bloqueio)", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500
    if bloqueio:
        return bloqueio

    try:
        # Só os registros do paciente: nome e e-mail nunca saem do servidor.
        resumo = ia_service.gerar_resumo(
            sintomas,
            data_inicio.isoformat() if data_inicio else None,
            data_fim.isoformat() if data_fim else None)
    except ia_service.IAIndisponivel:
        liberar_uso_ia(uid, "resumo", dia_reservado)
        return jsonify({"error": "O assistente de IA está indisponível agora. Tente de novo em instantes."}), 503
    except ia_service.IASaidaInvalida:
        liberar_uso_ia(uid, "resumo", dia_reservado)
        return jsonify({"error": "Não consegui montar o resumo agora. Tente novamente."}), 422
    except Exception as e:
        liberar_uso_ia(uid, "resumo", dia_reservado)
        log_erro("api_ia_resumo", e)
        return jsonify({"error": MSG_ERRO_INTERNO}), 500

    resumo["periodo"] = {
        "inicio": data_inicio.isoformat() if data_inicio else None,
        "fim": data_fim.isoformat() if data_fim else None,
    }
    return jsonify(resumo)


def _lista_de_textos(valor, maximo, limite):
    itens = [ia_service._texto(x, limite) for x in valor] if isinstance(valor, list) else []
    return [i for i in itens if i][:maximo]


@app.route("/api/ia/relatorio/pdf", methods=["POST"])
@login_required
def api_ia_relatorio_pdf():
    """PDF com o resumo por IA (já revisado/editado pelo paciente). Não chama a IA:
    as estatísticas são recalculadas aqui a partir dos dados do próprio usuário."""
    uid = request.current_user["usuario_id"]
    data = request.get_json(silent=True) or {}
    try:
        data_inicio, data_fim = _periodo_da_requisicao(data)
    except ValueError:
        return jsonify({"error": MSG_DATA_INVALIDA}), 400

    resumo = ia_service._texto(data.get("resumo"), 2000)
    if not resumo:
        return jsonify({"error": "Gere o resumo antes de exportar o PDF."}), 400

    try:
        usuario, sintomas = buscar_sintomas_usuario(uid, data_inicio, data_fim)
    except Exception as e:
        log_erro("api_ia_relatorio_pdf (consulta)", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500
    if not usuario:
        return jsonify({"error": "Usuário não encontrado"}), 404

    ia = {
        "resumo": resumo,
        "destaques": _lista_de_textos(data.get("destaques"), 8, 300),
        "perguntas": _lista_de_textos(data.get("perguntas"), 8, 300),
        "estatisticas": ia_service.calcular_estatisticas(sintomas),
    }
    try:
        pdf = gerar_pdf_relatorio(usuario, sintomas,
                                  data_inicio.isoformat() if data_inicio else None,
                                  data_fim.isoformat() if data_fim else None, ia=ia)
    except Exception as e:
        log_erro("api_ia_relatorio_pdf (geração do PDF)", e)
        return jsonify({"error": "Não foi possível gerar o relatório em PDF no momento."}), 500
    return _enviar_pdf(pdf)


@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'}), 200


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=False)

import psycopg2
import os
import re
import jwt
import logging
from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
from functools import wraps
from datetime import datetime, date, timedelta
from psycopg2.extras import RealDictCursor
from flask import request, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash

import ia_service
from relatorio_pdf import gerar_pdf_relatorio

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.environ.get("SECRET_KEY")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mediary")

if not DATABASE_URL:
    logger.warning("DATABASE_URL não definida. Configure a variável de ambiente antes de usar em produção.")

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

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY

# Mensagem genérica usada sempre que um erro interno não pode ser exposto ao usuário.
MSG_ERRO_INTERNO = "Ocorreu um erro inesperado. Tente novamente em instantes."
MSG_ERRO_BANCO = "Não foi possível completar a operação no momento. Tente novamente mais tarde."


def log_erro(contexto, excecao):
    """Loga o erro completo no servidor sem nunca expor detalhes internos ao cliente."""
    logger.error("Erro em %s: %s", contexto, excecao)


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
_allowed_origins += ["http://localhost", "http://localhost:80", "http://127.0.0.1"]

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

# ── DB ────────────────────────────────────────────────────────────────────────

def get_db():
    conn = psycopg2.connect(dsn=DATABASE_URL)
    conn.autocommit = False
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Usuarios (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Sintomas (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            subtipo TEXT,
            descricao TEXT,
            inicio TIMESTAMP NOT NULL,
            fim TIMESTAMP,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES Usuarios(id) ON DELETE CASCADE
        )
    """)
    # ── IA ──
    # Consentimento do usuário para enviar os dados ao serviço de IA (NULL = não consentiu).
    cursor.execute("ALTER TABLE Usuarios ADD COLUMN IF NOT EXISTS ia_consentimento_em TIMESTAMP")
    # Contador diário de uso da IA por usuário (limita custo e abuso). Não guarda conteúdo.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS IaUso (
            usuario_id INTEGER NOT NULL REFERENCES Usuarios(id) ON DELETE CASCADE,
            dia DATE NOT NULL,
            recurso TEXT NOT NULL,
            total INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (usuario_id, dia, recurso)
        )
    """)
    conn.commit()
    conn.close()

try:
    init_db()
except Exception as e:
    log_erro("init_db", e)

# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_token(usuario_id, nome):
    payload = {
        "usuario_id": usuario_id,
        "nome": nome,
        "exp": datetime.utcnow() + timedelta(days=30)
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
        cursor = conn.cursor(cursor_factory=RealDictCursor)
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
        cursor = conn.cursor(cursor_factory=RealDictCursor)
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
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("INSERT INTO Usuarios (nome, email, senha_hash) VALUES (%s, %s, %s)",
                       (nome, email, generate_password_hash(senha)))
        conn.commit()
        conn.close()
        return jsonify({"message": "Conta criada com sucesso!"}), 201
    except psycopg2.IntegrityError:
        return jsonify({"error": "E-mail já cadastrado"}), 400
    except Exception as e:
        log_erro("cadastro", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500


@app.route("/api/usuario", methods=["PUT"])
@login_required
def update_usuario():
    data = request.json or {}
    nome = data.get("nome")
    email = data.get("email")
    if not nome or not email:
        return jsonify({"error": "Nome e e-mail são obrigatórios"}), 400
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("UPDATE Usuarios SET nome=%s, email=%s WHERE id=%s",
                       (nome, email, request.current_user["usuario_id"]))
        conn.commit()
        conn.close()
        return jsonify({"message": "Perfil atualizado com sucesso", "nome": nome, "email": email})
    except psycopg2.IntegrityError:
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
        cursor = conn.cursor(cursor_factory=RealDictCursor)
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

@app.route("/api/sintomas/calendario")
@login_required
def api_calendario_info():
    ano = int(request.args.get("ano", date.today().year))
    mes = int(request.args.get("mes", date.today().month))
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT inicio, fim FROM Sintomas
            WHERE usuario_id = %s
            AND (TO_CHAR(inicio, 'YYYY-MM') <= %s
                AND (fim IS NULL OR TO_CHAR(fim, 'YYYY-MM') >= %s))
        """, (request.current_user["usuario_id"], f"{ano}-{mes:02d}", f"{ano}-{mes:02d}"))
        rows = cursor.fetchall()
        calendario = {}
        for row in rows:
            ini_str = row["inicio"].strftime("%Y-%m-%d")
            fim_str = row["fim"].strftime("%Y-%m-%d") if row["fim"] else ini_str
            try:
                ini_dt = datetime.strptime(ini_str, "%Y-%m-%d").date()
                fim_dt = datetime.strptime(fim_str, "%Y-%m-%d").date()
                curr = ini_dt
                while curr <= fim_dt:
                    if curr.year == ano and curr.month == mes:
                        d_str = curr.strftime("%Y-%m-%d")
                        calendario[d_str] = calendario.get(d_str, 0) + 1
                    curr += timedelta(days=1)
            except Exception:
                continue
        conn.close()
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
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT id, tipo, subtipo, descricao, inicio, fim FROM Sintomas
            WHERE usuario_id = %s
            AND ((fim IS NULL AND TO_CHAR(inicio, 'YYYY-MM-DD') = %s)
                OR (fim IS NOT NULL
                    AND TO_CHAR(inicio, 'YYYY-MM-DD') <= %s
                    AND TO_CHAR(fim, 'YYYY-MM-DD') >= %s))
            ORDER BY inicio
        """, (request.current_user["usuario_id"], data_sel, data_sel, data_sel))
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
            ini_dt = datetime.fromisoformat(inicio.replace('Z', '+00:00')) if 'T' in inicio else datetime.strptime(inicio, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return jsonify({"error": "Formato de data de início inválido"}), 400
        if ini_dt.replace(tzinfo=None) > agora + timedelta(minutes=5):
            return jsonify({"error": "A data de início não pode ser futura"}), 400
        if ini_dt.replace(tzinfo=None) < um_ano_atras:
            return jsonify({"error": "O registro é limitado a no máximo 1 ano atrás"}), 400
        if fim:
            try:
                fim_dt = datetime.fromisoformat(fim.replace('Z', '+00:00')) if 'T' in fim else datetime.strptime(fim, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return jsonify({"error": "Formato de data de fim inválido"}), 400
            if fim_dt.replace(tzinfo=None) < ini_dt.replace(tzinfo=None):
                return jsonify({"error": "A data de término não pode ser anterior à de início"}), 400
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "INSERT INTO Sintomas (usuario_id, tipo, subtipo, descricao, inicio, fim) VALUES (%s, %s, %s, %s, %s, %s)",
            (request.current_user["usuario_id"], tipo, subtipo, descricao, inicio, fim))
        conn.commit()
        conn.close()
        return jsonify({"message": "Sintoma adicionado com sucesso"}), 201
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
            cursor = conn.cursor(cursor_factory=RealDictCursor)
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
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM Sintomas WHERE id=%s AND usuario_id=%s", (sintoma_id, uid))
        sintoma_atual = cursor.fetchone()
        if not sintoma_atual:
            conn.close()
            return jsonify({"error": "Sintoma não encontrado"}), 404
        tipo      = data.get("tipo", sintoma_atual["tipo"])
        subtipo   = data.get("subtipo", sintoma_atual["subtipo"])
        descricao = data.get("descricao", sintoma_atual["descricao"])
        inicio    = data.get("inicio", sintoma_atual["inicio"])
        fim       = data.get("fim", sintoma_atual["fim"])
        cursor.execute("""UPDATE Sintomas SET tipo=%s, subtipo=%s, descricao=%s,
                         inicio=%s, fim=%s, atualizado_em=CURRENT_TIMESTAMP
                         WHERE id=%s AND usuario_id=%s""",
                       (tipo, subtipo, descricao, inicio, fim, sintoma_id, uid))
        conn.commit()
        conn.close()
        return jsonify({"message": "Sintoma atualizado"})
    except Exception as e:
        if 'conn' in locals(): conn.close()
        log_erro("api_sintoma_detail (PUT)", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500


@app.route("/api/sintomas/mes/<int:ano>/<int:mes>")
@login_required
def api_sintomas_mes(ano, mes):
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        mes_formatado = f"{ano}-{mes:02d}"
        cursor.execute("""
            SELECT id, tipo, subtipo, descricao, inicio, fim FROM Sintomas
            WHERE usuario_id = %s
            AND (TO_CHAR(inicio, 'YYYY-MM') <= %s
                AND (fim IS NULL OR TO_CHAR(fim, 'YYYY-MM') >= %s))
            ORDER BY inicio
        """, (request.current_user["usuario_id"], mes_formatado, mes_formatado))
        colunas = [desc[0] for desc in cursor.description]
        data = [dict(zip(colunas, row)) for row in cursor.fetchall()]
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
        cursor = conn.cursor(cursor_factory=RealDictCursor)
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


_DIA_LOCAL_SQL = "(now() AT TIME ZONE 'America/Sao_Paulo')::date"


def reservar_uso_ia(uid, recurso, limite):
    """Conta +1 uso hoje, de forma atômica. False se o limite diário já foi atingido."""
    if limite <= 0:
        return False
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            INSERT INTO IaUso (usuario_id, dia, recurso, total)
            VALUES (%s, {_DIA_LOCAL_SQL}, %s, 1)
            ON CONFLICT (usuario_id, dia, recurso)
            DO UPDATE SET total = IaUso.total + 1 WHERE IaUso.total < %s
            RETURNING total
        """, (uid, recurso, limite))
        liberado = cursor.fetchone() is not None
        conn.commit()
        return liberado
    finally:
        conn.close()


def liberar_uso_ia(uid, recurso):
    """Devolve o uso reservado quando a falha foi nossa (a IA não respondeu)."""
    try:
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE IaUso SET total = GREATEST(total - 1, 0)
                WHERE usuario_id = %s AND dia = {_DIA_LOCAL_SQL} AND recurso = %s
            """, (uid, recurso))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        log_erro("liberar_uso_ia", e)


def _bloqueio_ia(uid, recurso, limite):
    """None se pode usar a IA agora; senão, a resposta de erro pronta."""
    if not ia_service.ia_configurada():
        return jsonify({"error": "O assistente de IA não está disponível no momento."}), 503
    if not usuario_consentiu_ia(uid):
        return jsonify({
            "error": "Para usar a IA, aceite primeiro o envio dos seus registros ao assistente.",
            "codigo": "consentimento_necessario",
        }), 403
    if not reservar_uso_ia(uid, recurso, limite):
        return jsonify({"error": "Você atingiu o limite diário de uso da IA. Tente novamente amanhã."}), 429
    return None


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
            "UPDATE Usuarios SET ia_consentimento_em = CASE WHEN %s THEN now() ELSE NULL END WHERE id = %s",
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
        bloqueio = _bloqueio_ia(uid, "interpretar", limite)
    except Exception as e:
        log_erro("api_ia_interpretar (bloqueio)", e)
        return jsonify({"error": MSG_ERRO_BANCO}), 500
    if bloqueio:
        return bloqueio

    try:
        resultado = ia_service.interpretar_mensagem(mensagem, data.get("rascunho"), historico, agora)
    except ia_service.IAIndisponivel:
        liberar_uso_ia(uid, "interpretar")
        return jsonify({"error": "O assistente de IA está indisponível agora. Tente de novo em instantes ou use o botão + para registrar manualmente."}), 503
    except ia_service.IASaidaInvalida:
        liberar_uso_ia(uid, "interpretar")
        return jsonify({"error": "Não consegui entender essa mensagem. Pode contar de outro jeito?"}), 422
    except Exception as e:
        liberar_uso_ia(uid, "interpretar")
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
        bloqueio = _bloqueio_ia(uid, "resumo", limite)
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
        liberar_uso_ia(uid, "resumo")
        return jsonify({"error": "O assistente de IA está indisponível agora. Tente de novo em instantes."}), 503
    except ia_service.IASaidaInvalida:
        liberar_uso_ia(uid, "resumo")
        return jsonify({"error": "Não consegui montar o resumo agora. Tente novamente."}), 422
    except Exception as e:
        liberar_uso_ia(uid, "resumo")
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

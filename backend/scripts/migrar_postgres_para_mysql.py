"""
Migração controlada dos dados do Mediary: PostgreSQL (Supabase) -> MySQL 8.

O script NUNCA escreve nem apaga nada no Postgres: a conexão de origem é aberta
em modo somente leitura. São três passos, rodados por você, um de cada vez:

  1) contar    -> mostra quantas linhas há em cada tabela, na origem e no destino
  2) exportar  -> lê o Postgres e grava um arquivo .json.gz (fora do Git) com os dados
  3) importar  -> lê o arquivo e grava no MySQL em UMA transação; confere as
                  contagens antes do COMMIT e, se algo não bater, desfaz tudo

Instalação (dentro de backend/):
    pip install -r requirements-migracao.txt

Variáveis de ambiente (nunca passe senhas na linha de comando: elas ficam no
histórico do shell):
    PG_DATABASE_URL    postgresql://usuario:senha@host:porta/banco   (origem)
    DATABASE_URL       mysql://usuario@host:3306/banco                (destino)
    DATABASE_PASSWORD  senha do MySQL (opcional, se não estiver na URL)
    DATABASE_SSL_CA    certificado da CA do MySQL (opcional, ex.: RDS)

Exemplos:
    python scripts/migrar_postgres_para_mysql.py contar
    python scripts/migrar_postgres_para_mysql.py exportar --arquivo dumps/mediary.json.gz
    python scripts/migrar_postgres_para_mysql.py importar --arquivo dumps/mediary.json.gz

O arquivo exportado contém dados pessoais e de saúde: guarde em local seguro e
apague quando a migração estiver confirmada. A pasta dumps/ está no .gitignore.
O script só imprime contagens, nunca nomes, e-mails ou sintomas.
"""
import argparse
import gzip
import json
import os
import sys
from datetime import datetime, date, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))  # backend/

# Colunas migradas de cada tabela (na ordem de inserção, por causa das chaves estrangeiras).
TABELAS = [
    ("Usuarios", ["id", "nome", "email", "senha_hash", "criado_em", "ia_consentimento_em"]),
    ("Sintomas", ["id", "usuario_id", "tipo", "subtipo", "descricao", "inicio", "fim",
                  "criado_em", "atualizado_em"]),
    ("IaUso", ["usuario_id", "dia", "recurso", "total"]),
]
# Colunas que podem não existir numa origem antiga (são preenchidas com NULL).
OPCIONAIS = {("Usuarios", "ia_consentimento_em")}
# Limites de tamanho das colunas VARCHAR no MySQL (o Postgres usava TEXT).
TAMANHOS = {
    ("Usuarios", "nome"): 255, ("Usuarios", "email"): 255, ("Usuarios", "senha_hash"): 255,
    ("Sintomas", "tipo"): 100, ("Sintomas", "subtipo"): 100, ("IaUso", "recurso"): 40,
}
COLUNAS_DATA_HORA = {"criado_em", "atualizado_em", "inicio", "fim", "ia_consentimento_em"}
COLUNAS_DATA = {"dia"}
VERSAO_ARQUIVO = 1


def erro(msg):
    print(f"ERRO: {msg}", file=sys.stderr)
    sys.exit(1)


# ── Origem (Postgres, somente leitura) ───────────────────────────────────────

def conectar_postgres():
    url = os.environ.get("PG_DATABASE_URL")
    if not url:
        erro("defina PG_DATABASE_URL com a conexão do Postgres (origem).")
    try:
        import psycopg2
    except ImportError:
        erro("psycopg2 não instalado. Rode: pip install -r requirements-migracao.txt")
    conn = psycopg2.connect(dsn=url)
    conn.set_session(readonly=True, autocommit=False)
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")
    return conn


def tabelas_postgres(conn):
    """Mapa 'Usuarios' -> nome real na origem. O app criava as tabelas sem aspas, então
    no Postgres elas se chamam usuarios/sintomas/iauso (minúsculas). O schema.sql antigo
    criava "Usuarios"/"Sintomas" com aspas: se as duas existirem, usamos a do app e avisamos."""
    with conn.cursor() as cur:
        cur.execute("""SELECT table_name FROM information_schema.tables
                       WHERE table_schema = 'public'""")
        existentes = {r[0] for r in cur.fetchall()}
    mapa = {}
    for nome, _ in TABELAS:
        if nome.lower() in existentes:
            mapa[nome] = nome.lower()
            if nome in existentes and nome != nome.lower():
                print(f"AVISO: existem '{nome.lower()}' e '\"{nome}\"' no Postgres. Usando "
                      f"'{nome.lower()}' (a que o app usa). Confira a outra manualmente.")
        elif nome in existentes:
            mapa[nome] = nome
    return mapa


def colunas_postgres(conn, tabela_real):
    with conn.cursor() as cur:
        cur.execute("""SELECT column_name FROM information_schema.columns
                       WHERE table_schema = 'public' AND table_name = %s""", (tabela_real,))
        return {r[0] for r in cur.fetchall()}


def contar_postgres(conn):
    mapa = tabelas_postgres(conn)
    contagens = {}
    with conn.cursor() as cur:
        for nome, _ in TABELAS:
            if nome not in mapa:
                contagens[nome] = None
                continue
            cur.execute(f'SELECT COUNT(*) FROM "{mapa[nome]}"')
            contagens[nome] = cur.fetchone()[0]
    return contagens


# ── Destino (MySQL) ──────────────────────────────────────────────────────────

def conectar_mysql():
    if not os.environ.get("DATABASE_URL", "").startswith(("mysql://", "mysql+pymysql://")):
        erro("defina DATABASE_URL com a conexão do MySQL (destino), começando com mysql://")
    os.environ["MEDIARY_PULAR_INIT_DB"] = "1"  # não deixa o import do app mexer no banco
    import app as mediary_app
    import pymysql
    return mediary_app, pymysql.connect(**mediary_app._config_banco())


def contar_mysql(conn):
    contagens = {}
    with conn.cursor() as cur:
        for nome, _ in TABELAS:
            cur.execute("""SELECT 1 FROM information_schema.TABLES
                           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s""", (nome,))
            if not cur.fetchone():
                contagens[nome] = None
                continue
            cur.execute(f"SELECT COUNT(*) FROM `{nome}`")
            contagens[nome] = cur.fetchone()[0]
    return contagens


# ── Conversões ───────────────────────────────────────────────────────────────

def para_json(valor):
    if isinstance(valor, datetime):
        if valor.tzinfo is not None:  # TIMESTAMPTZ -> UTC sem fuso (mesma hora que o app via)
            valor = valor.astimezone(timezone.utc).replace(tzinfo=None)
        return valor.replace(microsecond=0).isoformat(sep=" ")
    if isinstance(valor, date):
        return valor.isoformat()
    return valor


def de_json(coluna, valor):
    if valor is None:
        return None
    if coluna in COLUNAS_DATA_HORA:
        return datetime.fromisoformat(valor)
    if coluna in COLUNAS_DATA:
        return date.fromisoformat(valor)
    return valor


def imprimir_contagens(titulo, contagens):
    print(titulo)
    for nome, _ in TABELAS:
        n = contagens.get(nome)
        print(f"  {nome:<10} {'(não existe)' if n is None else n}")


# ── Comandos ─────────────────────────────────────────────────────────────────

def cmd_contar(_args):
    if os.environ.get("PG_DATABASE_URL"):
        pg = conectar_postgres()
        try:
            imprimir_contagens("Postgres (origem):", contar_postgres(pg))
        finally:
            pg.rollback()
            pg.close()
    else:
        print("Postgres: PG_DATABASE_URL não definida, pulando.")
    if os.environ.get("DATABASE_URL"):
        _, my = conectar_mysql()
        try:
            imprimir_contagens("MySQL (destino):", contar_mysql(my))
        finally:
            my.close()
    else:
        print("MySQL: DATABASE_URL não definida, pulando.")


def cmd_exportar(args):
    if os.path.exists(args.arquivo) and not args.sobrescrever:
        erro(f"{args.arquivo} já existe. Use --sobrescrever ou outro nome.")
    pg = conectar_postgres()
    try:
        mapa = tabelas_postgres(pg)
        if "Usuarios" not in mapa or "Sintomas" not in mapa:
            erro("não encontrei as tabelas usuarios/sintomas no Postgres.")
        dados = {"versao": VERSAO_ARQUIVO,
                 "exportado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "contagens": {}, "tabelas": {}}
        with pg.cursor() as cur:
            for nome, colunas in TABELAS:
                if nome not in mapa:
                    print(f"AVISO: tabela {nome} não existe na origem; exportando vazia.")
                    dados["tabelas"][nome] = []
                    dados["contagens"][nome] = 0
                    continue
                existentes = colunas_postgres(pg, mapa[nome])
                selecao = []
                for c in colunas:
                    if c in existentes:
                        selecao.append(f'"{c}"')
                    elif (nome, c) in OPCIONAIS:
                        selecao.append(f'NULL AS "{c}"')
                    else:
                        erro(f"coluna {c} não existe em {mapa[nome]} na origem.")
                ordem = '"id"' if "id" in colunas else '"usuario_id", "dia", "recurso"'
                cur.execute(f'SELECT {", ".join(selecao)} FROM "{mapa[nome]}" ORDER BY {ordem}')
                linhas = [[para_json(v) for v in row] for row in cur.fetchall()]
                dados["tabelas"][nome] = linhas
                dados["contagens"][nome] = len(linhas)
        # Confere de novo as contagens dentro da mesma transação de leitura.
        recontagem = contar_postgres(pg)
    finally:
        pg.rollback()
        pg.close()

    for nome, _ in TABELAS:
        esperado = recontagem.get(nome) or 0
        if dados["contagens"][nome] != esperado:
            erro(f"contagem de {nome} mudou durante a exportação ({esperado} x "
                 f"{dados['contagens'][nome]}). Rode de novo.")
    pasta = os.path.dirname(os.path.abspath(args.arquivo))
    os.makedirs(pasta, exist_ok=True)
    fd = os.open(args.arquivo, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as bruto, gzip.open(bruto, "wt", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    imprimir_contagens(f"Exportado para {args.arquivo} (permissão 600):", dados["contagens"])
    print("Nada foi alterado no Postgres.")


def validar(dados):
    problemas = []
    for nome, colunas in TABELAS:
        linhas = dados["tabelas"].get(nome, [])
        if len(linhas) != dados["contagens"].get(nome, 0):
            problemas.append(f"{nome}: arquivo inconsistente (contagem não bate).")
        for (tabela, coluna), maximo in TAMANHOS.items():
            if tabela != nome:
                continue
            i = colunas.index(coluna)
            longas = sum(1 for l in linhas if isinstance(l[i], str) and len(l[i]) > maximo)
            if longas:
                problemas.append(f"{nome}.{coluna}: {longas} linha(s) com mais de {maximo} caracteres.")
    # E-mails que o MySQL consideraria iguais (collation sem distinção de maiúsculas/acentos).
    import unicodedata
    vistos, repetidos = set(), 0
    i_email = TABELAS[0][1].index("email")
    for l in dados["tabelas"].get("Usuarios", []):
        chave = unicodedata.normalize("NFKD", (l[i_email] or "").strip().lower())
        chave = "".join(c for c in chave if not unicodedata.combining(c))
        if chave in vistos:
            repetidos += 1
        vistos.add(chave)
    if repetidos:
        problemas.append(f"Usuarios.email: {repetidos} e-mail(s) que o MySQL trataria como "
                         "duplicados (diferem só em maiúsculas/acentos/espaços).")
    return problemas


def cmd_importar(args):
    with gzip.open(args.arquivo, "rt", encoding="utf-8") as f:
        dados = json.load(f)
    if dados.get("versao") != VERSAO_ARQUIVO:
        erro("versão do arquivo desconhecida.")
    imprimir_contagens(f"Arquivo {args.arquivo} (exportado em {dados.get('exportado_em')}):",
                       dados["contagens"])
    problemas = validar(dados)
    if problemas:
        print("Problemas encontrados (nada foi gravado):")
        for p in problemas:
            print("  -", p)
        sys.exit(1)

    import pymysql
    mediary_app, my = conectar_mysql()
    my.close()
    mediary_app.init_db()  # cria as tabelas se ainda não existirem (idempotente)
    my = pymysql.connect(**mediary_app._config_banco())
    try:
        antes = contar_mysql(my)
        imprimir_contagens("MySQL antes da importação:", antes)
        if any(antes.get(n) for n, _ in TABELAS):
            erro("o MySQL de destino já tem dados. A importação só roda em tabelas vazias, "
                 "para não misturar nem duplicar registros.")

        with my.cursor() as cur:
            for nome, colunas in TABELAS:
                linhas = [tuple(de_json(c, v) for c, v in zip(colunas, l))
                          for l in dados["tabelas"].get(nome, [])]
                if not linhas:
                    continue
                cols = ", ".join(f"`{c}`" for c in colunas)
                marc = ", ".join(["%s"] * len(colunas))
                for i in range(0, len(linhas), 500):
                    cur.executemany(f"INSERT INTO `{nome}` ({cols}) VALUES ({marc})", linhas[i:i + 500])
            depois = contar_mysql(my)  # mesma transação: enxerga as linhas ainda não confirmadas
            divergentes = [n for n, _ in TABELAS if (depois.get(n) or 0) != dados["contagens"].get(n, 0)]
            if divergentes:
                my.rollback()
                erro(f"contagens não bateram em {', '.join(divergentes)}. Nada foi gravado (ROLLBACK).")
            if args.simular:
                my.rollback()
                imprimir_contagens("Simulação OK (ROLLBACK, nada foi gravado). Contagens que ficariam:", depois)
                return
            my.commit()
        # O AUTO_INCREMENT do InnoDB já segue o maior id inserido; só conferimos.
        final = contar_mysql(my)
        imprimir_contagens("MySQL depois da importação (COMMIT feito):", final)
        print("Contagens conferem com a origem. Nada foi alterado no Postgres.")
    except pymysql.err.IntegrityError as e:
        my.rollback()
        erro(f"violação de integridade no MySQL (código {e.args[0]}). Nada foi gravado (ROLLBACK).")
    finally:
        my.close()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("contar", help="contagem de linhas na origem e no destino")
    e = sub.add_parser("exportar", help="Postgres -> arquivo .json.gz (somente leitura na origem)")
    e.add_argument("--arquivo", required=True)
    e.add_argument("--sobrescrever", action="store_true")
    i = sub.add_parser("importar", help="arquivo .json.gz -> MySQL (tabelas vazias, uma transação)")
    i.add_argument("--arquivo", required=True)
    i.add_argument("--simular", action="store_true", help="faz tudo e dá ROLLBACK no final")
    args = p.parse_args(argv)
    {"contar": cmd_contar, "exportar": cmd_exportar, "importar": cmd_importar}[args.comando](args)


if __name__ == "__main__":
    main()

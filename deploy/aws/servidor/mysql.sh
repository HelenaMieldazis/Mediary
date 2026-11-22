#!/bin/bash
# Abre o cliente MySQL no banco do RDS, com TLS verificado. Roda na EC2, como root,
# pela sessão do Session Manager. As senhas vêm do Parameter Store e não aparecem na
# tela, no histórico nem no "ps".
#
#   sudo /opt/mediary/deploy/aws/servidor/mysql.sh                 # usuário do app (recomendado)
#   sudo /opt/mediary/deploy/aws/servidor/mysql.sh admin           # usuário mestre (só para GRANT etc.)
#   sudo /opt/mediary/deploy/aws/servidor/mysql.sh app -e "SELECT COUNT(*) FROM Usuarios"
#   sudo /opt/mediary/deploy/aws/servidor/mysql.sh app < arquivo.sql
#
# Tudo depois do primeiro argumento é repassado ao cliente "mysql".
set -euo pipefail

PERFIL="${1:-app}"; shift || true
case "$PERFIL" in app|admin) ;; *) echo "uso: $0 [app|admin] [opções do mysql]"; exit 2;; esac

if [ -z "${AWS_REGION:-}" ]; then
  TOKEN=$(curl -sf -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
  AWS_REGION=$(curl -sf -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)
fi
export AWS_DEFAULT_REGION="$AWS_REGION"
ler() { aws ssm get-parameter --name "$1" --with-decryption --query Parameter.Value --output text; }

URL=$(ler /mediary/prod/DATABASE_URL)
eval "$(python3 - "$URL" <<'PY'
import shlex, sys, urllib.parse as u
p = u.urlsplit(sys.argv[1])
print(f"HOST={shlex.quote(p.hostname or '')}")
print(f"PORTA={p.port or 3306}")
print(f"USUARIO_APP={shlex.quote(u.unquote(p.username or ''))}")
print(f"BANCO={shlex.quote(u.unquote(p.path.lstrip('/')))}")
PY
)"

if [ "$PERFIL" = admin ]; then
  USUARIO=${ADMIN_USER:-mediary_admin}; SENHA=$(ler /mediary/prod/db-senha-admin)
  echo "Atenção: usuário MESTRE. Use só para administração (GRANT, usuários)." >&2
else
  USUARIO="$USUARIO_APP"; SENHA=$(ler /mediary/prod/DATABASE_PASSWORD)
fi

# Arquivo temporário de credenciais (permissão 600), apagado ao sair.
TMP=$(mktemp -d); chmod 700 "$TMP"
trap 'rm -rf "$TMP"' EXIT
(umask 077; python3 - "$USUARIO" "$SENHA" > "$TMP/cliente.cnf") <<'PY'
import sys
usuario, senha = sys.argv[1], sys.argv[2]
esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
print(f'[client]\nuser="{esc(usuario)}"\npassword="{esc(senha)}"')
PY
unset SENHA

CA="${RDS_CA:-/opt/mediary/rds-global-bundle.pem}"
if [ ! -s "$CA" ]; then
  curl -fsSL -o "$CA" https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
fi

TTY=(-i); [ -t 0 ] && [ -t 1 ] && TTY=(-it)
docker run --rm "${TTY[@]}" --network host \
  -v "$TMP/cliente.cnf:/cliente.cnf:ro" -v "$CA:/ca.pem:ro" \
  mysql:8.4 mysql --defaults-extra-file=/cliente.cnf \
  --ssl-mode="${SSL_MODE:-VERIFY_IDENTITY}" --ssl-ca=/ca.pem \
  -h "$HOST" -P "$PORTA" --default-character-set=utf8mb4 "$BANCO" "$@"

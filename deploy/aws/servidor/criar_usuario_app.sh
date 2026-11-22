#!/bin/bash
# Cria (uma vez) o usuário do banco que o app usa, com acesso só ao banco "mediary".
# Roda na EC2 como root, pelo Session Manager. Lê as senhas do Parameter Store:
#   /mediary/prod/db-senha-admin  (senha mestre do RDS)
#   /mediary/prod/DATABASE_PASSWORD (senha nova do usuário mediary_app)
# e o host de /mediary/prod/DATABASE_URL. Nenhuma senha aparece na tela nem no "ps".
set -euo pipefail
TOKEN=$(curl -sf -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
export AWS_DEFAULT_REGION=$(curl -sf -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)
ler() { aws ssm get-parameter --name "$1" --with-decryption --query Parameter.Value --output text; }

URL=$(ler /mediary/prod/DATABASE_URL)
HOST=$(python3 -c "import sys,urllib.parse as u;print(u.urlsplit(sys.argv[1]).hostname)" "$URL")
USUARIO=$(python3 -c "import sys,urllib.parse as u;print(u.unquote(u.urlsplit(sys.argv[1]).username))" "$URL")
SENHA_APP=$(ler /mediary/prod/DATABASE_PASSWORD)
case "$SENHA_APP" in *"'"*|*"\\"*) echo "A senha do app não pode ter aspas simples nem barra invertida."; exit 1;; esac

curl -fsSL -o /tmp/rds-ca.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
MYSQL_PWD=$(ler /mediary/prod/db-senha-admin) docker run --rm -i -e MYSQL_PWD \
  -v /tmp/rds-ca.pem:/ca.pem:ro mysql:8.4 \
  mysql --ssl-mode=VERIFY_IDENTITY --ssl-ca=/ca.pem -h "$HOST" -u mediary_admin <<SQL
CREATE USER IF NOT EXISTS '${USUARIO}'@'%' IDENTIFIED BY '${SENHA_APP}' REQUIRE SSL;
ALTER USER '${USUARIO}'@'%' IDENTIFIED BY '${SENHA_APP}';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES ON mediary.* TO '${USUARIO}'@'%';
SQL
echo "Usuário ${USUARIO} pronto (acesso só ao banco mediary, TLS obrigatório)."

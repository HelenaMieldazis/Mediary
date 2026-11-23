#!/bin/bash
# Atualiza e (re)sobe o Mediary na EC2. Roda como root (pelo Session Manager,
# pelo "aws ssm send-command" do deploy ou no primeiro boot).
#   uso: atualizar.sh [branch-ou-tag]     (padrão: a branch gravada no boot, ou main)
set -euo pipefail

# Tudo dentro de main(): o bash lê a função inteira antes de executar, então o
# "git checkout" abaixo pode trocar este arquivo sem bagunçar a execução atual.
main() {

  REF="${1:-$(cat /etc/mediary-branch 2>/dev/null || echo main)}"
  DIR=/opt/mediary
  ENV_DIR=/run/mediary   # tmpfs: os segredos não ficam gravados no disco
  PREFIXO=/mediary/prod/

  # Região e dados da instância via IMDSv2.
  TOKEN=$(curl -sf -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
  export AWS_REGION=$(curl -sf -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)
  export AWS_DEFAULT_REGION="$AWS_REGION"

  echo "==> Código: $REF"
  cd "$DIR"
  if [ -z "${MEDIARY_JA_ATUALIZADO:-}" ]; then
    ANTES=$(sha256sum "$DIR/deploy/aws/servidor/atualizar.sh" | cut -d' ' -f1)
    git fetch --quiet origin "$REF"
    git checkout --quiet --detach FETCH_HEAD
    DEPOIS=$(sha256sum "$DIR/deploy/aws/servidor/atualizar.sh" | cut -d' ' -f1)
    if [ "$ANTES" != "$DEPOIS" ]; then
      # O próprio script mudou nesta versão: reinicia com a versão nova.
      echo "    (atualizar.sh mudou; reiniciando com a versão nova)"
      exec env MEDIARY_JA_ATUALIZADO=1 bash "$DIR/deploy/aws/servidor/atualizar.sh" "$REF"
    fi
  fi
  git log -1 --format='    commit %h - %s'

  echo "==> Segredos do Parameter Store ($PREFIXO)"
  mkdir -p "$ENV_DIR" && chmod 700 "$ENV_DIR"
  umask 077
  python3 - "$PREFIXO" > "$ENV_DIR/backend.env.novo" <<'PY'
import json, subprocess, sys
prefixo = sys.argv[1]
args = ["aws", "ssm", "get-parameters-by-path", "--path", prefixo, "--with-decryption",
        "--recursive", "--output", "json"]
params, token = [], None
while True:
    saida = json.loads(subprocess.check_output(args + (["--next-token", token] if token else [])))
    params += saida["Parameters"]
    token = saida.get("NextToken")
    if not token:
        break
# Só variáveis do app (nomes em MAIÚSCULAS). A senha de admin do RDS fica de fora.
for p in sorted(params, key=lambda p: p["Name"]):
    nome = p["Name"][len(prefixo):]
    if not nome.isupper() and not nome.replace("_", "").isupper():
        continue
    valor = p["Value"]
    if "'" in valor or "\n" in valor:
        sys.exit(f"O parâmetro {nome} tem aspas simples ou quebra de linha; gere outro valor.")
    # Aspas simples: o docker compose não interpreta $ dentro delas.
    print(f"{nome}='{valor}'")
PY
  mv "$ENV_DIR/backend.env.novo" "$ENV_DIR/backend.env"
  for obrigatoria in DATABASE_URL DATABASE_PASSWORD SECRET_KEY DOMINIO; do
    grep -q "^$obrigatoria=" "$ENV_DIR/backend.env" || { echo "Falta $PREFIXO$obrigatoria"; exit 1; }
  done
  export DOMINIO=$(sed -n "s/^DOMINIO='\(.*\)'$/\1/p" "$ENV_DIR/backend.env")

  echo "==> Build e subida dos contêineres"
  cd "$DIR/deploy/aws"
  # O contêiner "caddy" das versões antigas foi substituído pelo "web".
  docker rm -f mediary-caddy >/dev/null 2>&1 || true
  docker compose -f docker-compose.prod.yml up -d --build --remove-orphans
  docker image prune -f >/dev/null

  echo "==> Verificando /api/health"
  for i in $(seq 1 30); do
    if docker exec mediary-backend python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:5000/api/health',timeout=3)" 2>/dev/null; then
      echo "OK: backend respondendo. Site: https://$DOMINIO  API: https://$DOMINIO/api/health"
      exit 0
    fi
    sleep 2
  done
  echo "ERRO: o backend não respondeu. Veja os logs no CloudWatch (/mediary/prod)."
  exit 1
}

main "$@"
exit $?

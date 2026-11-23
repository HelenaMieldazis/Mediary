# Deploy do Mediary na AWS

Guia para publicar o Mediary inteiro na AWS: site (React), API (Flask) e MySQL (RDS), com o DNS no Registro.br.
**Nada aqui cria recursos sozinho:** cada passo que gera custo é você quem executa.

> Pesquisa feita em **22/11/2026**. Regras, créditos e preços da AWS mudam: confira
> os links da seção 1 e a [calculadora de preços](https://calculator.aws/) antes de começar.

---

## 1. O que é gratuito hoje (contas criadas a partir de 15/07/2025)

| Item | Situação |
|---|---|
| Créditos | US$ 100 na criação da conta + até US$ 100 ao completar atividades (total até US$ 200). [Blog da AWS](https://aws.amazon.com/blogs/aws/aws-free-tier-update-new-customers-can-get-started-and-explore-aws-with-up-to-200-in-credits/) |
| Duração do **plano gratuito (Free plan)** | O que acontecer primeiro: **6 meses** desde a abertura da conta ou o fim dos créditos. [Termos](https://aws.amazon.com/free/terms/) |
| Fim do plano gratuito | A conta é **fechada automaticamente** e você perde acesso aos recursos e dados. A AWS guarda o conteúdo por 90 dias; para reabrir, é preciso migrar para o plano pago nesse prazo. [Doc de planos](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html) |
| **Dados sensíveis** | Os termos dizem que contas no Free plan são "para avaliação e **não devem ser usadas para processar dados sensíveis**". Dados de saúde são sensíveis pela LGPD. [Termos](https://aws.amazon.com/free/terms/) |
| Plano pago (Paid plan) | A conta não fecha. Os créditos restantes continuam valendo para uso elegível por até 12 meses após o cadastro. Quando acabam, a cobrança é normal (pague pelo uso). |
| EC2 elegível | t3.micro, t3.small, **t4g.micro**, t4g.small, c7i-flex.large, m7i-flex.large |
| RDS elegível | db.t3.micro e **db.t4g.micro** com MySQL, PostgreSQL, MariaDB ou SQL Server Express. [RDS Free Tier](https://aws.amazon.com/rds/free/) |
| IPv4 público | US$ 0,005/hora por IP (≈ US$ 3,65/mês), cobrado desde 02/2024. [Anúncio](https://aws.amazon.com/about-aws/whats-new/2024/02/aws-free-tier-750-hours-free-public-ipv4-addresses/) |
| Parameter Store | Parâmetros *standard* (inclusive SecureString) **sem custo**. [Preços](https://aws.amazon.com/systems-manager/pricing/) |
| Secrets Manager | US$ 0,40 por segredo/mês. Por isso usamos o Parameter Store. [Preços](https://aws.amazon.com/secrets-manager/pricing/) |

**Não consegui confirmar:**
- se EC2 e RDS de contas novas consomem créditos ou têm cota gratuita separada (as fontes divergem; trate como consumo de créditos e acompanhe em *Billing > Free Tier*);
- se há restrição de região no plano gratuito (nada indica que sim; `sa-east-1` é uma região comercial padrão).

O site aws.amazon.com estava bloqueado no ambiente da pesquisa. Os itens acima vêm de trechos das páginas oficiais (links) mostrados pela busca. Os preços por hora da seção 3 vêm de agregadores de terceiros.

### Recomendação sobre o plano da conta

Como o Mediary guarda **dados de saúde reais**, crie a conta no **plano pago (Paid plan)**.
Você continua recebendo os créditos de até US$ 200, e:
- a conta **não é fechada** depois de 6 meses (no Free plan, a conta e os dados seriam apagados);
- você respeita os termos do Free plan, que vetam dados sensíveis.

Em troca, quando os créditos acabarem a cobrança começa sem aviso. Por isso o **orçamento com alertas (passo 3.3) é obrigatório** e vem antes de qualquer recurso.

---

## 2. Arquitetura

Tudo na AWS, num endereço só: **`https://seudominio.com.br`**. O DNS fica no próprio Registro.br.

```
Navegador ──HTTPS──> seudominio.com.br  (registro A no DNS do Registro.br -> IP fixo da EC2)
                         │
                         EC2 t4g.micro
                         ├─ web: Caddy :443  (HTTPS automático, Let's Encrypt)
                         │    ├─ /          -> frontend React (arquivos estáticos)
                         │    └─ /api/*     -> backend
                         └─ backend: Flask/gunicorn :5000 (só rede interna)
                                   │  TLS, porta 3306, liberada só para o SG do backend
                                   └──> RDS MySQL 8.4 (sem IP público)
   www.seudominio.com.br -> redireciona para seudominio.com.br
   Segredos: SSM Parameter Store (/mediary/prod/*)    Logs: CloudWatch /mediary/prod (7 dias)
```

Por que o frontend fica no mesmo servidor, e não em S3 + CloudFront:
- **Custo extra zero:** mesmo servidor, mesmo IP, mesmo certificado.
- **Funciona com o DNS do Registro.br:** ele só precisa de registros **A**. O CloudFront exigiria
  CNAME/ALIAS no domínio raiz, que o DNS do Registro.br não oferece.
- **Sem CORS para configurar:** site e API na mesma origem, o frontend chama `/api` direto.

Alternativa para cortar custo depois: MySQL em contêiner na própria EC2 (t4g.small), ≈ US$ 26/mês
em vez de ≈ 45, mas com backup por sua conta. Em `us-east-1` os preços são ~40% menores; `sa-east-1`
tem menor latência e mantém os dados no Brasil.

### Custo estimado (sa-east-1, sob demanda, depois dos créditos)

| Recurso | US$/mês (aprox.) |
|---|---|
| EC2 t4g.micro (≈ US$ 0,0134/h) | 9,80 |
| Disco da EC2 16 GB gp3 | 2–3 |
| IPv4 público fixo (Elastic IP) | 3,65 |
| RDS db.t4g.micro MySQL (≈ US$ 0,034/h) | 24,80 |
| Armazenamento RDS 20 GB gp3 + backup | 4–5 |
| CloudWatch Logs (poucos MB, retenção 7 dias), Parameter Store, DNS do Registro.br | ≈ 0 |
| **Total** | **≈ 45** (≈ 4 meses cobertos por US$ 200 de créditos) |

À parte: a renovação do domínio no Registro.br e a API da Anthropic (cobrada pelo uso).

### Arquivos

| Arquivo | Para quê |
|---|---|
| `orcamento.yml` | Orçamento mensal com alertas por e-mail (crie **primeiro**) |
| `cloudformation.yml` | Security groups, RDS, EC2 com IP fixo, papel IAM mínimo, grupo de logs, identidade do domínio no SES (e-mail), papel de deploy do GitHub |
| `docker-compose.prod.yml` | Contêineres `web` (Caddy + frontend) e `backend` na EC2 |
| `Dockerfile.web`, `Caddyfile` | Compila o frontend e configura HTTPS, `/api` e redirecionamento do `www` |
| `servidor/atualizar.sh` | Na EC2: baixa o código, lê os segredos do Parameter Store, faz build e sobe |
| `servidor/criar_usuario_app.sh` | Na EC2: cria o usuário do banco do app (só acesso ao banco `mediary`) |
| `servidor/mysql.sh` | Na EC2: abre o cliente MySQL no RDS com TLS (seção 6) |
| `../../.github/workflows/deploy-aws.yml` | Deploy manual pelo GitHub Actions (OIDC, sem chaves guardadas) |

---

## 3. Passo a passo (o que depende de você)

Use o **AWS CloudShell** (ícone `>_` no topo do console) para os comandos: ele já vem autenticado,
roda dentro da AWS e é gratuito. Confira sempre se a região no topo do console é **São Paulo (sa-east-1)**.
Nos exemplos, troque `seudominio.com.br` pelo seu domínio.

### 3.1 Criar a conta e proteger o root
1. Crie a conta em https://aws.amazon.com/ e escolha o **Paid plan** (seção 1).
2. **MFA no root:** menu da conta > *Security credentials* > *Assign MFA device*.
3. Com o root: *Account* > *IAM user and role access to Billing information* > **Activate**.
4. Não crie chaves de acesso para o root.

### 3.2 Usuário IAM de administração (não root)
1. **IAM** > *Users* > *Create user*: `mediary-admin`, com acesso ao console e a política `AdministratorAccess`.
2. Entre com ele, ative MFA (*Security credentials* > *Assign MFA device*) e use **só ele** daqui em diante.
3. *Billing and Cost Management* > *Billing preferences* > ative **Receive AWS Free Tier alerts**.

### 3.3 Orçamento com alertas (ANTES de qualquer recurso)
1. Baixe `deploy/aws/orcamento.yml` do GitHub (abra o arquivo > **Download raw file**).
2. **CloudFormation** > *Create stack* > *With new resources* > *Upload a template file* > o arquivo > **Next**.
3. Nome `mediary-orcamento`, seu e-mail, limite (ex.: `10`) > **Next** > **Next** > **Submit**.
4. **Confirme o e-mail** que a AWS mandar (*AWS Notification - Subscription Confirmation*).

### 3.4 Chave da IA (Anthropic)
1. Em **platform.claude.com** > *API keys* > *Create key*: nome `mediary-producao`. Copie a chave.
2. Em *Billing*: confira se há créditos e defina um **limite mensal de gasto**.

### 3.5 Preparar o DNS no Registro.br (uma vez)
Para editar os registros, o domínio precisa usar o DNS do próprio Registro.br no **modo avançado**:
1. Entre em https://registro.br > **Domínios** > clique no domínio.
2. Em **DNS**, confira se está usando os servidores do Registro.br. Se estiver com servidores
   de outra empresa, troque para *Utilizar os servidores DNS do Registro.br*.
3. Clique em **Configurar endereçamento** > **Modo avançado** > **Confirmar**.
   A ativação pode levar alguns minutos. Quando terminar, aparece **Configurar zona DNS**.
4. Ainda **não** crie os registros: o IP só existe depois do passo 3.7.

Os nomes dos botões do Registro.br mudam de vez em quando. Se não achar, use a ajuda deles (registro.br/ajuda).

### 3.6 Segredos no Parameter Store
No CloudShell, crie a função auxiliar (ela some quando o CloudShell fecha; se precisar, crie de novo):
```bash
salvar() { read -rsp "Valor de $1: " V; echo; aws ssm put-parameter --region sa-east-1 --name "/mediary/prod/$1" --type "$2" --value "$V" --overwrite >/dev/null && echo "ok $1"; unset V; }
```
Para gerar cada senha (sem aspas, barras nem espaços):
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```
Crie, um por vez (o valor não aparece na tela):

| Comando | Valor |
|---|---|
| `salvar db-senha-admin SecureString` | senha gerada (mestre do RDS) |
| `salvar DATABASE_PASSWORD SecureString` | outra senha gerada (usuário do app) |
| `salvar SECRET_KEY SecureString` | outra senha gerada (tokens de login) |
| `salvar ANTHROPIC_API_KEY SecureString` | a chave do passo 3.4 |
| `salvar DOMINIO String` | só o domínio, sem `https://` e sem `www`: `seudominio.com.br` |

Confira em **Systems Manager** > *Parameter Store*: os 5 devem aparecer.

### 3.7 Criar a infraestrutura (a partir daqui consome créditos)
1. **VPC** > *Your VPCs*: anote o ID da VPC com **Default VPC = Yes**. Em *Subnets*, filtre por essa
   VPC e anote o **Subnet ID** da `sa-east-1a` e da `sa-east-1c`.
2. Baixe `deploy/aws/cloudformation.yml` do GitHub (**Download raw file**).
3. **CloudFormation** > *Create stack* > *With new resources (standard)* > *Upload a template file* > **Next**.
4. *Stack name* `mediary` e os parâmetros:

   | Parâmetro | Valor |
   |---|---|
   | `VpcId` | a VPC padrão |
   | `SubnetIds` | as **duas** subnets (a `sa-east-1a` primeiro) |
   | `InstanceType` / `DbInstanceClass` | `t4g.micro` / `db.t4g.micro` |
   | `DbBackupRetentionDays` | `7` (plano pago) ou `1` (plano gratuito) |
   | `RepoUrl` / `RepoBranch` | padrão (`main`) |
   | `GitHubRepo` | `HelenaMieldazis/Mediary` (vazio se não for usar o deploy pelo GitHub) |
   | `CriarProvedorOidcGitHub` | `true` |
   | `LogRetentionDays` | `7` |

5. **Next** > **Next** > na revisão, marque as **duas** caixas de IAM (a segunda: *"…with custom names"*) > **Submit**.
6. Acompanhe a aba **Events** por 10 a 20 minutos, até **CREATE_COMPLETE**. Na aba **Outputs**, anote
   `IpPublico`, `InstanceId`, `EnderecoBanco` e `PapelDeployGitHubArn`.
7. No CloudShell (troque `ENDERECO_DO_BANCO`):
   ```bash
   aws ssm put-parameter --region sa-east-1 --name /mediary/prod/DATABASE_URL --type String --overwrite --value "mysql://mediary_app@ENDERECO_DO_BANCO:3306/mediary"
   ```

**Se a stack falhar**, veja a primeira linha vermelha em *Events*:

| Erro | Correção |
|---|---|
| `Parameter ... db-senha-admin ... not found` | Crie o parâmetro em **sa-east-1** (3.6). |
| *backup retention ... free tier* | `DbBackupRetentionDays = 1`. |
| `Provider with url ... already exists` | `CriarProvedorOidcGitHub = false`. |
| `instance type ... not supported in ... Availability Zone` | Ponha a `sa-east-1c` como primeira subnet. |

Depois de uma falha, **delete a stack** (`ROLLBACK_COMPLETE`) antes de tentar de novo. Se ela travar em
`ROLLBACK_FAILED`/`DELETE_FAILED` por causa do banco: **RDS** > `mediary-mysql` > *Modify* > desmarque
*Enable deletion protection* > *Apply immediately* > delete a stack de novo.

### 3.8 Apontar o domínio (Registro.br)
1. Registro.br > **Domínios** > o domínio > **Configurar zona DNS** (ou *Editar zona*).
2. **Nova entrada** > Tipo **A** > Nome **vazio** (domínio raiz) > Dados/IP = `IpPublico` > adicionar.
3. **Nova entrada** > Tipo **A** > Nome **`www`** > Dados/IP = `IpPublico` > adicionar.
4. Se já existirem registros A ou CNAME antigos para o raiz ou para `www` (ex.: apontando para a Vercel),
   **apague-os**. Não mexa em registros MX/TXT de e-mail.
5. **Salvar alterações**.
6. No CloudShell (que não tem `dig` nem `nslookup`), confira. Deve mostrar o `IpPublico`;
   pode levar de minutos a algumas horas:
   ```bash
   python3 -c "import socket; print(socket.gethostbyname('seudominio.com.br'))"
   ```
   ```bash
   python3 -c "import socket; print(socket.gethostbyname('www.seudominio.com.br'))"
   ```

### 3.9 Primeiro deploy
Atenção: os comandos desta seção rodam **dentro do servidor (EC2)**, não no CloudShell. O CloudShell
(prompt `~ $`) é uma máquina separada e não tem a pasta `/opt/mediary`.
1. **EC2** > *Instances* > `mediary-backend` > **Connect** > aba **Session Manager** > **Connect**.
   Abre uma nova aba com o prompt `sh-5.2$`. Se o botão estiver cinza, espere 5 minutos (o agente está registrando).
   Para conferir onde você está: `hostname` no servidor mostra algo como `ip-172-31-...`.
2. Confira a instalação inicial (deve terminar com `Primeiro deploy falhou...`, o que é **esperado**):
   ```bash
   sudo tail -3 /var/log/mediary-bootstrap.log
   ```
3. Crie o usuário do app no MySQL (esperado: `Usuário mediary_app pronto...`):
   ```bash
   sudo /opt/mediary/deploy/aws/servidor/criar_usuario_app.sh
   ```
4. Suba o site e a API. Leva de 10 a 15 minutos na primeira vez (compila o backend e o frontend):
   ```bash
   sudo /opt/mediary/deploy/aws/servidor/atualizar.sh main
   ```
   Esperado no final: `OK: backend respondendo. Site: https://seudominio.com.br ...`.
   Se aparecer `Falta /mediary/prod/XXXX`, crie o parâmetro e rode de novo.
5. Abra **https://seudominio.com.br** no navegador: o site com cadeado. Teste também
   `https://seudominio.com.br/api/health` (`{"status":"ok"}`) e `http://www.seudominio.com.br`
   (deve ir para `https://seudominio.com.br`).

Se o cadeado não vier, o DNS ainda não aponta para o IP. Veja o log do servidor web:
```bash
sudo docker logs mediary-web --tail 30
```
`NXDOMAIN` ou `challenge failed` = DNS ainda propagando. Espere e reinicie:
```bash
sudo docker restart mediary-web
```

### 3.10 Migrar os dados do Supabase (controlado)
Faça **antes** de divulgar o site novo: a importação só roda com o banco vazio. Nada é apagado no Supabase.
1. Faça um backup no Supabase (*Database* > *Backups*).
2. Pegue a URL em Supabase > **Connect** > *Connection string* > **Session pooler** (endereço com
   `pooler.supabase.com:5432`). A *Direct connection* é só IPv6 e não funciona daqui. Troque
   `[YOUR-PASSWORD]` pela senha (se tiver `@ / ? # %`, codifique com
   `python3 -c "import urllib.parse,getpass; print(urllib.parse.quote(getpass.getpass('senha: '), safe=''))"`).
3. Se o Supabase tiver *Network restrictions*, libere `IpPublico/32`.
4. Na sessão da EC2:
   ```bash
   sudo docker exec -it mediary-backend sh
   ```
   ```bash
   pip install --user -q psycopg2-binary
   ```
   ```bash
   read -rsp "URL do Supabase: " PG_DATABASE_URL; export PG_DATABASE_URL; echo
   ```
   ```bash
   python scripts/migrar_postgres_para_mysql.py contar
   ```
   O MySQL tem que estar com **0** em tudo. Se não estiver, pare (alguém já se cadastrou).
   ```bash
   python scripts/migrar_postgres_para_mysql.py exportar --arquivo /tmp/dump/mediary.json.gz
   ```
   ```bash
   python scripts/migrar_postgres_para_mysql.py importar --arquivo /tmp/dump/mediary.json.gz --simular
   ```
   ```bash
   python scripts/migrar_postgres_para_mysql.py importar --arquivo /tmp/dump/mediary.json.gz
   ```
   ```bash
   python scripts/migrar_postgres_para_mysql.py contar
   ```
   ```bash
   rm -rf /tmp/dump; exit
   ```
5. Confira direto no MySQL:
   ```bash
   sudo /opt/mediary/deploy/aws/servidor/mysql.sh app -e "SELECT COUNT(*) FROM Usuarios; SELECT COUNT(*) FROM Sintomas;"
   ```

### 3.11 Deploy pelo GitHub Actions (opcional)
GitHub > *Settings* > *Environments* > *New environment* `producao`:
- marque *Required reviewers* (você);
- *Environment variables*: `AWS_DEPLOY_ROLE_ARN` (output `PapelDeployGitHubArn`), `AWS_REGION` (`sa-east-1`),
  `AWS_INSTANCE_ID` (output `InstanceId`).

Para publicar: *Actions* > **Deploy AWS** > *Run workflow* > aprove.

### 3.12 E-mail do "Esqueci minha senha" (Amazon SES)
O app envia o link de redefinição de senha pelo Amazon SES, a partir de `nao-responda@seudominio.com.br`.
O link vale 30 minutos e só uma vez, e cada conta pode pedir no máximo 3 por hora. Custo: US$ 0,10 por mil e-mails.

1. **Atualize a stack** (sem desligar o site; a EC2 não é recriada): baixe de novo o
   `deploy/aws/cloudformation.yml` da `main` > **CloudFormation** > stack `mediary` > **Update** >
   *Replace existing template* > *Upload a template file* > **Next**. Em **Dominio**, coloque só o
   domínio (ex.: `mediarymedico.com.br`); mantenha os outros parâmetros como estão > **Next** > **Next** >
   marque as caixas de IAM > **Submit**. Espere **UPDATE_COMPLETE** (2 a 5 minutos).
2. Na aba **Outputs** aparecem `DkimRegistro1`, `DkimRegistro2` e `DkimRegistro3`, no formato
   `abc123._domainkey.seudominio.com.br -> abc123.dkim.amazonses.com`.
3. **Registro.br** > *Configurar zona DNS* > crie **3 entradas CNAME**, uma para cada output:
   - **Nome:** só a parte antes do seu domínio (ex.: `abc123._domainkey`);
   - **Dados:** o que vem depois da seta (ex.: `abc123.dkim.amazonses.com`).

   Crie também uma entrada **TXT** com Nome `_dmarc` e Dados `v=DMARC1; p=none;`
   (ajuda o e-mail a não cair no spam) > **Salvar alterações**.
4. **Amazon SES** (região São Paulo) > *Identities* > `seudominio.com.br`: espere o status **Verified**
   (normalmente menos de 1 hora; pode levar até 72 h).
5. **Saia do modo sandbox.** Enquanto estiver no sandbox, o SES só entrega para endereços verificados.
   *SES* > *Account dashboard* > **Request production access**:
   - *Mail type*: **Transactional**; *Website URL*: `https://seudominio.com.br`;
   - *Use case description* (pode colar):
     > Mediary (https://seudominio.com.br) is a personal symptom diary web app. We only send
     > transactional emails: password reset links requested by the users themselves on the
     > "Forgot password" page. No marketing or bulk email. Expected volume: under 100 emails per
     > month. Recipients are only registered users who requested the reset; addresses are never
     > purchased or imported. Each account can request at most 3 emails per hour, and bounces and
     > complaints are monitored in the SES console.

   A resposta costuma vir em até 1 dia, por e-mail.
6. **Para testar antes da aprovação:** *SES* > *Identities* > **Create identity** > *Email address* >
   seu e-mail > clique no link de confirmação que chegar. Daí o SES já entrega para esse endereço.
7. Publique o código novo (na sessão da EC2):
   ```bash
   sudo /opt/mediary/deploy/aws/servidor/atualizar.sh main
   ```
8. Teste: no site, **Esqueci minha senha** com o e-mail de uma conta > o e-mail chega (confira o spam) >
   **Criar nova senha** > entre com a senha nova.

Se o e-mail não chegar, veja o motivo (não aparece o endereço nem o link no log):
```bash
sudo docker logs mediary-backend --tail 50 2>&1 | grep -i "e-mail\|email"
```
| Mensagem | Causa |
|---|---|
| `MessageRejected` | Domínio ainda não verificado, ou sandbox e destinatário não verificado (passos 4 a 6). |
| `AccessDeniedException` | A stack não foi atualizada com o `Dominio` (passo 1). |
| `NoCredentialsError` | A stack não foi atualizada (o servidor precisa do novo limite de metadados, passo 1). |
| `EMAIL_REMETENTE não configurado` | Rode o `atualizar.sh` de novo (passo 7). |

### 3.13 Desligar o que é antigo (só depois que a seção 4 passar inteira)
1. Anthropic: revogue a chave **antiga** (*API keys* > *Delete*).
2. Vercel: *Settings* > *General* > **Pause/Delete project** (e remova o domínio de lá, se estava ligado).
3. Render: serviço do backend > *Settings* > **Suspend Web Service** (reversível).
4. Supabase: troque a senha do banco (*Database* > *Settings* > *Reset database password*) e, depois
   de 1 a 2 semanas com tudo funcionando, **Pause project**.

---

## 4. Checklist de validação pós-deploy

- [ ] `https://seudominio.com.br` abre o app com cadeado válido; `www` e `http` redirecionam para ele
- [ ] `https://seudominio.com.br/api/health` → `{"status":"ok"}`
- [ ] Login de um usuário **migrado** (senha antiga) mostra os sintomas antigos; `contar` bate com o Supabase
- [ ] Cadastro de usuário novo
- [ ] **Esqueci minha senha**: o e-mail chega, o link cria a senha nova, o login funciona e o mesmo link não serve de novo
- [ ] Registrar, editar (a hora na edição é a registrada) e excluir um sintoma; o calendário marca o dia
- [ ] Relatório em PDF (sem IA) com acentos corretos
- [ ] IA: o botão do assistente aparece; o consentimento aparece no primeiro uso
- [ ] IA por **texto**: "ontem à noite tive dor de cabeça forte por duas horas" gera o cartão; **Salvar** grava
- [ ] IA pergunta o que falta: "tô com náusea" → ela pergunta quando começou
- [ ] IA por **voz** no celular (Chrome/Android ou Safari/iOS), com permissão de microfone
- [ ] Resumo para a consulta (últimos 30 dias): gera, editar uma frase, baixar o PDF com a edição
- [ ] Revogar o consentimento em Configurações bloqueia a IA
- [ ] Instalar como app (PWA) no celular funciona
- [ ] Painel da Anthropic > *Usage* mostra as chamadas
- [ ] RDS: *Publicly accessible = No*
- [ ] CloudWatch > `/mediary/prod`: retenção de 7 dias, sem senhas, tokens nem descrições de sintomas
- [ ] *Billing > Budgets*: orçamento ativo e e-mail confirmado

**Se a IA não aparecer ou falhar**, na sessão da EC2:
```bash
sudo grep -c "^ANTHROPIC_API_KEY=" /run/mediary/backend.env
```
```bash
sudo docker logs mediary-backend --tail 40 2>&1 | grep -i "ia\|erro"
```
`0` no primeiro = parâmetro faltando. `AuthenticationError (401)` = chave errada. Erro 400 sobre crédito =
sem saldo na Anthropic. Depois de corrigir com `salvar ANTHROPIC_API_KEY SecureString`, rode o `atualizar.sh` de novo.

## 5. Operação

- **Logs:** CloudWatch > *Log groups* > `/mediary/prod` (streams `backend` e `web`).
- **Atualizar:** GitHub Actions (3.11) ou, na sessão da EC2, `sudo /opt/mediary/deploy/aws/servidor/atualizar.sh main`.
- **Voltar uma versão:** `atualizar.sh <tag-ou-commit>`.
- **Trocar um segredo:** `salvar NOME SecureString` (3.6) e rodar o `atualizar.sh` de novo.
- **Pausar o custo:** parar a EC2 e o RDS reduz o custo, mas o RDS religa sozinho após 7 dias e o IP fixo continua sendo cobrado.
- **Apagar tudo:** antes, desligue *Deletion protection* no RDS. Ao apagar a stack, um snapshot final do banco é mantido (e cobrado) até você apagá-lo.

## 6. Rodar comandos direto no MySQL do RDS

O RDS não tem acesso público: só a EC2 do backend alcança a porta 3306. Você entra **pela EC2**,
sem abrir nenhuma porta, de um destes dois jeitos.

> O banco tem dados de saúde. Prefira o usuário do app, evite `SELECT *` em tabelas de sintomas
> sem necessidade e não ative a gravação de sessões do Session Manager (ela guardaria a saída das consultas).

### 6.1 Pelo navegador (Session Manager)
Console > **EC2** > `mediary-backend` > *Connect* > **Session Manager** > *Connect*:
```bash
sudo /opt/mediary/deploy/aws/servidor/mysql.sh
```
Isso abre o cliente `mysql>` como o usuário do app (`mediary_app`), no banco `mediary`, com TLS verificado.
As senhas vêm do Parameter Store e não aparecem na tela.

Outros usos:
```bash
sudo /opt/mediary/deploy/aws/servidor/mysql.sh app -e "SELECT COUNT(*) FROM Usuarios; SELECT COUNT(*) FROM Sintomas;"
```
```bash
sudo /opt/mediary/deploy/aws/servidor/mysql.sh app < /opt/mediary/backend/schema.sql
```
```bash
sudo /opt/mediary/deploy/aws/servidor/mysql.sh admin
```
O `admin` é o usuário mestre do RDS: use só para administração (usuários, `GRANT`).

### 6.2 Do seu computador (MySQL Workbench, DBeaver etc.), por túnel
Pré-requisitos no seu computador: [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html),
o [plugin do Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)
e credenciais do `mediary-admin` configuradas (`aws configure sso` ou chaves de acesso).

1. Abra o túnel (deixe o terminal aberto). Troque `ID_DA_INSTANCIA` e `ENDERECO_DO_BANCO` pelos *Outputs* da stack:
   ```bash
   aws ssm start-session --region sa-east-1 --target ID_DA_INSTANCIA --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters host="ENDERECO_DO_BANCO",portNumber="3306",localPortNumber="13306"
   ```
2. No Workbench: *Hostname* `127.0.0.1`, *Port* `13306`, *Username* `mediary_app` (senha: valor de
   `/mediary/prod/DATABASE_PASSWORD` no Parameter Store). Na aba *SSL*: *Use SSL* = **Require and Verify CA**
   e *SSL CA File* = o arquivo [global-bundle.pem](https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem)
   baixado. (Não use "Verify Identity": pelo túnel o nome do host é `127.0.0.1`, que não está no certificado.)
3. Feche o terminal do passo 1 quando terminar: o túnel é encerrado.

Os dados não passam pela internet aberta: o túnel é criptografado até a EC2, e de lá até o RDS a conexão é TLS.

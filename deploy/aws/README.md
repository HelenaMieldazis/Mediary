# Deploy do Mediary na AWS

Guia para publicar o backend (Flask + MySQL) na AWS. O frontend continua na Vercel.
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

### Opções comparadas

| | **A) EC2 + RDS (recomendada)** | B) Só EC2, MySQL em contêiner |
|---|---|---|
| Banco | RDS MySQL 8.4 db.t4g.micro, criptografado, sem IP público, TLS obrigatório, backups automáticos | MySQL no mesmo servidor; backup e atualização por sua conta |
| Servidor | EC2 t4g.micro: Docker com gunicorn + Caddy (HTTPS automático) | EC2 t4g.small (2 GB, para caber o MySQL) |
| Custo após os créditos (sa-east-1, estimado) | **≈ US$ 45/mês** (≈ R$ 250) | ≈ US$ 26/mês |
| Quanto duram US$ 200 de créditos | ≈ 4 meses | ≈ 7 meses |
| Risco | Baixo: backups e patches gerenciados pela AWS | Perder dados se o disco/instância falhar sem backup |

Recomendo a **A**: atende exatamente aos requisitos (banco gerenciado e isolado) com o mínimo de operação.
A **B** é o caminho para cortar custo depois, se você topar cuidar dos backups.
Em `us-east-1` os preços são ~40% menores, mas `sa-east-1` (São Paulo) tem menor latência e mantém os dados no Brasil.

Frontend: **continua na Vercel** (gratuito, HTTPS pronto). S3 + CloudFront também funcionaria, mas
daria mais trabalho sem ganho real.

```
Navegador ──HTTPS──> Vercel (frontend React)
    │
    └──HTTPS──> api.seudominio ──> EC2 [Caddy :443 ──> backend gunicorn :5000]
                                          │  TLS (porta 3306, só o SG do backend)
                                          └──> RDS MySQL (sem IP público)
       Segredos: SSM Parameter Store (/mediary/prod/*)   Logs: CloudWatch /mediary/prod (7 dias)
```

### Custo estimado (sa-east-1, sob demanda, depois dos créditos)

| Recurso | US$/mês (aprox.) |
|---|---|
| EC2 t4g.micro (≈ US$ 0,0134/h) | 9,80 |
| Disco da EC2 16 GB gp3 | 2–3 |
| IPv4 público fixo (Elastic IP) | 3,65 |
| RDS db.t4g.micro MySQL (≈ US$ 0,034/h) | 24,80 |
| Armazenamento RDS 20 GB gp3 + backup | 4–5 |
| CloudWatch Logs (poucos MB, retenção 7 dias), Parameter Store | ≈ 0 |
| **Total** | **≈ 45** |

Além disso: o domínio (se você ainda não tiver um; ≈ R$ 40/ano em .com.br) e a API da Anthropic (cobrada à parte pelo uso).

### Arquivos

| Arquivo | Para quê |
|---|---|
| `orcamento.yml` | Orçamento mensal com alertas por e-mail (crie **primeiro**) |
| `cloudformation.yml` | Security groups, RDS, EC2 com IP fixo, papel IAM mínimo, grupo de logs, papel de deploy do GitHub |
| `docker-compose.prod.yml`, `Caddyfile` | Backend + proxy HTTPS na EC2 |
| `servidor/atualizar.sh` | Na EC2: baixa o código, lê os segredos do Parameter Store, faz build e sobe |
| `servidor/criar_usuario_app.sh` | Na EC2: cria o usuário do banco do app (só acesso ao banco `mediary`) |
| `servidor/mysql.sh` | Na EC2: abre o cliente MySQL no RDS com TLS (seção 6) |
| `../../.github/workflows/deploy-aws.yml` | Deploy manual pelo GitHub Actions (OIDC, sem chaves guardadas) |

---

## 3. Passo a passo (o que depende de você)

Use o **AWS CloudShell** (ícone `>_` no topo do console) para os comandos: ele já vem
autenticado, roda dentro da AWS e é gratuito, então você não precisa criar chaves de acesso.
Antes de cada comando, confira se a região no topo do console é **São Paulo (sa-east-1)**.

### 3.1 Criar a conta e proteger o root
1. Crie a conta em https://aws.amazon.com/ e escolha o **Paid plan** (veja a seção 1).
2. Ative **MFA no usuário root**: menu da conta > *Security credentials* > *Assign MFA device*.
3. Não crie chaves de acesso para o root e use o root só para tarefas de cobrança da conta.

### 3.2 Usuário IAM de administração (não root)
1. Console > **IAM** > *Users* > *Create user*: `mediary-admin`, com acesso ao console.
2. Permissões: *Attach policies directly* > `AdministratorAccess`.
3. Entre com esse usuário e ative MFA nele (*Security credentials* > *Assign MFA device*).
4. A partir daqui, use sempre o `mediary-admin`.
5. Em *Billing and Cost Management* > *Billing preferences*, ative os **alertas do Free Tier** (*Receive AWS Free Tier alerts*). Para isso, ative antes, com o root, o *IAM user access to billing information* (*Account* > *IAM user and role access to Billing information*).

### 3.3 Orçamento com alertas (ANTES de qualquer recurso)
Console > **CloudFormation** > *Create stack* > *Upload a template file* > `deploy/aws/orcamento.yml`.
Nome: `mediary-orcamento`. Parâmetros: seu e-mail e o limite (ex.: 10 USD). Depois confirme o e-mail
de assinatura que a AWS enviar. Os alertas contam o consumo **sem descontar créditos**, então você
fica sabendo do gasto real desde o primeiro dia.

### 3.4 Domínio da API (HTTPS)
O microfone do navegador exige HTTPS, e o frontend (HTTPS na Vercel) só pode chamar uma API também em HTTPS.
- **Recomendado:** um subdomínio seu, ex.: `api.seudominio.com.br`. Depois do passo 3.6 você cria
  um registro **A** apontando para o `IpPublico` da stack (no Registro.br, na Vercel ou no seu DNS).
- **Sem domínio (provisório):** use `IP-COM-TRACOS.sslip.io` (ex.: IP `54.1.2.3` → `54-1-2-3.sslip.io`).
  É um serviço de DNS de terceiros, gratuito e sem garantia. Serve para testar, mas troque por um domínio seu.

O Caddy emite e renova o certificado (Let's Encrypt) sozinho na primeira requisição.

### 3.5 Segredos no Parameter Store
No CloudShell, crie cada parâmetro. Os comandos pedem o valor sem mostrar na tela, e assim nada fica no histórico.
Gere senhas com `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` (sem aspas nem barras).

```bash
salvar() { read -rsp "Valor de $1: " V; echo; aws ssm put-parameter --name "/mediary/prod/$1" --type "$2" --value "$V" --overwrite >/dev/null && echo "ok $1"; unset V; }
```
```bash
salvar db-senha-admin SecureString      # senha mestre do RDS (gerada)
```
```bash
salvar DATABASE_PASSWORD SecureString   # senha do usuário mediary_app (outra, gerada)
```
```bash
salvar SECRET_KEY SecureString          # nova! não reaproveite a antiga
```
```bash
salvar ANTHROPIC_API_KEY SecureString   # chave NOVA da Anthropic (revogue a antiga)
```
```bash
salvar FRONTEND_URL String              # ex.: https://mediary.vercel.app (sem barra no fim)
```
```bash
salvar API_DOMAIN String                # ex.: api.seudominio.com.br
```
Opcionais (só se quiser mudar os padrões): `IA_MODELO_EXTRACAO`, `IA_MODELO_RESUMO`,
`IA_LIMITE_DIARIO_INTERPRETAR`, `IA_LIMITE_DIARIO_RESUMO` (tipo String).
O `DATABASE_URL` vem no passo 3.6, depois que o banco existir.

### 3.6 Criar a infraestrutura (gera custo / consome créditos)
1. Console > **VPC** > *Your VPCs*: anote a VPC com *Default VPC = Yes*. Em *Subnets*, anote **duas**
   subnets dessa VPC em zonas diferentes (ex.: `sa-east-1a` e `sa-east-1b`).
2. Console > **CloudFormation** > *Create stack* > `deploy/aws/cloudformation.yml`. Nome: `mediary`.
   Preencha VPC e subnets e mantenha o resto padrão. Marque a confirmação de criação de recursos IAM.
   Se a conta já tiver o provedor OIDC do GitHub, use `CriarProvedorOidcGitHub=false`.
3. Aguarde de 10 a 15 minutos (o RDS é o mais lento). Na aba **Outputs**, anote `IpPublico`, `InstanceId`,
   `EnderecoBanco` e `PapelDeployGitHubArn`.
4. Crie o parâmetro que faltava:
   ```bash
   aws ssm put-parameter --name /mediary/prod/DATABASE_URL --type String --overwrite --value "mysql://mediary_app@ENDERECO_DO_BANCO:3306/mediary"
   ```
5. Aponte o DNS do `API_DOMAIN` para o `IpPublico` (registro A).

### 3.7 Primeiro deploy
Console > **EC2** > selecione `mediary-backend` > *Connect* > **Session Manager** > *Connect*. Não há SSH aberto.
```bash
sudo /opt/mediary/deploy/aws/servidor/criar_usuario_app.sh
```
```bash
sudo /opt/mediary/deploy/aws/servidor/atualizar.sh main
```
O script termina com `OK: backend respondendo`. Teste de fora: `https://API_DOMAIN/api/health`.

### 3.8 Migrar os dados do Supabase (controlado)
Ainda na sessão da EC2. **Nada é apagado no Supabase.** Faça primeiro um backup no painel do Supabase.
```bash
sudo docker exec -it mediary-backend sh
```
Dentro do contêiner:
```bash
pip install --user -q psycopg2-binary
```
```bash
read -rsp "URL do Postgres (Supabase): " PG_DATABASE_URL; export PG_DATABASE_URL; echo
```
```bash
python scripts/migrar_postgres_para_mysql.py contar
```
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
O destino já vem do `DATABASE_URL`/`DATABASE_PASSWORD` do contêiner. O `importar` só roda em
tabelas vazias e confere as contagens antes de gravar.

**Atenção:** o backend cria as tabelas ao subir. Se alguém se cadastrar no app novo antes da migração,
o `importar` recusa (o destino já tem dados). Migre antes de divulgar a nova URL.

### 3.9 Frontend na Vercel
Vercel > projeto > *Settings* > *Environment Variables*: `VITE_API_URL = https://API_DOMAIN`.
Depois, *Deployments* > *Redeploy*. Confira que o `FRONTEND_URL` do passo 3.5 é exatamente a URL da Vercel.

### 3.10 Deploy pelo GitHub Actions (opcional)
GitHub > *Settings* > *Environments* > *New environment* `producao`:
- marque *Required reviewers* (você), para nenhum deploy sair sem aprovação;
- *Environment variables*: `AWS_DEPLOY_ROLE_ARN` (output `PapelDeployGitHubArn`), `AWS_REGION` (`sa-east-1`),
  `AWS_INSTANCE_ID` (output `InstanceId`).

Para publicar: *Actions* > **Deploy AWS** > *Run workflow*. Não existe nenhuma chave da AWS no GitHub: o acesso é por OIDC
e o papel só pode mandar a EC2 rodar o `atualizar.sh`.

---

## 4. Checklist de validação pós-deploy

- [ ] `https://API_DOMAIN/api/health` → `{"status":"ok"}`, com cadeado válido no navegador
- [ ] `http://API_DOMAIN/api/health` redireciona para HTTPS
- [ ] Cadastro de usuário novo pelo app da Vercel
- [ ] Login e logout; login com e-mail em maiúsculas também funciona
- [ ] Registrar, editar (a hora exibida na edição é a mesma registrada) e excluir um sintoma; o calendário marca o dia
- [ ] Usuários migrados conseguem entrar com a senha antiga e veem os próprios registros (`contar` bate com o Supabase)
- [ ] Relatório em PDF (sem IA) baixa e abre, com acentos corretos
- [ ] IA: o consentimento aparece no primeiro uso; registro por **texto** gera o cartão Salvar/Corrigir
- [ ] IA: registro por **voz** no celular (Chrome/Android ou Safari/iOS), em HTTPS, com permissão de microfone
- [ ] Resumo para a consulta: gera o texto, permite editar e baixar o PDF
- [ ] Revogar o consentimento em Configurações bloqueia a IA
- [ ] CORS: abrir `https://API_DOMAIN/api/me` a partir de outro site não funciona (só a URL da Vercel)
- [ ] RDS: em *RDS > mediary-mysql > Connectivity*, *Publicly accessible = No*
- [ ] CloudWatch > *Log groups* > `/mediary/prod`: retenção de 7 dias, sem senhas, tokens nem descrições de sintomas
- [ ] *Billing > Budgets*: orçamento `mediary-mensal` ativo e e-mail confirmado
- [ ] `sudo /opt/mediary/deploy/aws/servidor/mysql.sh app -e "SELECT COUNT(*) FROM Usuarios"` mostra o mesmo total do Supabase

## 5. Operação

- **Logs:** CloudWatch > *Log groups* > `/mediary/prod` (streams `backend` e `caddy`).
- **Atualizar:** GitHub Actions (3.10) ou, na sessão da EC2, `sudo /opt/mediary/deploy/aws/servidor/atualizar.sh main`.
- **Voltar uma versão:** `atualizar.sh <tag-ou-commit>`.
- **Trocar um segredo:** `salvar NOME SecureString` (3.5) e rodar o `atualizar.sh` de novo.
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

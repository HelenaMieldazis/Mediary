# Mediary

### Seu diário de sintomas, sempre com você

---

## Sobre o projeto

**Mediary** é uma aplicação web (e PWA instalável) para registrar sintomas de saúde do dia a dia — dor, náusea, fadiga, e outros — com início, fim, descrição e visualização em um calendário mensal. Pensado para quem precisa acompanhar padrões de saúde ao longo do tempo, seja para uso pessoal ou para levar ao médico.

## Funcionalidades

- **Autenticação segura** via JWT (cadastro, login, logout)
- **Calendário interativo** com indicação de dias com sintomas registrados
- **Registro de sintomas** com tipo, subtipo, descrição, início e fim
- **Edição e exclusão** de registros existentes
- **Gerenciamento de perfil** (nome, e-mail, senha)
- **PWA instalável** — funciona offline e pode ser adicionado à tela inicial
- **API REST** própria, separada do frontend

## Stack Tecnológica

| Camada | Tecnologias |
|---|---|
| **Frontend** | React 19 + TypeScript, Vite, Tailwind CSS, Zustand, Axios |
| **Backend** | Flask (Python), Gunicorn, PyJWT, PyMySQL, ReportLab |
| **Banco de Dados** | MySQL 8 (local: Docker; produção: AWS RDS) |
| **IA** | API da Anthropic (Claude), só no backend |
| **PWA** | Vite PWA Plugin (Workbox) |
| **Infraestrutura** | Docker, Caddy (HTTPS), AWS EC2 + RDS, GitHub Actions |

## Estrutura do projeto

```
Mediary/
├── backend/                     # API Flask
│   ├── app.py                   # Rotas, banco (MySQL) e regras
│   ├── ia_service.py            # IA: cadastro por texto/voz e resumo para a consulta
│   ├── relatorio_pdf.py         # Relatório em PDF
│   ├── schema.sql               # Esquema MySQL (referência; o app cria as tabelas)
│   ├── scripts/migrar_postgres_para_mysql.py
│   └── tests/                   # Testes (unitários, integração MySQL, IA, migração)
├── frontend/                    # SPA React
├── deploy/aws/                  # Infra da AWS (CloudFormation, compose de produção, guia)
├── .github/workflows/           # Testes automáticos e deploy manual
└── docker-compose.yml           # Desenvolvimento local (MySQL + backend + frontend)
```

## Rodando localmente (Docker + MySQL)

Pré-requisito: [Docker](https://www.docker.com/) com Docker Compose.

```bash
git clone https://github.com/HelenaMieldazis/Mediary.git
```
```bash
cd Mediary
```
```bash
cp .env.example .env
```
```bash
cp backend/.env.example backend/.env
```
Edite os dois arquivos `.env` (senhas do MySQL local, `SECRET_KEY` e, se quiser a IA, `ANTHROPIC_API_KEY`).
Eles estão no `.gitignore` e **nunca** vão para o Git.
```bash
docker compose up --build
```
- Frontend: http://localhost
- Backend: http://localhost:5000/api/health
- MySQL: `127.0.0.1:3306` (dados no volume `mediary-mysql-data`, que sobrevive a `docker compose down`)

O backend cria as tabelas sozinho ao subir (`init_db`).

## Variáveis de ambiente

**`.env` da raiz** (só o `docker-compose.yml` local): `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`.

**Backend** (`backend/.env` local; em produção, Parameter Store `/mediary/prod/*`):

| Variável | Para quê |
|---|---|
| `DATABASE_URL` | `mysql://usuario[:senha]@host:3306/banco`. Senha com caracteres especiais: codifique na URL ou use `DATABASE_PASSWORD` |
| `DATABASE_PASSWORD` | Senha do banco (opcional; tem prioridade sobre a da URL) |
| `DATABASE_SSL_CA` | Certificado da CA para exigir TLS com o banco (opcional; usado no RDS) |
| `SECRET_KEY` | Assinatura dos tokens JWT |
| `FRONTEND_URL` | URL(s) do frontend permitidas no CORS, separadas por vírgula |
| `AMBIENTE` | `producao` exige `SECRET_KEY` e tira `localhost` do CORS |
| `ANTHROPIC_API_KEY` | Chave da API da Anthropic (sem ela, a IA fica oculta) |
| `IA_MODELO_EXTRACAO`, `IA_MODELO_RESUMO` | Modelos da IA (padrões: `claude-haiku-5-5`, `claude-sonnet-5-5`) |
| `IA_LIMITE_DIARIO_INTERPRETAR`, `IA_LIMITE_DIARIO_RESUMO` | Cota diária por usuário (padrões: 40 e 10) |
| `EMAIL_REMETENTE` | Remetente do e-mail de "Esqueci minha senha" (Amazon SES). Sem ela, em desenvolvimento o link aparece no log |
| `APP_URL` | Endereço público do site, usado no link do e-mail |
| `SES_REGIAO` | Região do SES (padrão: `AWS_REGION` ou `sa-east-1`) |

**Frontend** (build): `VITE_API_URL`. Só no desenvolvimento local (`http://localhost:5000`); em produção fica vazio e o site chama `/api` no mesmo domínio.

## Testes

Dentro de `backend/`:
```bash
pip install -r requirements-migracao.txt pypdf
```
Só os testes que não precisam de banco (lógica da IA, leitura da URL do banco):
```bash
python -m unittest discover -s tests -t . -v
```
Com um MySQL descartável no Docker (os testes **apagam** as tabelas desse banco, cujo nome precisa conter "teste"):
```bash
docker run -d --name mediary-mysql-teste -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=mediary_teste -p 127.0.0.1:3307:3306 mysql:8.4
```
```bash
MEDIARY_TEST_DATABASE_URL="mysql://root:root@127.0.0.1:3307/mediary_teste" python -m unittest discover -s tests -t . -v
```
Isso cobre cadastro, login, CRUD de sintomas, calendário, PDF, isolamento entre usuários, consentimento e
cota da IA (inclusive com requisições simultâneas). As rotas de IA são testadas contra um **servidor falso da
API da Anthropic** (`tests/fake_anthropic.py`), sem gastar créditos. O teste da migração precisa também de
`MEDIARY_TEST_PG_URL` e `MEDIARY_TEST_MIGRACAO_MYSQL_URL` (veja `tests/test_migracao.py`).
O GitHub Actions (`.github/workflows/testes.yml`) roda tudo isso a cada pull request.

Teste manual com a IA de verdade (gasta créditos): `python testar_ia.py`.

## Migração dos dados do PostgreSQL (Supabase) para o MySQL

`backend/scripts/migrar_postgres_para_mysql.py`, com os comandos `contar`, `exportar` e `importar`
(este último com `--simular`). Ele nunca escreve no Postgres. Passo a passo em
[`deploy/aws/README.md`](./deploy/aws/README.md#38-migrar-os-dados-do-supabase-controlado).

## Deploy em produção (AWS)

Site e API na mesma EC2 (Docker + Caddy com HTTPS, num único domínio com DNS no Registro.br) e MySQL no RDS, sem acesso público.
Guia completo, custos e checklist: **[`deploy/aws/README.md`](./deploy/aws/README.md)**.

## Instalando como App (PWA)

Acesse a URL do frontend em produção pelo navegador do celular ou computador:

- **Android (Chrome)**: toque no menu → "Instalar app" ou "Adicionar à tela inicial"
- **iOS (Safari)**: toque em compartilhar → "Adicionar à Tela de Início"
- **Desktop (Chrome/Edge)**: clique no ícone de instalação na barra de endereço

## Autenticação

A API utiliza **JWT (JSON Web Token)** em vez de cookies de sessão, garantindo compatibilidade total com navegadores mobile e cenários cross-domain. O token é retornado no login e enviado em cada requisição via header:

```
Authorization: Bearer <token>
```
# Raízes do Nordeste — Back-end Python

Atividade prática de Projeto Back-End - Tecnologia em Análise e Desenvolvimento de Sistemas

Centro Universitário Internacional UNINTER - 2026

Aluno: Bruno Henrique Nonato Gonçalves (RU: 4919651)

> API RESTful para a rede de restaurantes **"Raízes do Nordeste"**, implementada em **Python + Flask**
> seguindo a mesma arquitetura em camadas, os mesmos endpoints, perfis e regras do modelo de
> referência em Java/Spring Boot.

---

## Sobre o Projeto

- **Gestão multicanal de pedidos** (APP, TOTEM, BALCAO, PICKUP, WEB)
- **Controle de estoque por unidade** com entradas/saídas auditáveis, validação transacional e devolução conforme o estágio do pedido
- **Pagamento e estorno simulados** (gateway mock), com múltiplas tentativas e tolerância a indisponibilidade técnica
- **Programa de fidelidade** com acúmulo e resgate de pontos, condicionado a consentimento
- **Campanhas e cupons** com desativação lógica e proteção contra períodos sobrepostos
- **Gestão de unidades** (CRUD completo)
- **Autenticação JWT** com controle de acesso por perfil (RBAC)
- **Auditoria e rastreabilidade** com logs estruturados
- **Documentos legais versionados** com aceite contratual rastreável e consentimento LGPD separado
- **CORS configurável** e documentação **OpenAPI/Swagger**

### Rastreabilidade de requisições

Toda requisição recebe um `X-Request-ID`, devolvido no header da resposta, incluído nas respostas de erro
(`requestId`) e nos logs. Um identificador válido enviado pelo cliente é propagado; ausente ou inválido, é
substituído por UUID. E-mails são pseudonimizados antes de irem para o log.

---

## Tecnologias

| Tecnologia | Finalidade |
|------------|-----------|
| **Python** (testado com 3.13) | Linguagem principal |
| **Flask 3** | Framework web |
| **SQLite** | Banco de dados (dev e prod; ver *Limitações*) |
| **Migrations próprias** (`V1__...sql`, estilo Flyway) | Versionamento do schema |
| **PyJWT** | Tokens de autenticação |
| **PBKDF2-HMAC-SHA256** (stdlib) | Hash de senhas com salt por senha |
| **PyYAML** | Contrato OpenAPI em YAML |
| **pytest** | Testes automatizados |

---

## Requisitos

- **Python 3.13** (versão em que a suíte foi executada)
- **Git**
- **Insomnia** ou **Postman** (opcional)

```bash
python --version
git --version
```

---

## Como Rodar

```bash
# 1. Ambiente virtual e dependências
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. (opcional) variáveis de ambiente
cp .env.example .env
set -a; source .env; set +a

# 3. Executar em desenvolvimento
python run.py
```

A aplicação sobe em **http://localhost:8080/api**. O perfil `dev` já possui valores locais seguros e não
exige `.env`. O `.env` **nunca** deve ser commitado, e a aplicação não o lê sozinha: exporte as variáveis
na sessão, como acima.

Comandos de banco (via Flask CLI):

```bash
flask --app run db-migrar     # aplica migrations pendentes (também ocorre na inicialização)
flask --app run db-limpar     # apaga todo o banco (bloqueado no perfil prod)
```

---

## Perfis de Execução (`APP_PROFILE`)

### `dev` (padrão)
- SQLite em `data/raizes-dev.db`, com dados de demonstração (seed)
- Swagger/OpenAPI dinâmico ativo
- Pagamento forçado como `APROVADO` (determinístico) e header `X-Forcar-Status-Pagamento` habilitado
- CORS permissivo para `localhost` (3000, 4200, 5173)

### `prod`
- `JWT_SECRET` (mínimo 32 caracteres) e `DB_PATH` **obrigatórios**; sem eles a aplicação não inicia
- Segredo de desenvolvimento rejeitado
- Swagger dinâmico desativado e header de simulação de pagamento **ignorado**
- Seed desligado por padrão; `db-limpar` bloqueado
- CORS restrito às origens de `CORS_ALLOWED_ORIGINS`
- Pagamento aleatório por padrão (80% de aprovação) até que um gateway real seja integrado

```bash
export APP_PROFILE=prod
export JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export DB_PATH="/var/lib/raizes/raizes.db"
export CORS_ALLOWED_ORIGINS="https://app.exemplo.com.br"
python run.py
```

### `test`
Perfil usado pela suíte automatizada, com banco temporário isolado.

---

## Variáveis de Ambiente

Veja o `.env.example` para a lista completa. Principais:

| Variável | Descrição | Padrão |
|---|---|---|
| `APP_PROFILE` | `dev`, `prod` ou `test` | `dev` |
| `JWT_SECRET` | Segredo do JWT (≥ 32 caracteres) | segredo local (só dev) |
| `JWT_EXPIRATION_MINUTES` | Validade do token | `60` |
| `DB_PATH` | Arquivo SQLite | `data/raizes-dev.db` |
| `SEED_ENABLED` | Popular dados de demonstração | `true` em dev |
| `CORS_ALLOWED_ORIGINS` | Origens permitidas | localhost em dev |
| `PAGAMENTO_FORCAR_STATUS` | `APROVADO`, `RECUSADO`, `INDISPONIVEL` ou vazio (aleatório) | `APROVADO` em dev |
| `PAGAMENTO_FORCAR_STATUS_ESTORNO` | `CONFIRMADO`, `INDISPONIVEL` ou vazio | `CONFIRMADO` em dev |
| `TERMOS_USO_VERSAO` / `AVISO_PRIVACIDADE_VERSAO` / `TERMO_FIDELIDADE_VERSAO` | Versões vigentes dos documentos | `1.0` |
| `SERVER_PORT` | Porta | `8080` |

---

## Migrations e Seed

As migrations ficam em `src/raizesdonordeste/resources/db/migration/` e são aplicadas em ordem na
inicialização (cada versão é registrada e não roda duas vezes).

Com o banco vazio e `SEED_ENABLED=true`, são criados: 2 unidades (Centro e Zona Sul), 5 usuários, 4 produtos
(Tapioca, Cuscuz, Suco de Cajá, Carne de Sol), estoque nas duas unidades, a campanha **Terça da Tapioca** e
os cupons **NORDESTE10** e **PROMO5**.

| Perfil | E-mail | Senha |
|--------|--------|-------|
| Cliente | cliente@raizes.com | cliente123 |
| Cozinha | cozinha@raizes.com | cozinha123 |
| Atendente | atendente@raizes.com | atendente123 |
| Gerente | gerente@raizes.com | gerente123 |
| Admin | admin@raizes.com | admin123 |

Credenciais **somente para desenvolvimento**.

---

## Endpoints da API

**Base URL:** `http://localhost:8080/api` (52 rotas, 49 operações no contrato OpenAPI)

### Autenticação
| Método | Endpoint | Descrição | Auth |
|---|---|---|---|
| `POST` | `/auth/login` | Autenticar e obter token JWT | Público |

### Unidades
| Método | Endpoint | Descrição | Auth |
|---|---|---|---|
| `POST` | `/unidades` | Criar unidade | ADMIN |
| `GET` | `/unidades?page=0&limit=10` | Listar unidades ativas (paginado) | Autenticado |
| `GET` | `/unidades/{id}` | Buscar por ID | Autenticado |
| `PUT` | `/unidades/{id}` | Atualizar | ADMIN |
| `DELETE` | `/unidades/{id}` | Desativar (exclusão lógica) | ADMIN |

### Pedidos
| Método | Endpoint | Descrição | Auth |
|---|---|---|---|
| `POST` | `/pedidos` | Criar pedido; aceita `Idempotency-Key` | CLIENTE, ATENDENTE |
| `GET` | `/pedidos?canalPedido=APP&status=AGUARDANDO_PAGAMENTO&unidadeId=1&page=0&limit=10` | Listar com filtros combináveis | Autenticado |
| `GET` | `/pedidos/{id}` | Buscar por ID | Autenticado |
| `PATCH` | `/pedidos/{id}/status` | Atualizar status (cozinha → pronto → entregue) | COZINHA, ATENDENTE, GERENTE, ADMIN |
| `POST` | `/pedidos/{id}/cancelamento` | Cancelar e executar compensações | CLIENTE proprietário, ATENDENTE da unidade, ADMIN |

Fluxo de status: `AGUARDANDO_PAGAMENTO → RECEBIDO → EM_PREPARO → PRONTO → ENTREGUE`, com `CANCELADO`
pelo endpoint de cancelamento.

O header opcional `Idempotency-Key` (8 a 100 caracteres: alfanuméricos ou `.` `_` `:` `-`) é escopado ao
usuário. Repetir a mesma chave com o mesmo conteúdo devolve o pedido original (`200` e header
`Idempotency-Replayed: true`) sem nova reserva de estoque; com conteúdo diferente retorna
`409 CHAVE_IDEMPOTENCIA_REUTILIZADA`.

### Pagamento (mock)
| Método | Endpoint | Descrição | Auth |
|---|---|---|---|
| `POST` | `/pedidos/{pedidoId}/pagamento` | Processar pagamento | CLIENTE proprietário, ATENDENTE da unidade |
| `GET` | `/pedidos/{pedidoId}/pagamento/tentativas` | Histórico de tentativas | Usuário com acesso ao pedido |

Após pagamento recusado, o cliente pode tentar de novo com outro método. Se o gateway estiver
tecnicamente indisponível, a API retorna `503 GATEWAY_PAGAMENTO_INDISPONIVEL`, mantém o pedido em
`AGUARDANDO_PAGAMENTO` e não consome tentativa.

O cancelamento de pedido pago solicita **estorno** ao mesmo gateway simulado, e o pedido só é cancelado
após a confirmação. Cancelamentos concorrentes do mesmo pedido são serializados por transação de escrita
exclusiva (`BEGIN IMMEDIATE`), impedindo dois estornos. Com o gateway indisponível, a API retorna `503`,
preserva o pagamento e mantém o pedido no estado anterior.

### Produtos
| Método | Endpoint | Descrição | Auth |
|---|---|---|---|
| `GET` | `/produtos?page=0&limit=10` | Listar produtos ativos | Público |
| `GET` | `/produtos/unidade/{unidadeId}` | **Cardápio/disponibilidade por unidade** | Autenticado |
| `GET` | `/produtos/{id}` | Buscar por ID | Público |
| `POST` / `PUT` / `DELETE` | `/produtos[/{id}]` | Criar / atualizar / desativar | ADMIN, GERENTE |

### Estoque
| Método | Endpoint | Descrição | Auth |
|---|---|---|---|
| `POST` | `/estoque` | Criar registro | ADMIN, GERENTE da unidade |
| `GET` | `/estoque/unidade/{unidadeId}` | Listar por unidade | ADMIN, GERENTE da unidade |
| `GET` / `PUT` / `DELETE` | `/estoque/{id}` | Consultar / atualizar quantidade / remover | ADMIN, GERENTE da unidade |
| `POST` | `/estoque/{id}/movimentacoes` | Registrar entrada ou saída | ADMIN, GERENTE da unidade |
| `GET` | `/estoque/{id}/movimentacoes` | Histórico auditável | ADMIN, GERENTE da unidade |

Saídas manuais nunca tornam o saldo negativo, e cada movimentação guarda quantidade, motivo, saldo
anterior/posterior, data e responsável pseudonimizado. A venda baixa o estoque automaticamente; produtos sem
saldo ficam indisponíveis e o pedido é recusado (`409 ESTOQUE_INSUFICIENTE`). No cancelamento, o estoque volta
só se o pedido ainda está em `AGUARDANDO_PAGAMENTO` ou `RECEBIDO`; depois disso os itens são considerados
consumidos.

### Fidelidade
| Método | Endpoint | Descrição | Auth |
|---|---|---|---|
| `GET` | `/fidelidade/saldo` | Saldo de pontos | Autenticado |
| `GET` | `/fidelidade/consentimento` | Situação e versão do consentimento | Autenticado |
| `POST` | `/fidelidade/consentimento` | Consentir explicitamente | Autenticado |
| `DELETE` | `/fidelidade/consentimento` | Revogar | Autenticado |

Regras: **1 ponto a cada R$ 1,00 pago** (creditado na aprovação do pagamento), **1 ponto = R$ 0,05** no
resgate, limitado a **50% do valor do pedido** (após campanha e cupom).

Resgate e acúmulo exigem consentimento ativo para a versão vigente do termo. Concessões e revogações são
eventos imutáveis (finalidade, versão, data/hora, origem); nova versão do termo exige novo aceite.
Funcionários podem registrar pedidos para clientes, mas não consentem em nome deles. Se um cancelamento
exigir retirar pontos já gastos, o saldo fica **devedor** (`saldoDevedor`) e o cancelamento não é bloqueado.

### Campanhas e Cupons
| Método | Endpoint | Auth |
|---|---|---|
| `POST` / `GET` | `/campanhas` | ADMIN, GERENTE da unidade (no próprio escopo) |
| `GET` / `PUT` / `DELETE` | `/campanhas/{id}` | ADMIN, GERENTE da unidade |
| `POST` / `GET` | `/cupons` | ADMIN; GERENTE para cupom local |
| `GET` / `PUT` / `DELETE` | `/cupons/{id}` | ADMIN, GERENTE da unidade |

Campanhas aplicam desconto automático (por período, unidade, dia da semana e produto) e não podem ter
períodos sobrepostos no mesmo escopo. Cupons são informados no pedido. Ordem de aplicação: **campanha →
cupom → pontos**.

### Usuários
| Método | Endpoint | Descrição | Auth |
|---|---|---|---|
| `POST` | `/usuarios` | Registrar cliente com aceite dos termos vigentes | Público |
| `GET` | `/usuarios?page=0&limit=10` | Listar | ADMIN |
| `GET` | `/usuarios/{id}` | Buscar | ADMIN |
| `PUT` | `/usuarios/{id}` | Atualizar; mudar perfil só ADMIN | Próprio usuário, ADMIN |
| `DELETE` | `/usuarios/{id}` | Anonimizar (LGPD) | Próprio usuário, ADMIN |

Cadastro público cria sempre `CLIENTE`; perfis de equipe são atribuídos por um ADMIN.

### Documentos legais
| Método | Endpoint | Auth |
|---|---|---|
| `GET` | `/documentos-legais/termos-uso` | Público (versão, hash SHA-256 e conteúdo) |
| `GET` | `/documentos-legais/aviso-privacidade` | Público |
| `GET` / `PUT` | `/documentos-legais/termos-uso/aceite` | Autenticado |

O cadastro exige `aceiteTermosUso: true` com a versão e o hash vigentes. Quando a versão muda, operações
autenticadas retornam `409 TERMOS_USO_NAO_ACEITOS`, exceto as rotas de consulta e renovação do aceite. O
aceite é contratual (não revogável); o consentimento LGPD é separado e usado só para os pontos de fidelidade.

---

## Autenticação JWT

```bash
curl -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "cliente@raizes.com", "senha": "cliente123"}'
```

```json
{ "token": "eyJhbGciOiJIUzI1NiIs...", "tipo": "Bearer", "expiraEmSegundos": 3600 }
```

Use `Authorization: Bearer {token}` nas demais chamadas. Senhas são armazenadas com PBKDF2-HMAC-SHA256 e salt
aleatório por senha, e nunca são devolvidas pela API.

---

## Pagamento Determinístico (testes)

Header por requisição (somente fora de `prod`):

```bash
curl -X POST http://localhost:8080/api/pedidos/1/pagamento \
  -H "Authorization: Bearer {token}" -H "Content-Type: application/json" \
  -H "X-Forcar-Status-Pagamento: RECUSADO" \
  -d '{"formaPagamento": "PIX"}'
```

Ou via ambiente: `PAGAMENTO_FORCAR_STATUS` (pagamento) e `PAGAMENTO_FORCAR_STATUS_ESTORNO` (estorno).

| Valor | Efeito |
|---|---|
| `APROVADO` | Força aprovação |
| `RECUSADO` | Força recusa |
| `INDISPONIVEL` | Simula falha técnica: `503`, sem alterar o pedido nem consumir tentativa |
| (vazio) | Aleatório (80% de aprovação) |

---

## Documentação OpenAPI / Swagger

Em perfis diferentes de `prod`:

- **Swagger UI:** http://localhost:8080/api/swagger-ui.html
- **OpenAPI JSON:** http://localhost:8080/api/v3/api-docs
- **OpenAPI YAML:** http://localhost:8080/api/v3/api-docs.yaml

Cópias estáticas do contrato (49 operações), geradas por `python scripts/gerar_openapi.py`:
[`docs/openapi/openapi.json`](docs/openapi/openapi.json) e [`docs/openapi/openapi.yaml`](docs/openapi/openapi.yaml).

### Coleção Postman

[`postman/raizes_do_nordeste.postman_collection.json`](postman/raizes_do_nordeste.postman_collection.json)
reúne **40 chamadas encadeadas (T01 a T40)**, geradas por `python scripts/cenario_postman.py`. Execute no
perfil `dev`. A suíte reexecuta o mesmo cenário contra a API e confere se o JSON versionado está atualizado.

---

## Testes

```bash
python -m pytest -q
```

**Resultado na última execução: 126 testes passando.** A suíte cobre autenticação e usuários, catálogo e
estoque, pedidos e pagamento (incluindo idempotência, estorno e indisponibilidade do gateway), fidelidade e
consentimento, campanhas e cupons, concorrência de estoque, infraestrutura (CORS, perfis, migrations,
`X-Request-ID`) e o cenário Postman.

```bash
python -m pytest tests/test_pedidos_pagamento.py -q     # um módulo específico
```

---

## Estrutura do Projeto

```
projeto-back-end-uninter/
├── src/raizesdonordeste/
│   ├── config/        # Configuração por perfil, seed, CORS, OpenAPI e correlação de requisições
│   ├── controller/    # Contrato HTTP (blueprints Flask)
│   ├── dto/           # Validação de entrada e serialização de saída
│   ├── exception/     # ApiError e tratamento global
│   ├── gateway/       # Gateway de pagamento simulado
│   ├── model/         # Enumerações do domínio
│   ├── repository/    # Acesso a dados, migrations e transações
│   ├── security/      # JWT e hash de senhas
│   ├── service/       # Regras de negócio e autorização
│   ├── util/          # Tempo e pseudonimização para logs
│   └── resources/     # db/migration (SQL) e legal (termos e aviso de privacidade)
├── tests/             # Testes automatizados
├── scripts/           # Geração do OpenAPI e da coleção Postman
├── docs/openapi/      # Contrato estático JSON/YAML
├── postman/           # Coleção com 40 chamadas
├── .github/workflows/ # CI
├── .env.example
├── requirements.txt
├── pytest.ini
└── run.py             # Ponto de entrada
```

---

## Códigos de Status HTTP

| Código | Quando |
|---|---|
| `200` / `201` / `204` | Sucesso (com corpo / recurso criado / sem corpo) |
| `400` | Requisição malformada ou parâmetro inválido |
| `401` | Token ausente, expirado ou inválido |
| `403` | Sem permissão |
| `404` | Recurso inexistente |
| `409` | Violação de regra de negócio (estoque, idempotência, termos...) |
| `422` | Erro de validação de campos |
| `500` | Erro inesperado |
| `503` | Gateway de pagamento simulado indisponível |

Todas as falhas (inclusive autenticação e autorização) seguem o mesmo formato:

```json
{
  "error": "ESTOQUE_INSUFICIENTE",
  "message": "Não há quantidade suficiente para um ou mais itens.",
  "details": [ { "field": "itens[0].quantidade", "issue": "Disponível: 1" } ],
  "timestamp": "2026-11-22T12:00:00Z",
  "path": "/api/pedidos",
  "requestId": "a1b2c3d4-e5f6-7890-abcd-1234567890ab"
}
```

---

## Integração Contínua (CI)

O workflow [`ci.yml`](.github/workflows/ci.yml) roda a suíte (`pytest`) em push, pull request e acionamento
manual, e publica o relatório JUnit como artefato por 14 dias, inclusive quando os testes falham. O workflow
**não foi executado no GitHub**: confirme o resultado no histórico do Actions após o primeiro push.

---

## Limitações e diferenças em relação ao modelo Java

- **Banco:** usa SQLite nos dois perfis. O modelo Java usa H2 (dev) e PostgreSQL (prod); trocar para
  PostgreSQL exige adaptar `repository/database.py` (conexão, transações e paginação) e as migrations.
- **Pagamento:** é totalmente simulado. A integração com um provedor real substituiria
  `gateway/gateway_pagamento.py`, mantendo o contrato.
- **Gunicorn/HTTPS:** em produção, rode atrás de um servidor WSGI (ex.: gunicorn) e de proxy HTTPS; o
  `python run.py` usa o servidor de desenvolvimento do Flask.
- **Dados pessoais:** CPF e telefone são armazenados em texto; avalie criptografia em repouso antes de
  produção real.

# Raízes do Nordeste — Back-end Python

Atividade prática de Projeto Back-End - Tecnologia em Análise e Desenvolvimento de Sistemas

Centro Universitário Internacional UNINTER - 2026

Aluno: Bruno Henrique Nonato Gonçalves (RU: 4919651)

## Estrutura

```text
raizes_do_nordeste_python/
├── app/
│   ├── gateways/       # Integração simulada de pagamento
│   ├── routes/         # Controllers/endpoints REST
│   ├── schemas/        # DTOs e validações Pydantic
│   ├── security/       # JWT e hash de senha
│   ├── main.py         # Inicialização FastAPI
│   ├── database.py     # SQLite e tabelas
│   ├── config.py       # Configuração
│   └── middleware.py   # X-Request-ID
├── docs/               # Regras e fluxos
├── tests/              # Testes automatizados
├── .env.example
├── requirements.txt
└── README.md
```

## Instalação no Windows (PowerShell)

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Linux/macOS: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn app.main:app --reload`

- API: http://127.0.0.1:8000/api
- Swagger: http://127.0.0.1:8000/api/docs

## Administrador inicial

`admin@raizes.com` / `admin123` — altere antes de uso real.

## Principais rotas

- `POST /api/auth/usuarios` e `POST /api/auth/login`
- `GET /api/unidades`, `POST /api/unidades`
- `GET /api/produtos`, `GET /api/produtos?unidade_id=1`, `POST /api/produtos`
- `POST/GET /api/pedidos`, `PATCH /api/pedidos/{id}/status`
- `POST /api/estoque/{produto_id}/movimentacoes`
- `GET /api/fidelidade/saldo`, `POST /api/fidelidade/consentimento`, `POST /api/fidelidade/resgate`
- `GET/POST /api/campanhas`
- `POST /api/pedidos/{id}/pagamento`, `GET /api/pedidos/{id}/pagamento/tentativas`

Use `Authorization: Bearer <token>` nas rotas protegidas. Perfis previstos: CLIENTE, COZINHA,
ATENDENTE, GERENTE e ADMIN. O cadastro público cria apenas CLIENTE.

## Observações

O gateway é estritamente mock: não movimenta dinheiro nem coleta dados de cartão. Esta é uma
implementação didática organizada a partir da estrutura descrita no README de referência; não é
uma cópia funcional integral dos 49 endpoints e 255 testes citados naquele README Java.
Antes de produção, implementar migrations Alembic, PostgreSQL, controle concorrente robusto,
idempotência persistida, auditoria LGPD versionada, autorização por unidade e suíte ampliada.

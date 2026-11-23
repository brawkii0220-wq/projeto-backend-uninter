-- Schema completo - Raízes do Nordeste. Datas em UTC (AAAA-MM-DDTHH:MM:SSZ); valores em centavos.

CREATE TABLE unidades (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nome      TEXT NOT NULL,
    cidade    TEXT NOT NULL,
    ativa     INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL
);

CREATE TABLE usuarios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    senha_hash  TEXT NOT NULL,
    perfil      TEXT NOT NULL CHECK (perfil IN ('CLIENTE','COZINHA','ATENDENTE','GERENTE','ADMIN')),
    unidade_id  INTEGER REFERENCES unidades(id),
    telefone    TEXT,
    cpf         TEXT,
    pontos      INTEGER NOT NULL DEFAULT 0,          -- pode ficar negativo (saldo devedor)
    ativo       INTEGER NOT NULL DEFAULT 1,
    anonimizado INTEGER NOT NULL DEFAULT 0,
    criado_em   TEXT NOT NULL
);

-- Aceite contratual dos termos de uso (um evento por aceite de versão/hash).
CREATE TABLE aceites_documento (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
    documento   TEXT NOT NULL,
    versao      TEXT NOT NULL,
    hash_sha256 TEXT NOT NULL,
    origem      TEXT NOT NULL,
    criado_em   TEXT NOT NULL
);

-- Consentimento LGPD da fidelidade: eventos imutáveis de concessão/revogação.
CREATE TABLE consentimentos_fidelidade (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    tipo       TEXT NOT NULL CHECK (tipo IN ('CONCESSAO','REVOGACAO')),
    finalidade TEXT NOT NULL,
    versao     TEXT NOT NULL,
    origem     TEXT NOT NULL,
    criado_em  TEXT NOT NULL
);

CREATE TABLE produtos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    nome           TEXT NOT NULL,
    descricao      TEXT NOT NULL DEFAULT '',
    categoria      TEXT NOT NULL DEFAULT 'geral',
    preco_centavos INTEGER NOT NULL CHECK (preco_centavos >= 0),
    ativo          INTEGER NOT NULL DEFAULT 1,
    criado_em      TEXT NOT NULL
);

CREATE TABLE estoques (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    unidade_id INTEGER NOT NULL REFERENCES unidades(id),
    produto_id INTEGER NOT NULL REFERENCES produtos(id),
    quantidade INTEGER NOT NULL CHECK (quantidade >= 0),
    ativo      INTEGER NOT NULL DEFAULT 1,
    UNIQUE (unidade_id, produto_id)
);

CREATE TABLE movimentacoes_estoque (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    estoque_id      INTEGER NOT NULL REFERENCES estoques(id),
    tipo            TEXT NOT NULL CHECK (tipo IN ('ENTRADA','SAIDA')),
    quantidade      INTEGER NOT NULL CHECK (quantidade > 0),
    motivo          TEXT NOT NULL,
    saldo_anterior  INTEGER NOT NULL,
    saldo_posterior INTEGER NOT NULL,
    responsavel     TEXT NOT NULL,                   -- pseudonimizado
    pedido_id       INTEGER,
    criado_em       TEXT NOT NULL
);

CREATE TABLE campanhas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nome                TEXT NOT NULL,
    descricao           TEXT NOT NULL DEFAULT '',
    produto_id          INTEGER NOT NULL REFERENCES produtos(id),
    unidade_id          INTEGER REFERENCES unidades(id),      -- NULL = todas as unidades
    percentual_desconto INTEGER NOT NULL CHECK (percentual_desconto BETWEEN 1 AND 100),
    data_inicio         TEXT NOT NULL,
    data_fim            TEXT NOT NULL,
    dias_semana         TEXT,                                 -- ex.: '1,3' (0=segunda); NULL = todos
    ativa               INTEGER NOT NULL DEFAULT 1,
    criado_em           TEXT NOT NULL
);

CREATE TABLE cupons (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo                TEXT NOT NULL UNIQUE COLLATE NOCASE,
    descricao             TEXT NOT NULL DEFAULT '',
    tipo                  TEXT NOT NULL CHECK (tipo IN ('PERCENTUAL','VALOR_FIXO')),
    valor                 INTEGER NOT NULL CHECK (valor > 0),
    valor_minimo_centavos INTEGER NOT NULL DEFAULT 0,
    unidade_id            INTEGER REFERENCES unidades(id),    -- NULL = todas as unidades
    validade_inicio       TEXT,
    validade_fim          TEXT,
    limite_uso            INTEGER,
    usos                  INTEGER NOT NULL DEFAULT 0,
    ativo                 INTEGER NOT NULL DEFAULT 1,
    criado_em             TEXT NOT NULL
);

CREATE TABLE pedidos (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id                  INTEGER NOT NULL REFERENCES usuarios(id),
    criado_por_id               INTEGER NOT NULL REFERENCES usuarios(id),
    unidade_id                  INTEGER NOT NULL REFERENCES unidades(id),
    canal                       TEXT NOT NULL,
    status                      TEXT NOT NULL,
    status_pagamento            TEXT NOT NULL,
    subtotal_centavos           INTEGER NOT NULL,
    desconto_campanhas_centavos INTEGER NOT NULL DEFAULT 0,
    desconto_cupom_centavos     INTEGER NOT NULL DEFAULT 0,
    desconto_pontos_centavos    INTEGER NOT NULL DEFAULT 0,
    total_centavos              INTEGER NOT NULL,
    cupom_id                    INTEGER REFERENCES cupons(id),
    pontos_resgatados           INTEGER NOT NULL DEFAULT 0,
    pontos_concedidos           INTEGER NOT NULL DEFAULT 0,
    observacao                  TEXT,
    criado_em                   TEXT NOT NULL,
    atualizado_em               TEXT NOT NULL
);

CREATE TABLE itens_pedido (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id                   INTEGER NOT NULL REFERENCES pedidos(id),
    produto_id                  INTEGER NOT NULL REFERENCES produtos(id),
    nome                        TEXT NOT NULL,
    quantidade                  INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unitario_centavos     INTEGER NOT NULL,
    desconto_campanha_centavos  INTEGER NOT NULL DEFAULT 0,   -- total do desconto da linha
    campanha_id                 INTEGER REFERENCES campanhas(id),
    total_centavos              INTEGER NOT NULL
);

CREATE TABLE historico_status_pedido (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id  INTEGER NOT NULL REFERENCES pedidos(id),
    de_status  TEXT,
    para_status TEXT NOT NULL,
    usuario_id INTEGER REFERENCES usuarios(id),
    criado_em  TEXT NOT NULL
);

-- Cada pagamento ou estorno enviado ao gateway é registrado com a requisição e a resposta.
CREATE TABLE pagamento_tentativas (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id          INTEGER NOT NULL REFERENCES pedidos(id),
    tipo               TEXT NOT NULL CHECK (tipo IN ('PAGAMENTO','ESTORNO')),
    forma_pagamento    TEXT NOT NULL,
    status             TEXT NOT NULL,
    valor_centavos     INTEGER NOT NULL,
    referencia_gateway TEXT,
    payload_requisicao TEXT NOT NULL,
    payload_resposta   TEXT NOT NULL,
    criado_em          TEXT NOT NULL
);

CREATE TABLE idempotencia_pedidos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id     INTEGER NOT NULL REFERENCES usuarios(id),
    chave          TEXT NOT NULL,
    hash_requisicao TEXT NOT NULL,
    pedido_id      INTEGER NOT NULL REFERENCES pedidos(id),
    criado_em      TEXT NOT NULL,
    UNIQUE (usuario_id, chave)
);

CREATE TABLE fidelidade_movimentos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    pedido_id  INTEGER,
    pontos     INTEGER NOT NULL,
    motivo     TEXT NOT NULL,
    criado_em  TEXT NOT NULL
);

CREATE INDEX idx_pedidos_cliente ON pedidos (cliente_id);
CREATE INDEX idx_pedidos_unidade_status ON pedidos (unidade_id, status);
CREATE INDEX idx_mov_estoque ON movimentacoes_estoque (estoque_id);
CREATE INDEX idx_campanhas_produto ON campanhas (produto_id, ativa);

-- Trilhas de auditoria imutáveis.
CREATE TRIGGER trg_consentimentos_imutaveis_u BEFORE UPDATE ON consentimentos_fidelidade
BEGIN SELECT RAISE(ABORT, 'consentimentos são eventos imutáveis'); END;
CREATE TRIGGER trg_consentimentos_imutaveis_d BEFORE DELETE ON consentimentos_fidelidade
BEGIN SELECT RAISE(ABORT, 'consentimentos são eventos imutáveis'); END;
CREATE TRIGGER trg_movimentacoes_imutaveis_u BEFORE UPDATE ON movimentacoes_estoque
BEGIN SELECT RAISE(ABORT, 'movimentações são imutáveis'); END;
CREATE TRIGGER trg_movimentacoes_imutaveis_d BEFORE DELETE ON movimentacoes_estoque
BEGIN SELECT RAISE(ABORT, 'movimentações são imutáveis'); END;

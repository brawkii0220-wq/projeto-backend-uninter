"""Dados iniciais de demonstração (somente quando o banco está vazio e SEED_ENABLED=true)."""
from __future__ import annotations

import logging
from datetime import timedelta

from raizesdonordeste.model.enums import DiaSemana
from raizesdonordeste.repository import usuario_repository
from raizesdonordeste.repository.database import conexao, transacao
from raizesdonordeste.security import senhas
from raizesdonordeste.service import documento_legal_service
from raizesdonordeste.util.tempo import agora, agora_iso, para_iso

logger = logging.getLogger("raizes.seed")

USUARIOS_DEMO = (
    ("Cliente Demo", "cliente@raizes.com", "cliente123", "CLIENTE", None),
    ("Cozinha Centro", "cozinha@raizes.com", "cozinha123", "COZINHA", 1),
    ("Atendente Centro", "atendente@raizes.com", "atendente123", "ATENDENTE", 1),
    ("Gerente Centro", "gerente@raizes.com", "gerente123", "GERENTE", 1),
    ("Administrador", "admin@raizes.com", "admin123", "ADMIN", None),
)
PRODUTOS_DEMO = (
    ("Tapioca", "Tapioca recheada com queijo coalho", "lanches", 1200),
    ("Cuscuz", "Cuscuz nordestino com manteiga de garrafa", "lanches", 1000),
    ("Suco de Cajá", "Suco natural de cajá, 400 ml", "bebidas", 800),
    ("Carne de Sol", "Carne de sol com macaxeira e vinagrete", "pratos", 3500),
)


def popular(settings) -> None:
    conn = conexao()
    if usuario_repository.contar(conn):
        return
    with transacao():
        agora_s = agora_iso()
        for nome, cidade in (("Unidade Centro", "Recife"), ("Unidade Zona Sul", "Recife")):
            conn.execute("INSERT INTO unidades (nome, cidade, criado_em) VALUES (?,?,?)", (nome, cidade, agora_s))
        for nome, email, senha, perfil, unidade in USUARIOS_DEMO:
            novo = usuario_repository.inserir(conn, nome, email, senhas.gerar_hash(senha, settings.senha_iteracoes),
                                              perfil, unidade)
            documento_legal_service.registrar_aceite(conn, novo)
        for nome, descricao, categoria, preco in PRODUTOS_DEMO:
            conn.execute("INSERT INTO produtos (nome, descricao, categoria, preco_centavos, criado_em)"
                         " VALUES (?,?,?,?,?)", (nome, descricao, categoria, preco, agora_s))
        for unidade_id in (1, 2):
            for produto_id in (1, 2, 3, 4):
                conn.execute("INSERT INTO estoques (unidade_id, produto_id, quantidade) VALUES (?,?,?)",
                             (unidade_id, produto_id, 50))
        conn.execute(
            "INSERT INTO campanhas (nome, descricao, produto_id, unidade_id, percentual_desconto, data_inicio,"
            " data_fim, dias_semana, criado_em) VALUES (?,?,?,?,?,?,?,?,?)",
            ("Terça da Tapioca", "20% de desconto na tapioca às terças-feiras", 1, None, 20,
             para_iso(agora() - timedelta(days=1)), para_iso(agora() + timedelta(days=365)),
             str(DiaSemana.TERCA.indice), agora_s))
        for codigo, descricao, tipo, valor, minimo in (
                ("NORDESTE10", "10% de desconto no pedido", "PERCENTUAL", 10, 0),
                ("PROMO5", "R$ 5,00 de desconto em pedidos a partir de R$ 30,00", "VALOR_FIXO", 500, 3000)):
            conn.execute("INSERT INTO cupons (codigo, descricao, tipo, valor, valor_minimo_centavos, criado_em)"
                         " VALUES (?,?,?,?,?,?)", (codigo, descricao, tipo, valor, minimo, agora_s))
    logger.info("Seed de demonstração aplicado.")

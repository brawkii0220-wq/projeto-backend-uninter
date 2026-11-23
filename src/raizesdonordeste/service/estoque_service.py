from __future__ import annotations

from raizesdonordeste.dto.respostas import estoque_dto, movimentacao_dto
from raizesdonordeste.dto.validacao import Validador, corpo_json
from raizesdonordeste.exception.api_error import conflito, nao_encontrado
from raizesdonordeste.model.enums import TipoMovimentacao
from raizesdonordeste.repository import catalogo_repository, estoque_repository
from raizesdonordeste.repository.database import conexao, paginar, transacao
from raizesdonordeste.service.autorizacao import exigir_gestao_unidade
from raizesdonordeste.util.pseudonimizacao import pseudonimizar


def _carregar_com_acesso(conn, usuario, estoque_id: int):
    estoque = estoque_repository.buscar(conn, estoque_id)
    if estoque is None:
        raise nao_encontrado("Registro de estoque")
    exigir_gestao_unidade(usuario, estoque["unidade_id"])
    return estoque


def criar(usuario) -> dict:
    v = Validador(corpo_json())
    unidade_id = v.inteiro("unidadeId", minimo=1)
    produto_id = v.inteiro("produtoId", minimo=1)
    quantidade = v.inteiro("quantidade", minimo=0, maximo=1_000_000)
    v.verificar()
    exigir_gestao_unidade(usuario, unidade_id)
    with transacao() as conn:
        unidade = catalogo_repository.buscar_unidade(conn, unidade_id)
        if unidade is None or not unidade["ativa"]:
            raise nao_encontrado("Unidade")
        produto = catalogo_repository.buscar_produto(conn, produto_id)
        if produto is None or not produto["ativo"]:
            raise nao_encontrado("Produto")
        existente = estoque_repository.buscar_por_unidade_produto(conn, unidade_id, produto_id)
        if existente and existente["ativo"]:
            raise conflito("ESTOQUE_JA_CADASTRADO", "Este produto já possui estoque nesta unidade.")
        if existente:   # reativa um registro removido logicamente
            conn.execute("UPDATE estoques SET ativo=1 WHERE id=?", (existente["id"],))
            estoque_id = existente["id"]
        else:
            estoque_id = conn.execute("INSERT INTO estoques (unidade_id, produto_id, quantidade) VALUES (?,?,0)",
                                      (unidade_id, produto_id)).lastrowid
        if quantidade:
            estoque_repository.aplicar_movimento(conn, estoque_id, "ENTRADA", quantidade, "ESTOQUE_INICIAL",
                                                 pseudonimizar(usuario["email"]))
        return estoque_dto(estoque_repository.buscar(conn, estoque_id))


def listar_por_unidade(usuario, unidade_id: int) -> dict:
    exigir_gestao_unidade(usuario, unidade_id)
    if catalogo_repository.buscar_unidade(conexao(), unidade_id) is None:
        raise nao_encontrado("Unidade")
    return paginar(
        "SELECT e.*, p.nome AS produto_nome FROM estoques e JOIN produtos p ON p.id = e.produto_id"
        " WHERE e.unidade_id=? AND e.ativo=1 ORDER BY p.nome", [unidade_id], estoque_dto)


def buscar(usuario, estoque_id: int) -> dict:
    return estoque_dto(_carregar_com_acesso(conexao(), usuario, estoque_id))


def atualizar(usuario, estoque_id: int) -> dict:
    """Ajusta o saldo para a quantidade informada, registrando a diferença como movimentação."""
    v = Validador(corpo_json())
    nova = v.inteiro("quantidade", minimo=0, maximo=1_000_000)
    v.verificar()
    with transacao() as conn:
        estoque = _carregar_com_acesso(conn, usuario, estoque_id)
        diferenca = nova - estoque["quantidade"]
        if diferenca:
            estoque_repository.aplicar_movimento(
                conn, estoque_id, "ENTRADA" if diferenca > 0 else "SAIDA", abs(diferenca), "AJUSTE_DE_ESTOQUE",
                pseudonimizar(usuario["email"]))
        return estoque_dto(estoque_repository.buscar(conn, estoque_id))


def remover(usuario, estoque_id: int) -> None:
    """Remoção lógica: o item sai do cardápio da unidade, mas a trilha de movimentações permanece."""
    with transacao() as conn:
        _carregar_com_acesso(conn, usuario, estoque_id)
        conn.execute("UPDATE estoques SET ativo=0 WHERE id=?", (estoque_id,))


def movimentar(usuario, estoque_id: int) -> dict:
    v = Validador(corpo_json())
    tipo = v.enum("tipo", TipoMovimentacao.valores())
    quantidade = v.inteiro("quantidade", minimo=1, maximo=1_000_000)
    motivo = v.texto("motivo", minimo=3, maximo=200)
    v.verificar()
    with transacao() as conn:
        estoque = _carregar_com_acesso(conn, usuario, estoque_id)
        if not estoque["ativo"]:
            raise conflito("ESTOQUE_INATIVO", "Este registro de estoque foi removido.")
        estoque_repository.aplicar_movimento(conn, estoque_id, tipo, quantidade, motivo,
                                             pseudonimizar(usuario["email"]))
        ultima = conn.execute("SELECT * FROM movimentacoes_estoque WHERE estoque_id=? ORDER BY id DESC LIMIT 1",
                              (estoque_id,)).fetchone()
        return movimentacao_dto(ultima)


def listar_movimentacoes(usuario, estoque_id: int) -> dict:
    _carregar_com_acesso(conexao(), usuario, estoque_id)
    return paginar("SELECT * FROM movimentacoes_estoque WHERE estoque_id=? ORDER BY id DESC",
                   [estoque_id], movimentacao_dto)

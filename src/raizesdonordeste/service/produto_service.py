from __future__ import annotations

from raizesdonordeste.dto.respostas import produto_dto, produto_unidade_dto
from raizesdonordeste.dto.validacao import Validador, corpo_json
from raizesdonordeste.exception.api_error import nao_encontrado
from raizesdonordeste.repository import catalogo_repository
from raizesdonordeste.repository.database import conexao, paginar, transacao
from raizesdonordeste.util.tempo import agora_iso


def listar() -> dict:
    return paginar("SELECT * FROM produtos WHERE ativo=1 ORDER BY categoria, nome", [], produto_dto)


def listar_por_unidade(unidade_id: int) -> dict:
    """Cardápio da unidade com disponibilidade: itens sem saldo aparecem com disponivel=false."""
    unidade = catalogo_repository.buscar_unidade(conexao(), unidade_id)
    if unidade is None or not unidade["ativa"]:
        raise nao_encontrado("Unidade")
    return paginar(
        "SELECT p.*, e.unidade_id, e.quantidade FROM estoques e JOIN produtos p ON p.id = e.produto_id"
        " WHERE e.unidade_id=? AND e.ativo=1 AND p.ativo=1 ORDER BY p.categoria, p.nome",
        [unidade_id], produto_unidade_dto)


def buscar(produto_id: int) -> dict:
    produto = catalogo_repository.buscar_produto(conexao(), produto_id)
    if produto is None or not produto["ativo"]:
        raise nao_encontrado("Produto")
    return produto_dto(produto)


def _ler_corpo():
    v = Validador(corpo_json())
    nome = v.texto("nome", minimo=2, maximo=100)
    descricao = v.texto("descricao", obrigatorio=False, minimo=0, maximo=300, padrao="")
    categoria = v.texto("categoria", obrigatorio=False, minimo=2, maximo=50, padrao="geral")
    preco = v.inteiro("precoCentavos", minimo=0, maximo=10_000_000)
    v.verificar()
    return nome, descricao, categoria, preco


def criar() -> dict:
    nome, descricao, categoria, preco = _ler_corpo()
    with transacao() as conn:
        novo = conn.execute(
            "INSERT INTO produtos (nome, descricao, categoria, preco_centavos, criado_em) VALUES (?,?,?,?,?)",
            (nome, descricao, categoria, preco, agora_iso())).lastrowid
        return produto_dto(catalogo_repository.buscar_produto(conn, novo))


def atualizar(produto_id: int) -> dict:
    nome, descricao, categoria, preco = _ler_corpo()
    with transacao() as conn:
        if catalogo_repository.buscar_produto(conn, produto_id) is None:
            raise nao_encontrado("Produto")
        conn.execute("UPDATE produtos SET nome=?, descricao=?, categoria=?, preco_centavos=? WHERE id=?",
                     (nome, descricao, categoria, preco, produto_id))
        return produto_dto(catalogo_repository.buscar_produto(conn, produto_id))


def desativar(produto_id: int) -> None:
    with transacao() as conn:
        if catalogo_repository.buscar_produto(conn, produto_id) is None:
            raise nao_encontrado("Produto")
        conn.execute("UPDATE produtos SET ativo=0 WHERE id=?", (produto_id,))

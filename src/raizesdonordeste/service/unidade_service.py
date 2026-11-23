from __future__ import annotations

from raizesdonordeste.dto.respostas import unidade_dto
from raizesdonordeste.dto.validacao import Validador, corpo_json
from raizesdonordeste.exception.api_error import nao_encontrado
from raizesdonordeste.repository import catalogo_repository
from raizesdonordeste.repository.database import conexao, paginar, transacao
from raizesdonordeste.util.tempo import agora_iso


def criar() -> dict:
    v = Validador(corpo_json())
    nome = v.texto("nome", minimo=2, maximo=100)
    cidade = v.texto("cidade", minimo=2, maximo=100)
    v.verificar()
    with transacao() as conn:
        novo = conn.execute("INSERT INTO unidades (nome, cidade, criado_em) VALUES (?,?,?)",
                            (nome, cidade, agora_iso())).lastrowid
        return unidade_dto(catalogo_repository.buscar_unidade(conn, novo))


def listar() -> dict:
    return paginar("SELECT * FROM unidades WHERE ativa=1 ORDER BY id", [], unidade_dto)


def buscar(unidade_id: int) -> dict:
    unidade = catalogo_repository.buscar_unidade(conexao(), unidade_id)
    if unidade is None:
        raise nao_encontrado("Unidade")
    return unidade_dto(unidade)


def atualizar(unidade_id: int) -> dict:
    v = Validador(corpo_json())
    nome = v.texto("nome", minimo=2, maximo=100)
    cidade = v.texto("cidade", minimo=2, maximo=100)
    ativa = v.booleano("ativa", obrigatorio=False)
    v.verificar()
    with transacao() as conn:
        atual = catalogo_repository.buscar_unidade(conn, unidade_id)
        if atual is None:
            raise nao_encontrado("Unidade")
        conn.execute("UPDATE unidades SET nome=?, cidade=?, ativa=? WHERE id=?",
                     (nome, cidade, int(ativa) if ativa is not None else atual["ativa"], unidade_id))
        return unidade_dto(catalogo_repository.buscar_unidade(conn, unidade_id))


def desativar(unidade_id: int) -> None:
    """Exclusão lógica: a unidade deixa de aceitar pedidos, mas o histórico é preservado."""
    with transacao() as conn:
        if catalogo_repository.buscar_unidade(conn, unidade_id) is None:
            raise nao_encontrado("Unidade")
        conn.execute("UPDATE unidades SET ativa=0 WHERE id=?", (unidade_id,))

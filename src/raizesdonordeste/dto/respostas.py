"""Serializadores: linhas do banco -> JSON de resposta (camelCase)."""
from __future__ import annotations

from raizesdonordeste.model.enums import DiaSemana


def usuario_dto(u, completo: bool = True) -> dict:
    dto = {"id": u["id"], "nome": u["nome"], "email": u["email"], "perfil": u["perfil"],
           "unidadeId": u["unidade_id"]}
    if completo:
        dto.update({"pontos": u["pontos"], "telefone": u["telefone"], "cpf": u["cpf"]})
    return dto


def unidade_dto(u) -> dict:
    return {"id": u["id"], "nome": u["nome"], "cidade": u["cidade"], "ativa": bool(u["ativa"])}


def produto_dto(p) -> dict:
    return {"id": p["id"], "nome": p["nome"], "descricao": p["descricao"], "categoria": p["categoria"],
            "precoCentavos": p["preco_centavos"], "ativo": bool(p["ativo"])}


def produto_unidade_dto(r) -> dict:
    dto = produto_dto(r)
    dto.pop("ativo")
    dto.update({"unidadeId": r["unidade_id"], "quantidadeDisponivel": r["quantidade"],
                "disponivel": r["quantidade"] > 0})
    return dto


def estoque_dto(e) -> dict:
    return {"id": e["id"], "unidadeId": e["unidade_id"], "produtoId": e["produto_id"],
            "produtoNome": e["produto_nome"], "quantidade": e["quantidade"], "ativo": bool(e["ativo"])}


def movimentacao_dto(m) -> dict:
    return {"id": m["id"], "estoqueId": m["estoque_id"], "tipo": m["tipo"], "quantidade": m["quantidade"],
            "motivo": m["motivo"], "saldoAnterior": m["saldo_anterior"], "saldoPosterior": m["saldo_posterior"],
            "responsavel": m["responsavel"], "pedidoId": m["pedido_id"], "criadoEm": m["criado_em"]}


def _dias(texto: str | None) -> list[str]:
    if not texto:
        return []
    ordem = list(DiaSemana)
    return [ordem[int(i)].value for i in texto.split(",")]


def campanha_dto(c) -> dict:
    return {"id": c["id"], "nome": c["nome"], "descricao": c["descricao"], "produtoId": c["produto_id"],
            "unidadeId": c["unidade_id"], "percentualDesconto": c["percentual_desconto"],
            "dataInicio": c["data_inicio"], "dataFim": c["data_fim"], "diasSemana": _dias(c["dias_semana"]),
            "ativa": bool(c["ativa"])}


def cupom_dto(c) -> dict:
    return {"id": c["id"], "codigo": c["codigo"], "descricao": c["descricao"], "tipo": c["tipo"],
            "valor": c["valor"], "valorMinimoCentavos": c["valor_minimo_centavos"],
            "unidadeId": c["unidade_id"], "validadeInicio": c["validade_inicio"],
            "validadeFim": c["validade_fim"], "limiteUso": c["limite_uso"], "usos": c["usos"],
            "ativo": bool(c["ativo"])}

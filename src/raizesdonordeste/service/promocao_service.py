"""Campanhas (desconto automático por produto) e cupons (código informado no pedido)."""
from __future__ import annotations

import re

from flask import request

from raizesdonordeste.dto.respostas import campanha_dto, cupom_dto
from raizesdonordeste.dto.validacao import Validador, corpo_json
from raizesdonordeste.exception.api_error import ApiError, acesso_negado, conflito, nao_encontrado
from raizesdonordeste.model.enums import DiaSemana, TipoCupom
from raizesdonordeste.repository import catalogo_repository, promocao_repository
from raizesdonordeste.repository.database import conexao, paginar, transacao
from raizesdonordeste.service.autorizacao import exigir_gestao_unidade
from raizesdonordeste.util.tempo import agora, agora_iso, interpretar_iso, para_iso

_CODIGO_RE = re.compile(r"^[A-Za-z0-9_\-]{3,30}$")


def _escopo(usuario, unidade_id):
    """ADMIN gerencia qualquer escopo (inclusive global); GERENTE só a própria unidade."""
    if usuario["perfil"] == "ADMIN":
        return
    if unidade_id is None:
        raise acesso_negado("Somente ADMIN gerencia promoções globais (todas as unidades).")
    exigir_gestao_unidade(usuario, unidade_id)


def _unidade_existente(conn, unidade_id):
    if unidade_id is not None:
        unidade = catalogo_repository.buscar_unidade(conn, unidade_id)
        if unidade is None or not unidade["ativa"]:
            raise nao_encontrado("Unidade")


def _filtro_listagem(usuario) -> tuple[str, list]:
    if usuario["perfil"] == "ADMIN":
        return "1=1", []
    return "unidade_id = ?", [usuario["unidade_id"]]


# ============================== Campanhas ==========================================
def _ler_campanha():
    v = Validador(corpo_json())
    nome = v.texto("nome", minimo=2, maximo=100)
    descricao = v.texto("descricao", obrigatorio=False, minimo=0, maximo=300, padrao="")
    produto_id = v.inteiro("produtoId", minimo=1)
    unidade_id = v.inteiro("unidadeId", obrigatorio=False, minimo=1)
    percentual = v.inteiro("percentualDesconto", minimo=1, maximo=100)
    inicio = v.datahora("dataInicio")
    fim = v.datahora("dataFim")
    if inicio and fim and interpretar_iso(fim) <= interpretar_iso(inicio):
        v.erro("dataFim", "deve ser posterior a dataInicio")
    dias_brutos = v.corpo.get("diasSemana")
    dias: list[int] = []
    if dias_brutos is not None:
        validos = DiaSemana.valores()
        if not isinstance(dias_brutos, list) or any(not isinstance(d, str) or d.upper() not in validos
                                                    for d in dias_brutos):
            v.erro("diasSemana", "lista com valores: " + ", ".join(validos))
        else:
            dias = sorted({DiaSemana(d.upper()).indice for d in dias_brutos})
    v.verificar()
    return nome, descricao, produto_id, unidade_id, percentual, inicio, fim, dias


def _validar_sobreposicao(conn, produto_id, unidade_id, inicio, fim, dias, excluir_id=None):
    conflitos = promocao_repository.campanhas_sobrepostas(
        conn, produto_id, unidade_id, inicio, fim, {str(d) for d in dias}, excluir_id)
    if conflitos:
        raise conflito("CAMPANHA_PERIODO_SOBREPOSTO",
                       "Já existe campanha ativa para este produto no mesmo período, unidade e dias da semana.",
                       [{"field": "dataInicio", "issue": f"conflita com a campanha {c['id']} ({c['nome']})"}
                        for c in conflitos])


def criar_campanha(usuario) -> dict:
    nome, descricao, produto_id, unidade_id, percentual, inicio, fim, dias = _ler_campanha()
    _escopo(usuario, unidade_id)
    with transacao() as conn:   # transação serializada: impede duas campanhas sobrepostas em paralelo
        _unidade_existente(conn, unidade_id)
        produto = catalogo_repository.buscar_produto(conn, produto_id)
        if produto is None or not produto["ativo"]:
            raise nao_encontrado("Produto")
        _validar_sobreposicao(conn, produto_id, unidade_id, inicio, fim, dias)
        novo = conn.execute(
            "INSERT INTO campanhas (nome, descricao, produto_id, unidade_id, percentual_desconto, data_inicio,"
            " data_fim, dias_semana, criado_em) VALUES (?,?,?,?,?,?,?,?,?)",
            (nome, descricao, produto_id, unidade_id, percentual, inicio, fim,
             ",".join(map(str, dias)) or None, agora_iso())).lastrowid
        return campanha_dto(promocao_repository.buscar_campanha(conn, novo))


def listar_campanhas(usuario) -> dict:
    filtro, params = _filtro_listagem(usuario)
    return paginar(f"SELECT * FROM campanhas WHERE {filtro} ORDER BY id", params, campanha_dto)


def _campanha_com_acesso(conn, usuario, campanha_id):
    campanha = promocao_repository.buscar_campanha(conn, campanha_id)
    if campanha is None:
        raise nao_encontrado("Campanha")
    _escopo(usuario, campanha["unidade_id"])
    return campanha


def buscar_campanha(usuario, campanha_id: int) -> dict:
    return campanha_dto(_campanha_com_acesso(conexao(), usuario, campanha_id))


def atualizar_campanha(usuario, campanha_id: int) -> dict:
    nome, descricao, produto_id, unidade_id, percentual, inicio, fim, dias = _ler_campanha()
    _escopo(usuario, unidade_id)
    with transacao() as conn:
        _campanha_com_acesso(conn, usuario, campanha_id)
        _unidade_existente(conn, unidade_id)
        if catalogo_repository.buscar_produto(conn, produto_id) is None:
            raise nao_encontrado("Produto")
        _validar_sobreposicao(conn, produto_id, unidade_id, inicio, fim, dias, campanha_id)
        conn.execute(
            "UPDATE campanhas SET nome=?, descricao=?, produto_id=?, unidade_id=?, percentual_desconto=?,"
            " data_inicio=?, data_fim=?, dias_semana=? WHERE id=?",
            (nome, descricao, produto_id, unidade_id, percentual, inicio, fim,
             ",".join(map(str, dias)) or None, campanha_id))
        return campanha_dto(promocao_repository.buscar_campanha(conn, campanha_id))


def desativar_campanha(usuario, campanha_id: int) -> None:
    with transacao() as conn:
        _campanha_com_acesso(conn, usuario, campanha_id)
        conn.execute("UPDATE campanhas SET ativa=0 WHERE id=?", (campanha_id,))


# ================================ Cupons ===========================================
def _ler_cupom():
    v = Validador(corpo_json())
    codigo = v.texto("codigo", minimo=3, maximo=30, regex=_CODIGO_RE, mensagem="use letras, números, _ ou -")
    descricao = v.texto("descricao", obrigatorio=False, minimo=0, maximo=300, padrao="")
    tipo = v.enum("tipo", TipoCupom.valores())
    valor = v.inteiro("valor", minimo=1, maximo=100 if tipo == "PERCENTUAL" else 10_000_000)
    minimo = v.inteiro("valorMinimoCentavos", obrigatorio=False, minimo=0, padrao=0)
    unidade_id = v.inteiro("unidadeId", obrigatorio=False, minimo=1)
    inicio = v.datahora("validadeInicio", obrigatorio=False)
    fim = v.datahora("validadeFim", obrigatorio=False)
    if inicio and fim and interpretar_iso(fim) <= interpretar_iso(inicio):
        v.erro("validadeFim", "deve ser posterior a validadeInicio")
    limite = v.inteiro("limiteUso", obrigatorio=False, minimo=1)
    ativo = v.booleano("ativo", obrigatorio=False)
    v.verificar()
    return codigo.upper(), descricao, tipo, valor, minimo, unidade_id, inicio, fim, limite, ativo


def criar_cupom(usuario) -> dict:
    codigo, descricao, tipo, valor, minimo, unidade_id, inicio, fim, limite, _ = _ler_cupom()
    _escopo(usuario, unidade_id)
    with transacao() as conn:
        _unidade_existente(conn, unidade_id)
        if promocao_repository.buscar_cupom_por_codigo(conn, codigo):
            raise conflito("CUPOM_CODIGO_DUPLICADO", "Já existe um cupom com este código.")
        novo = conn.execute(
            "INSERT INTO cupons (codigo, descricao, tipo, valor, valor_minimo_centavos, unidade_id,"
            " validade_inicio, validade_fim, limite_uso, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (codigo, descricao, tipo, valor, minimo, unidade_id, inicio, fim, limite, agora_iso())).lastrowid
        return cupom_dto(promocao_repository.buscar_cupom(conn, novo))


def listar_cupons(usuario) -> dict:
    filtro, params = _filtro_listagem(usuario)
    return paginar(f"SELECT * FROM cupons WHERE {filtro} ORDER BY id", params, cupom_dto)


def _cupom_com_acesso(conn, usuario, cupom_id):
    cupom = promocao_repository.buscar_cupom(conn, cupom_id)
    if cupom is None:
        raise nao_encontrado("Cupom")
    _escopo(usuario, cupom["unidade_id"])
    return cupom


def buscar_cupom(usuario, cupom_id: int) -> dict:
    return cupom_dto(_cupom_com_acesso(conexao(), usuario, cupom_id))


def atualizar_cupom(usuario, cupom_id: int) -> dict:
    codigo, descricao, tipo, valor, minimo, unidade_id, inicio, fim, limite, ativo = _ler_cupom()
    _escopo(usuario, unidade_id)
    with transacao() as conn:
        atual = _cupom_com_acesso(conn, usuario, cupom_id)
        _unidade_existente(conn, unidade_id)
        outro = promocao_repository.buscar_cupom_por_codigo(conn, codigo)
        if outro and outro["id"] != cupom_id:
            raise conflito("CUPOM_CODIGO_DUPLICADO", "Já existe um cupom com este código.")
        conn.execute(
            "UPDATE cupons SET codigo=?, descricao=?, tipo=?, valor=?, valor_minimo_centavos=?, unidade_id=?,"
            " validade_inicio=?, validade_fim=?, limite_uso=?, ativo=? WHERE id=?",
            (codigo, descricao, tipo, valor, minimo, unidade_id, inicio, fim, limite,
             int(ativo) if ativo is not None else atual["ativo"], cupom_id))
        return cupom_dto(promocao_repository.buscar_cupom(conn, cupom_id))


def desativar_cupom(usuario, cupom_id: int) -> None:
    with transacao() as conn:
        _cupom_com_acesso(conn, usuario, cupom_id)
        conn.execute("UPDATE cupons SET ativo=0 WHERE id=?", (cupom_id,))


def aplicar_cupom(conn, codigo: str, unidade_id: int, base_centavos: int):
    """Regras do cupom na criação do pedido. Retorna (cupom, desconto em centavos)."""
    cupom = promocao_repository.buscar_cupom_por_codigo(conn, codigo.strip())

    def falha(codigo_erro, msg, status=422):
        raise ApiError(status, codigo_erro, msg, [{"field": "cupomCodigo", "issue": msg}])

    if cupom is None or not cupom["ativo"]:
        falha("CUPOM_INVALIDO", "Cupom inválido ou inativo.")
    instante = para_iso(agora())
    if cupom["validade_inicio"] and instante < cupom["validade_inicio"]:
        falha("CUPOM_FORA_DA_VIGENCIA", "Este cupom ainda não está vigente.")
    if cupom["validade_fim"] and instante > cupom["validade_fim"]:
        falha("CUPOM_FORA_DA_VIGENCIA", "Este cupom expirou.")
    if cupom["unidade_id"] is not None and cupom["unidade_id"] != unidade_id:
        falha("CUPOM_OUTRA_UNIDADE", "Este cupom não vale para a unidade do pedido.")
    if cupom["limite_uso"] is not None and cupom["usos"] >= cupom["limite_uso"]:
        falha("CUPOM_ESGOTADO", "Este cupom atingiu o limite de usos.", 409)
    if base_centavos < cupom["valor_minimo_centavos"]:
        falha("CUPOM_VALOR_MINIMO", f"Pedido abaixo do valor mínimo do cupom ({cupom['valor_minimo_centavos']} centavos).")
    if cupom["tipo"] == "PERCENTUAL":
        desconto = base_centavos * cupom["valor"] // 100
    else:
        desconto = min(cupom["valor"], base_centavos)
    return cupom, desconto


def registrar_uso_cupom(conn, cupom_id: int) -> None:
    alterado = conn.execute(
        "UPDATE cupons SET usos = usos + 1 WHERE id=? AND (limite_uso IS NULL OR usos < limite_uso)",
        (cupom_id,)).rowcount
    if not alterado:
        raise conflito("CUPOM_ESGOTADO", "Este cupom atingiu o limite de usos.")


def liberar_uso_cupom(conn, cupom_id: int) -> None:
    conn.execute("UPDATE cupons SET usos = MAX(usos - 1, 0) WHERE id=?", (cupom_id,))

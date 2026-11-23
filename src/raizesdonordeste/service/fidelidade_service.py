"""Programa de fidelidade: pontos, resgate e consentimento LGPD específico (eventos imutáveis)."""
from __future__ import annotations

from flask import current_app

from raizesdonordeste.exception.api_error import ApiError, conflito
from raizesdonordeste.model.enums import (CENTAVOS_POR_PONTO_GANHO, FINALIDADE_FIDELIDADE,
                                          LIMITE_RESGATE_PERCENTUAL, VALOR_PONTO_CENTAVOS)
from raizesdonordeste.repository import fidelidade_repository, usuario_repository
from raizesdonordeste.repository.database import conexao, transacao
from raizesdonordeste.util.origem import origem_requisicao
from raizesdonordeste.util.tempo import agora_iso


def versao_vigente() -> str:
    return current_app.extensions["settings"].termo_fidelidade_versao


def consentimento_ativo(conn, usuario_id: int) -> bool:
    return fidelidade_repository.consentimento_ativo(conn, usuario_id, versao_vigente())


def saldo(usuario) -> dict:
    conn = conexao()
    atual = usuario_repository.buscar(conn, usuario["id"])["pontos"]
    return {
        "saldo": atual,
        "pontosDisponiveis": max(atual, 0),
        "saldoDevedor": atual < 0,
        "consentimentoAtivo": consentimento_ativo(conn, usuario["id"]),
        "regras": {
            "acumulo": "1 ponto a cada R$ 1,00 pago, creditado na aprovação do pagamento",
            "resgate": f"1 ponto = R$ {VALOR_PONTO_CENTAVOS / 100:.2f}".replace(".", ",")
                       + f", limitado a {LIMITE_RESGATE_PERCENTUAL}% do valor do pedido",
        },
    }


def situacao_consentimento(usuario) -> dict:
    conn = conexao()
    ultimo = conn.execute("SELECT * FROM consentimentos_fidelidade WHERE usuario_id=? ORDER BY id DESC LIMIT 1",
                          (usuario["id"],)).fetchone()
    return {
        "consentimentoAtivo": consentimento_ativo(conn, usuario["id"]),
        "finalidade": FINALIDADE_FIDELIDADE, "versaoVigente": versao_vigente(),
        "ultimoEvento": None if ultimo is None else {
            "tipo": ultimo["tipo"], "versao": ultimo["versao"], "origem": ultimo["origem"],
            "em": ultimo["criado_em"]},
    }


def _registrar_evento(conn, usuario_id: int, tipo: str) -> None:
    conn.execute(
        "INSERT INTO consentimentos_fidelidade (usuario_id, tipo, finalidade, versao, origem, criado_em)"
        " VALUES (?,?,?,?,?,?)",
        (usuario_id, tipo, FINALIDADE_FIDELIDADE, versao_vigente(), origem_requisicao(), agora_iso()))


def consentir(usuario) -> tuple[dict, bool]:
    """Somente o próprio titular consente (funcionários não consentem em nome do cliente)."""
    with transacao() as conn:
        criado = not consentimento_ativo(conn, usuario["id"])
        if criado:
            _registrar_evento(conn, usuario["id"], "CONCESSAO")
    return situacao_consentimento(usuario), criado


def revogar(usuario) -> None:
    with transacao() as conn:
        if consentimento_ativo(conn, usuario["id"]):
            _registrar_evento(conn, usuario["id"], "REVOGACAO")


# --- usadas pelo fluxo de pedidos ---------------------------------------------------
def validar_resgate(conn, cliente_id: int, pontos: int, base_centavos: int) -> int:
    """Valida o resgate e devolve o desconto em centavos."""
    if pontos <= 0:
        return 0
    if not consentimento_ativo(conn, cliente_id):
        raise ApiError(403, "CONSENTIMENTO_FIDELIDADE_NECESSARIO",
                       "O cliente precisa consentir com o programa de fidelidade para resgatar pontos.",
                       [{"field": "pontosResgatar", "issue": "consentimento ausente ou desatualizado"}])
    disponiveis = max(usuario_repository.buscar(conn, cliente_id)["pontos"], 0)
    if pontos > disponiveis:
        raise conflito("PONTOS_INSUFICIENTES", "Saldo de pontos insuficiente.",
                       [{"field": "pontosResgatar", "issue": f"Disponível: {disponiveis}"}])
    maximo = (base_centavos * LIMITE_RESGATE_PERCENTUAL // 100) // VALOR_PONTO_CENTAVOS
    if pontos > maximo:
        raise ApiError(422, "LIMITE_RESGATE_EXCEDIDO",
                       f"Pontos podem cobrir no máximo {LIMITE_RESGATE_PERCENTUAL}% do pedido.",
                       [{"field": "pontosResgatar", "issue": f"Máximo para este pedido: {maximo}"}])
    return pontos * VALOR_PONTO_CENTAVOS


def conceder_por_pagamento(conn, pedido) -> int:
    if not consentimento_ativo(conn, pedido["cliente_id"]):
        return 0
    pontos = pedido["total_centavos"] // CENTAVOS_POR_PONTO_GANHO
    if pontos > 0:
        fidelidade_repository.movimentar_pontos(conn, pedido["cliente_id"], pontos, "ACUMULO_PAGAMENTO", pedido["id"])
        conn.execute("UPDATE pedidos SET pontos_concedidos=? WHERE id=?", (pontos, pedido["id"]))
    return pontos


def desfazer_no_cancelamento(conn, pedido) -> None:
    """Devolve pontos resgatados e retira os concedidos; o saldo pode ficar devedor sem bloquear o cancelamento."""
    if pedido["pontos_resgatados"] > 0:
        fidelidade_repository.movimentar_pontos(conn, pedido["cliente_id"], pedido["pontos_resgatados"],
                                                "DEVOLUCAO_RESGATE_CANCELAMENTO", pedido["id"])
    if pedido["pontos_concedidos"] > 0:
        fidelidade_repository.movimentar_pontos(conn, pedido["cliente_id"], -pedido["pontos_concedidos"],
                                                "ESTORNO_ACUMULO_CANCELAMENTO", pedido["id"])

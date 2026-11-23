"""Gateway de pagamento. A implementação é SIMULADA: nenhum pagamento real é feito.

Contrato:
  autorizar(requisicao, forcar) -> RespostaGateway(status APROVADO|RECUSADO, referencia, payload)
  estornar(requisicao, forcar)  -> RespostaGateway(status CONFIRMADO, referencia, payload)
  Indisponibilidade técnica -> GatewayIndisponivel (não é recusa comercial).
"""
from __future__ import annotations

import random
import secrets
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from raizesdonordeste.util.tempo import agora_iso


class GatewayIndisponivel(Exception):
    """Falha técnica do provedor (timeout, 5xx). O chamador não deve consumir tentativa."""


@dataclass
class RespostaGateway:
    status: str
    referencia: str
    payload: dict = field(default_factory=dict)


class GatewayPagamento(ABC):
    @abstractmethod
    def autorizar(self, requisicao: dict, forcar: str | None = None) -> RespostaGateway: ...

    @abstractmethod
    def estornar(self, requisicao: dict, forcar: str | None = None) -> RespostaGateway: ...


class GatewayPagamentoSimulado(GatewayPagamento):
    def __init__(self, forcar_status: str = "", forcar_estorno: str = "",
                 sorteio: Callable[[], float] = random.random, taxa_aprovacao: float = 0.8):
        self.forcar_status = forcar_status
        self.forcar_estorno = forcar_estorno
        self.sorteio = sorteio
        self.taxa_aprovacao = taxa_aprovacao

    def autorizar(self, requisicao: dict, forcar: str | None = None) -> RespostaGateway:
        decisao = forcar or self.forcar_status
        if decisao == "INDISPONIVEL":
            raise GatewayIndisponivel("Gateway de pagamento indisponível (simulação).")
        if not decisao:
            decisao = "APROVADO" if self.sorteio() < self.taxa_aprovacao else "RECUSADO"
        referencia = "gw_" + uuid.uuid4().hex[:16]
        if decisao == "APROVADO":
            payload = {"id": referencia, "status": "APROVADO",
                       "codigoAutorizacao": secrets.token_hex(3).upper(), "processadoEm": agora_iso()}
        else:
            payload = {"id": referencia, "status": "RECUSADO", "motivo": "TRANSACAO_NEGADA_PELO_EMISSOR",
                       "processadoEm": agora_iso()}
        return RespostaGateway(decisao, referencia, payload)

    def estornar(self, requisicao: dict, forcar: str | None = None) -> RespostaGateway:
        decisao = forcar or self.forcar_estorno
        if decisao == "INDISPONIVEL":
            raise GatewayIndisponivel("Gateway de estorno indisponível (simulação).")
        referencia = "est_" + uuid.uuid4().hex[:16]
        return RespostaGateway("CONFIRMADO", referencia, {
            "id": referencia, "status": "CONFIRMADO",
            "referenciaPagamento": requisicao.get("referenciaPagamento"), "processadoEm": agora_iso()})

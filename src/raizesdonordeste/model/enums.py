"""Enumerações e regras de negócio constantes do domínio."""
from __future__ import annotations

from enum import Enum


class _Texto(str, Enum):
    @classmethod
    def valores(cls) -> list[str]:
        return [m.value for m in cls]


class Perfil(_Texto):
    CLIENTE = "CLIENTE"
    COZINHA = "COZINHA"
    ATENDENTE = "ATENDENTE"
    GERENTE = "GERENTE"
    ADMIN = "ADMIN"


PERFIS_DE_UNIDADE = (Perfil.COZINHA.value, Perfil.ATENDENTE.value, Perfil.GERENTE.value)
PERFIS_DE_EQUIPE = PERFIS_DE_UNIDADE + (Perfil.ADMIN.value,)


class CanalPedido(_Texto):
    APP = "APP"
    TOTEM = "TOTEM"
    BALCAO = "BALCAO"
    PICKUP = "PICKUP"
    WEB = "WEB"


class StatusPedido(_Texto):
    AGUARDANDO_PAGAMENTO = "AGUARDANDO_PAGAMENTO"
    RECEBIDO = "RECEBIDO"
    EM_PREPARO = "EM_PREPARO"
    PRONTO = "PRONTO"
    ENTREGUE = "ENTREGUE"
    CANCELADO = "CANCELADO"


# Fluxo operacional após o pagamento (o cancelamento tem endpoint próprio, com compensações).
TRANSICOES_OPERACIONAIS = {
    "RECEBIDO": "EM_PREPARO",
    "EM_PREPARO": "PRONTO",
    "PRONTO": "ENTREGUE",
}
STATUS_POR_PERFIL = {
    "COZINHA": {"EM_PREPARO", "PRONTO"},
    "ATENDENTE": {"ENTREGUE"},
    "GERENTE": {"EM_PREPARO", "PRONTO", "ENTREGUE"},
    "ADMIN": {"EM_PREPARO", "PRONTO", "ENTREGUE"},
}
# Estágios em que o estoque reservado volta ao saldo no cancelamento.
STATUS_COM_DEVOLUCAO_DE_ESTOQUE = ("AGUARDANDO_PAGAMENTO", "RECEBIDO")
STATUS_CANCELAVEIS_PELO_CLIENTE = ("AGUARDANDO_PAGAMENTO", "RECEBIDO")
STATUS_CANCELAVEIS_PELA_EQUIPE = ("AGUARDANDO_PAGAMENTO", "RECEBIDO", "EM_PREPARO", "PRONTO")


class FormaPagamento(_Texto):
    PIX = "PIX"
    CARTAO_CREDITO = "CARTAO_CREDITO"
    CARTAO_DEBITO = "CARTAO_DEBITO"


class TipoMovimentacao(_Texto):
    ENTRADA = "ENTRADA"
    SAIDA = "SAIDA"


class TipoCupom(_Texto):
    PERCENTUAL = "PERCENTUAL"
    VALOR_FIXO = "VALOR_FIXO"


class DiaSemana(_Texto):
    SEGUNDA = "SEGUNDA"
    TERCA = "TERCA"
    QUARTA = "QUARTA"
    QUINTA = "QUINTA"
    SEXTA = "SEXTA"
    SABADO = "SABADO"
    DOMINGO = "DOMINGO"

    @property
    def indice(self) -> int:
        return list(DiaSemana).index(self)


# Programa de fidelidade
VALOR_PONTO_CENTAVOS = 5          # 1 ponto = R$ 0,05
CENTAVOS_POR_PONTO_GANHO = 100    # 1 ponto a cada R$ 1,00 pago
LIMITE_RESGATE_PERCENTUAL = 50    # pontos cobrem no máximo 50% do pedido
FINALIDADE_FIDELIDADE = "FIDELIDADE_PONTOS"
DOC_TERMOS_USO = "TERMOS_USO"
DOC_AVISO_PRIVACIDADE = "AVISO_PRIVACIDADE"

"""Pedidos multicanal: criação idempotente, reserva de estoque, descontos, status e cancelamento."""
from __future__ import annotations

import hashlib
import json
import re

from flask import current_app, request

from raizesdonordeste.dto.validacao import Validador, corpo_json
from raizesdonordeste.exception.api_error import ApiError, acesso_negado, conflito, nao_encontrado
from raizesdonordeste.gateway.gateway_pagamento import GatewayIndisponivel
from raizesdonordeste.model.enums import (CanalPedido, STATUS_CANCELAVEIS_PELA_EQUIPE,
                                          STATUS_CANCELAVEIS_PELO_CLIENTE, STATUS_COM_DEVOLUCAO_DE_ESTOQUE,
                                          STATUS_POR_PERFIL, StatusPedido, TRANSICOES_OPERACIONAIS,
                                          VALOR_PONTO_CENTAVOS)
from raizesdonordeste.repository import (catalogo_repository, estoque_repository, fidelidade_repository,
                                         pedido_repository, promocao_repository, usuario_repository)
from raizesdonordeste.repository.database import conexao, paginar, transacao
from raizesdonordeste.service import fidelidade_service, promocao_service
from raizesdonordeste.service.autorizacao import opera_na_unidade
from raizesdonordeste.util.pseudonimizacao import pseudonimizar
from raizesdonordeste.util.tempo import agora, agora_iso

_CHAVE_RE = re.compile(r"^[A-Za-z0-9._:\-]{8,100}$")


def carregar_autorizado(conn, usuario, pedido_id: int):
    """Cliente só enxerga os próprios pedidos; equipe só os da sua unidade (ADMIN: todos).
    Fora do escopo responde 404 para não revelar a existência do pedido."""
    pedido = pedido_repository.buscar(conn, pedido_id)
    if pedido is None:
        raise nao_encontrado("Pedido")
    if usuario["perfil"] == "CLIENTE":
        if pedido["cliente_id"] != usuario["id"]:
            raise nao_encontrado("Pedido")
    elif not opera_na_unidade(usuario, pedido["unidade_id"]):
        raise nao_encontrado("Pedido")
    return pedido


# ===================================== criação =====================================
def _validar_chave(chave: str | None) -> str | None:
    if chave is None:
        return None
    if not _CHAVE_RE.match(chave):
        raise ApiError(422, "VALIDACAO_ERRO", "Idempotency-Key inválida.", [{
            "field": "Idempotency-Key", "issue": "use de 8 a 100 caracteres: letras, números, ., _, : ou -"}])
    return chave


def criar(usuario, chave_idempotencia: str | None) -> tuple[dict, bool]:
    """Retorna (pedido, criado). Repetir a mesma chave com o mesmo conteúdo devolve o pedido original."""
    corpo = corpo_json()
    chave = _validar_chave(chave_idempotencia)

    v = Validador(corpo)
    unidade_id = v.inteiro("unidadeId", minimo=1)
    canal = v.enum("canalPedido", CanalPedido.valores())
    cupom_codigo = v.texto("cupomCodigo", obrigatorio=False, maximo=40)
    pontos = v.inteiro("pontosResgatar", obrigatorio=False, minimo=0, padrao=0)
    cliente_id = v.inteiro("clienteId", obrigatorio=False, minimo=1)
    observacao = v.texto("observacao", obrigatorio=False, minimo=0, maximo=300)
    itens_brutos = corpo.get("itens")
    itens: list[tuple[int, int, int]] = []
    if not isinstance(itens_brutos, list) or not (1 <= len(itens_brutos) <= 30):
        v.erro("itens", "informe de 1 a 30 itens")
    else:
        for i, item in enumerate(itens_brutos):
            if not isinstance(item, dict):
                v.erro(f"itens[{i}]", "deve ser um objeto")
                continue
            iv = Validador(item, f"itens[{i}].", v.erros)
            produto_id = iv.inteiro("produtoId", minimo=1)
            quantidade = iv.inteiro("quantidade", minimo=1, maximo=50)
            itens.append((i, produto_id, quantidade))
    v.verificar()

    # Quem é o cliente do pedido: o próprio usuário, ou (pelo atendente) um cliente informado.
    if usuario["perfil"] == "CLIENTE":
        if cliente_id not in (None, usuario["id"]):
            raise acesso_negado("Clientes só podem criar pedidos para si mesmos.")
        cliente_id = usuario["id"]
    else:  # ATENDENTE
        if usuario["unidade_id"] != unidade_id:
            raise acesso_negado("O atendente só registra pedidos da sua unidade.")
        if cliente_id is None:
            raise ApiError(422, "VALIDACAO_ERRO", "Informe o cliente do pedido.",
                           [{"field": "clienteId", "issue": "obrigatório para pedidos registrados por funcionários"}])

    hash_requisicao = hashlib.sha256(json.dumps(corpo, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    with transacao() as conn:
        if chave:
            anterior = conn.execute("SELECT * FROM idempotencia_pedidos WHERE usuario_id=? AND chave=?",
                                    (usuario["id"], chave)).fetchone()
            if anterior:
                if anterior["hash_requisicao"] != hash_requisicao:
                    raise conflito("CHAVE_IDEMPOTENCIA_REUTILIZADA",
                                   "Esta Idempotency-Key já foi usada com um conteúdo diferente.")
                return pedido_repository.montar_dto(conn, anterior["pedido_id"]), False

        unidade = catalogo_repository.buscar_unidade(conn, unidade_id)
        if unidade is None or not unidade["ativa"]:
            raise nao_encontrado("Unidade")
        cliente = usuario_repository.buscar(conn, cliente_id)
        if cliente is None or cliente["perfil"] != "CLIENTE" or not cliente["ativo"]:
            raise nao_encontrado("Cliente")

        # --- itens, estoque e campanhas -------------------------------------------------
        mesclado: dict[int, list[int]] = {}
        for indice, produto_id, quantidade in itens:
            if produto_id in mesclado:
                mesclado[produto_id][0] += quantidade
            else:
                mesclado[produto_id] = [quantidade, indice]
        momento = agora()
        linhas, faltas = [], []
        for produto_id, (quantidade, indice) in mesclado.items():
            estoque = estoque_repository.buscar_por_unidade_produto(conn, unidade_id, produto_id)
            if estoque is None or not estoque["ativo"] or not estoque["produto_ativo"]:
                raise conflito("PRODUTO_INDISPONIVEL", "Produto não faz parte do cardápio desta unidade.",
                               [{"field": f"itens[{indice}].produtoId", "issue": "indisponível nesta unidade"}])
            if estoque["quantidade"] < quantidade:
                faltas.append({"field": f"itens[{indice}].quantidade", "issue": f"Disponível: {estoque['quantidade']}"})
                continue
            campanha = promocao_repository.campanha_vigente(conn, unidade_id, produto_id, momento)
            preco = estoque["preco_centavos"]
            desconto_unitario = preco * campanha["percentual_desconto"] // 100 if campanha else 0
            linhas.append({"estoque_id": estoque["id"], "produto_id": produto_id, "nome": estoque["produto_nome"],
                           "quantidade": quantidade, "preco": preco,
                           "desconto_linha": desconto_unitario * quantidade,
                           "campanha_id": campanha["id"] if campanha else None,
                           "total": (preco - desconto_unitario) * quantidade})
        if faltas:
            raise conflito("ESTOQUE_INSUFICIENTE", "Não há quantidade suficiente para um ou mais itens.", faltas)

        # --- valores --------------------------------------------------------------------
        subtotal = sum(l["preco"] * l["quantidade"] for l in linhas)
        desconto_campanhas = sum(l["desconto_linha"] for l in linhas)
        apos_campanhas = subtotal - desconto_campanhas
        cupom, desconto_cupom = (None, 0)
        if cupom_codigo:
            cupom, desconto_cupom = promocao_service.aplicar_cupom(conn, cupom_codigo, unidade_id, apos_campanhas)
        apos_cupom = apos_campanhas - desconto_cupom
        desconto_pontos = fidelidade_service.validar_resgate(conn, cliente_id, pontos, apos_cupom)
        total = apos_cupom - desconto_pontos

        # --- gravação -------------------------------------------------------------------
        gratuito = total == 0
        status, status_pagamento = ("RECEBIDO", "ISENTO") if gratuito else ("AGUARDANDO_PAGAMENTO", "PENDENTE")
        agora_s = agora_iso()
        pedido_id = conn.execute(
            "INSERT INTO pedidos (cliente_id, criado_por_id, unidade_id, canal, status, status_pagamento,"
            " subtotal_centavos, desconto_campanhas_centavos, desconto_cupom_centavos, desconto_pontos_centavos,"
            " total_centavos, cupom_id, pontos_resgatados, observacao, criado_em, atualizado_em)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cliente_id, usuario["id"], unidade_id, canal, status, status_pagamento, subtotal, desconto_campanhas,
             desconto_cupom, desconto_pontos, total, cupom["id"] if cupom else None,
             desconto_pontos // VALOR_PONTO_CENTAVOS, observacao, agora_s, agora_s)).lastrowid
        responsavel = pseudonimizar(usuario["email"])
        for l in linhas:
            conn.execute(
                "INSERT INTO itens_pedido (pedido_id, produto_id, nome, quantidade, preco_unitario_centavos,"
                " desconto_campanha_centavos, campanha_id, total_centavos) VALUES (?,?,?,?,?,?,?,?)",
                (pedido_id, l["produto_id"], l["nome"], l["quantidade"], l["preco"], l["desconto_linha"],
                 l["campanha_id"], l["total"]))
            estoque_repository.aplicar_movimento(conn, l["estoque_id"], "SAIDA", l["quantidade"],
                                                 "RESERVA_PEDIDO", responsavel, pedido_id)
        if cupom:
            promocao_service.registrar_uso_cupom(conn, cupom["id"])
        if desconto_pontos:
            fidelidade_repository.movimentar_pontos(conn, cliente_id, -(desconto_pontos // VALOR_PONTO_CENTAVOS),
                                                    "RESGATE_PEDIDO", pedido_id)
        pedido_repository.registrar_historico(conn, pedido_id, None, status, usuario["id"])
        if chave:
            conn.execute("INSERT INTO idempotencia_pedidos (usuario_id, chave, hash_requisicao, pedido_id, criado_em)"
                         " VALUES (?,?,?,?,?)", (usuario["id"], chave, hash_requisicao, pedido_id, agora_s))
        return pedido_repository.montar_dto(conn, pedido_id), True


# ===================================== consulta ====================================
def listar(usuario) -> dict:
    erros, filtros, params = [], ["1=1"], []
    canal, status, unidade_bruta = (request.args.get("canalPedido"), request.args.get("status"),
                                    request.args.get("unidadeId"))
    if canal is not None:
        if canal.upper() not in CanalPedido.valores():
            erros.append({"field": "canalPedido", "issue": "valores aceitos: " + ", ".join(CanalPedido.valores())})
        else:
            filtros.append("canal = ?")
            params.append(canal.upper())
    if status is not None:
        if status.upper() not in StatusPedido.valores():
            erros.append({"field": "status", "issue": "valores aceitos: " + ", ".join(StatusPedido.valores())})
        else:
            filtros.append("status = ?")
            params.append(status.upper())
    unidade_filtro = None
    if unidade_bruta is not None:
        if not unidade_bruta.isdigit() or int(unidade_bruta) < 1:
            erros.append({"field": "unidadeId", "issue": "deve ser um inteiro positivo"})
        else:
            unidade_filtro = int(unidade_bruta)
    if erros:
        raise ApiError(422, "VALIDACAO_ERRO", "Filtros inválidos.", erros)

    if usuario["perfil"] == "CLIENTE":
        filtros.append("cliente_id = ?")
        params.append(usuario["id"])
        if unidade_filtro:
            filtros.append("unidade_id = ?")
            params.append(unidade_filtro)
    elif usuario["perfil"] == "ADMIN":
        if unidade_filtro:
            filtros.append("unidade_id = ?")
            params.append(unidade_filtro)
    else:
        if unidade_filtro not in (None, usuario["unidade_id"]):
            raise acesso_negado("Você só consulta pedidos da sua unidade.")
        filtros.append("unidade_id = ?")
        params.append(usuario["unidade_id"])
    conn = conexao()
    return paginar(f"SELECT id FROM pedidos WHERE {' AND '.join(filtros)} ORDER BY id DESC", params,
                   lambda linha: pedido_repository.montar_dto(conn, linha["id"]))


def buscar(usuario, pedido_id: int) -> dict:
    conn = conexao()
    carregar_autorizado(conn, usuario, pedido_id)
    return pedido_repository.montar_dto(conn, pedido_id)


# ================================ status operacional ===============================
def atualizar_status(usuario, pedido_id: int) -> dict:
    v = Validador(corpo_json())
    novo = v.enum("status", StatusPedido.valores())
    v.verificar()
    if novo == "CANCELADO":
        raise ApiError(422, "STATUS_INVALIDO", "Para cancelar use POST /pedidos/{id}/cancelamento, "
                       "que executa as compensações de estoque, pagamento e pontos.",
                       [{"field": "status", "issue": "use o endpoint de cancelamento"}])
    with transacao() as conn:
        pedido = carregar_autorizado(conn, usuario, pedido_id)
        if novo not in STATUS_POR_PERFIL[usuario["perfil"]]:
            raise acesso_negado("Seu perfil não pode definir este status.")
        esperado = TRANSICOES_OPERACIONAIS.get(pedido["status"])
        if esperado != novo:
            raise conflito("TRANSICAO_DE_STATUS_INVALIDA",
                           f"Não é possível mudar de {pedido['status']} para {novo}.",
                           [{"field": "status", "issue": "próximo status permitido: " + (esperado or "nenhum")}])
        conn.execute("UPDATE pedidos SET status=?, atualizado_em=? WHERE id=?", (novo, agora_iso(), pedido_id))
        pedido_repository.registrar_historico(conn, pedido_id, pedido["status"], novo, usuario["id"])
        return pedido_repository.montar_dto(conn, pedido_id)


# ===================================== cancelamento ================================
def cancelar(usuario, pedido_id: int) -> dict:
    """Cancela o pedido e executa as compensações aplicáveis ao estágio atual:
      - estoque volta ao saldo somente em AGUARDANDO_PAGAMENTO/RECEBIDO (depois, os itens foram consumidos);
      - pagamento aprovado é estornado no gateway ANTES de cancelar (503 se indisponível, sem alterar nada);
      - cupom é liberado, pontos resgatados voltam e pontos concedidos são retirados (saldo pode ficar devedor).
    A transação BEGIN IMMEDIATE serializa cancelamentos concorrentes do mesmo pedido."""
    v = Validador(corpo_json(obrigatorio=False))
    motivo = v.texto("motivo", obrigatorio=False, minimo=0, maximo=200)
    v.verificar()
    gateway = current_app.extensions["gateway"]
    with transacao() as conn:
        pedido = carregar_autorizado(conn, usuario, pedido_id)
        permitidos = STATUS_CANCELAVEIS_PELO_CLIENTE if usuario["perfil"] == "CLIENTE" else STATUS_CANCELAVEIS_PELA_EQUIPE
        if pedido["status"] not in permitidos:
            raise conflito("PEDIDO_NAO_CANCELAVEL",
                           f"Pedidos {pedido['status']} não podem ser cancelados por este perfil.")
        status_pagamento = pedido["status_pagamento"]
        if status_pagamento == "APROVADO":
            requisicao = {"referenciaPagamento": conn.execute(
                "SELECT referencia_gateway FROM pagamento_tentativas WHERE pedido_id=? AND tipo='PAGAMENTO'"
                " AND status='APROVADO' ORDER BY id DESC LIMIT 1", (pedido_id,)).fetchone()["referencia_gateway"],
                "valor": {"centavos": pedido["total_centavos"], "moeda": "BRL"}, "motivo": motivo}
            try:
                resposta = gateway.estornar(requisicao)
            except GatewayIndisponivel:
                raise ApiError(503, "GATEWAY_PAGAMENTO_INDISPONIVEL",
                               "O gateway de pagamento está indisponível. Nada foi alterado; tente novamente.")
            forma = conn.execute("SELECT forma_pagamento FROM pagamento_tentativas WHERE pedido_id=?"
                                 " AND tipo='PAGAMENTO' AND status='APROVADO' ORDER BY id DESC LIMIT 1",
                                 (pedido_id,)).fetchone()["forma_pagamento"]
            pedido_repository.registrar_tentativa(conn, pedido_id, "ESTORNO", forma, resposta.status,
                                                  pedido["total_centavos"], resposta.referencia,
                                                  requisicao, resposta.payload)
            status_pagamento = "ESTORNADO"
        elif status_pagamento in ("PENDENTE", "RECUSADO"):
            status_pagamento = "CANCELADO"

        if pedido["status"] in STATUS_COM_DEVOLUCAO_DE_ESTOQUE:
            responsavel = pseudonimizar(usuario["email"])
            for item in conn.execute("SELECT produto_id, quantidade FROM itens_pedido WHERE pedido_id=?",
                                     (pedido_id,)).fetchall():
                estoque = estoque_repository.buscar_por_unidade_produto(conn, pedido["unidade_id"], item["produto_id"])
                estoque_repository.aplicar_movimento(conn, estoque["id"], "ENTRADA", item["quantidade"],
                                                     "DEVOLUCAO_CANCELAMENTO", responsavel, pedido_id)
        if pedido["cupom_id"]:
            promocao_service.liberar_uso_cupom(conn, pedido["cupom_id"])
        fidelidade_service.desfazer_no_cancelamento(conn, pedido)

        conn.execute("UPDATE pedidos SET status='CANCELADO', status_pagamento=?, atualizado_em=? WHERE id=?",
                     (status_pagamento, agora_iso(), pedido_id))
        pedido_repository.registrar_historico(conn, pedido_id, pedido["status"], "CANCELADO", usuario["id"])
        return pedido_repository.montar_dto(conn, pedido_id)

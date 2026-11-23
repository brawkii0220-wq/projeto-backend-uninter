from __future__ import annotations

import json

from raizesdonordeste.util.tempo import agora_iso


def buscar(conn, pedido_id: int):
    return conn.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,)).fetchone()


def registrar_historico(conn, pedido_id: int, de_status: str | None, para_status: str, usuario_id: int | None) -> None:
    conn.execute("INSERT INTO historico_status_pedido (pedido_id, de_status, para_status, usuario_id, criado_em)"
                 " VALUES (?,?,?,?,?)", (pedido_id, de_status, para_status, usuario_id, agora_iso()))


def montar_dto(conn, pedido_id: int) -> dict:
    p = buscar(conn, pedido_id)
    cupom = conn.execute("SELECT codigo FROM cupons WHERE id=?", (p["cupom_id"],)).fetchone() if p["cupom_id"] else None
    itens = conn.execute("SELECT * FROM itens_pedido WHERE pedido_id=? ORDER BY id", (pedido_id,)).fetchall()
    historico = conn.execute("SELECT * FROM historico_status_pedido WHERE pedido_id=? ORDER BY id",
                             (pedido_id,)).fetchall()
    return {
        "id": p["id"], "clienteId": p["cliente_id"], "unidadeId": p["unidade_id"], "canalPedido": p["canal"],
        "status": p["status"], "statusPagamento": p["status_pagamento"],
        "subtotalCentavos": p["subtotal_centavos"],
        "descontoCampanhasCentavos": p["desconto_campanhas_centavos"],
        "descontoCupomCentavos": p["desconto_cupom_centavos"],
        "descontoPontosCentavos": p["desconto_pontos_centavos"],
        "totalCentavos": p["total_centavos"],
        "cupomCodigo": cupom["codigo"] if cupom else None,
        "pontosResgatados": p["pontos_resgatados"], "pontosConcedidos": p["pontos_concedidos"],
        "observacao": p["observacao"], "criadoEm": p["criado_em"], "atualizadoEm": p["atualizado_em"],
        "itens": [{"produtoId": i["produto_id"], "nome": i["nome"], "quantidade": i["quantidade"],
                   "precoUnitarioCentavos": i["preco_unitario_centavos"],
                   "descontoCampanhaCentavos": i["desconto_campanha_centavos"],
                   "campanhaId": i["campanha_id"], "totalCentavos": i["total_centavos"]} for i in itens],
        "historico": [{"de": h["de_status"], "para": h["para_status"], "usuarioId": h["usuario_id"],
                       "em": h["criado_em"]} for h in historico],
    }


def tentativa_dto(t) -> dict:
    return {"id": t["id"], "pedidoId": t["pedido_id"], "tipo": t["tipo"], "formaPagamento": t["forma_pagamento"],
            "status": t["status"], "valorCentavos": t["valor_centavos"],
            "referenciaGateway": t["referencia_gateway"], "criadoEm": t["criado_em"],
            "gateway": {"requisicao": json.loads(t["payload_requisicao"]),
                        "resposta": json.loads(t["payload_resposta"])}}


def registrar_tentativa(conn, pedido_id, tipo, forma, status, valor, referencia, requisicao, resposta) -> int:
    return conn.execute(
        "INSERT INTO pagamento_tentativas (pedido_id, tipo, forma_pagamento, status, valor_centavos,"
        " referencia_gateway, payload_requisicao, payload_resposta, criado_em) VALUES (?,?,?,?,?,?,?,?,?)",
        (pedido_id, tipo, forma, status, valor, referencia,
         json.dumps(requisicao, ensure_ascii=False), json.dumps(resposta, ensure_ascii=False),
         agora_iso())).lastrowid

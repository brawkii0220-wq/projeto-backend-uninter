"""Gera o contrato OpenAPI 3.1 a partir das rotas registradas (docstrings + metadados de segurança)."""
from __future__ import annotations

import re

from flask import Flask

from raizesdonordeste.config.settings import CONTEXT_PATH

# Operações cujo código de sucesso foge da regra (POST=201, DELETE=204, demais=200).
_SUCESSO_EXCECAO = {
    ("POST", "/auth/login"): "200",
    ("POST", "/pedidos/{pedido_id}/cancelamento"): "200",
}
_UNIDADE = {"nome": "Unidade Boa Viagem", "cidade": "Recife"}
_PRODUTO = {"nome": "Baião de Dois", "descricao": "Baião com queijo coalho", "categoria": "pratos",
            "precoCentavos": 2800}
_CAMPANHA = {"nome": "Quarta do Cuscuz", "descricao": "15% no cuscuz às quartas", "produtoId": 2,
             "unidadeId": 1, "percentualDesconto": 15, "dataInicio": "2027-01-01T00:00:00Z",
             "dataFim": "2027-12-31T23:59:59Z", "diasSemana": ["QUARTA"]}
_CUPOM = {"codigo": "VOLTA10", "descricao": "10% de volta", "tipo": "PERCENTUAL", "valor": 10,
          "valorMinimoCentavos": 2000, "unidadeId": 1, "validadeFim": "2027-12-31T23:59:59Z", "limiteUso": 100}
# Exemplos de corpo por operação (método, caminho).
_EXEMPLOS = {
    ("POST", "/auth/login"): {"email": "cliente@raizes.com", "senha": "cliente123"},
    ("POST", "/usuarios"): {
        "nome": "Maria da Silva", "email": "maria@exemplo.com", "senha": "senha-segura-1",
        "telefone": "(81) 99999-0000", "cpf": "529.982.247-25", "aceiteTermosUso": True,
        "versaoTermosUso": "1.0", "hashTermosUso": "<hashSha256 retornado por GET /documentos-legais/termos-uso>"},
    ("PUT", "/usuarios/{usuario_id}"): {"nome": "Maria S. Souza", "telefone": "(81) 98888-0000",
                                        "perfil": "GERENTE", "unidadeId": 1},
    ("POST", "/unidades"): _UNIDADE,
    ("PUT", "/unidades/{unidade_id}"): {**_UNIDADE, "ativa": True},
    ("POST", "/produtos"): _PRODUTO,
    ("PUT", "/produtos/{produto_id}"): _PRODUTO,
    ("POST", "/estoque"): {"unidadeId": 1, "produtoId": 1, "quantidade": 50},
    ("PUT", "/estoque/{estoque_id}"): {"quantidade": 40},
    ("POST", "/estoque/{estoque_id}/movimentacoes"): {"tipo": "ENTRADA", "quantidade": 10,
                                                      "motivo": "REPOSICAO_FORNECEDOR"},
    ("POST", "/pedidos"): {"unidadeId": 1, "canalPedido": "APP", "cupomCodigo": "NORDESTE10",
                           "pontosResgatar": 0, "observacao": "Sem pimenta",
                           "itens": [{"produtoId": 2, "quantidade": 2}, {"produtoId": 3, "quantidade": 1}]},
    ("PATCH", "/pedidos/{pedido_id}/status"): {"status": "EM_PREPARO"},
    ("POST", "/pedidos/{pedido_id}/cancelamento"): {"motivo": "Desistência do cliente"},
    ("POST", "/pedidos/{pedido_id}/pagamento"): {"formaPagamento": "PIX"},
    ("PUT", "/documentos-legais/termos-uso/aceite"): {"versao": "1.0",
                                                      "hashSha256": "<hash dos termos vigentes>"},
    ("POST", "/campanhas"): _CAMPANHA,
    ("PUT", "/campanhas/{campanha_id}"): _CAMPANHA,
    ("POST", "/cupons"): _CUPOM,
    ("PUT", "/cupons/{cupom_id}"): {**_CUPOM, "ativo": True},
}
_CORPO_OPCIONAL = ("/cancelamento", "/aceite")      # corpo pode ser omitido
_SEM_CORPO = ("/consentimento",)                    # POST sem corpo
_TITULOS_ERRO = {
    "400": "Requisição malformada", "401": "Não autenticado ou token inválido",
    "403": "Perfil sem permissão", "404": "Recurso inexistente ou fora do escopo",
    "409": "Conflito de regra de negócio", "422": "Erro de validação", "503": "Gateway indisponível",
}


def _sucesso(metodo: str, caminho: str) -> str:
    if (metodo, caminho) in _SUCESSO_EXCECAO:
        return _SUCESSO_EXCECAO[(metodo, caminho)]
    return {"POST": "201", "DELETE": "204"}.get(metodo, "200")


def gerar(app: Flask) -> dict:
    caminhos: dict = {}
    for regra in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if not regra.rule.startswith(CONTEXT_PATH + "/"):
            continue
        funcao = app.view_functions[regra.endpoint]
        meta = getattr(funcao, "_openapi", None)
        if meta is None:
            continue
        caminho = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", regra.rule[len(CONTEXT_PATH):])
        linhas = [l.strip() for l in (funcao.__doc__ or "").strip().splitlines()]
        resumo = linhas[0] if linhas else regra.endpoint
        descricao = " ".join(l for l in linhas[1:] if l)
        if meta["perfis"]:
            descricao = (descricao + " " if descricao else "") + "**Perfis:** " + ", ".join(meta["perfis"]) + "."
        for metodo in sorted(regra.methods - {"HEAD", "OPTIONS"}):
            sucesso = _sucesso(metodo, caminho)
            respostas = {sucesso: {"description": "Sucesso"}}
            if sucesso not in ("204",) and metodo != "DELETE":
                respostas[sucesso]["content"] = {"application/json": {"schema": {"type": "object"}}}
            erros = []
            if metodo in ("POST", "PUT", "PATCH"):
                erros += ["400", "422"]
            if not meta["publico"]:
                erros.append("401")
                if meta["perfis"]:
                    erros.append("403")
            if regra.arguments:
                erros.append("404")
            if caminho == "/auth/login":
                erros.append("401")                     # CREDENCIAIS_INVALIDAS (rota pública)
            elif metodo != "GET" or "pedidos" in caminho:
                erros.append("409")
            if caminho.endswith(("/pagamento", "/cancelamento")):
                erros.append("503")
            for codigo in sorted(set(erros)):
                respostas[codigo] = {"description": _TITULOS_ERRO[codigo], "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/ErroResposta"}}}}
            operacao = {
                "tags": [regra.endpoint.split(".")[0]],
                "summary": resumo, "operationId": regra.endpoint.replace(".", "_"), "responses": respostas,
            }
            if descricao:
                operacao["description"] = descricao
            if not meta["publico"]:
                operacao["security"] = [{"bearerAuth": []}]
            else:
                operacao["security"] = []
            parametros = [{"name": nome, "in": "path", "required": True, "schema": {"type": "integer"}}
                          for nome in sorted(regra.arguments)]
            if metodo == "GET" and funcao.__name__.startswith("listar") and "paginado" in resumo.lower():
                parametros += [{"name": "page", "in": "query", "schema": {"type": "integer", "default": 0}},
                               {"name": "limit", "in": "query",
                                "schema": {"type": "integer", "default": 10, "maximum": 100}}]
            if parametros:
                operacao["parameters"] = parametros
            if metodo in ("POST", "PUT", "PATCH") and not caminho.endswith(_SEM_CORPO):
                conteudo = {"schema": {"type": "object"}}
                if (metodo, caminho) in _EXEMPLOS:
                    conteudo["example"] = _EXEMPLOS[(metodo, caminho)]
                operacao["requestBody"] = {"required": not caminho.endswith(_CORPO_OPCIONAL),
                                           "content": {"application/json": conteudo}}
            caminhos.setdefault(caminho, {})[metodo.lower()] = operacao
    tags = sorted({op["tags"][0] for ops in caminhos.values() for op in ops.values()})
    return {
        "openapi": "3.1.0",
        "info": {"title": "Raízes do Nordeste - API", "version": "1.0.0",
                 "description": "API REST de pedidos multicanal, estoque por unidade, fidelidade, campanhas, "
                                "cupons e pagamento simulado. Valores monetários em centavos; datas em UTC "
                                "(AAAA-MM-DDTHH:MM:SSZ)."},
        "servers": [{"url": CONTEXT_PATH}],
        "tags": [{"name": t} for t in tags],
        "paths": caminhos,
        "components": {
            "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}},
            "schemas": {"ErroResposta": {"type": "object", "properties": {
                "error": {"type": "string", "example": "ESTOQUE_INSUFICIENTE"},
                "message": {"type": "string"},
                "details": {"type": "array", "items": {"type": "object", "properties": {
                    "field": {"type": "string"}, "issue": {"type": "string"}}}},
                "timestamp": {"type": "string", "format": "date-time"},
                "path": {"type": "string"}, "requestId": {"type": "string"}}}},
        },
    }


def contar_operacoes(spec: dict) -> int:
    return sum(len(ops) for ops in spec["paths"].values())

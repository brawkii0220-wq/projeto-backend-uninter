"""Cenário da coleção Postman (fonte única de verdade).

O mesmo cenário gera `postman/raizes_do_nordeste.postman_collection.json` e é reexecutado contra a API em
`tests/test_postman.py`, então a coleção não pode divergir do comportamento real sem o teste falhar.

Uso (na raiz do projeto):  python scripts/cenario_postman.py

Pré-requisito para rodar a coleção no Postman/Newman: API no perfil `dev` (seed + pagamento determinístico),
em http://localhost:8080/api  (variável de coleção `baseUrl`).

Campos de cada passo:
  nome, metodo, caminho   -> a requisição ({{variavel}} é substituída pelas variáveis da coleção)
  auth                    -> variável com o token JWT (ex.: "tokenCliente")
  corpo, headers          -> corpo JSON e cabeçalhos extras
  esperado                -> status HTTP aceito (int ou lista)
  espera                  -> {"caminho.no.json": valor}; "{{var}}" compara com o valor guardado
  salvar                  -> {"variavel": "caminho.no.json"} guardado para os próximos passos
  gerar                   -> {"variavel": "prefixo-{ts}"} gerado antes de enviar (valores únicos por execução)
"""
from __future__ import annotations

import json
import pathlib
import re
import uuid

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "postman" / "raizes_do_nordeste.postman_collection.json"
BASE_URL = "http://localhost:8080/api"
_VARIAVEL = re.compile(r"\{\{(\w+)\}\}")


def login(perfil: str, senha: str, variavel: str, nome: str) -> dict:
    return dict(nome=nome, metodo="POST", caminho="/auth/login", esperado=200,
                corpo={"email": f"{perfil}@raizes.com", "senha": senha},
                espera={"tipo": "Bearer"}, salvar={variavel: "token"})


_CAMPANHA = {"nome": "Postman - Suco às quartas", "produtoId": 3, "unidadeId": 1, "percentualDesconto": 10,
             "dataInicio": "2040-01-01T00:00:00Z", "dataFim": "2040-12-31T23:59:59Z", "diasSemana": ["QUARTA"]}
_PEDIDO = {"unidadeId": 1, "canalPedido": "APP", "itens": [{"produtoId": 2, "quantidade": 2}]}
_STATUS = "/pedidos/{{pedidoId}}/status"
_PAGAMENTO = "/pedidos/{{pedidoId}}/pagamento"

STEPS: list[dict] = [
    # --- autenticação e cadastro ---------------------------------------------------------------
    login("cliente", "cliente123", "tokenCliente", "Login do cliente"),
    login("cozinha", "cozinha123", "tokenCozinha", "Login da cozinha"),
    login("atendente", "atendente123", "tokenAtendente", "Login do atendente"),
    login("gerente", "gerente123", "tokenGerente", "Login do gerente"),
    login("admin", "admin123", "tokenAdmin", "Login do administrador"),
    dict(nome="Login com senha incorreta é rejeitado", metodo="POST", caminho="/auth/login", esperado=401,
         corpo={"email": "cliente@raizes.com", "senha": "senha-errada"}, espera={"error": "CREDENCIAIS_INVALIDAS"}),
    dict(nome="Consultar termos de uso vigentes (público)", metodo="GET", caminho="/documentos-legais/termos-uso",
         esperado=200, salvar={"versaoTermos": "versao", "hashTermos": "hashSha256"}),
    dict(nome="Cadastrar cliente com aceite dos termos", metodo="POST", caminho="/usuarios", esperado=201,
         gerar={"sufixo": "{ts}"}, espera={"perfil": "CLIENTE"},
         corpo={"nome": "Cliente Postman", "email": "cliente-{{sufixo}}@exemplo.com", "senha": "senha-forte-123",
                "aceiteTermosUso": True, "versaoTermosUso": "{{versaoTermos}}", "hashTermosUso": "{{hashTermos}}"}),
    dict(nome="Cadastro sem aceitar os termos (422)", metodo="POST", caminho="/usuarios", esperado=422,
         espera={"error": "VALIDACAO_ERRO"},
         corpo={"nome": "Sem Aceite", "email": "sem-aceite@exemplo.com", "senha": "senha-forte-123",
                "aceiteTermosUso": False, "versaoTermosUso": "{{versaoTermos}}", "hashTermosUso": "{{hashTermos}}"}),
    # --- catálogo e autorização ------------------------------------------------------------------
    dict(nome="Listar produtos (público, paginado)", metodo="GET", caminho="/produtos?page=0&limit=10", esperado=200),
    dict(nome="Disponibilidade dos produtos na unidade 1", metodo="GET", caminho="/produtos/unidade/1",
         auth="tokenCliente", esperado=200),
    dict(nome="Cliente não lista usuários (403)", metodo="GET", caminho="/usuarios", auth="tokenCliente",
         esperado=403, espera={"error": "ACESSO_NEGADO"}),
    dict(nome="Pedido inexistente (404)", metodo="GET", caminho="/pedidos/999999", auth="tokenCliente",
         esperado=404, espera={"error": "RECURSO_NAO_ENCONTRADO"}),
    dict(nome="Consentir com o programa de fidelidade", metodo="POST", caminho="/fidelidade/consentimento",
         auth="tokenCliente", esperado=[200, 201], espera={"consentimentoAtivo": True}),
    # --- pedido idempotente e estoque ------------------------------------------------------------
    dict(nome="Criar pedido com Idempotency-Key", metodo="POST", caminho="/pedidos", auth="tokenCliente",
         esperado=201, gerar={"chaveIdem": "postman-{ts}"}, headers={"Idempotency-Key": "{{chaveIdem}}"},
         corpo=_PEDIDO, salvar={"pedidoId": "id"},
         espera={"status": "AGUARDANDO_PAGAMENTO", "totalCentavos": 2000}),
    dict(nome="Repetir a mesma chave devolve o pedido original", metodo="POST", caminho="/pedidos",
         auth="tokenCliente", esperado=200, headers={"Idempotency-Key": "{{chaveIdem}}"}, corpo=_PEDIDO,
         espera={"id": "{{pedidoId}}"}),
    dict(nome="Mesma chave com conteúdo diferente (409)", metodo="POST", caminho="/pedidos", auth="tokenCliente",
         esperado=409, headers={"Idempotency-Key": "{{chaveIdem}}"},
         corpo={**_PEDIDO, "itens": [{"produtoId": 2, "quantidade": 3}]},
         espera={"error": "CHAVE_IDEMPOTENCIA_REUTILIZADA"}),
    dict(nome="Gerente da unidade reduz o estoque da Carne de Sol", metodo="PUT", caminho="/estoque/4",
         auth="tokenGerente", esperado=200, corpo={"quantidade": 1}, espera={"quantidade": 1}),
    dict(nome="Pedido acima do estoque (409)", metodo="POST", caminho="/pedidos", auth="tokenCliente", esperado=409,
         corpo={"unidadeId": 1, "canalPedido": "WEB", "itens": [{"produtoId": 4, "quantidade": 2}]},
         espera={"error": "ESTOQUE_INSUFICIENTE", "details.0.issue": "Disponível: 1"}),
    dict(nome="Restaurar o estoque da Carne de Sol", metodo="PUT", caminho="/estoque/4", auth="tokenGerente",
         esperado=200, corpo={"quantidade": 50}, espera={"quantidade": 50}),
    # --- pagamento (gateway simulado) -------------------------------------------------------------
    dict(nome="Cozinha não inicia pedido sem pagamento (409)", metodo="PATCH", caminho=_STATUS, auth="tokenCozinha",
         esperado=409, corpo={"status": "EM_PREPARO"}, espera={"error": "TRANSICAO_DE_STATUS_INVALIDA"}),
    dict(nome="Pagamento recusado pelo gateway", metodo="POST", caminho=_PAGAMENTO, auth="tokenCliente",
         esperado=201, headers={"X-Forcar-Status-Pagamento": "RECUSADO"}, corpo={"formaPagamento": "CARTAO_CREDITO"},
         espera={"status": "RECUSADO", "pedidoStatus": "AGUARDANDO_PAGAMENTO", "numeroTentativa": 1}),
    dict(nome="Gateway indisponível (503) não consome tentativa", metodo="POST", caminho=_PAGAMENTO,
         auth="tokenCliente", esperado=503, headers={"X-Forcar-Status-Pagamento": "INDISPONIVEL"},
         corpo={"formaPagamento": "PIX"}, espera={"error": "GATEWAY_PAGAMENTO_INDISPONIVEL"}),
    dict(nome="Pagamento aprovado (PIX)", metodo="POST", caminho=_PAGAMENTO, auth="tokenCliente", esperado=201,
         headers={"X-Forcar-Status-Pagamento": "APROVADO"}, corpo={"formaPagamento": "PIX"},
         espera={"status": "APROVADO", "pedidoStatus": "RECEBIDO", "numeroTentativa": 2,
                 "gateway.resposta.status": "APROVADO"}),
    dict(nome="Histórico auditável de tentativas", metodo="GET", caminho="/pedidos/{{pedidoId}}/pagamento/tentativas",
         auth="tokenCliente", esperado=200, espera={"0.status": "RECUSADO", "1.status": "APROVADO"}),
    # --- fluxo operacional ------------------------------------------------------------------------
    dict(nome="Cliente não altera status operacional (403)", metodo="PATCH", caminho=_STATUS, auth="tokenCliente",
         esperado=403, corpo={"status": "EM_PREPARO"}),
    dict(nome="Cozinha inicia o preparo", metodo="PATCH", caminho=_STATUS, auth="tokenCozinha", esperado=200,
         corpo={"status": "EM_PREPARO"}, espera={"status": "EM_PREPARO"}),
    dict(nome="Cozinha marca como pronto", metodo="PATCH", caminho=_STATUS, auth="tokenCozinha", esperado=200,
         corpo={"status": "PRONTO"}, espera={"status": "PRONTO"}),
    dict(nome="Atendente entrega o pedido", metodo="PATCH", caminho=_STATUS, auth="tokenAtendente", esperado=200,
         corpo={"status": "ENTREGUE"}, espera={"status": "ENTREGUE"}),
    dict(nome="Saldo de fidelidade do cliente", metodo="GET", caminho="/fidelidade/saldo", auth="tokenCliente",
         esperado=200, espera={"consentimentoAtivo": True}),
    dict(nome="Pedido entregue não pode ser cancelado (409)", metodo="POST",
         caminho="/pedidos/{{pedidoId}}/cancelamento", auth="tokenAdmin", esperado=409,
         espera={"error": "PEDIDO_NAO_CANCELAVEL"}),
    # --- cancelamento com estorno -------------------------------------------------------------------
    dict(nome="Criar pedido para cancelar", metodo="POST", caminho="/pedidos", auth="tokenCliente", esperado=201,
         corpo={"unidadeId": 1, "canalPedido": "TOTEM", "itens": [{"produtoId": 3, "quantidade": 1}]},
         salvar={"pedidoCancelarId": "id"}),
    dict(nome="Pagar o pedido que será cancelado", metodo="POST", caminho="/pedidos/{{pedidoCancelarId}}/pagamento",
         auth="tokenCliente", esperado=201, headers={"X-Forcar-Status-Pagamento": "APROVADO"},
         corpo={"formaPagamento": "PIX"}, espera={"status": "APROVADO"}),
    dict(nome="Cancelar pedido pago estorna o pagamento", metodo="POST",
         caminho="/pedidos/{{pedidoCancelarId}}/cancelamento", auth="tokenCliente", esperado=200,
         corpo={"motivo": "Desistência do cliente"}, espera={"status": "CANCELADO", "statusPagamento": "ESTORNADO"}),
    # --- campanhas, cupons e administração ------------------------------------------------------------
    dict(nome="Gerente cria campanha (409 se já existir de uma execução anterior)", metodo="POST",
         caminho="/campanhas", auth="tokenGerente", esperado=[201, 409], corpo=_CAMPANHA),
    dict(nome="Campanha com período sobreposto é rejeitada (409)", metodo="POST", caminho="/campanhas",
         auth="tokenGerente", esperado=409, corpo=_CAMPANHA, espera={"error": "CAMPANHA_PERIODO_SOBREPOSTO"}),
    dict(nome="Gerente cria cupom local", metodo="POST", caminho="/cupons", auth="tokenGerente", esperado=201,
         corpo={"codigo": "PM{{sufixo}}", "tipo": "PERCENTUAL", "valor": 10, "unidadeId": 1},
         espera={"usos": 0, "unidadeId": 1}),
    dict(nome="Cliente não cria cupom (403)", metodo="POST", caminho="/cupons", auth="tokenCliente", esperado=403,
         corpo={"codigo": "NAOPODE", "tipo": "PERCENTUAL", "valor": 10}),
    dict(nome="Administrador lista unidades", metodo="GET", caminho="/unidades?page=0&limit=10",
         auth="tokenAdmin", esperado=200),
    dict(nome="Contrato OpenAPI disponível (perfil dev)", metodo="GET", caminho="/v3/api-docs", esperado=200,
         espera={"openapi": "3.1.0"}),
]


# ------------------------------------------------------------------ utilitários compartilhados
def substituir(valor, variaveis: dict):
    """Troca {{var}} em textos (recursivamente). Uma string que é só `{{var}}` vira o valor original."""
    if isinstance(valor, str):
        inteira = _VARIAVEL.fullmatch(valor)
        if inteira:
            return variaveis[inteira.group(1)]
        return _VARIAVEL.sub(lambda m: str(variaveis[m.group(1)]), valor)
    if isinstance(valor, list):
        return [substituir(v, variaveis) for v in valor]
    if isinstance(valor, dict):
        return {k: substituir(v, variaveis) for k, v in valor.items()}
    return valor


def extrair(corpo, caminho: str):
    """Lê 'content.0.id' em um JSON já carregado."""
    atual = corpo
    for parte in caminho.split("."):
        atual = atual[int(parte)] if isinstance(atual, list) else atual[parte]
    return atual


def codigos(passo: dict) -> list[int]:
    esperado = passo["esperado"]
    return esperado if isinstance(esperado, list) else [esperado]


def variaveis_usadas(passo: dict) -> set[str]:
    texto = json.dumps({k: passo.get(k) for k in ("caminho", "corpo", "headers", "espera")}, ensure_ascii=False)
    return set(_VARIAVEL.findall(texto))


# ------------------------------------------------------------------ geração da coleção Postman
def _acessor(caminho: str) -> str:
    js = "corpo"
    for parte in caminho.split("."):
        js += f"[{parte}]" if parte.isdigit() else (f".{parte}" if parte.isidentifier() else f"[{json.dumps(parte)}]")
    return js


def _roteiro_teste(passo: dict) -> list[str]:
    linhas = ["let corpo = {};", "try { corpo = pm.response.json(); } catch (e) { /* sem corpo JSON */ }",
              f'pm.test("Status esperado: {" ou ".join(map(str, codigos(passo)))}", function () {{',
              f"  pm.expect(pm.response.code).to.be.oneOf({json.dumps(codigos(passo))});", "});"]
    for caminho, valor in (passo.get("espera") or {}).items():
        ref = _VARIAVEL.fullmatch(valor) if isinstance(valor, str) else None
        if ref:
            comparacao = (f"pm.expect(String({_acessor(caminho)})).to.eql("
                          f'String(pm.collectionVariables.get("{ref.group(1)}")));')
        else:
            comparacao = f"pm.expect({_acessor(caminho)}).to.eql({json.dumps(valor, ensure_ascii=False)});"
        linhas += [f'pm.test("{caminho} = {valor}", function () {{ {comparacao} }});']
    for variavel, caminho in (passo.get("salvar") or {}).items():
        linhas.append(f'pm.collectionVariables.set("{variavel}", {_acessor(caminho)});')
    return linhas


def _item(indice: int, passo: dict) -> dict:
    caminho = passo["caminho"]
    cabecalhos = [{"key": "Content-Type", "value": "application/json"}] if passo.get("corpo") is not None else []
    if passo.get("auth"):
        cabecalhos.append({"key": "Authorization", "value": "Bearer {{%s}}" % passo["auth"]})
    cabecalhos += [{"key": k, "value": v} for k, v in (passo.get("headers") or {}).items()]
    sem_consulta, _, consulta = caminho.partition("?")
    url = {"raw": "{{baseUrl}}" + caminho, "host": ["{{baseUrl}}"], "path": sem_consulta.strip("/").split("/")}
    if consulta:
        url["query"] = [dict(zip(("key", "value"), par.split("=", 1))) for par in consulta.split("&")]
    requisicao = {"method": passo["metodo"], "header": cabecalhos, "url": url}
    if passo.get("corpo") is not None:
        requisicao["body"] = {"mode": "raw", "options": {"raw": {"language": "json"}},
                              "raw": json.dumps(passo["corpo"], indent=2, ensure_ascii=False)}
    eventos = [{"listen": "test", "script": {"type": "text/javascript", "exec": _roteiro_teste(passo)}}]
    if passo.get("gerar"):
        pre = [f'pm.collectionVariables.set("{v}", {json.dumps(m.replace("{ts}", "")) } + String(Date.now()));'
               for v, m in passo["gerar"].items()]
        eventos.insert(0, {"listen": "prerequest", "script": {"type": "text/javascript", "exec": pre}})
    return {"name": f"T{indice:02d} - {passo['nome']}", "event": eventos, "request": requisicao}


def colecao() -> dict:
    return {
        "info": {
            "_postman_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "raizes-do-nordeste-postman")),
            "name": "Raízes do Nordeste - API",
            "description": ("Coleção encadeada (T01..T%02d). Execute com a API no perfil dev (seed + pagamento "
                            "determinístico) ou via Newman: newman run postman/"
                            "raizes_do_nordeste.postman_collection.json" % len(STEPS)),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
        "variable": [{"key": "baseUrl", "value": BASE_URL}],
        "item": [_item(i, p) for i, p in enumerate(STEPS, 1)],
    }


def como_json(spec: dict) -> str:
    return json.dumps(spec, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(como_json(colecao()), encoding="utf-8")
    print(f"Coleção gerada com {len(STEPS)} chamadas em {DESTINO}")


if __name__ == "__main__":
    main()

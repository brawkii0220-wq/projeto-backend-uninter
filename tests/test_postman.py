"""Reexecuta o cenário da coleção Postman contra a API e confere que o JSON versionado está atualizado."""
import json
import pathlib
import sys
import time

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import cenario_postman as cenario  # noqa: E402


def test_cenario_postman_executa_com_sucesso_contra_a_api(client):
    variaveis: dict = {}
    for indice, passo in enumerate(cenario.STEPS, 1):
        rotulo = f"T{indice:02d} - {passo['nome']}"
        for nome, modelo in (passo.get("gerar") or {}).items():
            variaveis[nome] = modelo.replace("{ts}", str(time.time_ns() // 1_000_000))
        cabecalhos = cenario.substituir(passo.get("headers") or {}, variaveis)
        if passo.get("auth"):
            cabecalhos["Authorization"] = f"Bearer {variaveis[passo['auth']]}"
        corpo = cenario.substituir(passo.get("corpo"), variaveis)
        resposta = client.open(cenario.substituir(f"/api{passo['caminho']}", variaveis), method=passo["metodo"],
                               json=corpo, headers=cabecalhos)
        dados = resposta.get_json(silent=True)
        assert resposta.status_code in cenario.codigos(passo), f"{rotulo}: {resposta.status_code} {dados}"
        for caminho, esperado in (passo.get("espera") or {}).items():
            obtido = cenario.extrair(dados, caminho)
            if isinstance(esperado, str) and esperado.startswith("{{"):
                esperado, obtido = str(cenario.substituir(esperado, variaveis)), str(obtido)
            assert obtido == esperado, f"{rotulo}: {caminho} = {obtido!r}, esperado {esperado!r}"
        for variavel, caminho in (passo.get("salvar") or {}).items():
            variaveis[variavel] = cenario.extrair(dados, caminho)


def test_toda_variavel_usada_e_definida_antes():
    definidas = {"baseUrl"}
    for indice, passo in enumerate(cenario.STEPS, 1):
        definidas |= set(passo.get("gerar") or {})
        faltando = cenario.variaveis_usadas(passo) - definidas - {"baseUrl"}
        assert not faltando, f"T{indice:02d} usa variável ainda não definida: {faltando}"
        definidas |= set(passo.get("salvar") or {})
        if passo.get("auth"):
            assert passo["auth"] in definidas, f"T{indice:02d} usa token ainda não obtido: {passo['auth']}"


def test_colecao_versionada_esta_atualizada():
    arquivo = cenario.DESTINO
    assert arquivo.is_file(), "execute: python scripts/cenario_postman.py"
    assert arquivo.read_text(encoding="utf-8") == cenario.como_json(cenario.colecao()), \
        "coleção desatualizada: execute python scripts/cenario_postman.py"


def test_colecao_tem_estrutura_valida_do_postman():
    colecao = json.loads(cenario.DESTINO.read_text(encoding="utf-8"))
    assert colecao["info"]["schema"].endswith("v2.1.0/collection.json")
    assert [v["key"] for v in colecao["variable"]] == ["baseUrl"]
    assert len(colecao["item"]) == len(cenario.STEPS)
    nomes = [i["name"] for i in colecao["item"]]
    assert nomes[0].startswith("T01 - ") and len(set(nomes)) == len(nomes)
    for item in colecao["item"]:
        assert item["request"]["url"]["raw"].startswith("{{baseUrl}}/")
        assert any(e["listen"] == "test" for e in item["event"])

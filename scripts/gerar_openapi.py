"""Gera o contrato OpenAPI estático (docs/openapi/openapi.json e openapi.yaml).

Uso (na raiz do projeto):  python scripts/gerar_openapi.py
O teste tests/test_contrato_openapi.py falha se os arquivos versionados divergirem das rotas.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import yaml  # noqa: E402

from raizesdonordeste import Settings, create_app  # noqa: E402
from raizesdonordeste.config import openapi  # noqa: E402

DESTINO = RAIZ / "docs" / "openapi"


def contrato_atual() -> dict:
    """Contrato gerado a partir das rotas (banco temporário, sem seed)."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Settings.carregar(env={}, profile="test", db_path=str(pathlib.Path(tmp) / "openapi.db"),
                                seed_enabled=False, senha_iteracoes=1000)
        return openapi.gerar(create_app(cfg))


def como_json(spec: dict) -> str:
    return json.dumps(spec, ensure_ascii=False, indent=2) + "\n"


def como_yaml(spec: dict) -> str:
    return yaml.safe_dump(json.loads(json.dumps(spec)), allow_unicode=True, sort_keys=False)


def main() -> None:
    spec = contrato_atual()
    DESTINO.mkdir(parents=True, exist_ok=True)
    (DESTINO / "openapi.json").write_text(como_json(spec), encoding="utf-8")
    (DESTINO / "openapi.yaml").write_text(como_yaml(spec), encoding="utf-8")
    print(f"Contrato gerado com {openapi.contar_operacoes(spec)} operações em {DESTINO}")


if __name__ == "__main__":
    main()

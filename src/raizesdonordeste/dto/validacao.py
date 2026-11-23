"""Validação de entrada (equivalente ao Bean Validation): acumula erros por campo."""
from __future__ import annotations

import re

from flask import request

from raizesdonordeste.exception.api_error import ApiError
from raizesdonordeste.util.tempo import interpretar_iso

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def cpf_valido(cpf: str) -> bool:
    digitos = re.sub(r"\D", "", cpf)
    if len(digitos) != 11 or digitos == digitos[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(digitos[i]) * (tamanho + 1 - i) for i in range(tamanho))
        if (soma * 10 % 11) % 10 != int(digitos[tamanho]):
            return False
    return True


def corpo_json(obrigatorio: bool = True) -> dict:
    if not obrigatorio and not request.get_data():
        return {}
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        raise ApiError(400, "CORPO_INVALIDO", "O corpo da requisição deve ser um objeto JSON válido.")
    return dados


class Validador:
    def __init__(self, corpo: dict, prefixo: str = "", erros: list[dict] | None = None):
        self.corpo = corpo
        self.prefixo = prefixo
        self.erros: list[dict] = erros if erros is not None else []

    def erro(self, campo: str, problema: str) -> None:
        self.erros.append({"field": self.prefixo + campo, "issue": problema})

    def _ausente(self, campo: str, obrigatorio: bool) -> bool:
        if self.corpo.get(campo) is None:
            if obrigatorio:
                self.erro(campo, "campo obrigatório")
            return True
        return False

    def texto(self, campo, obrigatorio=True, minimo=1, maximo=200, padrao=None, regex=None,
              mensagem="formato inválido", aparar=True):
        if self._ausente(campo, obrigatorio):
            return padrao
        valor = self.corpo[campo]
        if not isinstance(valor, str):
            self.erro(campo, "deve ser um texto")
            return padrao
        if aparar:
            valor = valor.strip()
        if not (minimo <= len(valor) <= maximo):
            self.erro(campo, f"deve ter entre {minimo} e {maximo} caracteres")
            return padrao
        if regex is not None and not regex.match(valor):
            self.erro(campo, mensagem)
            return padrao
        return valor

    def inteiro(self, campo, obrigatorio=True, minimo=None, maximo=None, padrao=None):
        if self._ausente(campo, obrigatorio):
            return padrao
        valor = self.corpo[campo]
        if isinstance(valor, bool) or not isinstance(valor, int):
            self.erro(campo, "deve ser um número inteiro")
            return padrao
        if (minimo is not None and valor < minimo) or (maximo is not None and valor > maximo):
            limites = f"entre {minimo} e {maximo}" if None not in (minimo, maximo) else (
                f"maior ou igual a {minimo}" if minimo is not None else f"menor ou igual a {maximo}")
            self.erro(campo, f"deve ser {limites}")
            return padrao
        return valor

    def booleano(self, campo, obrigatorio=True, padrao=None):
        if self._ausente(campo, obrigatorio):
            return padrao
        valor = self.corpo[campo]
        if not isinstance(valor, bool):
            self.erro(campo, "deve ser verdadeiro ou falso")
            return padrao
        return valor

    def enum(self, campo, valores, obrigatorio=True, padrao=None):
        if self._ausente(campo, obrigatorio):
            return padrao
        valor = self.corpo[campo]
        if not isinstance(valor, str) or valor.strip().upper() not in valores:
            self.erro(campo, "valores aceitos: " + ", ".join(valores))
            return padrao
        return valor.strip().upper()

    def datahora(self, campo, obrigatorio=True, padrao=None):
        if self._ausente(campo, obrigatorio):
            return padrao
        valor = self.corpo[campo]
        try:
            interpretar_iso(valor)
        except (TypeError, ValueError):
            self.erro(campo, "use o formato AAAA-MM-DDTHH:MM:SSZ (UTC)")
            return padrao
        return valor

    def verificar(self) -> None:
        if self.erros:
            raise ApiError(422, "VALIDACAO_ERRO", "Um ou mais campos são inválidos.", self.erros)

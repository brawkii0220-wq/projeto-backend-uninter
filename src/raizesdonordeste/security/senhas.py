"""Hash de senhas com PBKDF2-HMAC-SHA256, salt aleatório por senha e comparação em tempo constante."""
from __future__ import annotations

import hashlib
import hmac
import secrets


def gerar_hash(senha: str, iteracoes: int) -> str:
    sal = secrets.token_bytes(16)
    resumo = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal, iteracoes)
    return f"pbkdf2_sha256${iteracoes}${sal.hex()}${resumo.hex()}"


def verificar(senha: str, armazenado: str) -> bool:
    try:
        _, iteracoes, sal_hex, hash_hex = armazenado.split("$")
        resumo = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(sal_hex), int(iteracoes))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(resumo.hex(), hash_hex)

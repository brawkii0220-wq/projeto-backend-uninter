"""Pseudonimização de identificadores pessoais antes de logs e trilhas de auditoria."""
from __future__ import annotations

import hashlib

_SAL = "raizes-do-nordeste"


def pseudonimizar(valor: str | None) -> str:
    if not valor or not str(valor).strip():
        return "anonimo"
    digest = hashlib.sha256(f"{_SAL}:{str(valor).strip().lower()}".encode()).hexdigest()
    return "u_" + digest[:10]

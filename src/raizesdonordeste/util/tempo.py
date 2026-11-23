"""Relógio da aplicação (injetável em testes) e utilitários de data/hora em UTC."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import current_app, has_app_context

FORMATO_ISO = "%Y-%m-%dT%H:%M:%SZ"
FUSO_BRASILIA = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019


def agora() -> datetime:
    if has_app_context() and "relogio" in current_app.extensions:
        return current_app.extensions["relogio"]()
    return datetime.now(timezone.utc)


def para_iso(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).strftime(FORMATO_ISO)


def agora_iso() -> str:
    return para_iso(agora())


def interpretar_iso(texto: str) -> datetime:
    """Levanta ValueError se o texto não estiver no formato AAAA-MM-DDTHH:MM:SSZ."""
    return datetime.strptime(texto, FORMATO_ISO).replace(tzinfo=timezone.utc)


def dia_da_semana_local(momento: datetime) -> int:
    """0 = segunda ... 6 = domingo, no fuso de Brasília."""
    return momento.astimezone(FUSO_BRASILIA).weekday()

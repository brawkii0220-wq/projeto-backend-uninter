"""Configuração por perfil (dev / prod / test), lida das variáveis de ambiente."""
from __future__ import annotations

import os
from dataclasses import dataclass, replace

CONTEXT_PATH = "/api"
PERFIS_EXECUCAO = ("dev", "prod", "test")
SEGREDO_DEV = "segredo-local-somente-para-desenvolvimento-0123456789"
STATUS_PAGAMENTO_FORCADO = ("", "APROVADO", "RECUSADO", "INDISPONIVEL")
STATUS_ESTORNO_FORCADO = ("", "CONFIRMADO", "INDISPONIVEL")
CORS_DEV = ("http://localhost:3000", "http://localhost:4200", "http://localhost:5173")


def _lista(valor: str | None, padrao: tuple[str, ...] = ()) -> tuple[str, ...]:
    if valor is None or not valor.strip():
        return padrao
    return tuple(p.strip() for p in valor.split(",") if p.strip())


def _booleano(valor: str | None, padrao: bool) -> bool:
    if valor is None or not valor.strip():
        return padrao
    return valor.strip().lower() in ("1", "true", "yes", "sim")


@dataclass(frozen=True)
class Settings:
    profile: str = "dev"
    jwt_secret: str = SEGREDO_DEV
    jwt_expiration_minutes: int = 60
    db_path: str = "data/raizes-dev.db"
    cors_allowed_origins: tuple[str, ...] = CORS_DEV
    cors_allowed_methods: tuple[str, ...] = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
    cors_allowed_headers: tuple[str, ...] = ("*",)
    cors_allow_credentials: bool = True
    pagamento_forcar_status: str = "APROVADO"
    pagamento_forcar_status_estorno: str = "CONFIRMADO"
    termos_uso_versao: str = "1.0"
    aviso_privacidade_versao: str = "1.0"
    termo_fidelidade_versao: str = "1.0"
    seed_enabled: bool = True
    senha_iteracoes: int = 210_000
    server_port: int = 8080

    @property
    def docs_enabled(self) -> bool:
        """Swagger/OpenAPI dinâmico: desligado em produção."""
        return self.profile != "prod"

    @property
    def simulacao_header_habilitada(self) -> bool:
        """Header X-Forcar-Status-Pagamento é ignorado em produção."""
        return self.profile != "prod"

    def com(self, **alteracoes) -> "Settings":
        return replace(self, **alteracoes)

    @classmethod
    def carregar(cls, env=None, **overrides) -> "Settings":
        env = os.environ if env is None else env
        profile = overrides.pop("profile", None) or env.get("APP_PROFILE") or "dev"
        if profile not in PERFIS_EXECUCAO:
            raise RuntimeError(f"APP_PROFILE inválido: {profile!r}. Use dev, prod ou test.")
        prod = profile == "prod"

        if prod:
            # Overrides explícitos (ex.: testes ou embutir a app) também satisfazem a exigência.
            ausentes = [n for n in ("JWT_SECRET", "DB_PATH")
                        if not (env.get(n) or overrides.get(n.lower()))]
            if ausentes:
                raise RuntimeError(
                    "Variáveis obrigatórias ausentes no perfil prod: " + ", ".join(ausentes))

        valores = dict(
            profile=profile,
            jwt_secret=env.get("JWT_SECRET") or SEGREDO_DEV,
            jwt_expiration_minutes=int(env.get("JWT_EXPIRATION_MINUTES") or 60),
            db_path=env.get("DB_PATH") or "data/raizes-dev.db",
            cors_allowed_origins=_lista(env.get("CORS_ALLOWED_ORIGINS"), () if prod else CORS_DEV),
            cors_allowed_methods=_lista(env.get("CORS_ALLOWED_METHODS"),
                                        ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")),
            cors_allowed_headers=_lista(
                env.get("CORS_ALLOWED_HEADERS"),
                ("Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID") if prod else ("*",)),
            cors_allow_credentials=_booleano(env.get("CORS_ALLOW_CREDENTIALS"), True),
            # Em dev o pagamento é determinístico; em prod/test vazio = aleatório (80% aprovação).
            pagamento_forcar_status=(env.get("PAGAMENTO_FORCAR_STATUS")
                                     if env.get("PAGAMENTO_FORCAR_STATUS") is not None
                                     else ("" if prod else "APROVADO")).strip().upper(),
            pagamento_forcar_status_estorno=(env.get("PAGAMENTO_FORCAR_STATUS_ESTORNO")
                                             if env.get("PAGAMENTO_FORCAR_STATUS_ESTORNO") is not None
                                             else ("" if prod else "CONFIRMADO")).strip().upper(),
            termos_uso_versao=env.get("TERMOS_USO_VERSAO") or "1.0",
            aviso_privacidade_versao=env.get("AVISO_PRIVACIDADE_VERSAO") or "1.0",
            termo_fidelidade_versao=env.get("TERMO_FIDELIDADE_VERSAO") or "1.0",
            seed_enabled=_booleano(env.get("SEED_ENABLED"), not prod),
            senha_iteracoes=int(env.get("SENHA_ITERACOES") or 210_000),
            server_port=int(env.get("SERVER_PORT") or 8080),
        )
        valores.update(overrides)
        cfg = cls(**valores)
        cfg._validar()
        return cfg

    def _validar(self) -> None:
        if len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET deve ter pelo menos 32 caracteres.")
        if self.profile == "prod" and self.jwt_secret == SEGREDO_DEV:
            raise RuntimeError("O segredo de desenvolvimento não pode ser usado em prod.")
        if self.pagamento_forcar_status not in STATUS_PAGAMENTO_FORCADO:
            raise RuntimeError("PAGAMENTO_FORCAR_STATUS aceita APROVADO, RECUSADO, INDISPONIVEL ou vazio.")
        if self.pagamento_forcar_status_estorno not in STATUS_ESTORNO_FORCADO:
            raise RuntimeError("PAGAMENTO_FORCAR_STATUS_ESTORNO aceita CONFIRMADO, INDISPONIVEL ou vazio.")

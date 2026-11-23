"""Documentos legais versionados, aceite contratual rastreável (separado do consentimento LGPD)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from flask import current_app

from raizesdonordeste.config.settings import Settings
from raizesdonordeste.dto.validacao import Validador, corpo_json
from raizesdonordeste.exception.api_error import ApiError, nao_encontrado
from raizesdonordeste.model.enums import DOC_AVISO_PRIVACIDADE, DOC_TERMOS_USO
from raizesdonordeste.repository.database import conexao, transacao
from raizesdonordeste.util.origem import origem_requisicao
from raizesdonordeste.util.tempo import agora_iso

_BASE = Path(__file__).resolve().parent.parent / "resources" / "legal"


@dataclass(frozen=True)
class DocumentoLegal:
    tipo: str
    versao: str
    conteudo: str
    hash_sha256: str

    def dto(self) -> dict:
        return {"tipo": self.tipo, "versao": self.versao, "hashSha256": self.hash_sha256,
                "conteudo": self.conteudo}


def carregar(settings: Settings) -> dict[str, DocumentoLegal]:
    documentos = {}
    for tipo, prefixo, versao in ((DOC_TERMOS_USO, "termos-uso", settings.termos_uso_versao),
                                  (DOC_AVISO_PRIVACIDADE, "aviso-privacidade", settings.aviso_privacidade_versao)):
        arquivo = _BASE / f"{prefixo}-{versao}.md"
        if not arquivo.is_file():
            raise RuntimeError(f"Documento legal vigente não encontrado: {arquivo.name}")
        conteudo = arquivo.read_text(encoding="utf-8")
        documentos[tipo] = DocumentoLegal(tipo, versao, conteudo, hashlib.sha256(conteudo.encode()).hexdigest())
    return documentos


def vigente(tipo: str) -> DocumentoLegal:
    return current_app.extensions["documentos"][tipo]


def ultimo_aceite(conn, usuario_id: int):
    return conn.execute(
        "SELECT * FROM aceites_documento WHERE usuario_id=? AND documento=? ORDER BY id DESC LIMIT 1",
        (usuario_id, DOC_TERMOS_USO)).fetchone()


def aceite_vigente(conn, usuario_id: int) -> bool:
    aceite, doc = ultimo_aceite(conn, usuario_id), vigente(DOC_TERMOS_USO)
    return aceite is not None and aceite["versao"] == doc.versao and aceite["hash_sha256"] == doc.hash_sha256


def registrar_aceite(conn, usuario_id: int) -> None:
    doc = vigente(DOC_TERMOS_USO)
    conn.execute(
        "INSERT INTO aceites_documento (usuario_id, documento, versao, hash_sha256, origem, criado_em)"
        " VALUES (?,?,?,?,?,?)",
        (usuario_id, DOC_TERMOS_USO, doc.versao, doc.hash_sha256, origem_requisicao(), agora_iso()))


def consultar_termos() -> dict:
    return vigente(DOC_TERMOS_USO).dto()


def consultar_aviso_privacidade() -> dict:
    return vigente(DOC_AVISO_PRIVACIDADE).dto()


def _dto_aceite(conn, usuario) -> dict:
    doc, aceite = vigente(DOC_TERMOS_USO), ultimo_aceite(conn, usuario["id"])
    return {
        "aceiteVigente": aceite_vigente(conn, usuario["id"]),
        "versaoVigente": doc.versao, "hashVigente": doc.hash_sha256,
        "ultimoAceite": None if aceite is None else {
            "versao": aceite["versao"], "hashSha256": aceite["hash_sha256"],
            "origem": aceite["origem"], "aceitoEm": aceite["criado_em"]},
    }


def consultar_aceite(usuario) -> dict:
    return _dto_aceite(conexao(), usuario)


def aceitar(usuario) -> tuple[dict, bool]:
    """Registra o aceite da versão vigente. Repetir é idempotente. Retorna (dto, criado)."""
    corpo = corpo_json(obrigatorio=False)
    v = Validador(corpo)
    versao = v.texto("versao", obrigatorio=False, maximo=20)
    hash_informado = v.texto("hashSha256", obrigatorio=False, maximo=64)
    v.verificar()
    doc = vigente(DOC_TERMOS_USO)
    if (versao and versao != doc.versao) or (hash_informado and hash_informado != doc.hash_sha256):
        raise ApiError(409, "TERMOS_USO_VERSAO_DESATUALIZADA",
                       "A versão ou o hash informado não corresponde aos termos vigentes.",
                       [{"field": "versao", "issue": f"versão vigente: {doc.versao}"}])
    with transacao() as conn:
        criado = not aceite_vigente(conn, usuario["id"])
        if criado:
            registrar_aceite(conn, usuario["id"])
        return _dto_aceite(conn, usuario), criado

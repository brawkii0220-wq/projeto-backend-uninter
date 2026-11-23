from __future__ import annotations

import re
import secrets
import sqlite3

from flask import current_app

from raizesdonordeste.dto.respostas import usuario_dto
from raizesdonordeste.dto.validacao import EMAIL_RE, Validador, corpo_json, cpf_valido
from raizesdonordeste.exception.api_error import ApiError, acesso_negado, conflito, nao_encontrado
from raizesdonordeste.model.enums import DOC_TERMOS_USO, PERFIS_DE_UNIDADE, Perfil
from raizesdonordeste.repository import catalogo_repository, usuario_repository
from raizesdonordeste.repository.database import conexao, paginar, transacao
from raizesdonordeste.security import senhas
from raizesdonordeste.service import documento_legal_service

_TELEFONE_RE = re.compile(r"^[0-9+()\-\s]+$")


def _hash(senha: str) -> str:
    return senhas.gerar_hash(senha, current_app.extensions["settings"].senha_iteracoes)


def registrar() -> dict:
    """Cadastro público de cliente, com aceite dos termos de uso vigentes."""
    corpo = corpo_json()
    v = Validador(corpo)
    nome = v.texto("nome", minimo=2, maximo=100)
    email = v.texto("email", maximo=150, regex=EMAIL_RE, mensagem="e-mail inválido")
    senha = v.texto("senha", minimo=8, maximo=100, aparar=False)
    telefone = v.texto("telefone", obrigatorio=False, minimo=8, maximo=20, regex=_TELEFONE_RE)
    cpf = v.texto("cpf", obrigatorio=False, maximo=14)
    if cpf and not cpf_valido(cpf):
        v.erro("cpf", "CPF inválido")
    aceite = v.booleano("aceiteTermosUso")
    versao = v.texto("versaoTermosUso", maximo=20)
    hash_termos = v.texto("hashTermosUso", maximo=64)
    if aceite is False:
        v.erro("aceiteTermosUso", "é necessário aceitar os termos de uso para se cadastrar")
    v.verificar()

    doc = documento_legal_service.vigente(DOC_TERMOS_USO)
    if versao != doc.versao or hash_termos != doc.hash_sha256:
        raise conflito("TERMOS_USO_VERSAO_DESATUALIZADA",
                       "A versão ou o hash dos termos informados não corresponde ao documento vigente.",
                       [{"field": "versaoTermosUso", "issue": f"versão vigente: {doc.versao}"}])
    try:
        with transacao() as conn:
            if usuario_repository.buscar_por_email(conn, email):
                raise conflito("EMAIL_JA_CADASTRADO", "Já existe um usuário com este e-mail.")
            novo_id = usuario_repository.inserir(
                conn, nome, email, _hash(senha), Perfil.CLIENTE.value,
                telefone=telefone, cpf=re.sub(r"\D", "", cpf) if cpf else None)
            documento_legal_service.registrar_aceite(conn, novo_id)
            return usuario_dto(usuario_repository.buscar(conn, novo_id))
    except sqlite3.IntegrityError:
        raise conflito("EMAIL_JA_CADASTRADO", "Já existe um usuário com este e-mail.")


def listar() -> dict:
    return paginar("SELECT * FROM usuarios ORDER BY id", [], usuario_dto)


def buscar(usuario_id: int) -> dict:
    alvo = usuario_repository.buscar(conexao(), usuario_id)
    if alvo is None:
        raise nao_encontrado("Usuário")
    return usuario_dto(alvo)


def atualizar(usuario, usuario_id: int) -> dict:
    if usuario["perfil"] != "ADMIN" and usuario["id"] != usuario_id:
        raise acesso_negado("Você só pode alterar o seu próprio cadastro.")
    corpo = corpo_json()
    v = Validador(corpo)
    nome = v.texto("nome", obrigatorio=False, minimo=2, maximo=100)
    telefone = v.texto("telefone", obrigatorio=False, minimo=8, maximo=20, regex=_TELEFONE_RE)
    cpf = v.texto("cpf", obrigatorio=False, maximo=14)
    if cpf and not cpf_valido(cpf):
        v.erro("cpf", "CPF inválido")
    senha = v.texto("senha", obrigatorio=False, minimo=8, maximo=100, aparar=False)
    perfil = v.enum("perfil", Perfil.valores(), obrigatorio=False)
    unidade_id = v.inteiro("unidadeId", obrigatorio=False, minimo=1)
    v.verificar()
    if ("perfil" in corpo or "unidadeId" in corpo) and usuario["perfil"] != "ADMIN":
        raise acesso_negado("Somente ADMIN pode alterar perfil ou unidade.")

    with transacao() as conn:
        alvo = usuario_repository.buscar(conn, usuario_id)
        if alvo is None:
            raise nao_encontrado("Usuário")
        if alvo["anonimizado"]:
            raise conflito("USUARIO_ANONIMIZADO", "Usuário anonimizado não pode ser alterado.")
        novo_perfil = perfil or alvo["perfil"]
        novo_unidade = unidade_id if "unidadeId" in corpo else alvo["unidade_id"]
        if novo_perfil in PERFIS_DE_UNIDADE:
            if novo_unidade is None:
                raise ApiError(422, "VALIDACAO_ERRO", "Perfis de unidade exigem unidadeId.",
                               [{"field": "unidadeId", "issue": "campo obrigatório para este perfil"}])
            unidade = catalogo_repository.buscar_unidade(conn, novo_unidade)
            if unidade is None or not unidade["ativa"]:
                raise nao_encontrado("Unidade")
        else:
            novo_unidade = None
        if alvo["perfil"] == "ADMIN" and novo_perfil != "ADMIN" and not usuario_repository.outros_admins_ativos(conn, alvo["id"]):
            raise conflito("ULTIMO_ADMIN", "Não é possível remover o último administrador.")
        conn.execute(
            "UPDATE usuarios SET nome=?, telefone=?, cpf=?, perfil=?, unidade_id=?, senha_hash=? WHERE id=?",
            (nome or alvo["nome"], telefone if "telefone" in corpo else alvo["telefone"],
             re.sub(r"\D", "", cpf) if cpf else alvo["cpf"], novo_perfil, novo_unidade,
             _hash(senha) if senha else alvo["senha_hash"], usuario_id))
        return usuario_dto(usuario_repository.buscar(conn, usuario_id))


def anonimizar(usuario, usuario_id: int) -> None:
    """Direito de eliminação (LGPD): remove dados pessoais mantendo pedidos e trilhas financeiras."""
    if usuario["perfil"] != "ADMIN" and usuario["id"] != usuario_id:
        raise acesso_negado("Você só pode anonimizar a sua própria conta.")
    with transacao() as conn:
        alvo = usuario_repository.buscar(conn, usuario_id)
        if alvo is None:
            raise nao_encontrado("Usuário")
        if alvo["anonimizado"]:
            return
        if alvo["perfil"] == "ADMIN" and not usuario_repository.outros_admins_ativos(conn, alvo["id"]):
            raise conflito("ULTIMO_ADMIN", "Não é possível anonimizar o último administrador.")
        conn.execute(
            "UPDATE usuarios SET nome='Usuário anonimizado', email=?, senha_hash=?, telefone=NULL, cpf=NULL,"
            " ativo=0, anonimizado=1 WHERE id=?",
            (f"anonimizado-{usuario_id}@anonimizado.invalid", _hash(secrets.token_hex(24)), usuario_id))

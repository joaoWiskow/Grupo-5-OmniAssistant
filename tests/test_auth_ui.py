"""Testes unitários para o módulo de autenticação e sessão UI (src/core/auth_ui.py)."""

import time
import pytest
from src.core.auth_ui import (
    _USUARIOS_MOCK,
    _hash_senha,
    gerar_token_sessao,
    validar_token_sessao,
    SESSION_EXPIRATION_SECONDS,
)


def test_geracao_e_validacao_token():
    token = gerar_token_sessao("usr-gst-001")
    assert token.startswith("omni_usr-gst-001:")
    assert validar_token_sessao(token) is True


def test_tampering_token():
    token = gerar_token_sessao("usr-gst-001")
    # Forjar assinatura ou corpo
    token_adulterado = token[:-4] + "abcd"
    assert validar_token_sessao(token_adulterado) is False
    assert validar_token_sessao("token_invalido_sem_formato") is False
    assert validar_token_sessao(None) is False


def test_expiracao_token(monkeypatch):
    token = gerar_token_sessao("usr-gst-001")
    # Simula avanço no tempo além do limite de expiração
    futuro = time.time() + SESSION_EXPIRATION_SECONDS + 100
    monkeypatch.setattr(time, "time", lambda: futuro)
    assert validar_token_sessao(token) is False


def test_hash_e_verificacao_senhas():
    gestor = _USUARIOS_MOCK["gestor"]
    # Senha correta
    assert _hash_senha("admin123", gestor.salt) == gestor.senha_hash
    # Senha incorreta
    assert _hash_senha("senhaErrada", gestor.salt) != gestor.senha_hash


def test_perfis_e_permissoes():
    assert set(_USUARIOS_MOCK) == {"gestor", "analista", "auditor"}

    gestor = _USUARIOS_MOCK["gestor"]
    assert "auditoria_completa" in gestor.permissoes
    assert "exportar_dados" in gestor.permissoes

    analista = _USUARIOS_MOCK["analista"]
    assert "auditoria_completa" not in analista.permissoes
    assert "consultar_banco" in analista.permissoes

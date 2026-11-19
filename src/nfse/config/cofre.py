"""Senhas dos certificados A1, guardadas no Gerenciador de Credenciais do Windows (keyring).

Uma senha por CNPJ titular do certificado (serviço "nfse-dashboard", usuário = CNPJ, o mesmo formato
que a versão de uma empresa só já usava). As senhas nunca vão para o banco, para o .env nem para log:
ficam no computador do escritório que roda o robô, com o usuário do Windows dele.
"""
from __future__ import annotations

from typing import Protocol

from .secret import Segredo

SERVICO_KEYRING = "nfse-dashboard"


class CofreIndisponivel(Exception):
    pass


class Cofre(Protocol):
    def obter(self, cnpj: str) -> Segredo | None: ...
    def guardar(self, cnpj: str, senha: str) -> None: ...


class CofreKeyring:
    def __init__(self, servico: str = SERVICO_KEYRING):
        try:
            import keyring
        except ImportError:
            raise CofreIndisponivel('Falta a biblioteca keyring. Rode: pip install -e ".[keyring]"') from None
        self._keyring = keyring
        self.servico = servico

    def obter(self, cnpj: str) -> Segredo | None:
        try:
            valor = self._keyring.get_password(self.servico, cnpj)
        except Exception:  # backend indisponível não deve derrubar o robô inteiro
            return None
        return Segredo(valor) if valor else None

    def guardar(self, cnpj: str, senha: str) -> None:
        try:
            self._keyring.set_password(self.servico, cnpj, senha)
        except Exception as e:
            raise CofreIndisponivel(f"Não consegui gravar no Gerenciador de Credenciais ({type(e).__name__}).") from None


class CofreMemoria:
    """Para testes e para a senha única do .env (CERT_SENHA) na transição."""

    def __init__(self, senhas: dict[str, str] | None = None, reserva: Cofre | None = None):
        self._senhas = dict(senhas or {})
        self._reserva = reserva

    def obter(self, cnpj: str) -> Segredo | None:
        if cnpj in self._senhas:
            return Segredo(self._senhas[cnpj])
        return self._reserva.obter(cnpj) if self._reserva else None

    def guardar(self, cnpj: str, senha: str) -> None:
        self._senhas[cnpj] = senha

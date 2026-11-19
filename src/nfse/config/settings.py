"""Leitura única e validada das configurações.

Ordem de prioridade: variável de ambiente do sistema > arquivo .env > valor padrão.
No Streamlit Community Cloud, os segredos de nível raiz viram variáveis de ambiente, então
não é preciso .env lá.
O .env é lido com dotenv_values (não altera os.environ, então não vaza para subprocessos).
Caminhos relativos são resolvidos a partir da raiz do projeto, não da pasta de onde se rodou o comando.
"""
from __future__ import annotations

import getpass
import os
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values

from nfse.config.secret import Segredo
from nfse.domain.documentos import cnpj_valido, so_digitos


def _raiz_projeto() -> Path:
    """Raiz do repositório. Instalado sem -e (ex.: na nuvem), cai para NFSE_RAIZ ou a pasta atual."""
    candidata = Path(__file__).resolve().parents[3]
    if (candidata / "pyproject.toml").is_file():
        return candidata
    return Path(os.getenv("NFSE_RAIZ") or Path.cwd()).resolve()


RAIZ_PROJETO = _raiz_projeto()
CHAVES = ("CNPJ_EMPRESA", "CERT_PFX", "CERT_SENHA", "PASTA_NOTAS", "NFSE_BANCO", "NFSE_ESTADO", "ADN_AMBIENTE",
          "NFSE_DATABASE_URL", "CERT_PASTA", "ACESSORIAS_API_URL", "ACESSORIAS_API_TOKEN", "ACESSORIAS_CAMPO_DOMINIO",
          "NFSE_PARALELO")
URLS_ADN = {
    "producao": "https://adn.nfse.gov.br",
    "restrita": "https://adn.producaorestrita.nfse.gov.br",
}
SERVICO_KEYRING = "nfse-dashboard"


class ConfigError(Exception):
    """Configuração ausente ou inválida. A mensagem nunca contém o valor de segredos."""


# ---------------------------------------------------------------- caminhos
def _caminho(valor: str | None, padrao: str) -> Path:
    p = Path((valor or "").strip().strip('"') or padrao)
    return p if p.is_absolute() else (RAIZ_PROJETO / p).resolve()


# ---------------------------------------------------------------- modelo
@dataclass(frozen=True)
class Settings:
    cnpj_empresa: str               # opcional desde a versão multiempresa: dono das notas antigas (migração)
    pasta_notas: Path               # XMLs em <pasta>/<cnpj>/AAAA-MM/
    banco: Path
    arquivo_estado: Path            # estado do robô da versão de uma empresa só (lido só na migração)
    adn_ambiente: str
    cert_pfx: Path | None = None
    cert_senha: Segredo | None = field(default=None, repr=False)
    database_url: Segredo | None = field(default=None, repr=False)  # PostgreSQL; vazio = SQLite em `banco`
    cert_pasta: Path | None = None  # pasta de rede com os certificados A1 (.pfx/.p12) das empresas
    acessorias_api_url: str = "https://api.acessorias.com"
    acessorias_api_token: Segredo | None = field(default=None, repr=False)
    acessorias_campo_dominio: str = ""  # campo do Acessórias com o código da empresa no Domínio
    paralelo: int = 4               # empresas consultadas ao mesmo tempo no ADN

    @property
    def adn_base_url(self) -> str:
        return URLS_ADN[self.adn_ambiente]

    @property
    def destino(self):
        from nfse.data.database import DestinoBanco
        return DestinoBanco(self.banco, self.database_url, self.cnpj_empresa or None)

    def credenciais_certificado(self, interativo: bool | None = None) -> tuple[Path, Segredo]:
        """Devolve (pfx, senha) só quando o robô precisa falar com o ADN.

        Senha: .env/ambiente -> Gerenciador de Credenciais do Windows (keyring, se instalado)
        -> pergunta na tela. Sem terminal (tarefa agendada) falha na hora em vez de travar.
        """
        if self.cert_pfx is None:
            raise ConfigError("CERT_PFX não está configurado (.env).")
        if not self.cert_pfx.is_file():
            raise ConfigError(f"Arquivo do certificado não encontrado: {self.cert_pfx}")
        if self.cert_pfx.suffix.lower() not in (".pfx", ".p12"):
            raise ConfigError("CERT_PFX deve apontar para um arquivo .pfx ou .p12.")

        if self.cert_senha:
            return self.cert_pfx, self.cert_senha
        senha = _senha_keyring(self.cnpj_empresa)
        if senha:
            return self.cert_pfx, senha
        if interativo is None:
            interativo = sys.stdin is not None and sys.stdin.isatty()
        if not interativo:
            raise ConfigError("Senha do certificado indisponível: preencha CERT_SENHA ou guarde-a com "
                              f"'keyring set {SERVICO_KEYRING} {self.cnpj_empresa}'.")
        return self.cert_pfx, Segredo(getpass.getpass("Senha do certificado A1 (não aparece na tela): "))


def _senha_keyring(cnpj: str) -> Segredo | None:
    try:
        import keyring
    except ImportError:
        return None
    try:
        valor = keyring.get_password(SERVICO_KEYRING, cnpj)
    except Exception:  # backend indisponível não deve derrubar o robô
        return None
    return Segredo(valor) if valor else None


# ---------------------------------------------------------------- carga
def _ler_fontes(arquivo_env: Path) -> dict[str, str]:
    valores = {k: v for k, v in dotenv_values(arquivo_env).items() if v is not None} if arquivo_env.is_file() else {}
    valores.update({k: os.environ[k] for k in CHAVES if k in os.environ})
    return valores


def carregar(arquivo_env: Path | str | None = None) -> Settings:
    arquivo = Path(arquivo_env or os.getenv("NFSE_ENV_FILE") or RAIZ_PROJETO / ".env")
    v = _ler_fontes(arquivo)

    cnpj = so_digitos(v.get("CNPJ_EMPRESA"))
    if cnpj and not cnpj_valido(cnpj):
        raise ConfigError("CNPJ_EMPRESA inválido: precisa ter 14 dígitos com dígitos verificadores corretos.")

    ambiente = (v.get("ADN_AMBIENTE") or "producao").strip().lower()
    if ambiente not in URLS_ADN:
        raise ConfigError(f"ADN_AMBIENTE deve ser um de: {', '.join(URLS_ADN)}.")

    url = (v.get("NFSE_DATABASE_URL") or "").strip().strip('"')
    if url and not url.startswith(("postgresql://", "postgres://")):
        raise ConfigError("NFSE_DATABASE_URL deve começar com postgresql:// (ou deixe vazia para usar o SQLite).")

    pfx = (v.get("CERT_PFX") or "").strip().strip('"')
    senha = v.get("CERT_SENHA") or ""
    pasta_cert = (v.get("CERT_PASTA") or "").strip().strip('"')
    token = (v.get("ACESSORIAS_API_TOKEN") or "").strip()
    try:
        paralelo = max(1, min(16, int(v.get("NFSE_PARALELO") or 4)))
    except ValueError:
        raise ConfigError("NFSE_PARALELO deve ser um número de 1 a 16.") from None

    return Settings(
        cnpj_empresa=cnpj,
        pasta_notas=_caminho(v.get("PASTA_NOTAS"), "data/notas"),
        banco=_caminho(v.get("NFSE_BANCO"), "data/notas.db"),
        arquivo_estado=_caminho(v.get("NFSE_ESTADO"), "data/adn_estado.json"),
        adn_ambiente=ambiente,
        cert_pfx=_caminho(pfx, pfx) if pfx else None,
        cert_senha=Segredo(senha) if senha else None,
        database_url=Segredo(url) if url else None,
        cert_pasta=_caminho(pasta_cert, pasta_cert) if pasta_cert else None,
        acessorias_api_url=(v.get("ACESSORIAS_API_URL") or "https://api.acessorias.com").strip().rstrip("/"),
        acessorias_api_token=Segredo(token) if token else None,
        acessorias_campo_dominio=(v.get("ACESSORIAS_CAMPO_DOMINIO") or "").strip(),
        paralelo=paralelo,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ponto único de acesso às configurações no resto do sistema."""
    return carregar()

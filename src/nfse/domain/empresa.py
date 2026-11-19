"""Empresas clientes do escritório e regras de cadastro (regime tributário, raiz do CNPJ, certificado).

Sem I/O: o cadastro vem do Acessórias (clients.acessorias) e é gravado pelo data.empresas_repository.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from .documentos import so_digitos

# Categorias exibidas no filtro do dashboard, na ordem do menu.
SIMPLES = "Simples Nacional"
MEI = "MEI"
PRESUMIDO = "Lucro Presumido"
REAL = "Lucro Real"
IMUNE = "Imunes e isentas"
OUTROS = "Outros / não informado"
REGIMES = (SIMPLES, MEI, PRESUMIDO, REAL, IMUNE, OUTROS)

DIAS_ALERTA_CERTIFICADO = 30

# situação do certificado (calculada, não gravada)
CERT_OK = "ok"
CERT_VENCENDO = "vencendo"
CERT_VENCIDO = "vencido"
CERT_AUSENTE = "ausente"


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def normalizar_regime(texto: str | None) -> str:
    """O Acessórias guarda textos livres ("SIMPLES NACIONAL - C Inscrição Estadual e com folha de
    pagamento", "Lucro Presumido - S ...", "MEI - Micro Empreendedor Individual"...). Agrupa nas
    categorias do filtro."""
    t = _sem_acento(texto or "")
    if not t.strip():
        return OUTROS
    if re.search(r"\bmei\b|microempreendedor|micro empreendedor", t):
        return MEI
    if "simples" in t:
        return SIMPLES
    if "presumido" in t:
        return PRESUMIDO
    if re.search(r"lucro real|\breal\b", t):
        return REAL
    if "imune" in t or "isent" in t:
        return IMUNE
    return OUTROS


def raiz(cnpj: str) -> str:
    """8 primeiros dígitos: o ADN aceita o certificado da matriz para consultar as filiais."""
    return so_digitos(cnpj)[:8]


def situacao_certificado(validade: str | None, hoje: date | None = None) -> str:
    if not validade or not isinstance(validade, str):
        return CERT_AUSENTE
    hoje = hoje or date.today()
    try:
        venc = date.fromisoformat(validade[:10])
    except ValueError:
        return CERT_AUSENTE
    if venc < hoje:
        return CERT_VENCIDO
    if (venc - hoje).days <= DIAS_ALERTA_CERTIFICADO:
        return CERT_VENCENDO
    return CERT_OK


@dataclass(frozen=True)
class Empresa:
    cnpj: str
    razao_social: str
    fantasia: str = ""
    codigo_dominio: str = ""
    acessorias_id: str = ""
    regime_acessorias: str = ""     # texto original do Acessórias
    regime: str = OUTROS            # categoria normalizada
    grupo: str = ""
    uf: str = ""
    ativa: bool = True
    cert_arquivo: str = ""          # caminho do .pfx na pasta de rede
    cert_titular: str = ""          # CNPJ que consta no certificado (a matriz, quando a empresa é filial)
    cert_validade: str = ""         # AAAA-MM-DD

    @property
    def situacao_certificado(self) -> str:
        return situacao_certificado(self.cert_validade)

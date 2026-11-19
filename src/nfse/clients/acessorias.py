"""Cliente da API do Acessórias (somente leitura): cadastro das empresas clientes do escritório.

    GET {base}/companies/ListAll/?ativa=S&Pagina=n&registrationData
    GET {base}/companies/{cnpj}/?registrationData

Mesmo padrão dos outros sistemas da Informe (Auditoria de Folha, Alerta de Pendências): token do
escritório no cabeçalho Authorization, repetição em 429/5xx, nunca POST/PUT/DELETE.
O CNPJ é a chave entre o Acessórias e o NFS-e.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Callable, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from nfse.config.secret import Segredo
from nfse.domain.documentos import cnpj_valido, so_digitos
from nfse.domain.empresa import normalizar_regime

log = logging.getLogger(__name__)
_VAZIO = ("nenhum", "nao encontrad", "não encontrad", "sem registro")
# Nomes de campo em que o código do Domínio pode vir, quando ACESSORIAS_CAMPO_DOMINIO não é informado.
CAMPOS_DOMINIO = ("CodigoDominio", "CodDominio", "Dominio", "CodigoERP", "CodERP", "CodigoInterno", "Codigo")


class ErroAcessorias(Exception):
    """Mensagem para o usuário; nunca contém o token."""


def _abrir(req: Request, timeout: int) -> tuple[int, str]:
    try:
        with urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


class AcessoriasClient:
    def __init__(self, base_url: str, token: Segredo | None, timeout: int = 30, max_paginas: int = 200,
                 dormir: Callable[[float], None] = time.sleep,
                 abrir: Callable[[Request, int], tuple[int, str]] = _abrir):
        if not token:
            raise ErroAcessorias("Token da API do Acessórias não configurado (ACESSORIAS_API_TOKEN no .env).")
        self.base_url = base_url.rstrip("/")
        self._token = token
        self.timeout = timeout
        self.max_paginas = max_paginas
        self._dormir = dormir
        self._abrir = abrir

    def _get(self, endpoint: str, params: dict | None = None, flags: tuple[str, ...] = ("registrationData",)):
        partes = [f"{k}={quote(str(v))}" for k, v in (params or {}).items() if v not in (None, "")] + list(flags)
        url = f"{self.base_url}/{endpoint.lstrip('/')}" + (f"?{'&'.join(partes)}" if partes else "")
        req = Request(url, headers={"Authorization": f"Bearer {self._token.revelar()}", "Accept": "application/json"})
        ultimo = ""
        for tentativa in range(4):
            try:
                status, corpo = self._abrir(req, self.timeout)
            except (URLError, TimeoutError, OSError) as e:
                ultimo = type(e).__name__
                self._dormir(2 * (tentativa + 1))
                continue
            if status in (401, 403):
                raise ErroAcessorias(f"O Acessórias recusou o token (HTTP {status}).")
            if status == 429 or status >= 500:
                ultimo = f"HTTP {status}"
                self._dormir(3 * (tentativa + 1))
                continue
            if status in (204, 404) or not corpo.strip():
                return []
            if status >= 400:
                raise ErroAcessorias(f"O Acessórias respondeu HTTP {status}: {corpo[:150]}")
            try:
                return json.loads(corpo)
            except ValueError:
                if any(v in corpo.lower() for v in _VAZIO):
                    return []
                raise ErroAcessorias(f"Resposta inesperada do Acessórias: {corpo[:150]}") from None
        raise ErroAcessorias(f"Acessórias indisponível ({ultimo}). Tente de novo mais tarde.")

    @staticmethod
    def registros(payload) -> list[dict]:
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict):
            for k in ("Empresas", "empresas", "data", "dados", "items"):
                if isinstance(payload.get(k), list):
                    return [x for x in payload[k] if isinstance(x, dict)]
            if "Identificador" in payload or "Razao" in payload:
                return [payload]
        return []

    def listar_ativas(self) -> Iterator[dict]:
        """Todas as empresas ativas, página a página (50 por página)."""
        anterior = None
        for pagina in range(1, self.max_paginas + 1):
            regs = self.registros(self._get("companies/ListAll/", {"ativa": "S", "Pagina": pagina}))
            assinatura = [r.get("Identificador") for r in regs[:3]]
            if not regs or assinatura == anterior:
                return
            anterior = assinatura
            yield from regs
        raise ErroAcessorias(f"Paginação interrompida em {self.max_paginas} páginas; a lista pode estar incompleta.")

    def buscar(self, cnpj: str) -> dict | None:
        regs = self.registros(self._get(f"companies/{so_digitos(cnpj)}/"))
        return regs[0] if regs else None


def _txt(v) -> str:
    return " ".join(str(v or "").split())


def mapear(raw: dict, campo_dominio: str = "") -> dict | None:
    """Registro da API -> colunas da tabela empresas. None quando não é um CNPJ (CPF/CAEPF ficam de fora:
    o ADN só é consultado por CNPJ)."""
    cnpj = so_digitos(raw.get("Identificador"))
    if not cnpj_valido(cnpj):
        return None
    if campo_dominio:
        codigo = _txt(raw.get(campo_dominio))
    else:
        codigo = next((_txt(raw.get(c)) for c in CAMPOS_DOMINIO if _txt(raw.get(c))), "")
    regime = _txt(raw.get("Regime"))
    return {
        "cnpj": cnpj,
        "razao_social": _txt(raw.get("Razao")),
        "fantasia": _txt(raw.get("Fantasia")),
        "codigo_dominio": codigo,
        "acessorias_id": _txt(raw.get("ID")),
        "regime_acessorias": regime,
        "regime": normalizar_regime(regime),
        "grupo": _txt(raw.get("GrupoDeEmpresas")),
        "uf": _txt(raw.get("UF")),
    }

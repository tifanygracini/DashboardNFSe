"""Cliente HTTP do ADN: só transporte (mTLS, tentativas, tradução de erros). Não grava nada."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, NoReturn

import requests

from nfse.config.settings import Segredo

from . import errors
from .schemas import STATUS_FILA_VAZIA, DocumentoDFe, RespostaDFe

log = logging.getLogger(__name__)


class AdnClient:
    def __init__(self, base_url: str, cnpj: str, certificado: tuple[Path, Segredo] | None = None,
                 timeout: int = 60, esperas_retry: tuple[int, ...] = (5, 15),
                 dormir: Callable[[float], None] = time.sleep, sessao: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.cnpj = cnpj
        self.timeout = timeout
        self.esperas_retry = esperas_retry
        self._dormir = dormir
        self._sessao = sessao or requests.Session()
        if certificado:
            self._montar_certificado(*certificado)

    def _montar_certificado(self, pfx: Path, senha: Segredo):
        try:
            from requests_pkcs12 import Pkcs12Adapter
        
        except ImportError:
            raise errors.AdnCertificadoInvalido("Falta a biblioteca requests-pkcs12. Rode: pip install requests-pkcs12")
        
        try:
            adaptador = Pkcs12Adapter(pkcs12_filename=str(pfx), pkcs12_password=senha.revelar())

        except OSError as e:
            raise errors.AdnCertificadoInvalido(
                f"Não consegui ler o arquivo do certificado ({e.strerror or e}). Confira a permissão de "
                "acesso e se a unidade de rede está conectada.") from None
        
        except ValueError as e:
            raise errors.AdnCertificadoInvalido(
                f"Não consegui abrir o certificado: senha incorreta ou arquivo .pfx inválido ({e}). "
                "Para investigar: python tools/diagnosticar_certificado.py") from None
        
        self._sessao.mount(self.base_url, adaptador)

    # ------------------------------------------------------------ API pública
    def consultar(self, nsu: int) -> RespostaDFe:
        """Documentos com NSU maior que `nsu` (até 50)."""
        r = self._get(f"{self.base_url}/contribuintes/DFe/{nsu}", {"cnpjConsulta": self.cnpj})
        js = _json_ou_none(r)
        if r.status_code == 404 and isinstance(js, dict) and js.get("StatusProcessamento") == STATUS_FILA_VAZIA:
            return RespostaDFe(fila_esgotada=True)
        if r.status_code != 200 or not isinstance(js, dict):
            _levantar_erro(r, js)
        docs = [DocumentoDFe.from_json(d) for d in js.get("LoteDFe") or []]
        return RespostaDFe(documentos=docs, fila_esgotada=not docs)

    # ------------------------------------------------------------ HTTP
    def _get(self, url: str, params: dict) -> requests.Response:
        """GET com novas tentativas (espera crescente) para 429 e 5xx."""
        tentativas = len(self.esperas_retry) + 1
        for tentativa in range(tentativas):
            try:
                r = self._sessao.get(url, params=params, timeout=self.timeout)
            except requests.exceptions.SSLError:
                raise errors.AdnTlsError(
                    "Falha no TLS ao conectar. Confira: certificado vencido, senha errada, arquivo .pfx errado "
                    "ou certificado A3 (cartão/token), que não serve para o robô.") from None
            except requests.exceptions.ConnectionError:
                raise errors.AdnConexaoError(
                    "Não consegui conectar ao servidor. Confira a internet e a URL base (--base-url).") from None
            except requests.exceptions.Timeout:
                raise errors.AdnTimeout("O servidor demorou demais para responder. Tente de novo mais tarde.") from None

            if r.status_code != 429 and r.status_code < 500:
                return r
            if tentativa < tentativas - 1:
                espera = self.esperas_retry[tentativa]
                log.info("HTTP %s: nova tentativa em %ss (%s/%s)...", r.status_code, espera, tentativa + 2, tentativas)
                self._dormir(espera)
                continue
            if r.status_code == 429:
                raise errors.AdnLimiteChamadas("O ADN limitou as chamadas (429). Espere um pouco e rode de novo.")
            raise errors.AdnInstavel(
                f"O ADN está instável (HTTP {r.status_code}). Tente de novo mais tarde, ou use o simulador.")
        raise errors.AdnRespostaInesperada("Não foi possível obter resposta do servidor.")


def _json_ou_none(r: requests.Response):
    try:
        return r.json()
    except ValueError:
        return None


def _levantar_erro(r: requests.Response, js) -> NoReturn:
    if r.status_code == 403:
        raise errors.AdnAcessoNegado(
            "Acesso negado (403). O CNPJ consultado precisa ter a mesma raiz do CNPJ do certificado.")
    if r.status_code == 400:
        codigos = [str(e.get("Codigo") or e.get("codigo") or "")
                   for e in (js.get("Erros") or [] if isinstance(js, dict) else [])]
        if "E2242" in codigos or "E2242" in r.text:
            raise errors.AdnCertificadoPessoaFisica(
                "Erro E2242: certificado de pessoa física (e-CPF). A consulta precisa ser feita sem o "
                "parâmetro de CNPJ, o que este robô ainda não suporta.")
        raise errors.AdnRequisicaoInvalida(f"Requisição recusada (400): {r.text[:300]}")
    if r.status_code == 404:
        raise errors.AdnUrlInvalida("404 sem a resposta esperada do ADN. Confira a URL: o caminho certo é "
                                    "/contribuintes/DFe/ (com \"s\" em contribuintes).")
    raise errors.AdnRespostaInesperada(f"Resposta inesperada do servidor: HTTP {r.status_code}.")

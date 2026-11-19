"""Robô de todas as empresas: ADN -> pasta de XMLs da empresa -> banco.

Para cada empresa ativa com certificado: consulta o ADN com o certificado dela (ou o da matriz),
grava os XMLs em <pasta_notas>/<cnpj>/AAAA-MM/ e importa as notas novas. As consultas ao ADN rodam
em paralelo (rede); a importação roda uma empresa por vez (banco).

Um erro numa empresa não para as outras: fica registrado na tabela empresas (robo_situacao /
robo_mensagem) e aparece no dashboard.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from nfse.clients.adn.client import AdnClient
from nfse.clients.adn.errors import AdnError
from nfse.config.cofre import Cofre
from nfse.data import ERROS_BANCO, DestinoBanco, EmpresasRepository, EstadoBanco, XmlStorage, conectar
from nfse.domain.empresa import Empresa
from nfse.services.certificados_service import CertificadoIlegivel, CertificadosService
from nfse.services.download_service import DownloadService
from nfse.services.import_service import ImportService

log = logging.getLogger(__name__)

OK = "ok"
AGUARDANDO = "aguardando"          # regra de 1 hora do ADN
SEM_CERTIFICADO = "sem_certificado"
ERRO = "erro"


@dataclass
class ResultadoEmpresa:
    cnpj: str
    nome: str
    situacao: str = OK
    mensagem: str = ""
    recebidos: int = 0
    novos: int = 0
    importadas: int = 0
    canceladas: int = 0


def pasta_da_empresa(pasta_notas: Path, cnpj: str) -> Path:
    return pasta_notas / cnpj


class RoboService:
    def __init__(self, destino: DestinoBanco, cofre: Cofre, pasta_notas: Path, base_url: str,
                 paralelo: int = 4, usar_certificado: bool = True,
                 fabrica_cliente: Callable[..., AdnClient] = AdnClient,
                 relogio: Callable[[], datetime] = datetime.now):
        self.destino = destino
        self.certificados = CertificadosService(destino, cofre)
        self.pasta_notas = pasta_notas
        self.base_url = base_url
        self.paralelo = max(1, paralelo)
        self.usar_certificado = usar_certificado
        self.fabrica_cliente = fabrica_cliente
        self.relogio = relogio

    def empresas(self, cnpjs: list[str] | None = None) -> list[Empresa]:
        with conectar(self.destino) as con:
            ativas = EmpresasRepository(con).listar(so_ativas=True)
        return [e for e in ativas if not cnpjs or e.cnpj in cnpjs]

    def executar(self, cnpjs: list[str] | None = None, forcar: bool = False,
                 ao_concluir: Callable[[ResultadoEmpresa], None] | None = None) -> list[ResultadoEmpresa]:
        empresas = self.empresas(cnpjs)
        with ThreadPoolExecutor(max_workers=self.paralelo, thread_name_prefix="adn") as pool:
            resultados = list(pool.map(lambda e: self._baixar(e, forcar), empresas))

        for emp, res in zip(empresas, resultados):  # importação: uma empresa por vez
            if res.situacao in (OK, AGUARDANDO) and (res.novos or forcar):
                self._importar(res)
            self._registrar(res)
            if ao_concluir:
                ao_concluir(res)
        return resultados

    # ------------------------------------------------------------ etapas
    def _baixar(self, emp: Empresa, forcar: bool) -> ResultadoEmpresa:
        res = ResultadoEmpresa(emp.cnpj, emp.razao_social or emp.cnpj)
        try:
            certificado = self.certificados.credenciais(emp) if self.usar_certificado else None
        except CertificadoIlegivel as e:
            res.situacao, res.mensagem = SEM_CERTIFICADO, str(e)
            return res
        try:
            cliente = self.fabrica_cliente(self.base_url, emp.cnpj, certificado=certificado)
            servico = DownloadService(cliente, EstadoBanco(self.destino, emp.cnpj),
                                      XmlStorage(pasta_da_empresa(self.pasta_notas, emp.cnpj)), relogio=self.relogio)
            r = servico.executar(forcar=forcar)
        except AdnError as e:
            res.situacao, res.mensagem = ERRO, str(e)
            return res
        except OSError as e:
            res.situacao, res.mensagem = ERRO, f"erro ao gravar os XMLs: {e.strerror or e}"
            return res
        except ERROS_BANCO as e:
            res.situacao, res.mensagem = ERRO, f"erro no banco: {str(e).strip().splitlines()[0]}"
            return res
        except Exception as e:  # uma empresa com problema inesperado não derruba o robô
            log.exception("falha inesperada na empresa %s", emp.cnpj)
            res.situacao, res.mensagem = ERRO, f"falha inesperada ({type(e).__name__})"
            return res
        res.recebidos, res.novos = r.recebidos, r.novos
        if r.aguardar_ate:
            res.situacao, res.mensagem = AGUARDANDO, f"próxima consulta permitida às {r.aguardar_ate:%H:%M}"
        elif not r.fila_esgotada:
            res.mensagem = "limite de lotes por execução atingido; continua na próxima"
        return res

    def _importar(self, res: ResultadoEmpresa):
        try:
            imp = ImportService(XmlStorage(pasta_da_empresa(self.pasta_notas, res.cnpj)), self.destino, res.cnpj).importar()
        except (OSError, *ERROS_BANCO) as e:
            res.situacao, res.mensagem = ERRO, f"erro na importação: {str(e).strip().splitlines()[0]}"
            return
        res.importadas, res.canceladas = imp.novas, imp.canceladas
        if imp.falhas:
            res.mensagem = (res.mensagem + "; " if res.mensagem else "") + f"{len(imp.falhas)} XML(s) com erro: {imp.falhas[0]}"

    def _registrar(self, res: ResultadoEmpresa):
        try:
            with conectar(self.destino, criar=False) as con:
                EmpresasRepository(con).registrar_execucao(res.cnpj, res.situacao, res.mensagem)
        except ERROS_BANCO:
            log.exception("não consegui registrar a execução da empresa %s", res.cnpj)

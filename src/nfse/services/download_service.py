"""ADN -> pasta de XMLs. Aplica a regra de 1 hora entre consultas e o limite de lotes por execução."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Callable

from nfse.clients.adn.client import AdnClient, DocumentoDFe
from nfse.data.estado_repository import EstadoRepository
from nfse.data.xml_storage import XmlStorage
from nfse.domain.documentos import so_digitos
from nfse.parsers.codec import decodificar
from nfse.parsers.evento_parser import CODIGO_CANCELAMENTO, chave_no_xml, competencia_documento, tipo_do_evento

MAX_LOTES = 20
INTERVALO_CONSULTAS = timedelta(minutes=60)


@dataclass
class ResultadoDownload:
    nsu_inicial: int = 0
    ultimo_nsu: int = 0
    lotes: int = 0
    recebidos: int = 0
    novos: int = 0
    fila_esgotada: bool = False
    aguardar_ate: datetime | None = None  # preenchido quando a regra de 1 hora impediu a consulta


def nome_arquivo(chave: str, tipo_documento: str, tipo_evento: str) -> str:
    if tipo_documento == "NFSE":
        return f"{chave}-nfse.xml"
    return f"{chave}-canc.xml" if tipo_evento == CODIGO_CANCELAMENTO else f"{chave}-evento-{tipo_evento}.xml"


class DownloadService:
    def __init__(self, client: AdnClient, estado: EstadoRepository, storage: XmlStorage,
                 max_lotes: int = MAX_LOTES, intervalo: timedelta = INTERVALO_CONSULTAS,
                 relogio: Callable[[], datetime] = datetime.now):
        self.client = client
        self.estado = estado
        self.storage = storage
        self.max_lotes = max_lotes
        self.intervalo = intervalo
        self.relogio = relogio

    def executar(self, desde_nsu: int | None = None, forcar: bool = False,
                 ao_iniciar: Callable[[int], None] | None = None,
                 ao_concluir_lote: Callable[[int, int, int, int], None] | None = None) -> ResultadoDownload:
        est = self.estado.ler()
        if est.ultima_consulta and not forcar:
            proxima = est.ultima_consulta + self.intervalo
            if self.relogio() < proxima:
                return ResultadoDownload(est.ultimo_nsu, est.ultimo_nsu, aguardar_ate=proxima)

        nsu = desde_nsu if desde_nsu is not None else est.ultimo_nsu
        res = ResultadoDownload(nsu_inicial=nsu, ultimo_nsu=nsu)
        if ao_iniciar:
            ao_iniciar(nsu)

        while res.lotes < self.max_lotes:
            resposta = self.client.consultar(nsu)
            if resposta.fila_esgotada:
                res.fila_esgotada = True
                break
            res.lotes += 1
            novos_lote = sum(1 for doc in resposta.documentos if self._gravar(doc) == "novo")
            res.recebidos += len(resposta.documentos)
            res.novos += novos_lote
            nsu = max(d.nsu for d in resposta.documentos)
            res.ultimo_nsu = nsu
            est = replace(est, ultimo_nsu=nsu)
            self.estado.gravar(est)  # progresso salvo a cada lote
            if ao_concluir_lote:
                ao_concluir_lote(res.lotes, len(resposta.documentos), novos_lote, nsu)

        if res.fila_esgotada:
            self.estado.gravar(replace(est, ultima_consulta=self.relogio().replace(microsecond=0)))
        return res

    def _gravar(self, doc: DocumentoDFe) -> str:
        """Devolve 'novo', 'existente' ou 'ignorado'."""
        if doc.tipo_documento not in ("NFSE", "EVENTO"):
            return "ignorado"
        xml = decodificar(doc.arquivo_xml)
        chave = so_digitos(doc.chave) or chave_no_xml(xml)
        if not chave:
            return "ignorado"
        tipo_ev = tipo_do_evento(xml, doc.tipo_evento) if doc.tipo_documento == "EVENTO" else ""
        nome = nome_arquivo(chave, doc.tipo_documento, tipo_ev)
        competencia = competencia_documento(xml, doc.tipo_documento, doc.data_geracao)
        return "novo" if self.storage.gravar(competencia, nome, xml) else "existente"

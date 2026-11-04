import base64
import gzip

import pytest

from conftest import CNPJ_EXEMPLO
from src.nfse.domain import RegraError, StatusNota, TipoNota
from src.nfse.parsers.codec import codificar, decodificar
from src.nfse.parsers.evento_parser import chave_cancelada, competencia_documento, tipo_do_evento
from src.nfse.parsers.nfse_parser import ler_nota

XML = b"<?xml version='1.0'?><a/>"


def test_codec_ida_e_volta():
    assert decodificar(codificar(XML)) == XML


def test_codec_base64_duplo():
    duplo = base64.b64encode(base64.b64encode(gzip.compress(XML)))
    assert decodificar(duplo) == XML


def test_le_nota_emitida(xml_raiz):
    raiz, arq = xml_raiz("2026-07-04-")
    nota = ler_nota(raiz, CNPJ_EXEMPLO, arq.name)
    assert nota.tipo is TipoNota.EMITIDA
    assert nota.chave == "52087072111223344000186000000000002521440159982464"
    assert nota.competencia == "2026-07"
    assert nota.base_calculo == 5143.23 and nota.valor_iss == 154.30
    assert nota.tomador_nome == "PREFEITURA FICTICIA DE TESTE"
    assert nota.iss_retido is False and nota.status is StatusNota.NORMAL


def test_le_nota_recebida(xml_raiz):
    raiz, arq = xml_raiz("2026-09-05-")
    assert ler_nota(raiz, CNPJ_EXEMPLO, arq.name).tipo is TipoNota.RECEBIDA


def test_nota_de_outra_empresa(xml_raiz):
    raiz, arq = xml_raiz("2026-07-04-")
    with pytest.raises(RegraError):
        ler_nota(raiz, "11222333000181", arq.name)


def test_evento_de_cancelamento(xml_raiz):
    raiz, _ = xml_raiz("2026-07-28-617252-canc")
    assert chave_cancelada(raiz) == "52087072111223344000186000000000000197911723617252"


def test_nota_nao_e_evento(xml_raiz):
    raiz, _ = xml_raiz("2026-07-04-")
    assert chave_cancelada(raiz) is None


def test_metadados_do_evento(pasta_xml):
    xml = next(pasta_xml.glob("*-canc.xml")).read_bytes()
    assert tipo_do_evento(xml, None) == "101101"
    assert tipo_do_evento(xml, "e101101") == "101101"
    assert competencia_documento(xml, "EVENTO", None) == "2026-07"
    assert competencia_documento(b"lixo", "NFSE", "2026-10-01T00:00:00") == "2026-10"
    assert competencia_documento(b"lixo", "NFSE", None) == "sem-data"

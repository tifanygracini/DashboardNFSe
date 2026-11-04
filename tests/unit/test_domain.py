from dataclasses import fields

import pytest

from src.nfse.data.database import COLUNAS
from src.nfse.domain import Nota, RegraError, TipoNota
from src.nfse.domain import regras
from src.nfse.domain.documentos import cnpj_valido, so_digitos


def test_classificar_tipo():
    assert regras.classificar_tipo("1", "2", "1") is TipoNota.EMITIDA
    assert regras.classificar_tipo("1", "2", "2") is TipoNota.RECEBIDA
    with pytest.raises(RegraError):
        regras.classificar_tipo("1", "2", "3")


def test_valores_com_e_sem_campos_da_nota():
    assert regras.base_calculo(900.0, 1000.0, 50.0) == 900.0
    assert regras.base_calculo(None, 1000.0, 50.0) == 950.0
    assert regras.valor_liquido(None, 1000.0, 50.0, 30.0) == 920.0
    assert regras.iss_retido("2") and not regras.iss_retido("1")


def test_cnpj():
    assert so_digitos("11.223.344/0001-86") == "11223344000186"
    assert cnpj_valido("11223344000186")
    assert not cnpj_valido("11223344000187")
    assert not cnpj_valido("00000000000000")


def test_colunas_do_banco_batem_com_a_entidade():
    assert [f.name for f in fields(Nota)] == [nome for nome, _ in COLUNAS]

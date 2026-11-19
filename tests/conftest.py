import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

PASTA_XML = Path(__file__).parent / "fixtures" / "xml"
CNPJ_EXEMPLO = "11223344000186"


@pytest.fixture
def pasta_xml() -> Path:
    return PASTA_XML


@pytest.fixture
def xml_raiz():
    """Raiz parseada de um arquivo de fixture cujo nome começa com o prefixo dado."""
    def _abrir(prefixo: str):
        arq = next(PASTA_XML.rglob(f"{prefixo}*.xml"))
        return ET.parse(arq).getroot(), arq
    return _abrir


def cadastrar(destino, cnpj: str, razao: str, regime: str = "Simples Nacional", codigo: str = "", **extra):
    """Empresa no cadastro, como se viesse do Acessórias."""
    from nfse.data import EmpresasRepository, conectar
    with conectar(destino) as con:
        EmpresasRepository(con).gravar_do_acessorias({
            "cnpj": cnpj, "razao_social": razao, "fantasia": extra.get("fantasia", ""), "codigo_dominio": codigo,
            "acessorias_id": extra.get("acessorias_id", ""), "regime_acessorias": extra.get("regime_acessorias", regime),
            "regime": regime, "grupo": "", "uf": "SP"})

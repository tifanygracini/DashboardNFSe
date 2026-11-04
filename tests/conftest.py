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
        arq = next(PASTA_XML.glob(f"{prefixo}*.xml"))
        return ET.parse(arq).getroot(), arq
    return _abrir

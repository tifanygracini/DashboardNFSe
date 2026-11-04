"""Roda o app Streamlit de verdade (sem navegador) contra um banco importado das fixtures."""
from pathlib import Path

import pytest

from conftest import CNPJ_EXEMPLO
from src.nfse.config import get_settings
from src.nfse.data import XmlStorage
from src.nfse.services.import_service import ImportService

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP = Path(__file__).resolve().parents[2] / "src" / "nfse" / "ui" / "dashboard" / "app.py"


@pytest.fixture
def ambiente(tmp_path, pasta_xml, monkeypatch):
    banco = tmp_path / "notas.db"
    ImportService(XmlStorage(pasta_xml), banco, CNPJ_EXEMPLO).importar()
    env = tmp_path / ".env"
    env.write_text(f"CNPJ_EMPRESA={CNPJ_EXEMPLO}\nNFSE_BANCO={banco}\n", encoding="utf-8")
    for k in ("CNPJ_EMPRESA", "NFSE_BANCO"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NFSE_ENV_FILE", str(env))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_dashboard_renderiza(ambiente):
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    assert [m.label for m in at.metric] == ["Faturamento (emitidas)", "Serviços tomados (recebidas)",
                                            "ISS retido pelos clientes", "Quantidade de notas"]
    assert at.metric[3].value == "48"
    assert len(at.dataframe) == 4


def test_dashboard_sem_banco(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(f"CNPJ_EMPRESA={CNPJ_EXEMPLO}\nNFSE_BANCO={tmp_path / 'nao-existe.db'}\n", encoding="utf-8")
    monkeypatch.setenv("NFSE_ENV_FILE", str(env))
    monkeypatch.delenv("NFSE_BANCO", raising=False)
    get_settings.cache_clear()
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    get_settings.cache_clear()
    assert not at.exception
    assert "Rode primeiro" in at.warning[0].value

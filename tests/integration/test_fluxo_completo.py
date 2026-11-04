"""Simulador do ADN -> download -> importação -> relatórios, salvo em pasta temporária."""
import importlib.util
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from conftest import CNPJ_EXEMPLO
from src.nfse.clients.adn import AdnClient
from src.nfse.clients.adn.errors import AdnUrlInvalida
from src.nfse.data import EstadoRepository, XmlStorage
from src.nfse.services import relatorios_service as rel
from src.nfse.services.download_service import DownloadService
from src.nfse.services.import_service import ImportService

RAIZ = Path(__file__).resolve().parents[2]


def _fake_adn():
    spec = importlib.util.spec_from_file_location("fake_adn", RAIZ / "tools" / "fake_adn.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def servidor(pasta_xml):
    fake = _fake_adn()
    srv = fake.ServidorFake(("127.0.0.1", 0), fake.carregar(pasta_xml), verboso=False)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_download_importacao_e_relatorios(servidor, tmp_path):
    storage = XmlStorage(tmp_path / "notas")
    estado = EstadoRepository(tmp_path / "estado.json")
    agora = datetime(2026, 11, 3, 8, 0)
    servico = DownloadService(AdnClient(servidor, CNPJ_EXEMPLO), estado, storage, relogio=lambda: agora)

    res = servico.executar()
    assert (res.lotes, res.recebidos, res.novos, res.ultimo_nsu, res.fila_esgotada) == (2, 54, 54, 54, True)
    assert len(storage.listar()) == 54
    assert estado.ler().ultima_consulta == agora

    # regra de 1 hora
    assert servico.executar().aguardar_ate == agora + timedelta(hours=1)
    # forçado: nada novo, nada duplicado
    assert servico.executar(forcar=True).novos == 0

    banco = tmp_path / "notas.db"
    imp = ImportService(storage, banco, CNPJ_EXEMPLO)
    r1 = imp.importar()
    assert (r1.novas, r1.existentes, r1.erros, r1.cancelamentos, r1.canceladas) == (51, 0, 0, 3, 3)
    r2 = imp.importar()
    assert (r2.novas, r2.existentes, r2.canceladas) == (0, 51, 0)

    df = rel.carregar_notas(banco)
    recorte = rel.recortar(df, df["competencia"].unique(), ["EMITIDA", "RECEBIDA"])
    t = rel.totais(recorte)
    assert t.quantidade == 48 and t.canceladas == 3
    assert t.faturamento == pytest.approx(recorte.emitidas["base_calculo"].sum())
    assert len(rel.ranking(recorte.emitidas, "tomador_nome")) == 5
    assert set(rel.mensal(recorte.validas)["competencia"]) == {"2026-07", "2026-08", "2026-09"}


def test_url_errada(servidor):
    cliente = AdnClient(servidor + "/errado", CNPJ_EXEMPLO)
    with pytest.raises(AdnUrlInvalida):
        cliente.consultar(0)

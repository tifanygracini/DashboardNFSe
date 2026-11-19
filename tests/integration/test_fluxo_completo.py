"""Simulador do ADN -> robô multiempresa -> download -> importação -> relatórios, em pasta temporária."""
import importlib.util
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from conftest import CNPJ_EXEMPLO, cadastrar
from nfse.clients.adn import AdnClient
from nfse.clients.adn.errors import AdnUrlInvalida
from nfse.config.cofre import CofreMemoria
from nfse.data import DestinoBanco, EmpresasRepository, EstadoBanco, conectar
from nfse.services import relatorios_service as rel
from nfse.services.robo_service import AGUARDANDO, OK, SEM_CERTIFICADO, RoboService

RAIZ = Path(__file__).resolve().parents[2]
OUTRA = "11222333000181"  # cliente sem certificado


def _fake_adn():
    spec = importlib.util.spec_from_file_location("fake_adn", RAIZ / "tools" / "fake_adn.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def servidor(pasta_xml):
    from http.server import HTTPServer
    fake = _fake_adn()
    fake.carregar(pasta_xml)
    srv = HTTPServer(("127.0.0.1", 0), fake.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_robo_baixa_importa_e_respeita_a_regra_de_1_hora(servidor, tmp_path):
    destino = DestinoBanco(tmp_path / "notas.db")
    cadastrar(destino, CNPJ_EXEMPLO, "EMPRESA EXEMPLO LTDA")
    agora = datetime(2026, 11, 3, 8, 0)
    robo = RoboService(destino, CofreMemoria(), tmp_path / "notas", servidor, usar_certificado=False,
                       relogio=lambda: agora)

    [r] = robo.executar()
    assert (r.situacao, r.recebidos, r.novos, r.importadas, r.canceladas) == (OK, 54, 54, 51, 3)
    assert len(list((tmp_path / "notas" / CNPJ_EXEMPLO).rglob("*.xml"))) == 54
    estado = EstadoBanco(destino, CNPJ_EXEMPLO).ler()
    assert estado.ultimo_nsu == 54 and estado.ultima_consulta == agora

    [r2] = robo.executar()  # regra de 1 hora
    assert r2.situacao == AGUARDANDO and r2.novos == 0
    with conectar(destino) as con:
        assert EmpresasRepository(con).obter(CNPJ_EXEMPLO).cert_arquivo == ""
        linha = con.linhas(f"SELECT robo_situacao FROM {con.empresas} WHERE cnpj=?", (CNPJ_EXEMPLO,))[0]
    assert linha["robo_situacao"] == AGUARDANDO

    df = rel.carregar_notas(destino, CNPJ_EXEMPLO)
    recorte = rel.recortar(df, df["competencia"].unique(), ["EMITIDA", "RECEBIDA"])
    t = rel.totais(recorte)
    assert t.quantidade == 48 and t.canceladas == 3
    assert t.faturamento == pytest.approx(recorte.emitidas["base_calculo"].sum())
    assert len(rel.ranking(recorte.emitidas, "tomador_nome")) == 5
    assert set(rel.mensal(recorte.validas)["competencia"]) == {"2026-07", "2026-08", "2026-09"}


def test_empresa_sem_certificado_nao_para_as_outras(servidor, tmp_path):
    destino = DestinoBanco(tmp_path / "notas.db")
    cadastrar(destino, CNPJ_EXEMPLO, "EMPRESA EXEMPLO LTDA")
    cadastrar(destino, OUTRA, "OUTRA LTDA")
    robo = RoboService(destino, CofreMemoria(), tmp_path / "notas", servidor, usar_certificado=True,
                       fabrica_cliente=lambda base, cnpj, certificado: AdnClient(base, cnpj))
    with conectar(destino) as con:  # só a primeira tem certificado (o simulador não confere)
        EmpresasRepository(con).definir_certificado(CNPJ_EXEMPLO, str(tmp_path / "x.pfx"), CNPJ_EXEMPLO,
                                                     (datetime.now() + timedelta(days=200)).date().isoformat())
    robo.certificados.cofre.guardar(CNPJ_EXEMPLO, "senha")
    resultados = {r.cnpj: r for r in robo.executar()}
    assert resultados[CNPJ_EXEMPLO].situacao == OK and resultados[CNPJ_EXEMPLO].importadas == 51
    assert resultados[OUTRA].situacao == SEM_CERTIFICADO


def test_url_errada(servidor):
    cliente = AdnClient(servidor + "/errado", CNPJ_EXEMPLO)
    with pytest.raises(AdnUrlInvalida):
        cliente.consultar(0)

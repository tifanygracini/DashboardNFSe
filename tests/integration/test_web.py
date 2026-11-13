"""Interface web (FastAPI) contra um banco SQLite importado das fixtures.

O login do portal é simulado: o teste substitui a dependência de usuário do informe-auth.
O fluxo real de sessão compartilhada é testado no repositório informe-portal.
"""
import re

import pytest

pytest.importorskip("informe_auth")
from fastapi import Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from conftest import CNPJ_EXEMPLO  # noqa: E402
from informe_auth import Banco, Identidade, Usuario  # noqa: E402
from informe_auth.config import Config  # noqa: E402
from nfse.config.settings import carregar  # noqa: E402
from nfse.data import DestinoBanco, XmlStorage  # noqa: E402
from nfse.services.import_service import ImportService  # noqa: E402
from nfse.web.app import PASTA, criar_app  # noqa: E402

CONSULTA = Usuario(1, "Carla Consulta", "carla@x.com", frozenset({"nfse:ver"}))
ANALISTA = Usuario(2, "Ana Analista", "ana@x.com", frozenset({"nfse:ver", "nfse:exportar"}))
SEM_ACESSO = Usuario(3, "Davi DP", "davi@x.com", frozenset({"folha:ver"}))


@pytest.fixture
def settings(tmp_path, pasta_xml, monkeypatch):
    banco = tmp_path / "notas.db"
    ImportService(XmlStorage(pasta_xml), DestinoBanco(banco), CNPJ_EXEMPLO).importar()
    env = tmp_path / ".env"
    env.write_text(f"CNPJ_EMPRESA={CNPJ_EXEMPLO}\nNFSE_BANCO={banco}\n", encoding="utf-8")
    for k in ("CNPJ_EMPRESA", "NFSE_BANCO", "NFSE_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    return carregar(env)


def montar(settings, usuario: Usuario | None):
    cfg = Config(database_url="postgresql://ninguem@localhost/nada", sistema="nfse",
                 portal_url="https://portal.informecontabil.com", session_secret="s" * 40, cookie_secure=False)
    idt = Identidade(cfg, Banco(cfg.database_url), pasta_templates=PASTA / "templates")
    app = criar_app(settings, identidade=idt, abrir_banco_acesso=False)
    registrados = []
    idt.registrar = lambda request, u, acao, **kw: registrados.append((u.id, acao, kw))

    if usuario is not None:
        def falso(request: Request) -> Usuario:
            request.state.usuario = usuario
            return usuario
        app.dependency_overrides[idt.usuario] = falso
    else:
        idt.usuario_da_requisicao = lambda request: None
    c = TestClient(app)
    c.registrados = registrados
    return c


def test_sem_login_vai_para_o_portal(settings):
    r = montar(settings, None).get("/?de=2026-07", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("https://portal.informecontabil.com/entrar?volta=http%3A%2F%2Ftestserver%2F")


def test_sem_permissao(settings):
    r = montar(settings, SEM_ACESSO).get("/")
    assert r.status_code == 403 and "Acesso não liberado" in r.text


def test_painel_mostra_os_mesmos_totais_do_streamlit(settings):
    r = montar(settings, CONSULTA).get("/")
    assert r.status_code == 200
    rotulos = re.findall(r'class="metrica__rotulo">([^<]+)<', r.text)
    assert rotulos == ["Faturamento (emitidas)", "Serviços tomados (recebidas)", "ISS retido pelos clientes",
                       "Quantidade de notas"]
    valores = re.findall(r'class="metrica__valor">([^<]+)<', r.text)
    assert valores[3] == "48"  # mesmo número que o teste do Streamlit (test_dashboard.py)
    assert 'id="dados-grafico"' in r.text
    for titulo in ("Maiores clientes", "Maiores fornecedores de serviço", "Faturamento por tipo de serviço",
                   "Todas as notas filtradas"):
        assert titulo in r.text
    assert "Exportar planilha" not in r.text  # consulta não exporta
    assert "'unsafe-inline'" in r.headers["content-security-policy"]


def test_filtros_e_busca(settings):
    c = montar(settings, CONSULTA)
    tudo = c.get("/").text
    competencias = re.findall(r'<option(?: selected)?>(\d{4}-\d{2})</option>', tudo)
    assert competencias, "sem competências no filtro"
    primeira = competencias[0]
    so_emitidas = c.get(f"/?de={primeira}&ate={primeira}&tipo=EMITIDA").text
    assert "Recebida</td>" not in so_emitidas
    nada = c.get("/?busca=texto-que-nao-existe-em-nota")
    assert "0 nota(s)" in nada.text
    # parâmetros inválidos não quebram a página
    assert c.get("/?de=xx&ate=yy&tipo=OUTRO&pagina=-3").status_code == 200


def test_exportar_exige_permissao(settings):
    assert montar(settings, CONSULTA).get("/exportar.csv").status_code == 403


def test_exportar_csv(settings):
    c = montar(settings, ANALISTA)
    assert "Exportar planilha" in c.get("/").text
    r = c.get("/exportar.csv?tipo=EMITIDA")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    texto = r.content.decode("utf-8-sig")
    cabecalho = texto.splitlines()[0].split(";")
    assert cabecalho[:5] == ["Chave", "Número", "Emissão", "Competência", "Tipo"]
    assert all(";RECEBIDA;" not in linha for linha in texto.splitlines()[1:])
    assert c.registrados and c.registrados[0][1] == "nfse_exportou"


def test_plotly_servido_localmente(settings):
    r = montar(settings, CONSULTA).get("/_vendor/plotly.min.js")
    assert r.status_code == 200 and len(r.content) > 1_000_000


def test_banco_vazio(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(f"CNPJ_EMPRESA={CNPJ_EXEMPLO}\nNFSE_BANCO={tmp_path / 'nao-existe.db'}\n", encoding="utf-8")
    for k in ("CNPJ_EMPRESA", "NFSE_BANCO", "NFSE_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    r = montar(carregar(env), CONSULTA).get("/")
    assert r.status_code in (200, 503)
    assert "aviso" in r.text

"""Interface web (FastAPI) contra um banco SQLite com três empresas (uma com as notas das fixtures).

O login do portal é simulado: o teste substitui a dependência de usuário do informe-auth.
O fluxo real de sessão compartilhada é testado no repositório informe-portal.
"""
import re

import pytest

pytest.importorskip("informe_auth")
from fastapi import Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from conftest import CNPJ_EXEMPLO, cadastrar  # noqa: E402
from informe_auth import Banco, Identidade, Usuario  # noqa: E402
from informe_auth.config import Config  # noqa: E402
from nfse.config.settings import carregar  # noqa: E402
from nfse.data import DestinoBanco, EmpresasRepository, XmlStorage, conectar  # noqa: E402
from nfse.services.import_service import ImportService  # noqa: E402
from nfse.web.app import PASTA, criar_app  # noqa: E402

CONSULTA = Usuario(1, "Carla Consulta", "carla@x.com", frozenset({"nfse:ver"}))
ANALISTA = Usuario(2, "Ana Analista", "ana@x.com", frozenset({"nfse:ver", "nfse:exportar"}))
SEM_ACESSO = Usuario(3, "Davi DP", "davi@x.com", frozenset({"folha:ver"}))
OUTRA = "11222333000181"
MEI = "11444777000161"
LIMPAR = ("CNPJ_EMPRESA", "NFSE_BANCO", "NFSE_DATABASE_URL")


@pytest.fixture
def settings(tmp_path, pasta_xml, monkeypatch):
    banco = tmp_path / "notas.db"
    destino = DestinoBanco(banco)
    ImportService(XmlStorage(pasta_xml), destino, CNPJ_EXEMPLO).importar()
    cadastrar(destino, CNPJ_EXEMPLO, "EXEMPLO SERVICOS LTDA", "Lucro Presumido", codigo="315", fantasia="Exemplo")
    cadastrar(destino, OUTRA, "OUTRA COMERCIO LTDA", "Simples Nacional", codigo="42")
    cadastrar(destino, MEI, "JOÃO DA SILVA", "MEI", codigo="7")
    with conectar(destino) as con:
        EmpresasRepository(con).definir_certificado(CNPJ_EXEMPLO, "S:/cert/x.pfx", CNPJ_EXEMPLO, "2099-01-01")
        EmpresasRepository(con).registrar_execucao(OUTRA, "erro", "Acesso negado (403)")
    env = tmp_path / ".env"
    env.write_text(f"NFSE_BANCO={banco}\n", encoding="utf-8")
    for k in LIMPAR:
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


def empresas_na_tela(html: str) -> list[str]:
    """Empresas da tabela; na visão de empresa única (sem tabela), a empresa mostrada."""
    if "cabecalho-unica" in html:
        return re.findall(r'href="/empresa/(\d{14})\?de=', html)[:1]
    return re.findall(r'<a href="/empresa/(\d{14})\?', html)


def test_uma_empresa_escolhida_adapta_a_tela(settings):
    c = montar(settings, CONSULTA)
    html = c.get(f"/?empresa={CNPJ_EXEMPLO}&busca=outra&regime=MEI").text  # o seletor vale sozinho
    assert "cabecalho-unica" in html and "EXEMPLO SERVICOS LTDA" in html
    assert 'class="empresas"' not in html and 'class="regimes"' not in html  # sem tabela nem botões de regime
    rotulos = re.findall(r'class="metrica__rotulo">([^<]+)<', html)
    assert rotulos == ["Faturamento no período", "Notas emitidas", "Ticket médio por nota", "Média mensal",
                       "Receita dos últimos 12 meses"]
    for grafico in ("dados-evolucao-faturamento", "dados-evolucao-notas", "dados-evolucao-acumulado"):
        assert f'id="{grafico}"' in html
    assert f'<option value="{CNPJ_EXEMPLO}" selected>315 · EXEMPLO SERVICOS LTDA</option>' in html
    assert 'href="/?de=' in html  # "← Todas as empresas" sai da visão única
    assert "única empresa nos filtros" not in html


def test_busca_com_um_resultado_tambem_adapta(settings):
    html = montar(settings, CONSULTA).get("/?busca=outra+comercio").text
    assert "cabecalho-unica" in html and "única empresa nos filtros" in html
    assert "Nenhuma nota emitida por esta empresa" in html  # sem notas: avisa em vez de gráfico vazio


def test_empresa_invalida_no_seletor_e_ignorada(settings):
    html = montar(settings, CONSULTA).get("/?empresa=00000000000000").text
    assert "cabecalho-unica" not in html and len(empresas_na_tela(html)) == 3


def test_tela_da_empresa_tem_os_graficos_de_evolucao(settings):
    html = montar(settings, CONSULTA).get(f"/empresa/{CNPJ_EXEMPLO}").text
    assert 'id="dados-evolucao-faturamento"' in html and 'id="dados-evolucao-notas"' in html


def test_sem_login_vai_para_o_portal(settings):
    r = montar(settings, None).get("/?regime=MEI", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("https://portal.informecontabil.com/entrar?volta=http%3A%2F%2Ftestserver%2F")


def test_sem_permissao(settings):
    for url in ("/", f"/empresa/{CNPJ_EXEMPLO}"):
        r = montar(settings, SEM_ACESSO).get(url)
        assert r.status_code == 403 and "Acesso não liberado" in r.text


def test_carteira_lista_todas_as_empresas(settings):
    r = montar(settings, CONSULTA).get("/")
    assert r.status_code == 200
    na_tela = empresas_na_tela(r.text)
    assert na_tela[0] == CNPJ_EXEMPLO and set(na_tela) == {CNPJ_EXEMPLO, OUTRA, MEI}  # maior faturamento primeiro
    rotulos = re.findall(r'class="metrica__rotulo">([^<]+)<', r.text)
    assert rotulos == ["Empresas na seleção", "Faturamento (emitidas)", "Serviços tomados (recebidas)",
                       "Certificados com pendência"]
    valores = re.findall(r'class="metrica__valor">([^<]+)<', r.text)
    assert valores[0] == "3" and valores[3] == "2"  # duas sem certificado
    assert "Simples Nacional" in r.text and "Lucro Presumido" in r.text and 'id="dados-grafico"' in r.text
    assert "Exportar lista" not in r.text
    assert "'unsafe-inline'" in r.headers["content-security-policy"]


@pytest.mark.parametrize("consulta, esperadas", [
    ("regime=MEI", {MEI}),
    ("regime=Lucro+Presumido", {CNPJ_EXEMPLO}),
    ("busca=outra+comercio", {OUTRA}),
    ("busca=exemplo", {CNPJ_EXEMPLO}),               # nome fantasia
    ("busca=11.222.333%2F0001-81", {OUTRA}),         # CNPJ com máscara
    ("busca=4777", {MEI}),                           # pedaço do CNPJ
    ("busca=315", {CNPJ_EXEMPLO}),                   # código do Domínio
    ("busca=0042", {OUTRA}),                         # código com zeros à esquerda
    ("busca=joao", {MEI}),                           # acento não importa
    ("situacao=com_notas", {CNPJ_EXEMPLO}),
    ("situacao=sem_notas", {OUTRA, MEI}),
    ("situacao=cert_pendente", {OUTRA, MEI}),
    ("situacao=erro_robo", {OUTRA}),
    ("busca=nada-com-isso", set()),
])
def test_filtros_da_carteira(settings, consulta, esperadas):
    r = montar(settings, CONSULTA).get(f"/?{consulta}")
    assert r.status_code == 200
    assert set(empresas_na_tela(r.text)) == esperadas


def test_contagem_por_regime_respeita_a_busca(settings):
    html = montar(settings, CONSULTA).get("/?busca=ltda").text
    assert re.search(r'Todos <span class="regime__qtd">2</span>', html)
    assert "MEI <span" not in html


def test_parametros_invalidos_nao_quebram(settings):
    c = montar(settings, CONSULTA)
    assert c.get("/?de=xx&ate=yy&regime=OUTRO&situacao=z&ordem=w&pagina=-3").status_code == 200
    r = c.get("/empresa/123")
    assert r.status_code == 200 and "não encontrada" in r.text
    assert c.get(f"/empresa/{CNPJ_EXEMPLO}?de=xx&tipo=OUTRO&pagina=-3").status_code == 200
    assert 'href="//malicioso.com"' not in c.get(f"/empresa/{CNPJ_EXEMPLO}?volta=//malicioso.com").text


def test_painel_da_empresa_mostra_os_mesmos_totais_do_streamlit(settings):
    r = montar(settings, CONSULTA).get(f"/empresa/{CNPJ_EXEMPLO}?volta=/%3Fregime%3DMEI")
    assert r.status_code == 200
    assert "EXEMPLO SERVICOS LTDA" in r.text and "315" in r.text and "Lucro Presumido" in r.text
    assert 'href="/?regime=MEI"' in r.text  # volta para a lista filtrada
    rotulos = re.findall(r'class="metrica__rotulo">([^<]+)<', r.text)
    assert rotulos == ["Faturamento (emitidas)", "Serviços tomados (recebidas)", "ISS retido pelos clientes",
                       "Quantidade de notas"]
    assert re.findall(r'class="metrica__valor">([^<]+)<', r.text)[3] == "48"
    for titulo in ("Maiores clientes", "Maiores fornecedores de serviço", "Faturamento por tipo de serviço",
                   "Todas as notas filtradas"):
        assert titulo in r.text


def test_empresa_sem_notas_e_com_erro_do_robo(settings):
    r = montar(settings, CONSULTA).get(f"/empresa/{OUTRA}")
    assert r.status_code == 200
    assert "Ainda não há notas desta empresa" in r.text and "Acesso negado (403)" in r.text


def test_filtros_da_empresa(settings):
    c = montar(settings, CONSULTA)
    tudo = c.get(f"/empresa/{CNPJ_EXEMPLO}").text
    primeira = re.findall(r'<option(?: selected)?>(\d{4}-\d{2})</option>', tudo)[0]
    so_emitidas = c.get(f"/empresa/{CNPJ_EXEMPLO}?de={primeira}&ate={primeira}&tipo=EMITIDA").text
    assert "Recebida</td>" not in so_emitidas
    assert "0 nota(s)" in c.get(f"/empresa/{CNPJ_EXEMPLO}?busca=texto-que-nao-existe-em-nota").text


def test_exportar_exige_permissao(settings):
    c = montar(settings, CONSULTA)
    assert c.get("/exportar.csv").status_code == 403
    assert c.get(f"/empresa/{CNPJ_EXEMPLO}/exportar.csv").status_code == 403


def test_exportar_csv_da_empresa(settings):
    c = montar(settings, ANALISTA)
    assert "Exportar planilha" in c.get(f"/empresa/{CNPJ_EXEMPLO}").text
    r = c.get(f"/empresa/{CNPJ_EXEMPLO}/exportar.csv?tipo=EMITIDA")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    texto = r.content.decode("utf-8-sig")
    assert texto.splitlines()[0].split(";")[:5] == ["Chave", "Número", "Emissão", "Competência", "Tipo"]
    assert all(";RECEBIDA;" not in linha for linha in texto.splitlines()[1:])
    assert c.registrados[-1][1] == "nfse_exportou" and CNPJ_EXEMPLO in c.registrados[-1][2]["alvo"]


def test_exportar_csv_da_carteira(settings):
    c = montar(settings, ANALISTA)
    assert "Exportar lista" in c.get("/").text
    r = c.get("/exportar.csv?regime=Simples+Nacional")
    assert r.status_code == 200
    linhas = r.content.decode("utf-8-sig").splitlines()
    assert linhas[0].startswith("Código Domínio;CNPJ;Razão social") and len(linhas) == 2
    assert "11.222.333/0001-81" in linhas[1]
    assert c.registrados[-1][1] == "nfse_exportou_carteira"


def test_plotly_servido_localmente(settings):
    r = montar(settings, CONSULTA).get("/_vendor/plotly.min.js")
    assert r.status_code == 200 and len(r.content) > 1_000_000


def test_banco_vazio(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(f"NFSE_BANCO={tmp_path / 'nao-existe.db'}\n", encoding="utf-8")
    for k in LIMPAR:
        monkeypatch.delenv(k, raising=False)
    r = montar(carregar(env), CONSULTA).get("/")
    assert r.status_code in (200, 503)
    assert "aviso" in r.text

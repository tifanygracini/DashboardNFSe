"""Cadastro de empresas, migração do banco de uma empresa só e sincronização com o Acessórias."""
import json
import sqlite3
from datetime import date

import pytest

from conftest import CNPJ_EXEMPLO, cadastrar
from nfse.clients.acessorias import AcessoriasClient, ErroAcessorias, mapear
from nfse.config.secret import Segredo
from nfse.data import BancoDesatualizado, DestinoBanco, EmpresasRepository, NotasRepository, XmlStorage, conectar
from nfse.domain import empresa as emp
from nfse.services import relatorios_service as rel
from nfse.services import sincronizar_service
from nfse.services.import_service import ImportService

OUTRA = "11222333000181"


@pytest.mark.parametrize("texto, categoria", [
    ("SIMPLES NACIONAL - C  Inscrição Estadual  e com folha de pagamento", emp.SIMPLES),
    ("MEI - Micro Empreendedor Individual", emp.MEI),
    ("Lucro Presumido - S  Inscrição Estadual - Serviço exclusivamente", emp.PRESUMIDO),
    ("Lucro Real C inscrição estadual com folha de pagamento  e Contribuinte do IPI", emp.REAL),
    ("Entidades imunes e isentas - sem inscrição estadual", emp.IMUNE),
    ("", emp.OUTROS), (None, emp.OUTROS), ("Produtor rural", emp.OUTROS),
])
def test_regime_normalizado(texto, categoria):
    assert emp.normalizar_regime(texto) == categoria


def test_situacao_do_certificado():
    hoje = date(2026, 11, 18)
    assert emp.situacao_certificado("", hoje) == emp.CERT_AUSENTE
    assert emp.situacao_certificado("2026-11-17", hoje) == emp.CERT_VENCIDO
    assert emp.situacao_certificado("2026-12-10", hoje) == emp.CERT_VENCENDO
    assert emp.situacao_certificado("2027-06-01", hoje) == emp.CERT_OK
    assert emp.raiz("12.345.678/0002-00") == "12345678"


def test_mapear_registro_do_acessorias():
    raw = {"ID": "720", "Identificador": "11.222.333/0001-81", "Razao": "2 M  TERRAPLANAGEM LTDA",
           "Fantasia": "2M", "UF": "SP", "Regime": "SIMPLES NACIONAL - C  Inscrição Estadual",
           "GrupoDeEmpresas": "Geral", "CodigoDominio": "315"}
    d = mapear(raw)
    assert d["cnpj"] == OUTRA and d["razao_social"] == "2 M TERRAPLANAGEM LTDA"
    assert d["regime"] == emp.SIMPLES and d["codigo_dominio"] == "315" and d["acessorias_id"] == "720"
    assert mapear(raw, campo_dominio="ID")["codigo_dominio"] == "720"
    assert mapear({**raw, "Identificador": "123.456.789-09"}) is None  # CPF fica de fora


def _banco_antigo(arquivo, linhas=1):
    """Tabela notas como na versão de uma empresa só (chave primária = chave)."""
    con = sqlite3.connect(arquivo)
    con.execute("CREATE TABLE notas (chave TEXT PRIMARY KEY, numero TEXT, data_emissao TEXT, competencia TEXT, tipo TEXT, "
                "prestador_cnpj TEXT, prestador_nome TEXT, tomador_cnpj TEXT, tomador_nome TEXT, codigo_servico TEXT, "
                "descricao_servico TEXT, valor_servico REAL, desconto REAL, base_calculo REAL, aliquota REAL, "
                "valor_iss REAL, iss_retido INTEGER, valor_retido REAL, valor_liquido REAL, status TEXT, arquivo TEXT)")
    for i in range(linhas):
        con.execute("INSERT INTO notas (chave, competencia, tipo, base_calculo, status) VALUES (?, '2026-01', "
                    "'EMITIDA', 100, 'NORMAL')", (f"chave{i}",))
    con.commit()
    con.close()


def test_migra_banco_de_uma_empresa(tmp_path):
    arq = tmp_path / "notas.db"
    _banco_antigo(arq, linhas=3)
    with pytest.raises(BancoDesatualizado):  # sem saber de quem são as notas, não migra
        with conectar(DestinoBanco(arq)):
            pass
    with pytest.raises(BancoDesatualizado):  # o dashboard avisa em vez de quebrar
        rel.carregar_resumo(DestinoBanco(arq))

    destino = DestinoBanco(arq, cnpj_legado=CNPJ_EXEMPLO)
    with conectar(destino) as con:
        assert con.executar("SELECT count(*) FROM notas WHERE empresa_cnpj=?", (CNPJ_EXEMPLO,)).fetchone()[0] == 3
        assert EmpresasRepository(con).obter(CNPJ_EXEMPLO) is not None
    with conectar(destino):  # rodar de novo não faz nada
        pass
    assert len(rel.carregar_notas(destino, CNPJ_EXEMPLO)) == 3


def test_mesma_nota_em_duas_empresas(tmp_path, pasta_xml):
    """Nota entre dois clientes do escritório: emitida para um, recebida para o outro."""
    destino = DestinoBanco(tmp_path / "notas.db")
    ImportService(XmlStorage(pasta_xml), destino, CNPJ_EXEMPLO).importar()
    df = rel.carregar_notas(destino, CNPJ_EXEMPLO)
    linha = df.iloc[0]
    with conectar(destino) as con:
        from nfse.domain.models import Nota, StatusNota, TipoNota
        campos = {k: linha[k] for k in Nota.__dataclass_fields__ if k not in ("tipo", "status", "iss_retido")}
        nota = Nota(**campos, tipo=TipoNota.RECEBIDA, status=StatusNota.NORMAL, iss_retido=False)
        assert NotasRepository(con, OUTRA).inserir(nota) is True
        assert NotasRepository(con, OUTRA).inserir(nota) is False
    assert len(rel.carregar_notas(destino, OUTRA)) == 1
    assert len(rel.carregar_notas(destino, CNPJ_EXEMPLO)) == len(df)


class _ApiFalsa:
    def __init__(self, paginas):
        self.paginas, self.urls = paginas, []

    def __call__(self, req, timeout):
        self.urls.append(req.full_url)
        assert req.get_header("Authorization") == "Bearer token-secreto"
        pagina = int(req.full_url.split("Pagina=")[1].split("&")[0])
        corpo = self.paginas[pagina - 1] if pagina <= len(self.paginas) else []
        return 200, json.dumps(corpo)


def _empresa(cnpj, razao, regime="SIMPLES NACIONAL - S  Inscrição Estadual", **extra):
    return {"ID": cnpj[-3:], "Identificador": cnpj, "Razao": razao, "Fantasia": "", "UF": "SP",
            "Regime": regime, "GrupoDeEmpresas": "Geral", **extra}


def test_sincronizar_acessorias(tmp_path):
    destino = DestinoBanco(tmp_path / "notas.db")
    api = _ApiFalsa([[_empresa(CNPJ_EXEMPLO, "EXEMPLO LTDA"), _empresa("12345678909", "PESSOA FISICA")],
                     [_empresa(OUTRA, "OUTRA LTDA", "Lucro Presumido - S")]])
    cliente = AcessoriasClient("https://api.acessorias.com", Segredo("token-secreto"), abrir=api, dormir=lambda s: None)
    r = sincronizar_service.sincronizar(cliente, destino)
    assert (r.lidas, r.novas, r.ignoradas, r.inativadas) == (3, 2, 1, 0)
    assert "registrationData" in api.urls[0] and "ativa=S" in api.urls[0]

    with conectar(destino) as con:  # código do Domínio vindo de planilha não é apagado pela sincronização
        EmpresasRepository(con).definir_codigo_dominio(OUTRA, "77")
    api2 = _ApiFalsa([[_empresa(OUTRA, "OUTRA LTDA (NOVO NOME)", "Lucro Presumido - S")]])
    r2 = sincronizar_service.sincronizar(
        AcessoriasClient("https://x", Segredo("token-secreto"), abrir=api2, dormir=lambda s: None), destino)
    assert (r2.novas, r2.atualizadas, r2.inativadas) == (0, 1, 1)
    with conectar(destino) as con:
        repo = EmpresasRepository(con)
        outra = repo.obter(OUTRA)
        assert outra.razao_social == "OUTRA LTDA (NOVO NOME)" and outra.codigo_dominio == "77"
        assert outra.regime == emp.PRESUMIDO
        assert repo.obter(CNPJ_EXEMPLO).ativa is False


def test_acessorias_token_recusado_e_sem_token():
    with pytest.raises(ErroAcessorias, match="Token"):
        AcessoriasClient("https://x", None)
    cliente = AcessoriasClient("https://x", Segredo("t"), abrir=lambda req, t: (401, ""), dormir=lambda s: None)
    with pytest.raises(ErroAcessorias, match="recusou") as e:
        list(cliente.listar_ativas())
    assert "t" not in str(e.value).split("token")[0].split()  # o token nunca vai na mensagem


def test_importar_codigos_dominio(tmp_path):
    destino = DestinoBanco(tmp_path / "notas.db")
    cadastrar(destino, OUTRA, "OUTRA LTDA")
    planilha = tmp_path / "codigos.csv"
    planilha.write_text("cnpj;codigo\n11.222.333/0001-81;0042\n99999999000191;5\n", encoding="utf-8")
    feitas, avisos = sincronizar_service.importar_codigos_dominio(planilha, destino)
    assert feitas == 1 and len(avisos) == 1
    with conectar(destino) as con:
        assert EmpresasRepository(con).obter(OUTRA).codigo_dominio == "0042"

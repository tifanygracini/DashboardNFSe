import pytest

from src.nfse.config.secret import Segredo
from src.nfse.config.settings import ConfigError, carregar

CNPJ = "11222333000181"  # CNPJ fictício com DV válido


@pytest.fixture(autouse=True)
def limpar_ambiente(monkeypatch):
    for k in ("CNPJ_EMPRESA", "CERT_PFX", "CERT_SENHA", "PASTA_NOTAS", "NFSE_BANCO", "NFSE_ESTADO", "ADN_AMBIENTE"):
        monkeypatch.delenv(k, raising=False)


def env(tmp_path, texto):
    arq = tmp_path / ".env"
    arq.write_text(texto, encoding="utf-8")
    return arq


def test_carrega_e_resolve_caminhos(tmp_path):
    s = carregar(env(tmp_path, f"CNPJ_EMPRESA={CNPJ}\n"))
    assert s.cnpj_empresa == CNPJ
    assert s.pasta_notas.is_absolute() and s.pasta_notas.name == "notas"
    assert s.adn_base_url == "https://adn.nfse.gov.br"


def test_cnpj_com_pontuacao_e_invalido(tmp_path):
    assert carregar(env(tmp_path, "CNPJ_EMPRESA=11.222.333/0001-81\n")).cnpj_empresa == CNPJ
    with pytest.raises(ConfigError):
        carregar(env(tmp_path, "CNPJ_EMPRESA=11222333000199\n"))


def test_ambiente_do_sistema_tem_prioridade(tmp_path, monkeypatch):
    monkeypatch.setenv("ADN_AMBIENTE", "restrita")
    s = carregar(env(tmp_path, f"CNPJ_EMPRESA={CNPJ}\nADN_AMBIENTE=producao\n"))
    assert s.adn_ambiente == "restrita"


def test_senha_nunca_aparece(tmp_path):
    s = carregar(env(tmp_path, f"CNPJ_EMPRESA={CNPJ}\nCERT_SENHA=minha-senha-secreta\n"))
    assert "minha-senha-secreta" not in repr(s) and "minha-senha-secreta" not in str(s.cert_senha)
    assert s.cert_senha.revelar() == "minha-senha-secreta"


def test_nao_altera_os_environ(tmp_path):
    import os
    carregar(env(tmp_path, f"CNPJ_EMPRESA={CNPJ}\nCERT_SENHA=x\n"))
    assert "CERT_SENHA" not in os.environ


def test_sem_terminal_falha_em_vez_de_travar(tmp_path):
    pfx = tmp_path / "cert.pfx"
    pfx.write_bytes(b"")
    s = carregar(env(tmp_path, f"CNPJ_EMPRESA={CNPJ}\nCERT_PFX={pfx}\n"))
    with pytest.raises(ConfigError, match="CERT_SENHA"):
        s.credenciais_certificado(interativo=False)


def test_segredo_nao_serializa():
    import pickle
    with pytest.raises(TypeError):
        pickle.dumps(Segredo("x"))

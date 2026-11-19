"""Certificados A1 na pasta de rede: leitura do CNPJ/validade, ligação matriz/filial e senhas no cofre.

Os certificados são gerados no próprio teste (autoassinados, no formato ICP-Brasil: CN "RAZAO:CNPJ" e
otherName 2.16.76.1.3.3 com o CNPJ).
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from conftest import cadastrar
from nfse.config.cofre import CofreMemoria
from nfse.config.secret import Segredo
from nfse.data import DestinoBanco, EmpresasRepository, conectar
from nfse.services.certificados_service import (CertificadoIlegivel, CertificadosService, cnpj_no_nome,
                                                ler_certificado)

MATRIZ = "11222333000181"
FILIAL = "11222333000262"
OUTRO = "11223344000186"


def gerar_pfx(caminho, cnpj, senha, dias=365, no_cn=True, no_san=True):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    chave = ec.generate_private_key(ec.SECP256R1())
    cn = f"EMPRESA TESTE LTDA:{cnpj}" if no_cn else "EMPRESA TESTE LTDA"
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    fim = datetime.now(timezone.utc) + timedelta(days=dias)
    b = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key())
         .serial_number(x509.random_serial_number()).not_valid_before(fim - timedelta(days=dias + 365))
         .not_valid_after(fim))
    if no_san:
        valor = b"\x04\x0e" + cnpj.encode()  # OCTET STRING com os 14 dígitos
        b = b.add_extension(x509.SubjectAlternativeName([x509.OtherName(x509.ObjectIdentifier("2.16.76.1.3.3"), valor)]),
                            critical=False)
    cert = b.sign(chave, hashes.SHA256())
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(pkcs12.serialize_key_and_certificates(
        b"cert", chave, cert, None, serialization.BestAvailableEncryption(senha.encode())))
    return caminho


def test_cnpj_no_nome_do_arquivo(tmp_path):
    assert cnpj_no_nome(tmp_path / "EMPRESA - 11.222.3330001-81.pfx") == MATRIZ
    assert cnpj_no_nome(tmp_path / "Empresa Teste 11222333000181 senha.pfx") == MATRIZ
    assert cnpj_no_nome(tmp_path / "Empresa 11.222.333-0001-81.pfx") is None  # pontuação fora do padrão
    assert cnpj_no_nome(tmp_path / "Empresa 11222333000199.pfx") is None   # DV inválido
    assert cnpj_no_nome(tmp_path / "sem cnpj.pfx") is None


@pytest.mark.parametrize("no_cn, no_san", [(True, False), (False, True), (True, True)])
def test_le_cnpj_e_validade(tmp_path, no_cn, no_san):
    pfx = gerar_pfx(tmp_path / "a.pfx", MATRIZ, "s3nha", dias=100, no_cn=no_cn, no_san=no_san)
    info = ler_certificado(pfx, Segredo("s3nha"))
    assert info.titular == MATRIZ and info.nome == "EMPRESA TESTE LTDA"
    assert abs((info.validade - date.today()).days - 100) <= 1


def test_senha_errada_e_sem_cnpj(tmp_path):
    pfx = gerar_pfx(tmp_path / "a.pfx", MATRIZ, "certa")
    with pytest.raises(CertificadoIlegivel, match="senha incorreta"):
        ler_certificado(pfx, Segredo("errada"))
    sem = gerar_pfx(tmp_path / "b.pfx", MATRIZ, "x", no_cn=False, no_san=False)
    with pytest.raises(CertificadoIlegivel, match="sem CNPJ"):
        ler_certificado(sem, Segredo("x"))


def test_varredura_liga_matriz_filial_e_avisa_pendencias(tmp_path):
    destino = DestinoBanco(tmp_path / "notas.db")
    for cnpj, nome in ((MATRIZ, "MATRIZ"), (FILIAL, "FILIAL"), (OUTRO, "SEM CERTIFICADO")):
        cadastrar(destino, cnpj, nome)
    pasta = tmp_path / "certificados"
    novo = gerar_pfx(pasta / "2026" / f"Empresa {MATRIZ}.pfx", MATRIZ, "nova", dias=300)
    gerar_pfx(pasta / f"Empresa {MATRIZ} antigo.pfx", MATRIZ, "nova", dias=-10)        # vencido: perde
    gerar_pfx(pasta / "sem cnpj no nome.p12", "99999999000191", "x")                    # sem senha no cofre
    gerar_pfx(pasta / "Cliente 11444777000161.pfx", "11444777000161", "y")             # não é cliente
    (pasta / "leia-me.txt").write_text("não é certificado")

    cofre = CofreMemoria({MATRIZ: "nova", "11444777000161": "y"})
    r = CertificadosService(destino, cofre).varrer(pasta)
    assert r.arquivos == 4 and len(r.lidos) == 3
    assert len(r.sem_senha) == 1 and "sem cnpj no nome" in r.sem_senha[0]
    assert len(r.sem_empresa) == 1
    assert (r.empresas_com_certificado, r.empresas_sem_certificado) == (2, 1)

    with conectar(destino) as con:
        repo = EmpresasRepository(con)
        matriz, filial, outro = repo.obter(MATRIZ), repo.obter(FILIAL), repo.obter(OUTRO)
    assert matriz.cert_arquivo == str(novo) and filial.cert_arquivo == str(novo)
    assert filial.cert_titular == MATRIZ and matriz.situacao_certificado == "ok"
    assert outro.cert_arquivo == "" and outro.situacao_certificado == "ausente"

    servico = CertificadosService(destino, cofre)
    arq, senha = servico.credenciais(filial)
    assert arq == novo and senha.revelar() == "nova"
    with pytest.raises(CertificadoIlegivel):
        servico.credenciais(outro)


def test_planilha_de_senhas_por_arquivo(tmp_path):
    destino = DestinoBanco(tmp_path / "notas.db")
    cadastrar(destino, MATRIZ, "MATRIZ")
    pasta = tmp_path / "certificados"
    gerar_pfx(pasta / "certificado-sem-cnpj.pfx", MATRIZ, "abc123")
    planilha = tmp_path / "senhas.csv"
    planilha.write_text("arquivo;senha\ncertificado-sem-cnpj.pfx;abc123\nnao-existe.pfx;x\n;sem-arquivo\n",
                        encoding="utf-8")
    cofre = CofreMemoria()
    servico = CertificadosService(destino, cofre)
    feitas, avisos = servico.importar_senhas(planilha, pasta)
    assert feitas == 1 and len(avisos) == 2
    assert cofre.obter(MATRIZ).revelar() == "abc123"
    # a varredura seguinte reconhece o arquivo mesmo sem CNPJ no nome
    r = servico.varrer(pasta)
    assert r.empresas_com_certificado == 1 and not r.sem_senha


# ---------------------------------------------------------------- coleta automática das senhas
from nfse.services.certificados_service import NOVO, PRIMEIRO, escrever_relatorio  # noqa: E402
from nfse.services.coleta_senhas import senhas_candidatas  # noqa: E402


def test_senhas_candidatas_nos_formatos_da_pasta(tmp_path):
    raiz = tmp_path / "certificados"
    a = raiz / "EMPRESA A" / "EMPRESA A SENHA 019226.pfx"
    b = raiz / "EMPRESA B - senha abc@123" / "certificado.pfx"
    c = raiz / "EMPRESA C" / "cert.p12"
    d = raiz / "EMPRESA D" / "cert.pfx"
    for arq in (a, b, c, d):
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_bytes(b"")
    (c.parent / "senha.txt").write_text("Senha do certificado: Xy9#k2\n", encoding="utf-8")
    (d.parent / "leia.txt").write_text("q1w2e3\n", encoding="utf-8")         # .txt só com a senha
    (d.parent / "SENHA 777.txt").write_text("", encoding="utf-8")            # senha no nome do .txt
    assert senhas_candidatas(a, raiz) == ["019226"]
    assert senhas_candidatas(b, raiz) == ["abc@123"]
    assert senhas_candidatas(c, raiz)[0] == "Xy9#k2"
    assert set(senhas_candidatas(d, raiz)) >= {"q1w2e3", "777"}


def test_varredura_coleta_senha_da_pasta_e_troca_certificado_vencido(tmp_path):
    destino = DestinoBanco(tmp_path / "notas.db")
    cadastrar(destino, MATRIZ, "MATRIZ")
    cadastrar(destino, FILIAL, "FILIAL")
    pasta = tmp_path / "certificados"
    gerar_pfx(pasta / "MATRIZ" / "MATRIZ 2025 SENHA velha1.pfx", MATRIZ, "velha1", dias=-5)
    cofre = CofreMemoria()
    servico = CertificadosService(destino, cofre)

    r1 = servico.varrer(pasta)  # ninguém cadastrou senha: veio do nome do arquivo
    assert cofre.obter(MATRIZ).revelar() == "velha1" and r1.senhas_atualizadas == 1
    assert r1.contagem(PRIMEIRO) == 2 and all(m["vencido"] for m in r1.mudancas)

    # o certificado venceu; o escritório coloca o novo na subpasta, com a senha num .txt
    novo = gerar_pfx(pasta / "MATRIZ" / "2026" / "certificado.pfx", MATRIZ, "Nova#2026", dias=365)
    (novo.parent / "senha.txt").write_text("senha: Nova#2026", encoding="utf-8")
    r2 = servico.varrer(pasta)
    assert cofre.obter(MATRIZ).revelar() == "Nova#2026"  # trocou sozinho
    assert r2.contagem(NOVO) == 2 and not any(m["vencido"] for m in r2.mudancas)
    with conectar(destino) as con:
        filial = EmpresasRepository(con).obter(FILIAL)
    assert filial.cert_arquivo == str(novo) and filial.situacao_certificado == "ok"
    assert servico.credenciais(filial)[1].revelar() == "Nova#2026"

    r3 = servico.varrer(pasta)  # nada mudou: nada é regravado
    assert r3.senhas_atualizadas == 0 and r3.contagem("sem mudança") == 2

    relatorio = escrever_relatorio(r2, tmp_path / "logs" / "certificados.csv")
    texto = relatorio.read_text(encoding="utf-8-sig")
    assert "certificado novo" in texto and "Nova#2026" not in texto and "velha1" not in texto


def test_senha_anotada_errada_aparece_como_nao_abriu(tmp_path):
    destino = DestinoBanco(tmp_path / "notas.db")
    cadastrar(destino, MATRIZ, "MATRIZ")
    pasta = tmp_path / "certificados"
    gerar_pfx(pasta / "MATRIZ SENHA errada.pfx", MATRIZ, "certa")
    gerar_pfx(pasta / "sem anotacao.pfx", OUTRO, "x")
    r = CertificadosService(destino, CofreMemoria()).varrer(pasta)
    assert len(r.ilegiveis) == 1 and "senha incorreta" in r.ilegiveis[0]
    assert len(r.sem_senha) == 1 and "sem anotacao" in r.sem_senha[0]
    assert r.empresas_sem_certificado == 1

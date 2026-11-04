"""Gera 54 documentos FICTÍCIOS (51 NFS-e + 3 cancelamentos) para testar o sistema."""
import hashlib
import random
import sys
from pathlib import Path

saida = Path(sys.argv[1])
saida.mkdir(parents=True, exist_ok=True)
random.seed(42)

EMPRESA = "11223344000186"
clientes = [("45678901000123", "CONSTRUTORA ALFA LTDA"), ("56789012000134", "INCORPORADORA BETA S/A"),
            ("67890123000145", "PREFEITURA FICTICIA DE TESTE"), ("78901234000156", "INDUSTRIA GAMA LTDA"),
            ("89012345000167", "COMERCIAL DELTA EIRELI")]
fornecedores = [("90123456000178", "TOPOGRAFIA E MEDICOES LTDA"), ("12345678000190", "SOFTWARE CAD SERVICOS LTDA"),
                ("23456789000101", "CONTABILIDADE EXEMPLO S/S"), ("34567890000112", "LIMPEZA PREDIAL ZETA LTDA")]
servicos_emit = [("070201", "Projeto de engenharia civil"), ("070202", "Consultoria em engenharia"),
                 ("070601", "Laudo tecnico e vistoria")]
servicos_rec = [("070401", "Servicos de topografia"), ("010701", "Suporte tecnico de software"),
                ("170101", "Assessoria contabil"), ("070901", "Servicos de limpeza")]


def chave_50(cnpj, num, ano_mes):
    base = f"5208707" + "2" + "1" + cnpj + f"{num:013d}"      # 7+1+1+14+13 = 36
    resto = hashlib.sha256((base + ano_mes).encode()).hexdigest()
    return base + "".join(str(int(c, 16) % 10) for c in resto[:14])  # + 14 = 50


def f(v):
    return f"{v:.2f}"


docs = []
for i in range(51):
    mes = ["2026-07", "2026-08", "2026-09"][i % 3]
    dia = random.randint(1, 28)
    data = f"{mes}-{dia:02d}T{random.randint(8, 17):02d}:{random.randint(0, 59):02d}:00-03:00"
    emitida = i % 3 != 2                           # 34 emitidas, 17 recebidas
    if emitida:
        prest = (EMPRESA, "EXEMPLO ENGENHARIA E CONSULTORIA LTDA")
        toma = random.choice(clientes)
        cod, desc = random.choice(servicos_emit)
        valor = round(random.uniform(3000, 40000), 2)
        retido = random.random() < 0.35
    else:
        prest = random.choice(fornecedores)
        toma = (EMPRESA, "EXEMPLO ENGENHARIA E CONSULTORIA LTDA")
        cod, desc = random.choice(servicos_rec)
        valor = round(random.uniform(500, 9000), 2)
        retido = False
    desconto = round(valor * 0.05, 2) if i % 7 == 0 else 0.0
    base = round(valor - desconto, 2)
    aliq = 3.0
    iss = round(base * aliq / 100, 2)
    ret = iss if retido else 0.0
    liq = round(valor - desconto - ret, 2)
    chave = chave_50(prest[0], i + 1, mes)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">
  <infNFSe Id="NFS{chave}">
    <xLocEmi>Goiania</xLocEmi>
    <nNFSe>{i + 1}</nNFSe>
    <emit><CNPJ>{prest[0]}</CNPJ><xNome>{prest[1]}</xNome></emit>
    <valores>
      <vBC>{f(base)}</vBC><pAliqAplic>{f(aliq)}</pAliqAplic><vISSQN>{f(iss)}</vISSQN>
      <vTotalRet>{f(ret)}</vTotalRet><vLiq>{f(liq)}</vLiq>
    </valores>
    <DPS versao="1.00">
      <infDPS Id="DPS{i + 1:044d}">
        <dhEmi>{data}</dhEmi>
        <prest><CNPJ>{prest[0]}</CNPJ></prest>
        <toma><CNPJ>{toma[0]}</CNPJ><xNome>{toma[1]}</xNome></toma>
        <serv><cServ><cTribNac>{cod}</cTribNac><xDescServ>{desc}</xDescServ></cServ></serv>
        <valores>
          <vServPrest><vServ>{f(valor)}</vServ></vServPrest>
          <vDescCondIncond><vDescIncond>{f(desconto)}</vDescIncond></vDescCondIncond>
          <trib><tribMun><tribISSQN>1</tribISSQN><tpRetISSQN>{2 if retido else 1}</tpRetISSQN></tribMun></trib>
        </valores>
      </infDPS>
    </DPS>
  </infNFSe>
</NFSe>
"""
    docs.append((data[:10], chave, "nfse", xml))

# 3 cancelamentos (de notas emitidas), com data um pouco depois da emissão
canceladas = [docs[0], docs[4], docs[10]]
for dia_nota, chave, _, _ in canceladas:
    ano_mes = dia_nota[:7]
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<evento xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">
  <infEvento Id="EVT{chave}101101001">
    <dhEvento>{ano_mes}-28T18:00:00-03:00</dhEvento>
    <chNFSe>{chave}</chNFSe>
    <e101101><xDesc>Cancelamento de NFS-e</xDesc><cMotivo>1</cMotivo></e101101>
  </infEvento>
</evento>
"""
    docs.append((f"{ano_mes}-28", chave, "canc", xml))

for data, chave, tipo, xml in docs:
    (saida / f"{data}-{chave}-{tipo}.xml").write_text(xml, encoding="utf-8")
print(f"{len(docs)} documentos gerados em {saida}")

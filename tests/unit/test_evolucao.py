"""Números da visão de uma empresa (evolução do faturamento e das notas emitidas)."""
import pandas as pd

from nfse.web.marca import Marca
from nfse.web import evolucao as evo

CNPJ = "11222333000181"


def resumo(linhas):
    return pd.DataFrame([{"empresa_cnpj": c, "competencia": m, "tipo": t, "valor": v, "notas": n, "iss_retido": 0.0,
                          "ultima_emissao": f"{m}-10"} for c, m, t, v, n in linhas])


R = resumo([
    (CNPJ, "2025-01", "EMITIDA", 100.0, 1), (CNPJ, "2025-02", "EMITIDA", 100.0, 1),
    (CNPJ, "2026-01", "EMITIDA", 300.0, 2), (CNPJ, "2026-03", "EMITIDA", 300.0, 4),
    (CNPJ, "2026-03", "RECEBIDA", 999.0, 9),                       # recebidas não contam
    ("99999999000191", "2026-03", "EMITIDA", 5000.0, 50),          # outra empresa não conta
])


def test_intervalo_de_meses():
    assert evo.intervalo("2025-11", "2026-02") == ["2025-11", "2025-12", "2026-01", "2026-02"]
    assert evo.deslocar("2026-01", -1) == "2025-12" and evo.rotulo_mes("2026-03") == "Mar/26"


def test_metricas_com_mes_sem_nota_e_variacao():
    m = {x["rotulo"]: x for x in evo.metricas(evo.serie_emitidas(R, CNPJ), "2026-01", "2026-03")}
    assert m["Faturamento no período"]["valor"] == "R$ 600,00"
    assert m["Notas emitidas"]["valor"] == "6"
    assert m["Ticket médio por nota"]["valor"] == "R$ 100,00"
    assert m["Média mensal"]["valor"] == "R$ 200,00" and "2 de 3 meses" in m["Média mensal"]["dica"]
    assert m["Faturamento no período"]["variacao"] is None  # out-dez/2025 sem faturamento: sem base de comparação
    assert m["Receita dos últimos 12 meses"]["valor"] == "R$ 600,00"  # abr/25 a mar/26


def test_variacao_contra_o_periodo_anterior():
    m = {x["rotulo"]: x for x in evo.metricas(evo.serie_emitidas(R, CNPJ), "2025-03", "2026-03")}
    m2 = {x["rotulo"]: x for x in evo.metricas(evo.serie_emitidas(R, CNPJ), "2026-01", "2026-01")}
    assert m["Receita dos últimos 12 meses"]["valor"] == "R$ 600,00"
    assert m2["Faturamento no período"]["variacao"] is None
    m3 = {x["rotulo"]: x for x in evo.metricas(evo.serie_emitidas(R, CNPJ), "2025-02", "2025-02")}
    assert m3["Faturamento no período"]["variacao"] == {"texto": "+0,0%", "positiva": True}


def test_graficos():
    dados = evo.montar(R, CNPJ, "2026-01", "2026-03", Marca())
    ids = [g["id"] for g in dados["graficos"]]
    assert ids == ["evolucao-faturamento", "evolucao-notas", "evolucao-acumulado"]
    fat = dados["graficos"][0]["dados"]["figura"]["data"][0]
    assert list(fat["x"]) == ["Jan/26", "Fev/26", "Mar/26"]  # fevereiro aparece, com zero
    acumulado = dados["graficos"][2]["dados"]["figura"]["data"]
    assert [t["name"] for t in acumulado] == ["2025", "2026"]  # 2024 sem nota fica de fora


def test_empresa_sem_notas_nao_tem_graficos():
    dados = evo.montar(R, "11444777000161", "2026-01", "2026-03", Marca())
    assert dados["graficos"] == [] and dados["tem_notas"] is False

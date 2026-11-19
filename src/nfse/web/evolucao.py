"""Visão de uma única empresa: métricas e gráficos de evolução do faturamento e das notas emitidas.

Usa o resumo agregado no banco (empresa × competência × tipo), o mesmo da carteira: não precisa ler as
notas uma a uma. Meses sem nota entram como zero, para a evolução não pular meses.
"""
from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go

from nfse.domain.models import TipoNota
from nfse.ui.dashboard.formatters import brl
from nfse.ui.dashboard.marca import Marca

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
CINZA = {"light": "#8A97A8", "dark": "#6F7F96"}
FONTE = "Segoe UI, system-ui, sans-serif"


# ---------------------------------------------------------------- meses
def _mes(c: str) -> int:
    return int(c[:4]) * 12 + int(c[5:7]) - 1


def _comp(n: int) -> str:
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


def intervalo(de: str, ate: str) -> list[str]:
    """Todas as competências de `de` a `ate`, inclusive."""
    if not de or not ate:
        return []
    return [_comp(n) for n in range(_mes(de), _mes(ate) + 1)]


def deslocar(c: str, meses: int) -> str:
    return _comp(_mes(c) + meses)


def rotulo_mes(c: str) -> str:
    return f"{MESES[int(c[5:7]) - 1]}/{c[2:4]}"


# ---------------------------------------------------------------- números
def serie_emitidas(resumo: pd.DataFrame, cnpj: str) -> pd.DataFrame:
    """competencia (índice) -> faturamento, notas. Só notas emitidas e não canceladas."""
    r = resumo[(resumo["empresa_cnpj"] == cnpj) & (resumo["tipo"] == TipoNota.EMITIDA.value)]
    return r.groupby("competencia").agg(faturamento=("valor", "sum"), notas=("notas", "sum"))


def _no_intervalo(serie: pd.DataFrame, meses: list[str]) -> pd.DataFrame:
    return serie.reindex(meses, fill_value=0).astype({"notas": int})


def _variacao(atual: float, anterior: float) -> dict | None:
    if not anterior:
        return None
    v = (atual - anterior) / anterior * 100
    return {"texto": f"{'+' if v >= 0 else '−'}{abs(v):.1f}%".replace(".", ","), "positiva": v >= 0}


def metricas(serie: pd.DataFrame, de: str, ate: str) -> list[dict]:
    meses = intervalo(de, ate)
    atual = _no_intervalo(serie, meses)
    antes = _no_intervalo(serie, intervalo(deslocar(de, -len(meses)), deslocar(de, -1))) if meses else atual
    fat, notas = float(atual["faturamento"].sum()), int(atual["notas"].sum())
    fat_ant, notas_ant = float(antes["faturamento"].sum()), int(antes["notas"].sum())
    rbt12 = float(_no_intervalo(serie, intervalo(deslocar(ate, -11), ate))["faturamento"].sum()) if ate else 0.0
    ativos = int((atual["notas"] > 0).sum())
    comparado = f"vs. {len(meses)} meses anteriores" if len(meses) > 1 else "vs. mês anterior"
    return [
        {"rotulo": "Faturamento no período", "valor": brl(fat), "variacao": _variacao(fat, fat_ant), "dica": comparado},
        {"rotulo": "Notas emitidas", "valor": f"{notas}", "variacao": _variacao(notas, notas_ant), "dica": comparado},
        {"rotulo": "Ticket médio por nota", "valor": brl(fat / notas) if notas else "—",
         "dica": "faturamento ÷ notas emitidas"},
        {"rotulo": "Média mensal", "valor": brl(fat / len(meses)) if meses else "—",
         "dica": f"{ativos} de {len(meses)} meses com nota emitida"},
        {"rotulo": "Receita dos últimos 12 meses", "valor": brl(rbt12),
         "dica": f"{rotulo_mes(deslocar(ate, -11))} a {rotulo_mes(ate)} (base do RBT12 no Simples)" if ate else None},
    ]


# ---------------------------------------------------------------- gráficos
def _layout(fig: go.Figure, **extra):
    fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", separators=",.",
                      font=dict(size=12, family=FONTE), margin=dict(t=48, l=10, r=10, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=1.14, x=0, font=dict(size=13)), bargap=0.3, **extra)
    fig.update_xaxes(type="category", showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,.22)", zeroline=False)


def _pacote(fig: go.Figure, cores: dict) -> dict:
    """Figura + cores por série nos dois temas (o painel.js escolhe conforme o navegador)."""
    return {"figura": json.loads(fig.to_json()), "cores": cores}


def grafico_faturamento(serie: pd.DataFrame, meses: list[str], marca: Marca) -> dict:
    s = _no_intervalo(serie, meses)
    x = [rotulo_mes(m) for m in meses]
    media = s["faturamento"].rolling(3, min_periods=1).mean()
    fig = go.Figure([
        go.Bar(x=x, y=s["faturamento"], name="Faturamento", customdata=[brl(v) for v in s["faturamento"]],
               hovertemplate="%{customdata}<extra>Faturamento</extra>"),
        go.Scatter(x=x, y=media, name="Média móvel de 3 meses", mode="lines+markers", line=dict(width=3, shape="spline"),
                   customdata=[brl(v) for v in media], hovertemplate="%{customdata}<extra>Média 3 meses</extra>"),
    ])
    _layout(fig, yaxis_tickprefix="R$ ")
    (ce, cr), (ee, er) = marca.cores_grafico("light"), marca.cores_grafico("dark")
    return _pacote(fig, {"light": {"Faturamento": ce, "Média móvel de 3 meses": cr},
                         "dark": {"Faturamento": ee, "Média móvel de 3 meses": er}})


def grafico_notas(serie: pd.DataFrame, meses: list[str], marca: Marca) -> dict:
    s = _no_intervalo(serie, meses)
    x = [rotulo_mes(m) for m in meses]
    ticket = [f / n if n else None for f, n in zip(s["faturamento"], s["notas"])]
    fig = go.Figure([
        go.Bar(x=x, y=s["notas"], name="Notas emitidas", text=s["notas"], textposition="outside", cliponaxis=False,
               hovertemplate="%{y} nota(s)<extra>Notas emitidas</extra>"),
        go.Scatter(x=x, y=ticket, name="Ticket médio", yaxis="y2", mode="lines+markers", connectgaps=False,
                   line=dict(width=3), customdata=[brl(t) if t else "—" for t in ticket],
                   hovertemplate="%{customdata}<extra>Ticket médio</extra>"),
    ])
    _layout(fig, yaxis=dict(title="Notas", rangemode="tozero"),
            yaxis2=dict(title="Ticket médio (R$)", overlaying="y", side="right", showgrid=False, rangemode="tozero",
                        tickprefix="R$ "))
    (ce, cr), (ee, er) = marca.cores_grafico("light"), marca.cores_grafico("dark")
    return _pacote(fig, {"light": {"Notas emitidas": ce, "Ticket médio": cr},
                         "dark": {"Notas emitidas": ee, "Ticket médio": er}})


def grafico_acumulado(serie: pd.DataFrame, ate: str, marca: Marca, anos: int = 3) -> dict | None:
    """Faturamento acumulado mês a mês, uma linha por ano (compara o ano atual com os anteriores)."""
    if not ate or serie.empty:
        return None
    ultimo = int(ate[:4])
    fig = go.Figure()
    cores = {"light": {}, "dark": {}}
    for i, ano in enumerate(range(ultimo - anos + 1, ultimo + 1)):
        fim = ate if ano == ultimo else f"{ano}-12"
        meses = intervalo(f"{ano}-01", fim)
        valores = _no_intervalo(serie, meses)["faturamento"].cumsum()
        if not valores.any():
            continue
        nome = str(ano)
        fig.add_trace(go.Scatter(x=[MESES[int(m[5:7]) - 1] for m in meses], y=valores, name=nome,
                                 mode="lines+markers", line=dict(width=4 if ano == ultimo else 2),
                                 customdata=[brl(v) for v in valores], hovertemplate=f"%{{customdata}}<extra>{nome}</extra>"))
        for modo in ("light", "dark"):
            principal, segunda = marca.cores_grafico(modo)
            cores[modo][nome] = principal if ano == ultimo else segunda if ano == ultimo - 1 else CINZA[modo]
    if not fig.data:
        return None
    _layout(fig, yaxis_tickprefix="R$ ")
    fig.update_xaxes(categoryorder="array", categoryarray=MESES)
    return _pacote(fig, cores)


def montar(resumo: pd.DataFrame, cnpj: str, de: str, ate: str, marca: Marca) -> dict:
    """Tudo o que a tela precisa para a visão de uma empresa no período [de, ate]."""
    serie = serie_emitidas(resumo, cnpj)
    meses = intervalo(de, ate)
    tem_notas = bool(serie["notas"].sum()) if not serie.empty else False
    return {
        "metricas": metricas(serie, de, ate),
        "tem_notas": tem_notas,
        "graficos": [g for g in [
            {"id": "evolucao-faturamento", "titulo": "Evolução do faturamento",
             "dica": "Base de cálculo das notas emitidas, mês a mês, com a média móvel de 3 meses.",
             "dados": grafico_faturamento(serie, meses, marca) if tem_notas and meses else None},
            {"id": "evolucao-notas", "titulo": "Notas emitidas por mês",
             "dica": "Quantidade de notas emitidas (barras) e valor médio por nota (linha, eixo da direita).",
             "dados": grafico_notas(serie, meses, marca) if tem_notas and meses else None},
            {"id": "evolucao-acumulado", "titulo": "Faturamento acumulado no ano",
             "dica": "Cada linha é um ano: mostra se a empresa está faturando mais ou menos que nos anos anteriores.",
             "dados": grafico_acumulado(serie, ate, marca) if tem_notas else None},
        ] if g["dados"]],
    }

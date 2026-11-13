"""Monta os dados da página a partir do relatorios_service (sem FastAPI aqui: fácil de testar)."""
from __future__ import annotations

import io
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd
import plotly.express as px

from nfse.data.database import DestinoBanco
from nfse.domain.models import TipoNota
from nfse.services import relatorios_service as rel
from nfse.ui.dashboard.formatters import brl, percentual, sim_nao
from nfse.ui.dashboard.marca import Marca

POR_PAGINA = 50
ROTULOS_TIPO = {TipoNota.EMITIDA.value: "Prestados (emitidas)", TipoNota.RECEBIDA.value: "Tomados (recebidas)"}
COLUNAS_MOEDA = ["valor_servico", "desconto", "base_calculo", "valor_iss", "valor_retido", "valor_liquido"]
TITULOS = {
    "chave": "Chave", "numero": "Número", "data_emissao": "Emissão", "competencia": "Competência", "tipo": "Tipo",
    "prestador_cnpj": "CNPJ prestador", "prestador_nome": "Prestador", "tomador_cnpj": "CNPJ tomador",
    "tomador_nome": "Tomador", "codigo_servico": "Cód. serviço", "descricao_servico": "Serviço",
    "valor_servico": "Valor do serviço", "desconto": "Desconto", "base_calculo": "Base de cálculo",
    "aliquota": "Alíquota", "valor_iss": "ISS", "iss_retido": "ISS retido?", "valor_retido": "Valor retido",
    "valor_liquido": "Valor líquido", "status": "Status", "arquivo": "Arquivo",
}
COLUNAS_TELA = ["data_emissao", "numero", "competencia", "tipo", "prestador_nome", "tomador_nome",
                "descricao_servico", "base_calculo", "valor_iss", "iss_retido", "status"]


class CacheNotas:
    """Mesmo papel do @st.cache_data(ttl=60): lê o banco no máximo uma vez por minuto."""

    def __init__(self, destino: DestinoBanco, ttl: int = 60,
                 carregar: Callable[[DestinoBanco], pd.DataFrame] = rel.carregar_notas):
        self.destino, self.ttl, self._carregar = destino, ttl, carregar
        self._dados: pd.DataFrame | None = None
        self._ate = 0.0
        self._trava = threading.Lock()

    def obter(self) -> pd.DataFrame:
        with self._trava:
            if self._dados is None or time.monotonic() > self._ate:
                self._dados = self._carregar(self.destino)
                self._ate = time.monotonic() + self.ttl
            return self._dados


@dataclass
class Filtros:
    de: str
    ate: str
    tipos: list[str]
    busca: str = ""
    pagina: int = 1
    todas_competencias: list[str] = field(default_factory=list)

    @property
    def competencias(self) -> list[str]:
        return [c for c in self.todas_competencias if self.de <= c <= self.ate]

    def query(self, **troca) -> str:
        """Query string com os filtros atuais (para paginação e exportação)."""
        from urllib.parse import urlencode
        p = {"de": self.de, "ate": self.ate, "busca": self.busca, "pagina": self.pagina}
        p.update(troca)
        pares = [(k, v) for k, v in p.items() if v not in ("", None)] + [("tipo", t) for t in self.tipos]
        return urlencode(pares)


def ler_filtros(dados: pd.DataFrame, de: str | None, ate: str | None, tipos: list[str] | None,
                busca: str = "", pagina: int = 1) -> Filtros:
    todas = sorted(dados["competencia"].dropna().unique()) if not dados.empty else []
    primeira, ultima = (todas[0], todas[-1]) if todas else ("", "")
    de = de if de in todas else primeira
    ate = ate if ate in todas else ultima
    if de > ate:
        de, ate = ate, de
    validos = [t.value for t in TipoNota]
    tipos = [t for t in (tipos or []) if t in validos] or validos
    return Filtros(de, ate, tipos, busca.strip()[:100], max(1, pagina), todas)


def _ranking(df: pd.DataFrame, coluna: str, extra: str | None = None) -> list[dict]:
    r = rel.ranking(df, coluna, extra=extra)
    return [{"nome": x["Nome"] if pd.notna(x["Nome"]) else "—", "descricao": x.get("Descrição"),
             "total": brl(x["Total"]), "notas": int(x["Notas"])} for x in r.to_dict("records")]


def grafico(mensal: pd.DataFrame, marca: Marca) -> dict | None:
    """Figura Plotly (JSON) + as cores dos dois modos; o painel.js escolhe conforme o tema do navegador."""
    if mensal.empty:
        return None
    mensal = mensal.assign(tipo=mensal["tipo"].map(ROTULOS_TIPO))
    claro_e, claro_r = marca.cores_grafico("light")
    escuro_e, escuro_r = marca.cores_grafico("dark")
    e, r = ROTULOS_TIPO[TipoNota.EMITIDA.value], ROTULOS_TIPO[TipoNota.RECEBIDA.value]
    fig = px.bar(mensal, x="competencia", y="base_calculo", color="tipo", barmode="group",
                 color_discrete_map={e: claro_e, r: claro_r},
                 labels={"competencia": "Competência", "base_calculo": "Base de cálculo (R$)", "tipo": ""},
                 text=mensal["base_calculo"].map(brl))
    fig.update_traces(textposition="outside", cliponaxis=False, marker_line_width=0, textfont_size=11)
    fig.update_layout(legend=dict(orientation="h", y=1.14, x=0, font=dict(size=13)), yaxis_tickprefix="R$ ",
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", bargap=0.25,
                      margin=dict(t=48, l=10, r=10, b=10), font=dict(size=12, family="Segoe UI, system-ui, sans-serif"),
                      separators=",.")
    fig.update_xaxes(type="category", showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,.22)", zeroline=False)
    return {"figura": json.loads(fig.to_json()),
            "cores": {"light": {e: claro_e, r: claro_r}, "dark": {e: escuro_e, r: escuro_r}}}


def montar(dados: pd.DataFrame, f: Filtros, marca: Marca) -> dict:
    recorte = rel.recortar(dados, f.competencias, f.tipos)
    t = rel.totais(recorte)
    tabela = rel.buscar(recorte.filtrado, f.busca).sort_values("data_emissao", ascending=False)
    total_linhas = len(tabela)
    paginas = max(1, -(-total_linhas // POR_PAGINA))
    f.pagina = min(f.pagina, paginas)
    pagina = tabela.iloc[(f.pagina - 1) * POR_PAGINA: f.pagina * POR_PAGINA]
    linhas = [{
        "emissao": (x["data_emissao"] or "")[:10], "numero": x["numero"], "competencia": x["competencia"],
        "tipo": "Emitida" if x["tipo"] == TipoNota.EMITIDA.value else "Recebida",
        "prestador": x["prestador_nome"], "tomador": x["tomador_nome"], "servico": x["descricao_servico"],
        "base": brl(x["base_calculo"] or 0), "iss": brl(x["valor_iss"] or 0), "retido": sim_nao(x["iss_retido"]),
        "cancelada": x["status"] == "CANCELADA", "chave": x["chave"],
    } for x in pagina.to_dict("records")]
    return {
        "metricas": [
            {"rotulo": "Faturamento (emitidas)", "valor": brl(t.faturamento)},
            {"rotulo": "Serviços tomados (recebidas)", "valor": brl(t.tomados)},
            {"rotulo": "ISS retido pelos clientes", "valor": brl(t.iss_retido_clientes)},
            {"rotulo": "Quantidade de notas", "valor": f"{t.quantidade}",
             "dica": f"{t.canceladas} cancelada(s) fora da contagem" if t.canceladas else None},
        ],
        "grafico": grafico(rel.mensal(recorte.validas), marca),
        "clientes": _ranking(recorte.emitidas, "tomador_nome"),
        "fornecedores": _ranking(recorte.recebidas, "prestador_nome"),
        "servicos": _ranking(recorte.emitidas, "codigo_servico", extra="descricao_servico"),
        "linhas": linhas, "total_linhas": total_linhas, "paginas": paginas,
    }


def csv_exportacao(dados: pd.DataFrame, f: Filtros) -> bytes:
    """Todas as colunas, no formato que o Excel brasileiro abre direto (; e vírgula decimal)."""
    recorte = rel.recortar(dados, f.competencias, f.tipos)
    df = rel.buscar(recorte.filtrado, f.busca).sort_values("data_emissao", ascending=False).copy()
    df["iss_retido"] = df["iss_retido"].map(sim_nao)
    df["aliquota"] = df["aliquota"].map(lambda v: percentual(v or 0))
    df = df[[c for c in TITULOS if c in df.columns]].rename(columns=TITULOS)
    buf = io.StringIO()
    df.to_csv(buf, sep=";", decimal=",", index=False, float_format="%.2f")
    return buf.getvalue().encode("utf-8-sig")

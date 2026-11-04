"""Dashboard das NFS-e. Rodar com:  streamlit run dashboard.py"""
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

BANCO = Path(__file__).resolve().parent / "notas.db"

st.set_page_config(page_title="Dashboard NFS-e", page_icon="📄", layout="wide")


def brl(v):
    """R$ 1.234,56"""
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@st.cache_data(ttl=30)
def carregar():
    con = sqlite3.connect(BANCO)
    df = pd.read_sql_query("SELECT * FROM notas", con)
    con.close()
    return df


def tabela_ranking(df, coluna_nome, coluna_valor="base_calculo", extra=None):
    cols = [coluna_nome] + ([extra] if extra else [])
    r = df.groupby(cols, dropna=False)[coluna_valor].agg(["sum", "count"]).reset_index()
    r = r.sort_values("sum", ascending=False).head(10)
    r["Total"] = r["sum"].map(brl)
    r = r.rename(columns={"count": "Notas", coluna_nome: "Nome", extra or "": "Descrição"})
    return r[[c for c in ["Nome", "Descrição", "Total", "Notas"] if c in r.columns]]


st.title("📄 Dashboard de NFS-e")

if not BANCO.exists():
    st.warning("Ainda não existe notas.db. Rode primeiro: python baixar_adn.py (ou python importador.py).")
    st.stop()

dados = carregar()
if dados.empty:
    st.warning("O banco está vazio. Rode python baixar_adn.py ou python importador.py.")
    st.stop()

# ----------------------------------------------------------- filtros
st.sidebar.header("Filtros")
competencias = sorted(dados["competencia"].dropna().unique())
sel_comp = st.sidebar.multiselect("Competência", competencias, default=competencias)
sel_tipo = st.sidebar.multiselect("Tipo", ["EMITIDA", "RECEBIDA"], default=["EMITIDA", "RECEBIDA"],
                                  format_func=str.capitalize)

filtrado = dados[dados["competencia"].isin(sel_comp) & dados["tipo"].isin(sel_tipo)]
validas = filtrado[filtrado["status"] != "CANCELADA"]
n_canc = len(filtrado) - len(validas)
emitidas = validas[validas["tipo"] == "EMITIDA"]
recebidas = validas[validas["tipo"] == "RECEBIDA"]

st.sidebar.caption("Notas canceladas aparecem na tabela, mas não entram nos totais.")

# ----------------------------------------------------------- números grandes
c1, c2, c3, c4 = st.columns(4)
c1.metric("Faturamento (emitidas)", brl(emitidas["base_calculo"].sum()))
c2.metric("Serviços tomados (recebidas)", brl(recebidas["base_calculo"].sum()))
c3.metric("ISS retido pelos clientes", brl(emitidas.loc[emitidas["iss_retido"] == 1, "valor_retido"].sum()))
c4.metric("Quantidade de notas", f"{len(validas)}", help=f"{n_canc} cancelada(s) fora da contagem" if n_canc else None)

# ----------------------------------------------------------- gráfico mensal
st.subheader("Prestados × tomados por mês")
mensal = validas.groupby(["competencia", "tipo"])["base_calculo"].sum().reset_index()
mensal["tipo"] = mensal["tipo"].map({"EMITIDA": "Prestados (emitidas)", "RECEBIDA": "Tomados (recebidas)"})
if mensal.empty:
    st.info("Nenhuma nota nos filtros escolhidos.")
else:
    fig = px.bar(mensal, x="competencia", y="base_calculo", color="tipo", barmode="group",
                 labels={"competencia": "Competência", "base_calculo": "Base de cálculo (R$)", "tipo": ""},
                 text=mensal["base_calculo"].map(brl))
    fig.update_layout(legend=dict(orientation="h", y=1.1), yaxis_tickprefix="R$ ")
    st.plotly_chart(fig, width="stretch")

# ----------------------------------------------------------- listas
col_a, col_b, col_c = st.columns(3)
with col_a:
    st.subheader("Maiores clientes")
    st.caption("Tomadores das notas emitidas")
    st.dataframe(tabela_ranking(emitidas, "tomador_nome").drop(columns=["Descrição"], errors="ignore"),
                 hide_index=True, width="stretch")
with col_b:
    st.subheader("Maiores fornecedores de serviço")
    st.caption("Prestadores das notas recebidas")
    st.dataframe(tabela_ranking(recebidas, "prestador_nome").drop(columns=["Descrição"], errors="ignore"),
                 hide_index=True, width="stretch")
with col_c:
    st.subheader("Faturamento por tipo de serviço")
    st.caption("Código nacional (cTribNac) das emitidas")
    r = tabela_ranking(emitidas, "codigo_servico", extra="descricao_servico")
    r = r.rename(columns={"Nome": "Código"})
    st.dataframe(r, hide_index=True, width="stretch")

# ----------------------------------------------------------- tabela completa
st.subheader("Todas as notas filtradas")
busca = st.text_input("Buscar (número, nome, serviço, chave...)")
tabela = filtrado.copy()
if busca:
    mask = tabela.astype(str).apply(lambda col: col.str.contains(busca, case=False, regex=False)).any(axis=1)
    tabela = tabela[mask]

mostrar = tabela.sort_values("data_emissao", ascending=False).copy()
for c in ["valor_servico", "desconto", "base_calculo", "valor_iss", "valor_retido", "valor_liquido"]:
    mostrar[c] = mostrar[c].map(brl)
mostrar["aliquota"] = mostrar["aliquota"].map(lambda v: f"{v:.2f}".replace(".", ",") + "%")
mostrar["iss_retido"] = mostrar["iss_retido"].map({1: "Sim", 0: "Não"})
mostrar["data_emissao"] = mostrar["data_emissao"].str[:10]
mostrar = mostrar.rename(columns={
    "chave": "Chave", "numero": "Número", "data_emissao": "Emissão", "competencia": "Competência", "tipo": "Tipo",
    "prestador_cnpj": "CNPJ prestador", "prestador_nome": "Prestador", "tomador_cnpj": "CNPJ tomador",
    "tomador_nome": "Tomador", "codigo_servico": "Cód. serviço", "descricao_servico": "Serviço",
    "valor_servico": "Valor do serviço", "desconto": "Desconto", "base_calculo": "Base de cálculo",
    "aliquota": "Alíquota", "valor_iss": "ISS", "iss_retido": "ISS retido?", "valor_retido": "Valor retido",
    "valor_liquido": "Valor líquido", "status": "Status", "arquivo": "Arquivo"})
st.caption(f"{len(mostrar)} nota(s)")
st.dataframe(mostrar, hide_index=True, width="stretch")

import pandas as pd
import plotly.express as px
import streamlit as st

from nfse.domain.models import TipoNota

from ..formatters import brl
from ..marca import Marca

ROTULOS_TIPO = {TipoNota.EMITIDA.value: "Prestados (emitidas)", TipoNota.RECEBIDA.value: "Tomados (recebidas)"}


def grafico_mensal(mensal: pd.DataFrame, marca: Marca):
    st.subheader("Prestados × tomados por mês")
    if mensal.empty:
        st.info("Nenhuma nota nos filtros escolhidos.")
        return
    mensal = mensal.assign(tipo=mensal["tipo"].map(ROTULOS_TIPO))
    emitidas, recebidas = marca.cores_grafico(st.context.theme.type)
    cores = {ROTULOS_TIPO[TipoNota.EMITIDA.value]: emitidas, ROTULOS_TIPO[TipoNota.RECEBIDA.value]: recebidas}
    fig = px.bar(mensal, x="competencia", y="base_calculo", color="tipo", barmode="group",
                 color_discrete_map=cores,
                 labels={"competencia": "Competência", "base_calculo": "Base de cálculo (R$)", "tipo": ""},
                 text=mensal["base_calculo"].map(brl))
    fig.update_traces(textposition="outside", cliponaxis=False, marker_line_width=0, textfont_size=12)
    # fundo transparente e fontes do tema do Streamlit: o gráfico acompanha o modo claro/escuro.
    # No escuro, tema.py reforça cores, textos e grade (ver _css_escuro).
    fig.update_layout(legend=dict(orientation="h", y=1.14, x=0, font=dict(size=13)), yaxis_tickprefix="R$ ",
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      bargap=0.25, margin=dict(t=48, l=10, r=10, b=10), font=dict(size=12))
    fig.update_xaxes(type="category", showgrid=False, tickfont_size=12)
    fig.update_yaxes(gridcolor="rgba(128,128,128,.22)", zeroline=False, tickfont_size=12)
    st.plotly_chart(fig, width="stretch", theme="streamlit")

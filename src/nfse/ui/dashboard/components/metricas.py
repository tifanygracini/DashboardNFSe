import streamlit as st

from nfse.services.relatorios_service import Totais

from ..formatters import brl


def mostrar_metricas(t: Totais):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Faturamento (emitidas)", brl(t.faturamento))
    c2.metric("Serviços tomados (recebidas)", brl(t.tomados))
    c3.metric("ISS retido pelos clientes", brl(t.iss_retido_clientes))
    c4.metric("Quantidade de notas", f"{t.quantidade}",
              help=f"{t.canceladas} cancelada(s) fora da contagem" if t.canceladas else None)

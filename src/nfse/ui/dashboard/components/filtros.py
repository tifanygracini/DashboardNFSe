import pandas as pd
import streamlit as st

from nfse.domain.models import TipoNota


def filtros_sidebar(dados: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Devolve (competências, tipos) escolhidos."""
    st.sidebar.header("Filtros")
    competencias = sorted(dados["competencia"].dropna().unique())
    sel_comp = st.sidebar.multiselect("Competência", competencias, default=competencias)
    tipos = [t.value for t in TipoNota]
    sel_tipo = st.sidebar.multiselect("Tipo", tipos, default=tipos, format_func=str.capitalize)
    st.sidebar.caption("Notas canceladas aparecem na tabela, mas não entram nos totais.")
    return sel_comp, sel_tipo

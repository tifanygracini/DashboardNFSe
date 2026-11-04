import pandas as pd
import streamlit as st

from nfse.services import relatorios_service as rel

from ..formatters import brl, percentual, sim_nao

COLUNAS_MOEDA = ["valor_servico", "desconto", "base_calculo", "valor_iss", "valor_retido", "valor_liquido"]
TITULOS = {
    "chave": "Chave", "numero": "Número", "data_emissao": "Emissão", "competencia": "Competência", "tipo": "Tipo",
    "prestador_cnpj": "CNPJ prestador", "prestador_nome": "Prestador", "tomador_cnpj": "CNPJ tomador",
    "tomador_nome": "Tomador", "codigo_servico": "Cód. serviço", "descricao_servico": "Serviço",
    "valor_servico": "Valor do serviço", "desconto": "Desconto", "base_calculo": "Base de cálculo",
    "aliquota": "Alíquota", "valor_iss": "ISS", "iss_retido": "ISS retido?", "valor_retido": "Valor retido",
    "valor_liquido": "Valor líquido", "status": "Status", "arquivo": "Arquivo",
}


def _ranking_formatado(df: pd.DataFrame, coluna: str, extra: str | None = None) -> pd.DataFrame:
    r = rel.ranking(df, coluna, extra=extra)
    return r.assign(Total=r["Total"].map(brl))


def mostrar_rankings(emitidas: pd.DataFrame, recebidas: pd.DataFrame):
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.subheader("Maiores clientes")
        st.caption("Tomadores das notas emitidas")
        st.dataframe(_ranking_formatado(emitidas, "tomador_nome"), hide_index=True, width="stretch")
    with col_b:
        st.subheader("Maiores fornecedores de serviço")
        st.caption("Prestadores das notas recebidas")
        st.dataframe(_ranking_formatado(recebidas, "prestador_nome"), hide_index=True, width="stretch")
    with col_c:
        st.subheader("Faturamento por tipo de serviço")
        st.caption("Código nacional (cTribNac) das emitidas")
        r = _ranking_formatado(emitidas, "codigo_servico", extra="descricao_servico").rename(columns={"Nome": "Código"})
        st.dataframe(r, hide_index=True, width="stretch")


def mostrar_tabela_completa(filtrado: pd.DataFrame):
    st.subheader("Todas as notas filtradas")
    busca = st.text_input("Buscar (número, nome, serviço, chave...)")
    mostrar = rel.buscar(filtrado, busca).sort_values("data_emissao", ascending=False).copy()
    for c in COLUNAS_MOEDA:
        mostrar[c] = mostrar[c].map(brl)
    mostrar["aliquota"] = mostrar["aliquota"].map(percentual)
    mostrar["iss_retido"] = mostrar["iss_retido"].map(sim_nao)
    mostrar["data_emissao"] = mostrar["data_emissao"].str[:10]
    st.caption(f"{len(mostrar)} nota(s)")
    st.dataframe(mostrar.rename(columns=TITULOS), hide_index=True, width="stretch")

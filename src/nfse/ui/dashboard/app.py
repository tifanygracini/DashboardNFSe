"""Dashboard das NFS-e. Rodar com:  nfse-dashboard  (ou streamlit run src/nfse/ui/dashboard/app.py)"""
import streamlit as st

from nfse.config.settings import ConfigError, get_settings
from nfse.data import ERROS_BANCO, BancoIndisponivel, DestinoBanco
from nfse.services import relatorios_service as rel
from nfse.ui.dashboard.components.filtros import filtros_sidebar
from nfse.ui.dashboard.components.graficos import grafico_mensal
from nfse.ui.dashboard.components.metricas import mostrar_metricas
from nfse.ui.dashboard.components.tabelas import mostrar_rankings, mostrar_tabela_completa
from nfse.ui.dashboard.components.tema import aplicar_tema, barra_superior, rodape, titulo_pagina
from nfse.ui.dashboard.marca import carregar_marca


@st.cache_data(ttl=60, show_spinner="Carregando notas...")
def _carregar(_destino: DestinoBanco, chave: str):
    """`_destino` fica fora da chave do cache (tem a senha); `chave` identifica o banco sem a senha."""
    return rel.carregar_notas(_destino)


def main():
    marca = carregar_marca()
    st.set_page_config(page_title=f"NFS-e · {marca.escritorio}",
                       page_icon=str(marca.logo) if marca.logo else "📄", layout="wide")
    aplicar_tema(marca)
    barra_superior(marca, "NFS-e")

    try:
        cfg = get_settings()
    except ConfigError as e:
        titulo_pagina("Dashboard de NFS-e")
        st.error(f"Configuração inválida: {e}")
        st.stop()

    titulo_pagina("Dashboard de NFS-e", f"Notas fiscais de serviço · CNPJ {_cnpj(cfg.cnpj_empresa)}")
    for aviso in marca.avisos:
        st.sidebar.warning(aviso)

    destino = DestinoBanco(cfg.banco, cfg.database_url)
    try:
        dados = _carregar(destino, destino.chave_cache())
    except BancoIndisponivel as e:
        st.warning(str(e))
        st.stop()
    except ERROS_BANCO as e:
        st.error(f"Erro ao ler o banco de notas: {str(e).strip().splitlines()[0]}")
        st.stop()
    if dados.empty:
        st.warning("O banco está vazio. Rode nfse-baixar ou nfse-importar.")
        st.stop()

    competencias, tipos = filtros_sidebar(dados)
    recorte = rel.recortar(dados, competencias, tipos)

    mostrar_metricas(rel.totais(recorte))
    grafico_mensal(rel.mensal(recorte.validas), marca)
    mostrar_rankings(recorte.emitidas, recorte.recebidas)
    mostrar_tabela_completa(recorte.filtrado)
    rodape(marca)


def _cnpj(c: str) -> str:
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else c


if __name__ == "__main__":
    main()

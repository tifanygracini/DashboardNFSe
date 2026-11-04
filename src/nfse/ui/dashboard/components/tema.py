"""Identidade visual do escritório: barra superior fixa, título da página, cartões e rodapé.

Funciona nos modos claro e escuro: as cores de fundo e de texto vêm do tema do Streamlit
([theme.light] / [theme.dark], ver Marca.opcoes_streamlit) e o CSS usa `currentColor`,
então os cartões e bordas acompanham o modo ativo sem precisar saber qual é.
Só a barra superior tem cor fixa (azul-marinho), que funciona sobre os dois fundos.
"""
import base64
from functools import lru_cache
from html import escape
from pathlib import Path

import streamlit as st

from ..marca import Marca

ALTURA_BARRA = 64  # px


@lru_cache(maxsize=4)
def _logo_base64(caminho: Path, _modificado: float) -> str:
    return base64.b64encode(caminho.read_bytes()).decode()


def aplicar_tema(m: Marca):
    st.markdown(f"""
<style>
:root {{
  --cor-primaria: {m.cor_primaria};
  --cor-destaque: {m.cor_destaque};
  --altura-barra: {ALTURA_BARRA}px;
  --linha: color-mix(in srgb, currentColor 14%, transparent);
  --fundo-cartao: color-mix(in srgb, currentColor 4%, transparent);
}}

/* ---------- barra superior fixa ---------- */
.nfse-barra {{
  position: fixed; top: 0; left: 0; right: 0; height: var(--altura-barra); z-index: 999989;
  display: flex; align-items: center; gap: .9rem; padding: 0 1.5rem 0 3.6rem;
  background: var(--cor-primaria); border-bottom: 3px solid var(--cor-destaque);
  box-shadow: 0 2px 10px rgba(0, 0, 0, .25);
}}
/* logo direto sobre a faixa, sem fundo: use um PNG com fundo transparente */
.nfse-barra .logo {{ height: 100%; display: flex; align-items: center; }}
.nfse-barra .logo img {{ height: 46px; width: auto; max-width: 260px; object-fit: contain; display: block; }}
.nfse-barra .nome {{ color: #FFFFFF; font-size: 1.2rem; font-weight: 700; letter-spacing: .01em; white-space: nowrap; }}
.nfse-barra .divisor {{ width: 1px; height: 26px; background: rgba(255, 255, 255, .3); }}
.nfse-barra .modulo {{
  color: var(--cor-destaque); font-size: .78rem; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; white-space: nowrap;
}}
@media (max-width: 640px) {{ .nfse-barra .divisor, .nfse-barra .modulo {{ display: none; }} }}

/* cabeçalho nativo do Streamlit fica transparente por cima da barra (menu ⋮ continua clicável) */
header[data-testid="stHeader"] {{ background: transparent !important; height: var(--altura-barra); }}
header[data-testid="stHeader"] button, header[data-testid="stHeader"] a,
header[data-testid="stHeader"] span {{ color: #FFFFFF !important; }}
div[data-testid="stDecoration"] {{ display: none; }}

/* conteúdo e barra lateral começam abaixo da barra */
.block-container {{ padding-top: calc(var(--altura-barra) + 1.6rem) !important; }}
section[data-testid="stSidebar"] {{
  top: var(--altura-barra) !important; height: calc(100vh - var(--altura-barra)) !important;
  border-right: 3px solid var(--cor-destaque);
}}

/* ---------- título da página ---------- */
.nfse-titulo {{ border-left: 5px solid var(--cor-destaque); padding: .1rem 0 .1rem .85rem; margin-bottom: 1.4rem; }}
.nfse-titulo .titulo {{ font-size: 1.75rem; font-weight: 700; line-height: 1.2; }}
.nfse-titulo .subtitulo {{ font-size: .92rem; opacity: .72; margin-top: .15rem; }}

/* ---------- cartões de indicadores ---------- */
div[data-testid="stMetric"] {{
  background: var(--fundo-cartao); border: 1px solid var(--linha); border-top: 4px solid var(--cor-destaque);
  border-radius: 12px; padding: .95rem 1.1rem;
}}
div[data-testid="stMetricLabel"] p {{ font-weight: 600; font-size: .85rem; opacity: .78; white-space: normal; }}
div[data-testid="stMetricValue"], div[data-testid="stMetricValue"] * {{
  font-weight: 700 !important; font-size: clamp(1.1rem, 1.7vw, 1.8rem) !important; line-height: 1.25 !important;
}}
/* valor inteiro: quebra a linha em vez de virar "R$ ..." */
div[data-testid="stMetricValue"] > div {{
  overflow: visible !important; text-overflow: clip !important; white-space: normal !important;
}}

/* ---------- títulos das seções ---------- */
div[data-testid="stHeading"] h3 {{
  font-weight: 700; font-size: 1.25rem; line-height: 1.3;
  border-left: 4px solid var(--cor-destaque); padding: 0 0 0 .6rem; margin-top: .6rem;
}}

/* ---------- tabelas ---------- */
div[data-testid="stDataFrame"] {{ border: 1px solid var(--linha); border-radius: 10px; overflow: hidden; }}

/* ---------- rodapé ---------- */
.nfse-rodape {{
  margin-top: 2.5rem; padding: .9rem 0 .4rem; border-top: 2px solid var(--cor-destaque);
  display: flex; justify-content: space-between; flex-wrap: wrap; gap: .5rem; font-size: .85rem;
}}
.nfse-rodape span {{ opacity: .7; }}
.nfse-rodape a {{ color: inherit; font-weight: 600; text-decoration: underline; text-decoration-color: var(--cor-destaque); }}
</style>
""", unsafe_allow_html=True)


def barra_superior(m: Marca, modulo: str = "", mostrar_nome: bool | None = None):
    """Faixa horizontal fixa no topo com a logo e o nome do escritório.

    mostrar_nome=None: o nome em texto só aparece se não houver logo, porque a logo do
    escritório já traz o nome. Passe True para mostrar os dois.
    """
    logo = ""
    if m.logo is not None:
        dados = _logo_base64(m.logo, m.logo.stat().st_mtime)
        logo = f'<div class="logo"><img src="data:image/png;base64,{dados}" alt="{escape(m.escritorio)}"></div>'
    if mostrar_nome is None:
        mostrar_nome = m.logo is None
    nome = f'<div class="nome">{escape(m.escritorio)}</div>' if mostrar_nome else ""
    extra = f'<div class="divisor"></div><div class="modulo">{escape(modulo)}</div>' if modulo else ""
    st.markdown(f'<div class="nfse-barra">{logo}{nome}{extra}</div>', unsafe_allow_html=True)


def titulo_pagina(titulo: str, subtitulo: str = ""):
    sub = f'<div class="subtitulo">{escape(subtitulo)}</div>' if subtitulo else ""
    st.markdown(f'<div class="nfse-titulo"><div class="titulo">{escape(titulo)}</div>{sub}</div>',
                unsafe_allow_html=True)


def rodape(m: Marca):
    assinatura = escape(m.assinatura or m.escritorio)
    site = ""
    if m.site:
        rotulo = escape(m.site.split("://", 1)[-1].rstrip("/"))
        site = f'<a href="{escape(m.site)}" target="_blank" rel="noopener">{rotulo}</a>'
    st.markdown(f'<div class="nfse-rodape"><span>{assinatura}</span>{site}</div>', unsafe_allow_html=True)

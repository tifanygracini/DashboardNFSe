"""Tela inicial: todas as empresas do escritório, com filtros por regime, busca e situação.

Sem FastAPI aqui (fácil de testar). Os números vêm do relatorios_service, agregados no banco.
"""
from __future__ import annotations

import io
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlencode

import pandas as pd

from nfse.data.database import DestinoBanco
from nfse.domain.documentos import so_digitos
from nfse.domain.empresa import (CERT_AUSENTE, CERT_OK, CERT_VENCENDO, CERT_VENCIDO, REGIMES,
                                 situacao_certificado)
from nfse.services import relatorios_service as rel
from nfse.ui.dashboard.formatters import brl
from nfse.ui.dashboard.marca import Marca

from . import evolucao, painel

POR_PAGINA = 50
MESES_PADRAO = 12

SITUACOES = {
    "": "Todas",
    "com_notas": "Com notas no período",
    "sem_notas": "Sem notas no período",
    "cert_pendente": "Certificado vencido, vencendo ou ausente",
    "erro_robo": "Robô com erro ou sem certificado",
}
ORDENS = {
    "faturamento": "Faturamento",
    "razao": "Razão social",
    "codigo": "Código Domínio",
    "notas": "Nº de notas",
}
ROTULO_CERT = {CERT_OK: ("válido", "selo--ok"), CERT_VENCENDO: ("vence em breve", "selo--ouro"),
               CERT_VENCIDO: ("vencido", "selo--alerta"), CERT_AUSENTE: ("sem certificado", "")}
ROTULO_ROBO = {"ok": ("ok", "selo--ok"), "aguardando": ("ok", "selo--ok"), "erro": ("erro", "selo--alerta"),
               "sem_certificado": ("parado", "selo--ouro")}


@dataclass(frozen=True)
class DadosCarteira:
    empresas: pd.DataFrame
    resumo: pd.DataFrame


class CacheCarteira:
    """Lê o banco no máximo uma vez por minuto (como o cache do painel)."""

    def __init__(self, destino: DestinoBanco, ttl: int = 60,
                 carregar: Callable[[DestinoBanco], DadosCarteira] | None = None):
        self.destino, self.ttl = destino, ttl
        self._carregar = carregar or (lambda d: DadosCarteira(rel.carregar_empresas(d), rel.carregar_resumo(d)))
        self._dados: DadosCarteira | None = None
        self._ate = 0.0
        self._trava = threading.Lock()

    def obter(self) -> DadosCarteira:
        with self._trava:
            if self._dados is None or time.monotonic() > self._ate:
                self._dados = self._carregar(self.destino)
                self._ate = time.monotonic() + self.ttl
            return self._dados


def formatar_cnpj(c: str) -> str:
    c = c or ""
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else c


def _simples(s) -> str:
    s = "" if s is None or (isinstance(s, float) and pd.isna(s)) else str(s)
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def _data_br(iso) -> str:
    iso = str(iso or "")
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if len(iso) >= 10 else ""


@dataclass
class FiltrosCarteira:
    de: str
    ate: str
    regime: str = ""
    busca: str = ""
    situacao: str = ""
    ordem: str = "faturamento"
    inativas: bool = False
    pagina: int = 1
    empresa: str = ""               # CNPJ escolhido no seletor: visão de uma única empresa
    todas_competencias: list[str] = field(default_factory=list)

    @property
    def competencias(self) -> list[str]:
        return [c for c in self.todas_competencias if self.de <= c <= self.ate]

    def query(self, **troca) -> str:
        p = {"de": self.de, "ate": self.ate, "regime": self.regime, "busca": self.busca, "situacao": self.situacao,
             "ordem": self.ordem if self.ordem != "faturamento" else "", "inativas": "1" if self.inativas else "",
             "pagina": self.pagina if self.pagina > 1 else "", "empresa": self.empresa}
        p.update(troca)
        return urlencode([(k, v) for k, v in p.items() if v not in ("", None)])

    @property
    def periodo(self) -> str:
        return self.de if self.de == self.ate else f"{self.de} a {self.ate}"


def ler_filtros(dados: DadosCarteira, de: str = "", ate: str = "", regime: str = "", busca: str = "",
                situacao: str = "", ordem: str = "", inativas: str = "", pagina: int = 1,
                empresa: str = "") -> FiltrosCarteira:
    todas = sorted(c for c in dados.resumo["competencia"].dropna().unique() if c) if not dados.resumo.empty else []
    ultima = todas[-1] if todas else ""
    padrao_de = todas[-MESES_PADRAO] if len(todas) >= MESES_PADRAO else (todas[0] if todas else "")
    de = de if de in todas else padrao_de
    ate = ate if ate in todas else ultima
    if de > ate:
        de, ate = ate, de
    return FiltrosCarteira(
        de=de, ate=ate, regime=regime if regime in REGIMES else "", busca=(busca or "").strip()[:100],
        situacao=situacao if situacao in SITUACOES else "", ordem=ordem if ordem in ORDENS else "faturamento",
        inativas=inativas == "1", pagina=max(1, pagina), todas_competencias=todas,
        empresa=empresa if empresa and empresa in set(dados.empresas["cnpj"]) else "")


def _filtrar(df: pd.DataFrame, f: FiltrosCarteira, aplicar_regime: bool = True) -> pd.DataFrame:
    if f.empresa:  # escolhida no seletor: vale sozinha, sem os outros filtros
        return df[df["cnpj"] == f.empresa]
    if not f.inativas:
        df = df[df["ativa"].fillna(0).astype(int) == 1]
    if aplicar_regime and f.regime:
        df = df[df["regime"].fillna("") == f.regime]
    if f.busca:
        termo = _simples(f.busca)
        digitos = so_digitos(f.busca)
        alvo = (df["razao_social"].map(_simples) + " " + df["fantasia"].map(_simples))
        mask = alvo.str.contains(termo, regex=False)
        codigo = df["codigo_dominio"].fillna("").astype(str).str.strip()
        mask |= codigo.str.lower() == termo
        if digitos:
            if len(digitos) >= 4:  # pedaço de CNPJ; números curtos são código do Domínio
                mask |= df["cnpj"].str.contains(digitos, regex=False)
            mask |= codigo.str.lstrip("0") == (digitos.lstrip("0") or "0")
        df = df[mask]
    if f.situacao == "com_notas":
        df = df[df["notas"] > 0]
    elif f.situacao == "sem_notas":
        df = df[df["notas"] == 0]
    elif f.situacao == "cert_pendente":
        df = df[df["cert_situacao"] != CERT_OK]
    elif f.situacao == "erro_robo":
        df = df[df["robo_situacao"].fillna("").isin(["erro", "sem_certificado"])]
    return df


def _ordenar(df: pd.DataFrame, ordem: str) -> pd.DataFrame:
    if ordem == "razao":
        return df.sort_values("razao_social", key=lambda s: s.map(_simples))
    if ordem == "codigo":
        num = pd.to_numeric(df["codigo_dominio"], errors="coerce")
        return df.assign(_c=num).sort_values(["_c", "codigo_dominio"], na_position="last").drop(columns="_c")
    if ordem == "notas":
        return df.sort_values(["notas", "faturamento"], ascending=False)
    return df.sort_values(["faturamento", "notas"], ascending=False)


def tabela(dados: DadosCarteira, f: FiltrosCarteira) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(todas as empresas ativas com os totais do período, as que passam nos filtros), já ordenadas."""
    base = rel.carteira(dados.empresas, dados.resumo, f.competencias)
    base["cert_situacao"] = base["cert_validade"].map(lambda v: situacao_certificado(v if isinstance(v, str) else None))
    return base, _ordenar(_filtrar(base, f), f.ordem)


def _linha(x: dict) -> dict:
    cert_rotulo, cert_classe = ROTULO_CERT[x["cert_situacao"]]
    robo = x.get("robo_situacao") or ""
    robo_rotulo, robo_classe = ROTULO_ROBO.get(robo, ("—", ""))
    return {
        "cnpj": x["cnpj"], "cnpj_fmt": formatar_cnpj(x["cnpj"]),
        "razao": x.get("razao_social") or formatar_cnpj(x["cnpj"]),
        "fantasia": x.get("fantasia") if x.get("fantasia") and x.get("fantasia") != x.get("razao_social") else "",
        "codigo": x.get("codigo_dominio") or "", "regime": x.get("regime") or "",
        "regime_original": x.get("regime_acessorias") or "",
        "faturamento": brl(x["faturamento"]), "tomados": brl(x["tomados"]), "notas": int(x["notas"]),
        "ultima": _data_br(x.get("ultima_emissao")),
        "cert_rotulo": cert_rotulo, "cert_classe": cert_classe,
        "cert_dica": f"Válido até {_data_br(x.get('cert_validade'))}" if x.get("cert_validade") else
                     "Nenhum certificado desta empresa (ou da matriz) na pasta de rede",
        "robo_rotulo": robo_rotulo, "robo_classe": robo_classe,
        "robo_dica": f"{_data_br(x.get('robo_execucao'))} {x.get('robo_mensagem') or ''}".strip(),
        "inativa": not bool(x.get("ativa")),
    }


def ficha(e: dict) -> dict:
    """Cadastro de uma empresa para o cabeçalho (código, regime, certificado, robô)."""
    validade = e.get("cert_validade") or ""
    rotulo, classe = ROTULO_CERT[situacao_certificado(validade or None)]
    robo_rotulo, robo_classe = ROTULO_ROBO.get(e.get("robo_situacao") or "", ("ainda não consultada", ""))
    return {
        "cnpj": e["cnpj"], "cnpj_fmt": formatar_cnpj(e["cnpj"]),
        "razao": e.get("razao_social") or formatar_cnpj(e["cnpj"]),
        "fantasia": e.get("fantasia") if e.get("fantasia") and e.get("fantasia") != e.get("razao_social") else "",
        "codigo": e.get("codigo_dominio") or "", "regime": e.get("regime") or "",
        "regime_original": e.get("regime_acessorias") or "", "ativa": bool(e.get("ativa")),
        "cert_rotulo": rotulo, "cert_classe": classe, "cert_validade": _data_br(validade),
        "cert_filial": bool(e.get("cert_titular")) and e.get("cert_titular") != e["cnpj"],
        "robo_rotulo": robo_rotulo, "robo_classe": robo_classe,
        "robo_execucao": _data_br(e.get("robo_execucao")), "robo_mensagem": e.get("robo_mensagem") or "",
    }


def _sem_nan(d: dict) -> dict:
    return {k: (None if isinstance(v, float) and v != v else v) for k, v in d.items()}


def opcoes_empresas(base: pd.DataFrame, f: FiltrosCarteira) -> list[dict]:
    """Seletor de empresa: código do Domínio + razão social, em ordem alfabética."""
    df = base if f.inativas else base[(base["ativa"].fillna(0).astype(int) == 1) | (base["cnpj"] == f.empresa)]
    df = df.sort_values("razao_social", key=lambda s: s.map(_simples))
    return [{"cnpj": x["cnpj"], "selecionada": x["cnpj"] == f.empresa,
             "rotulo": " · ".join(p for p in (str(x.get("codigo_dominio") or ""), x.get("razao_social") or
                                              formatar_cnpj(x["cnpj"])) if p)}
            for x in df.to_dict("records")]


def montar_unica(dados: DadosCarteira, f: FiltrosCarteira, linha: dict, marca: Marca) -> dict:
    """Uma única empresa selecionada: cabeçalho + métricas e gráficos de evolução só dela."""
    cnpj = linha["cnpj"]
    volta = "/?" + urlencode({"de": f.de, "ate": f.ate})  # todas as empresas, mesmo período
    return {"ficha": ficha(_sem_nan(linha)), **evolucao.montar(dados.resumo, cnpj, f.de, f.ate, marca),
            "detalhes": f"/empresa/{cnpj}?" + urlencode({"de": f.de, "ate": f.ate, "volta": "/?" + f.query()}),
            "volta": volta, "escolhida": bool(f.empresa)}


def montar(dados: DadosCarteira, f: FiltrosCarteira, marca: Marca) -> dict:
    base, filtradas = tabela(dados, f)
    opcoes = opcoes_empresas(base, f)
    if len(filtradas) == 1:  # a interface se adapta: visão da empresa
        return {"unica": montar_unica(dados, f, filtradas.iloc[0].to_dict(), marca), "opcoes_empresas": opcoes,
                "situacoes": SITUACOES, "ordens": ORDENS, "regimes": [], "total_linhas": 1,
                "sincronizado_em": _data_br(max(dados.empresas["sincronizado_em"].dropna()))
                if dados.empresas["sincronizado_em"].notna().any() else ""}
    sem_regime = _filtrar(base, f, aplicar_regime=False)
    contagem = sem_regime["regime"].fillna("").value_counts().to_dict()
    regimes = [{"nome": "Todos", "valor": "", "qtd": len(sem_regime), "ativo": not f.regime}] + [
        {"nome": r, "valor": r, "qtd": int(contagem.get(r, 0)), "ativo": f.regime == r}
        for r in REGIMES if contagem.get(r, 0) or f.regime == r]

    total = len(filtradas)
    paginas = max(1, -(-total // POR_PAGINA))
    f.pagina = min(f.pagina, paginas)
    pagina = filtradas.iloc[(f.pagina - 1) * POR_PAGINA: f.pagina * POR_PAGINA]
    pendentes = int((filtradas["cert_situacao"] != CERT_OK).sum())
    com_notas = int((filtradas["notas"] > 0).sum())
    mensal = rel.mensal_carteira(dados.resumo, filtradas["cnpj"], f.competencias)
    sinc = dados.empresas["sincronizado_em"].dropna()
    return {
        "metricas": [
            {"rotulo": "Empresas na seleção", "valor": f"{total}", "dica": f"{com_notas} com notas no período"},
            {"rotulo": "Faturamento (emitidas)", "valor": brl(float(filtradas["faturamento"].sum()))},
            {"rotulo": "Serviços tomados (recebidas)", "valor": brl(float(filtradas["tomados"].sum()))},
            {"rotulo": "Certificados com pendência", "valor": f"{pendentes}",
             "dica": "vencidos, vencendo em 30 dias ou ausentes" if pendentes else None, "alerta": pendentes > 0},
        ],
        "grafico": painel.grafico(mensal, marca),
        "regimes": regimes, "situacoes": SITUACOES, "ordens": ORDENS, "opcoes_empresas": opcoes,
        "linhas": [_linha(x) for x in pagina.to_dict("records")],
        "total_linhas": total, "paginas": paginas,
        "sincronizado_em": _data_br(max(sinc)) if len(sinc) else "",
    }


def csv_carteira(dados: DadosCarteira, f: FiltrosCarteira) -> bytes:
    _, df = tabela(dados, f)
    df = df.assign(cnpj=df["cnpj"].map(formatar_cnpj), cert_validade=df["cert_validade"].map(_data_br),
                   ultima_emissao=df["ultima_emissao"].map(_data_br))
    titulos = {"codigo_dominio": "Código Domínio", "cnpj": "CNPJ", "razao_social": "Razão social",
               "fantasia": "Nome fantasia", "regime": "Regime", "regime_acessorias": "Regime (Acessórias)",
               "faturamento": "Faturamento", "tomados": "Serviços tomados", "iss_retido": "ISS retido pelos clientes",
               "notas_emitidas": "Notas emitidas", "notas_recebidas": "Notas recebidas",
               "ultima_emissao": "Última emissão", "cert_validade": "Certificado válido até",
               "robo_situacao": "Robô", "robo_mensagem": "Mensagem do robô"}
    df = df[list(titulos)].rename(columns=titulos)
    buf = io.StringIO()
    df.to_csv(buf, sep=";", decimal=",", index=False, float_format="%.2f")
    return buf.getvalue().encode("utf-8-sig")

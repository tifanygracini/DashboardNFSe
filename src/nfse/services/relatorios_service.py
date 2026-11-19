"""Leitura do banco e agregações do dashboard (pandas). Devolve números, a formatação fica na UI.

Duas visões:
  carteira  todas as empresas: uma linha por (empresa, competência, tipo) agregada no próprio banco
  empresa   as notas de uma empresa, como no dashboard original
"""
from dataclasses import dataclass

import pandas as pd

from nfse.data import BancoDesatualizado, DestinoBanco, conectar
from nfse.data.database import COLUNAS, COLUNAS_EMPRESAS, existe_tabela, notas_no_formato_antigo
from nfse.domain.models import StatusNota, TipoNota

COLUNAS_RESUMO = ["empresa_cnpj", "competencia", "tipo", "valor", "notas", "iss_retido", "ultima_emissao"]


def _verificar(con):
    if notas_no_formato_antigo(con):
        raise BancoDesatualizado("O banco ainda está no formato de uma empresa só. No computador do robô, rode: "
                                 "nfse-empresas migrar")


def carregar_notas(destino: DestinoBanco, empresa_cnpj: str | None = None) -> pd.DataFrame:
    """Notas de uma empresa (ou de todas). Só leitura: funciona com o usuário somente-leitura do PostgreSQL."""
    with conectar(destino, criar=False) as con:
        if not existe_tabela(con):
            return pd.DataFrame(columns=[nome for nome, _ in COLUNAS])
        _verificar(con)
        sql, params = f"SELECT * FROM {con.tabela}", ()
        if empresa_cnpj:
            sql, params = sql + " WHERE empresa_cnpj=?", (empresa_cnpj,)
        cur = con.executar(sql, params)
        colunas = [d[0] for d in cur.description]
        linhas = cur.fetchall()
    return pd.DataFrame(linhas, columns=colunas)


def carregar_empresas(destino: DestinoBanco) -> pd.DataFrame:
    with conectar(destino, criar=False) as con:
        if not existe_tabela(con, "empresas"):
            return pd.DataFrame(columns=[n for n, _ in COLUNAS_EMPRESAS])
        return pd.DataFrame(con.linhas(f"SELECT * FROM {con.empresas}"), columns=[n for n, _ in COLUNAS_EMPRESAS])


def carregar_resumo(destino: DestinoBanco) -> pd.DataFrame:
    """Totais por empresa, competência e tipo, sem as canceladas (agregado no banco: leve mesmo com
    centenas de milhares de notas)."""
    with conectar(destino, criar=False) as con:
        if not existe_tabela(con):
            return pd.DataFrame(columns=COLUNAS_RESUMO)
        _verificar(con)
        linhas = con.executar(
            "SELECT empresa_cnpj, competencia, tipo, SUM(base_calculo), COUNT(*), "
            "SUM(CASE WHEN iss_retido=1 THEN valor_retido ELSE 0 END), MAX(data_emissao) "
            f"FROM {con.tabela} WHERE status<>? GROUP BY empresa_cnpj, competencia, tipo",
            (StatusNota.CANCELADA.value,)).fetchall()
    df = pd.DataFrame(linhas, columns=COLUNAS_RESUMO)
    for c in ("valor", "iss_retido"):
        df[c] = pd.to_numeric(df[c]).fillna(0.0)
    return df


def carteira(empresas: pd.DataFrame, resumo: pd.DataFrame, competencias) -> pd.DataFrame:
    """Uma linha por empresa: faturamento, tomados, notas, ISS retido e última emissão no período."""
    r = resumo[resumo["competencia"].isin(competencias)]
    emit = r[r["tipo"] == TipoNota.EMITIDA.value].groupby("empresa_cnpj").agg(
        faturamento=("valor", "sum"), notas_emitidas=("notas", "sum"), iss_retido=("iss_retido", "sum"))
    receb = r[r["tipo"] == TipoNota.RECEBIDA.value].groupby("empresa_cnpj").agg(
        tomados=("valor", "sum"), notas_recebidas=("notas", "sum"))
    ultima = resumo.groupby("empresa_cnpj")["ultima_emissao"].max().rename("ultima_emissao")
    df = empresas.set_index("cnpj").join([emit, receb, ultima])
    for c in ("faturamento", "tomados", "iss_retido", "notas_emitidas", "notas_recebidas"):
        df[c] = df[c].fillna(0)
    df["notas"] = (df["notas_emitidas"] + df["notas_recebidas"]).astype(int)
    return df.reset_index().rename(columns={"index": "cnpj"})


def mensal_carteira(resumo: pd.DataFrame, cnpjs, competencias) -> pd.DataFrame:
    """competencia, tipo, base_calculo (soma) das empresas escolhidas — mesmo formato de mensal()."""
    r = resumo[resumo["empresa_cnpj"].isin(cnpjs) & resumo["competencia"].isin(competencias)]
    return r.groupby(["competencia", "tipo"])["valor"].sum().reset_index().rename(columns={"valor": "base_calculo"})


@dataclass(frozen=True)
class Recorte:
    filtrado: pd.DataFrame   # inclui canceladas (para a tabela)
    validas: pd.DataFrame    # sem canceladas (para os totais)

    @property
    def emitidas(self) -> pd.DataFrame:
        return self.validas[self.validas["tipo"] == TipoNota.EMITIDA.value]

    @property
    def recebidas(self) -> pd.DataFrame:
        return self.validas[self.validas["tipo"] == TipoNota.RECEBIDA.value]

    @property
    def canceladas(self) -> int:
        return len(self.filtrado) - len(self.validas)


def recortar(df: pd.DataFrame, competencias, tipos) -> Recorte:
    filtrado = df[df["competencia"].isin(competencias) & df["tipo"].isin(tipos)]
    return Recorte(filtrado, filtrado[filtrado["status"] != StatusNota.CANCELADA.value])


@dataclass(frozen=True)
class Totais:
    faturamento: float
    tomados: float
    iss_retido_clientes: float
    quantidade: int
    canceladas: int


def totais(r: Recorte) -> Totais:
    emitidas = r.emitidas
    return Totais(
        faturamento=float(emitidas["base_calculo"].sum()),
        tomados=float(r.recebidas["base_calculo"].sum()),
        iss_retido_clientes=float(emitidas.loc[emitidas["iss_retido"] == 1, "valor_retido"].sum()),
        quantidade=len(r.validas),
        canceladas=r.canceladas,
    )


def mensal(validas: pd.DataFrame) -> pd.DataFrame:
    """competencia, tipo, base_calculo (soma)."""
    return validas.groupby(["competencia", "tipo"])["base_calculo"].sum().reset_index()


def ranking(df: pd.DataFrame, coluna_nome: str, coluna_valor: str = "base_calculo",
            extra: str | None = None, limite: int = 10) -> pd.DataFrame:
    """Colunas: Nome, [Descrição], Total, Notas."""
    cols = [coluna_nome] + ([extra] if extra else [])
    r = df.groupby(cols, dropna=False)[coluna_valor].agg(["sum", "count"]).reset_index()
    r = r.sort_values("sum", ascending=False).head(limite)
    nomes = {coluna_nome: "Nome", "sum": "Total", "count": "Notas"}
    if extra:
        nomes[extra] = "Descrição"
    r = r.rename(columns=nomes)
    return r[[c for c in ["Nome", "Descrição", "Total", "Notas"] if c in r.columns]]


def buscar(df: pd.DataFrame, termo: str) -> pd.DataFrame:
    if not termo:
        return df
    mask = df.astype(str).apply(lambda col: col.str.contains(termo, case=False, regex=False)).any(axis=1)
    return df[mask]

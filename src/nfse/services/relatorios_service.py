"""Leitura do banco e agregações do dashboard (pandas). Devolve números, a formatação fica na UI."""
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from nfse.data.database import conectar
from nfse.domain.models import StatusNota, TipoNota


def carregar_notas(banco: Path) -> pd.DataFrame:
    with conectar(banco) as con:
        return pd.read_sql_query("SELECT * FROM notas", con)


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

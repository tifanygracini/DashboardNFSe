"""Formatação para exibição (padrão brasileiro)."""


def brl(v: float) -> str:
    """R$ 1.234,56"""
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def percentual(v: float) -> str:
    return f"{v:.2f}".replace(".", ",") + "%"


def sim_nao(v) -> str:
    return "Sim" if v else "Não"

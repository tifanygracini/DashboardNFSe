"""Identificadores fiscais (CNPJ/CPF)."""
import re


def so_digitos(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def cnpj_valido(cnpj: str) -> bool:
    if len(cnpj) != 14 or not cnpj.isdigit() or len(set(cnpj)) == 1:
        return False

    def dv(parcial: str) -> str:
        pesos = list(range(len(parcial) - 7, 1, -1)) + list(range(9, 1, -1))
        resto = sum(int(d) * p for d, p in zip(parcial, pesos)) % 11
        return "0" if resto < 2 else str(11 - resto)

    return cnpj[12] == dv(cnpj[:12]) and cnpj[13] == dv(cnpj[:13])

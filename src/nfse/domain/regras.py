"""Regras de negócio da NFS-e (ver CLAUDE.md, seção "Regras de negócio")."""
from .models import TipoNota

CODIGO_ISS_RETIDO = "2"  # tpRetISSQN = 2: ISS retido pelo tomador


class RegraError(ValueError):
    """Nota que não se encaixa nas regras da empresa."""


def classificar_tipo(prestador_cnpj: str, tomador_cnpj: str, cnpj_empresa: str) -> TipoNota:
    if prestador_cnpj == cnpj_empresa:
        return TipoNota.EMITIDA
    if tomador_cnpj == cnpj_empresa:
        return TipoNota.RECEBIDA
    raise RegraError("a empresa não é prestadora nem tomadora desta nota")


def base_calculo(vbc: float | None, valor_servico: float, desconto: float) -> float:
    """Usa vBC da nota; se faltar, serviço menos descontos."""
    return vbc if vbc is not None else valor_servico - desconto


def valor_liquido(vliq: float | None, valor_servico: float, desconto: float, valor_retido: float) -> float:
    return vliq if vliq is not None else valor_servico - desconto - valor_retido


def iss_retido(tp_ret_issqn: str) -> bool:
    return tp_ret_issqn == CODIGO_ISS_RETIDO


def competencia(data_iso: str) -> str:
    """AAAA-MM a partir de uma data ISO."""
    return data_iso[:7]

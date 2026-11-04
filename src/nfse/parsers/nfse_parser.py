"""XML de NFS-e (padrão nacional) -> Nota."""
from nfse.domain import regras
from nfse.domain.documentos import so_digitos
from nfse.domain.models import Nota, StatusNota

from .xml_utils import filho, local, numero, texto


def _numero_ou_none(s: str) -> float | None:
    return numero(s) if s else None


def ler_nota(raiz, cnpj_empresa: str, arquivo: str) -> Nota | None:
    """Devolve a Nota, ou None se o XML não for NFS-e. Levanta ValueError se a nota for inválida."""
    inf = raiz if local(raiz.tag) == "infNFSe" else filho(raiz, "infNFSe")
    if inf is None:
        return None
    chave = so_digitos((inf.get("Id") or "").replace("NFS", "", 1))
    if len(chave) != 50:
        raise ValueError(f"chave de acesso inválida no Id ({inf.get('Id')!r})")

    dps = filho(inf, "DPS", "infDPS")
    val_nfse = filho(inf, "valores")
    val_dps = filho(dps, "valores")

    prest_cnpj = so_digitos(texto(dps, "prest", "CNPJ") or texto(dps, "prest", "CPF") or texto(inf, "emit", "CNPJ"))
    prest_nome = texto(inf, "emit", "xNome") or texto(dps, "prest", "xNome")
    toma_cnpj = so_digitos(texto(dps, "toma", "CNPJ") or texto(dps, "toma", "CPF"))
    toma_nome = texto(dps, "toma", "xNome")
    tipo = regras.classificar_tipo(prest_cnpj, toma_cnpj, cnpj_empresa)

    v_serv = numero(texto(val_dps, "vServPrest", "vServ"))
    desconto = numero(texto(val_dps, "vDescCondIncond", "vDescIncond")) + \
        numero(texto(val_dps, "vDescCondIncond", "vDescCond"))
    v_ret = numero(texto(val_nfse, "vTotalRet"))
    data = texto(dps, "dhEmi")

    return Nota(
        chave=chave, numero=texto(inf, "nNFSe"), data_emissao=data, competencia=regras.competencia(data),
        tipo=tipo, prestador_cnpj=prest_cnpj, prestador_nome=prest_nome,
        tomador_cnpj=toma_cnpj, tomador_nome=toma_nome,
        codigo_servico=texto(dps, "serv", "cServ", "cTribNac"),
        descricao_servico=texto(dps, "serv", "cServ", "xDescServ"),
        valor_servico=v_serv, desconto=desconto,
        base_calculo=regras.base_calculo(_numero_ou_none(texto(val_nfse, "vBC")), v_serv, desconto),
        aliquota=numero(texto(val_nfse, "pAliqAplic")), valor_iss=numero(texto(val_nfse, "vISSQN")),
        iss_retido=regras.iss_retido(texto(val_dps, "trib", "tribMun", "tpRetISSQN")),
        valor_retido=v_ret,
        valor_liquido=regras.valor_liquido(_numero_ou_none(texto(val_nfse, "vLiq")), v_serv, desconto, v_ret),
        status=StatusNota.NORMAL, arquivo=arquivo,
    )

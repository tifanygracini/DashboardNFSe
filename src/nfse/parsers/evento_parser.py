"""Eventos da NFS-e (cancelamento = e101101) e metadados de documentos do ADN."""
import re
import xml.etree.ElementTree as ET

from nfse.domain.documentos import so_digitos

from .xml_utils import achar, achar_texto, local

CODIGO_CANCELAMENTO = "101101"


def chave_cancelada(raiz) -> str | None:
    """Se o XML for evento de cancelamento, devolve a chave da nota cancelada."""
    if achar(raiz, f"e{CODIGO_CANCELAMENTO}") is None:
        return None
    el = achar(raiz, "chNFSe")
    return so_digitos(el.text) if el is not None and el.text else None


def tipo_do_evento(xml: bytes, informado: str | None) -> str:
    if informado:
        return re.sub(r"\D", "", str(informado)) or str(informado)
    try:
        for el in ET.fromstring(xml).iter():
            m = re.fullmatch(r"e(\d{6})", local(el.tag))
            if m:
                return m.group(1)
    except ET.ParseError:
        pass
    return "desconhecido"


def chave_no_xml(xml: bytes) -> str:
    try:
        return so_digitos(achar_texto(ET.fromstring(xml), "chNFSe"))
    except ET.ParseError:
        return ""


def competencia_documento(xml: bytes, tipo_documento: str, data_geracao: str | None) -> str:
    """AAAA-MM pela dhEmi (nota) ou dhEvento (evento); se faltar, pela data de geração."""
    campo = "dhEvento" if tipo_documento == "EVENTO" else "dhEmi"
    try:
        data = achar_texto(ET.fromstring(xml), campo)
    except ET.ParseError:
        data = ""
    for candidata in (data, data_geracao or ""):
        if re.match(r"\d{4}-\d{2}", candidata):
            return candidata[:7]
    return "sem-data"

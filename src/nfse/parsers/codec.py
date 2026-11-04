"""Decodificação do campo ArquivoXml do ADN."""
import base64
import binascii
import gzip


def decodificar(conteudo: str | bytes) -> bytes:
    """base64 -> gzip -> XML (trata base64 duplo)."""
    dados = base64.b64decode(conteudo)
    for _ in range(3):
        if dados[:2] == b"\x1f\x8b":
            dados = gzip.decompress(dados)
        elif dados.lstrip(b"\xef\xbb\xbf \r\n\t")[:1] != b"<":
            try:
                dados = base64.b64decode(dados, validate=True)
            except (binascii.Error, ValueError):
                break
        else:
            break
    return dados


def codificar(xml: bytes) -> str:
    """Inverso de decodificar (usado pelo simulador e pelos testes)."""
    return base64.b64encode(gzip.compress(xml)).decode()

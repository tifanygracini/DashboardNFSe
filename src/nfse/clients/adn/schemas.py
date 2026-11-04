"""Formato das respostas do ADN (ver docs/adn-api.md)."""
from dataclasses import dataclass, field

STATUS_FILA_VAZIA = "NENHUM_DOCUMENTO_LOCALIZADO"


@dataclass(frozen=True)
class DocumentoDFe:
    nsu: int
    chave: str
    tipo_documento: str        # NFSE ou EVENTO
    tipo_evento: str | None
    arquivo_xml: str           # base64(gzip(xml))
    data_geracao: str | None

    @classmethod
    def from_json(cls, d: dict) -> "DocumentoDFe":
        return cls(
            nsu=int(d["NSU"]),
            chave=str(d.get("ChaveAcesso") or ""),
            tipo_documento=str(d.get("TipoDocumento", "")).upper(),
            tipo_evento=d.get("TipoEvento"),
            arquivo_xml=d.get("ArquivoXml") or "",
            data_geracao=d.get("DataHoraGeracao"),
        )


@dataclass(frozen=True)
class RespostaDFe:
    documentos: list[DocumentoDFe] = field(default_factory=list)
    fila_esgotada: bool = False

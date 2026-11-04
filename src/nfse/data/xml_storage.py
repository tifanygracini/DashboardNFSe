"""Pasta de XMLs organizada por competência: <pasta>/AAAA-MM/<arquivo>.xml"""
import re
from pathlib import Path

_NOME_SEGURO = re.compile(r"[\w.-]+")


class XmlStorage:
    def __init__(self, pasta: Path):
        self.pasta = pasta

    def gravar(self, competencia: str, nome: str, conteudo: bytes) -> bool:
        """Grava se ainda não existir. Devolve True se o arquivo é novo."""
        for parte in (competencia, nome):
            if not _NOME_SEGURO.fullmatch(parte) or parte in (".", ".."):
                raise ValueError(f"nome de arquivo inválido: {parte!r}")
        destino = self.pasta / competencia / nome
        if destino.exists():
            return False
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
        return True

    def listar(self) -> list[Path]:
        return sorted(self.pasta.rglob("*.xml")) if self.pasta.exists() else []

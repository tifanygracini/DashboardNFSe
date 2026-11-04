"""Pasta de XMLs -> banco. Pode rodar várias vezes: a chave de acesso evita duplicidade."""
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from nfse.data import DestinoBanco, NotasRepository, XmlStorage, conectar
from nfse.parsers.evento_parser import chave_cancelada
from nfse.parsers.nfse_parser import ler_nota


@dataclass
class ResultadoImportacao:
    novas: int = 0
    existentes: int = 0
    cancelamentos: int = 0
    canceladas: int = 0          # notas que mudaram para CANCELADA nesta execução
    avisos: list[str] = field(default_factory=list)
    falhas: list[str] = field(default_factory=list)

    @property
    def erros(self) -> int:
        return len(self.falhas)


class ImportService:
    def __init__(self, storage: XmlStorage, destino: DestinoBanco, cnpj_empresa: str):
        self.storage = storage
        self.destino = destino
        self.cnpj_empresa = cnpj_empresa

    def importar(self) -> ResultadoImportacao:
        res = ResultadoImportacao()
        cancelamentos: list[str] = []
        with conectar(self.destino) as con:
            repo = NotasRepository(con)
            for arq in self.storage.listar():
                try:
                    raiz = ET.parse(arq).getroot()
                    chave = chave_cancelada(raiz)
                    if chave:
                        cancelamentos.append(chave)
                        continue
                    nota = ler_nota(raiz, self.cnpj_empresa, arq.name)
                    if nota is None:
                        res.avisos.append(f"{arq.name} não é uma NFS-e; pulado.")
                        continue
                    if repo.inserir(nota):
                        res.novas += 1
                    else:
                        res.existentes += 1
                except (ET.ParseError, ValueError, KeyError) as e:
                    res.falhas.append(f"{arq.name}: {e}")
            res.cancelamentos = len(cancelamentos)
            res.canceladas = repo.marcar_canceladas(cancelamentos)
        return res

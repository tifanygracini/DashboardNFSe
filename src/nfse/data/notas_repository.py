"""Gravação das notas no banco (SQLite ou PostgreSQL). Cada nota pertence a uma empresa (empresa_cnpj)."""
from collections.abc import Iterable

from nfse.domain.models import Nota, StatusNota

from .database import Conexao


class NotasRepository:
    def __init__(self, con: Conexao, empresa_cnpj: str):
        self.con = con
        self.empresa_cnpj = empresa_cnpj

    def inserir(self, nota: Nota) -> bool:
        """Insere se a chave ainda não existe para esta empresa. Devolve True se a nota é nova."""
        linha = {"empresa_cnpj": self.empresa_cnpj, **nota.como_linha()}
        cols = ", ".join(linha)
        marcas = ", ".join("?" for _ in linha)
        cur = self.con.executar(
            f"INSERT INTO {self.con.tabela} ({cols}) VALUES ({marcas}) ON CONFLICT (empresa_cnpj, chave) DO NOTHING",
            list(linha.values()))
        return cur.rowcount > 0

    def marcar_canceladas(self, chaves: Iterable[str]) -> int:
        """Marca como CANCELADA. Devolve quantas mudaram de status agora."""
        canc = StatusNota.CANCELADA.value
        return sum(
            self.con.executar(f"UPDATE {self.con.tabela} SET status=? WHERE empresa_cnpj=? AND chave=? AND status<>?",
                              (canc, self.empresa_cnpj, chave, canc)).rowcount
            for chave in chaves)

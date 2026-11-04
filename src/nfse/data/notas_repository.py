"""Gravação das notas no banco (SQLite ou PostgreSQL)."""
from collections.abc import Iterable

from nfse.domain.models import Nota, StatusNota

from .database import Conexao


class NotasRepository:
    def __init__(self, con: Conexao):
        self.con = con

    def inserir(self, nota: Nota) -> bool:
        """Insere se a chave ainda não existe. Devolve True se a nota é nova."""
        linha = nota.como_linha()
        cols = ", ".join(linha)
        marcas = ", ".join("?" for _ in linha)
        cur = self.con.executar(
            f"INSERT INTO {self.con.tabela} ({cols}) VALUES ({marcas}) ON CONFLICT (chave) DO NOTHING",
            list(linha.values()))
        return cur.rowcount > 0

    def marcar_canceladas(self, chaves: Iterable[str]) -> int:
        """Marca como CANCELADA. Devolve quantas mudaram de status agora."""
        canc = StatusNota.CANCELADA.value
        return sum(
            self.con.executar(f"UPDATE {self.con.tabela} SET status=? WHERE chave=? AND status<>?",
                              (canc, chave, canc)).rowcount
            for chave in chaves)

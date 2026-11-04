"""Conexão com o banco de notas: SQLite (arquivo local) ou PostgreSQL (nuvem).

Usa PostgreSQL quando NFSE_DATABASE_URL está configurada; senão, o SQLite em data/notas.db.
O SQL do projeto é escrito uma vez só, com "?" como marcador; a Conexao troca por "%s" no PostgreSQL.
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from nfse.config import Segredo

ESQUEMA_PG = "nfse"  # esquema próprio: fora do "public", que o Supabase expõe pela API REST

COLUNAS = [
    ("chave", "TEXT PRIMARY KEY"), ("numero", "TEXT"), ("data_emissao", "TEXT"), ("competencia", "TEXT"),
    ("tipo", "TEXT"), ("prestador_cnpj", "TEXT"), ("prestador_nome", "TEXT"),
    ("tomador_cnpj", "TEXT"), ("tomador_nome", "TEXT"), ("codigo_servico", "TEXT"),
    ("descricao_servico", "TEXT"), ("valor_servico", "REAL"), ("desconto", "REAL"),
    ("base_calculo", "REAL"), ("aliquota", "REAL"), ("valor_iss", "REAL"), ("iss_retido", "INTEGER"),
    ("valor_retido", "REAL"), ("valor_liquido", "REAL"), ("status", "TEXT"), ("arquivo", "TEXT"),
]
_HOSTS_LOCAIS = {"", "localhost", "127.0.0.1", "::1"}


class BancoIndisponivel(Exception):
    """Banco ausente, inacessível ou sem a tabela. A mensagem nunca contém a senha."""


try:
    import psycopg
    ERROS_BANCO: tuple[type[Exception], ...] = (BancoIndisponivel, sqlite3.Error, psycopg.Error)
except ImportError:  # psycopg só é necessário quando se usa PostgreSQL
    psycopg = None
    ERROS_BANCO = (BancoIndisponivel, sqlite3.Error)


@dataclass(frozen=True)
class DestinoBanco:
    arquivo: Path                                       # SQLite
    url: Segredo | None = field(default=None, repr=False)  # PostgreSQL (tem precedência)

    @property
    def postgres(self) -> bool:
        return bool(self.url)

    def descricao(self) -> str:
        """Onde estão os dados, sem usuário nem senha (para mensagens e chave de cache)."""
        if not self.postgres:
            return f"SQLite ({self.arquivo})"
        try:
            p = _parametros_pg(self.url.revelar())
            return f"PostgreSQL ({p.get('host') or 'local'}/{p.get('dbname', '')})"
        except BancoIndisponivel:
            return "PostgreSQL"

    def chave_cache(self) -> str:
        """Muda quando a credencial muda, sem conter a senha (hash de mão única)."""
        alvo = self.url.revelar() if self.postgres else str(self.arquivo)
        return f"{self.descricao()}#{hashlib.sha256(alvo.encode()).hexdigest()[:16]}"


class Conexao:
    """Envelope fino sobre a conexão do driver: mesmo SQL nos dois bancos."""

    def __init__(self, bruta, postgres: bool):
        self.bruta = bruta
        self.postgres = postgres
        self.tabela = f"{ESQUEMA_PG}.notas" if postgres else "notas"

    def executar(self, sql: str, params=()):
        if self.postgres:
            sql = sql.replace("?", "%s")
        cur = self.bruta.cursor()
        cur.execute(sql, params)
        return cur


def _parametros_pg(url: str) -> dict:
    if psycopg is None:
        raise BancoIndisponivel('Falta a biblioteca do PostgreSQL. Rode: pip install "psycopg[binary]"')
    from psycopg.conninfo import conninfo_to_dict
    try:
        return conninfo_to_dict(url)
    except psycopg.ProgrammingError:
        raise BancoIndisponivel("NFSE_DATABASE_URL inválida (formato esperado: "
                                "postgresql://usuario:senha@host:5432/banco).") from None


def _abrir_pg(url: str):
    params = _parametros_pg(url)
    host = params.get("host", "")
    if "sslmode" not in params and host not in _HOSTS_LOCAIS:
        params["sslmode"] = "require"  # nunca trafegar notas sem criptografia pela internet
    params.setdefault("connect_timeout", 10)
    params.setdefault("application_name", "nfse-dashboard")
    try:
        return psycopg.connect(**params)
    except psycopg.OperationalError as e:
        detalhe = str(e).strip().splitlines()[-1] if str(e).strip() else type(e).__name__
        raise BancoIndisponivel(f"Não consegui conectar ao PostgreSQL ({host or 'local'}): {detalhe}") from None


def criar_tabela(con: Conexao):
    colunas = ", ".join(f"{n} {t.replace('REAL', 'DOUBLE PRECISION') if con.postgres else t}" for n, t in COLUNAS)
    try:
        con.executar(f"CREATE TABLE IF NOT EXISTS {con.tabela} ({colunas})")
    except ERROS_BANCO[2:] as e:
        raise BancoIndisponivel(f"Não consegui criar a tabela {con.tabela} ({str(e).strip().splitlines()[0]}). "
                                "Rode antes o sql/setup_postgres.sql e use o usuário do robô.") from None


def existe_tabela(con: Conexao) -> bool:
    if con.postgres:
        return con.executar("SELECT to_regclass(?)", (con.tabela,)).fetchone()[0] is not None
    return con.executar("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (con.tabela,)).fetchone() is not None


@contextmanager
def conectar(destino: DestinoBanco, criar: bool = True) -> Iterator[Conexao]:
    """Abre o banco, faz commit no fim e sempre fecha.

    criar=True (robô): cria pasta/tabela se faltar. criar=False (dashboard): só lê; serve para um
    usuário somente-leitura no PostgreSQL e não cria um SQLite vazio por engano.
    """
    if destino.postgres:
        bruta = _abrir_pg(destino.url.revelar())
    else:
        if criar:
            destino.arquivo.parent.mkdir(parents=True, exist_ok=True)
        elif not destino.arquivo.exists():
            raise BancoIndisponivel("Ainda não existe o banco de notas. Rode primeiro: nfse-baixar (ou nfse-importar).")
        bruta = sqlite3.connect(destino.arquivo)
    con = Conexao(bruta, destino.postgres)
    try:
        if criar:
            criar_tabela(con)
        yield con
        bruta.commit()
    finally:
        bruta.close()  # sem commit = rollback do que estava pendente

"""Conexão com o banco de notas: SQLite (arquivo local) ou PostgreSQL (nuvem).

Usa PostgreSQL quando NFSE_DATABASE_URL está configurada; senão, o SQLite em data/notas.db.
O SQL do projeto é escrito uma vez só, com "?" como marcador; a Conexao troca por "%s" no PostgreSQL.

Tabelas (no PostgreSQL, dentro do esquema nfse):
  empresas  cadastro das empresas clientes (Acessórias), certificado e estado do robô no ADN
  notas     NFS-e de todas as empresas; chave primária (empresa_cnpj, chave), porque uma nota entre
            dois clientes do escritório é EMITIDA para um e RECEBIDA para o outro
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
    ("empresa_cnpj", "TEXT NOT NULL"),
    ("chave", "TEXT NOT NULL"), ("numero", "TEXT"), ("data_emissao", "TEXT"), ("competencia", "TEXT"),
    ("tipo", "TEXT"), ("prestador_cnpj", "TEXT"), ("prestador_nome", "TEXT"),
    ("tomador_cnpj", "TEXT"), ("tomador_nome", "TEXT"), ("codigo_servico", "TEXT"),
    ("descricao_servico", "TEXT"), ("valor_servico", "REAL"), ("desconto", "REAL"),
    ("base_calculo", "REAL"), ("aliquota", "REAL"), ("valor_iss", "REAL"), ("iss_retido", "INTEGER"),
    ("valor_retido", "REAL"), ("valor_liquido", "REAL"), ("status", "TEXT"), ("arquivo", "TEXT"),
]
CHAVE_NOTAS = "PRIMARY KEY (empresa_cnpj, chave)"

COLUNAS_EMPRESAS = [
    ("cnpj", "TEXT PRIMARY KEY"), ("razao_social", "TEXT"), ("fantasia", "TEXT"), ("codigo_dominio", "TEXT"),
    ("acessorias_id", "TEXT"), ("regime_acessorias", "TEXT"), ("regime", "TEXT"), ("grupo", "TEXT"),
    ("uf", "TEXT"), ("ativa", "INTEGER"),
    ("cert_arquivo", "TEXT"), ("cert_titular", "TEXT"), ("cert_validade", "TEXT"),
    ("adn_ultimo_nsu", "INTEGER"), ("adn_ultima_consulta", "TEXT"),
    ("robo_execucao", "TEXT"), ("robo_situacao", "TEXT"), ("robo_mensagem", "TEXT"),
    ("sincronizado_em", "TEXT"),
]
# certificados já abertos pelo robô: lembra de quem é cada arquivo da pasta de rede (sem guardar o conteúdo)
COLUNAS_CERTIFICADOS = [("arquivo", "TEXT PRIMARY KEY"), ("titular", "TEXT"), ("nome", "TEXT"),
                        ("validade", "TEXT"), ("lido_em", "TEXT")]
_HOSTS_LOCAIS = {"", "localhost", "127.0.0.1", "::1"}


class BancoIndisponivel(Exception):
    """Banco ausente, inacessível ou sem a tabela. A mensagem nunca contém a senha."""


class BancoDesatualizado(BancoIndisponivel):
    """Tabela de notas ainda no formato de uma empresa só (antes da migração multiempresa)."""


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
    cnpj_legado: str | None = None  # dono das notas gravadas antes da migração multiempresa (CNPJ_EMPRESA)

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
        self.tabela = self.nome("notas")
        self.empresas = self.nome("empresas")

    def nome(self, tabela: str) -> str:
        return f"{ESQUEMA_PG}.{tabela}" if self.postgres else tabela

    def executar(self, sql: str, params=()):
        if self.postgres:
            sql = sql.replace("?", "%s")
        cur = self.bruta.cursor()
        cur.execute(sql, params)
        return cur

    def linhas(self, sql: str, params=()) -> list[dict]:
        cur = self.executar(sql, params)
        nomes = [d[0] for d in cur.description]
        return [dict(zip(nomes, r)) for r in cur.fetchall()]


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


# ---------------------------------------------------------------- estrutura
def _tipo(con: Conexao, t: str) -> str:
    return t.replace("REAL", "DOUBLE PRECISION") if con.postgres else t


def _ddl_notas(con: Conexao, tabela: str) -> str:
    colunas = ", ".join(f"{n} {_tipo(con, t)}" for n, t in COLUNAS)
    return f"CREATE TABLE IF NOT EXISTS {tabela} ({colunas}, {CHAVE_NOTAS})"


def existe_tabela(con: Conexao, tabela: str = "notas") -> bool:
    nome = con.nome(tabela)
    if con.postgres:
        return con.executar("SELECT to_regclass(?)", (nome,)).fetchone()[0] is not None
    return con.executar("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)).fetchone() is not None


def colunas_da_tabela(con: Conexao, tabela: str) -> set[str]:
    if con.postgres:
        cur = con.executar("SELECT column_name FROM information_schema.columns WHERE table_schema=? AND table_name=?",
                           (ESQUEMA_PG, tabela))
        return {r[0] for r in cur.fetchall()}
    return {r[1] for r in con.executar(f"PRAGMA table_info({tabela})").fetchall()}


def notas_no_formato_antigo(con: Conexao) -> bool:
    return existe_tabela(con) and "empresa_cnpj" not in colunas_da_tabela(con, "notas")


def _migrar_notas(con: Conexao, cnpj_legado: str | None):
    """Notas de antes da migração (uma empresa só) passam a ser da empresa CNPJ_EMPRESA."""
    qtd = con.executar(f"SELECT count(*) FROM {con.tabela}").fetchone()[0]
    if qtd and not cnpj_legado:
        raise BancoDesatualizado(
            f"A tabela de notas tem {qtd} notas no formato antigo (uma empresa só). Configure CNPJ_EMPRESA com o "
            "CNPJ dessas notas e rode de novo para migrar.")
    antigas = [n for n, _ in COLUNAS if n != "empresa_cnpj"]
    lista = ", ".join(antigas)
    if con.postgres:
        con.executar(f"ALTER TABLE {con.tabela} ADD COLUMN IF NOT EXISTS empresa_cnpj TEXT")
        con.executar(f"UPDATE {con.tabela} SET empresa_cnpj=? WHERE empresa_cnpj IS NULL", (cnpj_legado or "",))
        con.executar(f"ALTER TABLE {con.tabela} ALTER COLUMN empresa_cnpj SET NOT NULL")
        con.executar(f"ALTER TABLE {con.tabela} DROP CONSTRAINT IF EXISTS notas_pkey")
        con.executar(f"ALTER TABLE {con.tabela} ADD {CHAVE_NOTAS}")
    else:  # SQLite não troca a chave primária: recria a tabela
        con.executar(_ddl_notas(con, "notas_nova"))
        con.executar(f"INSERT INTO notas_nova (empresa_cnpj, {lista}) SELECT ?, {lista} FROM notas", (cnpj_legado or "",))
        con.executar("DROP TABLE notas")
        con.executar("ALTER TABLE notas_nova RENAME TO notas")


def _completar_colunas(con: Conexao, tabela: str, colunas: list[tuple[str, str]]):
    """Colunas novas em versões futuras entram sem recriar a tabela."""
    existentes = colunas_da_tabela(con, tabela)
    for nome, tipo in colunas:
        if nome not in existentes:
            tipo = tipo.replace(" PRIMARY KEY", "").replace(" NOT NULL", "")
            con.executar(f"ALTER TABLE {con.nome(tabela)} ADD COLUMN {nome} {_tipo(con, tipo)}")


def preparar(con: Conexao, cnpj_legado: str | None = None):
    """Cria/atualiza as tabelas (robô). Pode rodar sempre: só faz o que falta."""
    try:
        if notas_no_formato_antigo(con):
            _migrar_notas(con, cnpj_legado)
        con.executar(_ddl_notas(con, con.tabela))
        _completar_colunas(con, "notas", COLUNAS)
        con.executar(f"CREATE INDEX IF NOT EXISTS notas_empresa_competencia ON {con.tabela} (empresa_cnpj, competencia)")
        colunas = ", ".join(f"{n} {_tipo(con, t)}" for n, t in COLUNAS_EMPRESAS)
        con.executar(f"CREATE TABLE IF NOT EXISTS {con.empresas} ({colunas})")
        _completar_colunas(con, "empresas", COLUNAS_EMPRESAS)
        colunas = ", ".join(f"{n} {t}" for n, t in COLUNAS_CERTIFICADOS)
        con.executar(f"CREATE TABLE IF NOT EXISTS {con.nome('certificados')} ({colunas})")
        if cnpj_legado:  # a empresa das notas antigas precisa existir no cadastro
            con.executar(f"INSERT INTO {con.empresas} (cnpj, razao_social, ativa, regime) VALUES (?, ?, 1, ?) "
                         "ON CONFLICT (cnpj) DO NOTHING", (cnpj_legado, "", "Outros / não informado"))
    except BancoDesatualizado:
        raise
    except ERROS_BANCO[1:] as e:
        raise BancoIndisponivel(f"Não consegui criar/atualizar as tabelas ({str(e).strip().splitlines()[0]}). "
                                "Rode antes o sql/setup_postgres.sql e use o usuário do robô.") from None


# compatibilidade com quem chamava a versão de uma empresa só
criar_tabela = preparar


@contextmanager
def conectar(destino: DestinoBanco, criar: bool = True) -> Iterator[Conexao]:
    """Abre o banco, faz commit no fim e sempre fecha.

    criar=True (robô): cria pasta/tabelas e migra se faltar. criar=False (dashboard): só lê; serve para
    um usuário somente-leitura no PostgreSQL e não cria um SQLite vazio por engano.
    """
    if destino.postgres:
        bruta = _abrir_pg(destino.url.revelar())
    else:
        if criar:
            destino.arquivo.parent.mkdir(parents=True, exist_ok=True)
        elif not destino.arquivo.exists():
            raise BancoIndisponivel("Ainda não existe o banco de notas. Rode primeiro: nfse-baixar (ou nfse-importar).")
        bruta = sqlite3.connect(destino.arquivo, timeout=30, check_same_thread=False)
    con = Conexao(bruta, destino.postgres)
    try:
        if criar:
            preparar(con, destino.cnpj_legado)
        yield con
        bruta.commit()
    finally:
        bruta.close()  # sem commit = rollback do que estava pendente

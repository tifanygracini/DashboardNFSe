"""Cadastro das empresas no banco: dados do Acessórias, certificado e estado do robô no ADN."""
from __future__ import annotations

from dataclasses import fields
from datetime import datetime

from nfse.domain.empresa import Empresa

from .database import Conexao, DestinoBanco, conectar
from .estado_repository import EstadoAdn

CAMPOS_ACESSORIAS = ("razao_social", "fantasia", "acessorias_id", "regime_acessorias", "regime", "grupo", "uf")
_CAMPOS_EMPRESA = {f.name for f in fields(Empresa)}


def agora() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _empresa(linha: dict) -> Empresa:
    dados = {k: (v if v is not None else "") for k, v in linha.items() if k in _CAMPOS_EMPRESA}
    dados["ativa"] = bool(linha.get("ativa"))
    return Empresa(**dados)


class EmpresasRepository:
    def __init__(self, con: Conexao):
        self.con = con

    # ------------------------------------------------------------ leitura
    def listar(self, so_ativas: bool = False) -> list[Empresa]:
        filtro = " WHERE ativa=1" if so_ativas else ""
        return [_empresa(l) for l in self.con.linhas(f"SELECT * FROM {self.con.empresas}{filtro} ORDER BY razao_social")]

    def obter(self, cnpj: str) -> Empresa | None:
        linhas = self.con.linhas(f"SELECT * FROM {self.con.empresas} WHERE cnpj=?", (cnpj,))
        return _empresa(linhas[0]) if linhas else None

    def cnpjs(self) -> set[str]:
        return {r[0] for r in self.con.executar(f"SELECT cnpj FROM {self.con.empresas}").fetchall()}

    # ------------------------------------------------------------ Acessórias
    def gravar_do_acessorias(self, dados: dict) -> bool:
        """Insere ou atualiza pelo CNPJ. O código Domínio só é trocado quando o Acessórias traz um valor
        (não apaga o que foi importado de planilha). Devolve True se a empresa é nova."""
        nova = self.obter(dados["cnpj"]) is None
        campos = {k: dados.get(k, "") for k in CAMPOS_ACESSORIAS}
        campos.update(cnpj=dados["cnpj"], ativa=1, sincronizado_em=agora())
        if dados.get("codigo_dominio"):
            campos["codigo_dominio"] = dados["codigo_dominio"]
        cols = ", ".join(campos)
        marcas = ", ".join("?" for _ in campos)
        atualiza = ", ".join(f"{k}=excluded.{k}" for k in campos if k != "cnpj")
        self.con.executar(f"INSERT INTO {self.con.empresas} ({cols}) VALUES ({marcas}) "
                          f"ON CONFLICT (cnpj) DO UPDATE SET {atualiza}", list(campos.values()))
        return nova

    def inativar_ausentes(self, presentes: set[str]) -> int:
        """Empresas que saíram da lista de ativas do Acessórias deixam de ser consultadas pelo robô."""
        ausentes = [c for c in self.cnpjs() if c not in presentes]
        for cnpj in ausentes:
            self.con.executar(f"UPDATE {self.con.empresas} SET ativa=0 WHERE cnpj=? AND ativa=1", (cnpj,))
        return len(ausentes)

    def definir_codigo_dominio(self, cnpj: str, codigo: str) -> bool:
        return self.con.executar(f"UPDATE {self.con.empresas} SET codigo_dominio=? WHERE cnpj=?",
                                 (codigo, cnpj)).rowcount > 0

    # ------------------------------------------------------------ certificado
    def definir_certificado(self, cnpj: str, arquivo: str, titular: str, validade: str):
        self.con.executar(f"UPDATE {self.con.empresas} SET cert_arquivo=?, cert_titular=?, cert_validade=? WHERE cnpj=?",
                          (arquivo, titular, validade, cnpj))

    def limpar_certificado(self, cnpj: str):
        self.definir_certificado(cnpj, "", "", "")

    def lembrar_certificado(self, arquivo: str, titular: str, nome: str, validade: str):
        self.con.executar(f"INSERT INTO {self.con.nome('certificados')} (arquivo, titular, nome, validade, lido_em) "
                          "VALUES (?, ?, ?, ?, ?) ON CONFLICT (arquivo) DO UPDATE SET titular=excluded.titular, "
                          "nome=excluded.nome, validade=excluded.validade, lido_em=excluded.lido_em",
                          (arquivo, titular, nome, validade, agora()))

    def titulares_conhecidos(self) -> dict[str, str]:
        """arquivo -> CNPJ titular, dos certificados já abertos alguma vez."""
        return dict(self.con.executar(f"SELECT arquivo, titular FROM {self.con.nome('certificados')}").fetchall())

    # ------------------------------------------------------------ robô
    def registrar_execucao(self, cnpj: str, situacao: str, mensagem: str = ""):
        self.con.executar(f"UPDATE {self.con.empresas} SET robo_execucao=?, robo_situacao=?, robo_mensagem=? WHERE cnpj=?",
                          (agora(), situacao, mensagem[:500], cnpj))


class EstadoBanco:
    """Mesmo papel do EstadoRepository (arquivo JSON), mas por empresa, na tabela empresas.

    Abre uma conexão curta a cada chamada: o robô consulta várias empresas ao mesmo tempo (threads).
    """

    def __init__(self, destino: DestinoBanco, cnpj: str):
        self.destino = destino
        self.cnpj = cnpj

    def ler(self) -> EstadoAdn:
        with conectar(self.destino, criar=False) as con:
            r = con.executar(f"SELECT adn_ultimo_nsu, adn_ultima_consulta FROM {con.empresas} WHERE cnpj=?",
                             (self.cnpj,)).fetchone()
        if not r:
            return EstadoAdn()
        return EstadoAdn(int(r[0] or 0), datetime.fromisoformat(r[1]) if r[1] else None)

    def gravar(self, estado: EstadoAdn):
        ultima = estado.ultima_consulta.isoformat(timespec="seconds") if estado.ultima_consulta else None
        with conectar(self.destino, criar=False) as con:
            con.executar(f"UPDATE {con.empresas} SET adn_ultimo_nsu=?, adn_ultima_consulta=? WHERE cnpj=?",
                         (estado.ultimo_nsu, ultima, self.cnpj))

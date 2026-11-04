"""Entidades do domínio. Sem I/O: nada aqui lê arquivo, banco ou rede."""
from dataclasses import asdict, dataclass
from enum import StrEnum


class TipoNota(StrEnum):
    EMITIDA = "EMITIDA"    # a empresa é a prestadora (faturamento)
    RECEBIDA = "RECEBIDA"  # a empresa é a tomadora (despesa)


class StatusNota(StrEnum):
    NORMAL = "NORMAL"
    CANCELADA = "CANCELADA"


@dataclass(frozen=True)
class Nota:
    chave: str
    numero: str
    data_emissao: str
    competencia: str
    tipo: TipoNota
    prestador_cnpj: str
    prestador_nome: str
    tomador_cnpj: str
    tomador_nome: str
    codigo_servico: str
    descricao_servico: str
    valor_servico: float
    desconto: float
    base_calculo: float
    aliquota: float
    valor_iss: float
    iss_retido: bool
    valor_retido: float
    valor_liquido: float
    status: StatusNota
    arquivo: str

    def como_linha(self) -> dict:
        """Dicionário com tipos simples, pronto para gravar no banco."""
        linha = asdict(self)
        linha["tipo"] = self.tipo.value
        linha["status"] = self.status.value
        linha["iss_retido"] = 1 if self.iss_retido else 0
        return linha

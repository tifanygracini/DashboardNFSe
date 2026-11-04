"""Estado do robô do ADN (último NSU e horário da última consulta completa)."""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class EstadoCorrompido(Exception):
    pass


@dataclass(frozen=True)
class EstadoAdn:
    ultimo_nsu: int = 0
    ultima_consulta: datetime | None = None


class EstadoRepository:
    def __init__(self, arquivo: Path):
        self.arquivo = arquivo

    def ler(self) -> EstadoAdn:
        if not self.arquivo.exists():
            return EstadoAdn()
        try:
            js = json.loads(self.arquivo.read_text(encoding="utf-8"))
            ultima = js.get("ultima_consulta")
            return EstadoAdn(int(js.get("ultimo_nsu", 0)), datetime.fromisoformat(ultima) if ultima else None)
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
            raise EstadoCorrompido(f"{self.arquivo.name} está corrompido. Apague o arquivo "
                                   "(ou use --desde-nsu) e rode de novo.") from None

    def gravar(self, estado: EstadoAdn):
        """Grava em arquivo temporário e troca, para não corromper se o robô cair no meio."""
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        dados = {
            "ultimo_nsu": estado.ultimo_nsu,
            "ultima_consulta": estado.ultima_consulta.isoformat(timespec="seconds") if estado.ultima_consulta else None,
        }
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.arquivo)

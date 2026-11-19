"""Passagem da versão de uma empresa só (CNPJ_EMPRESA) para a multiempresa.

- Banco: feito pelo data.database.preparar (notas ganham empresa_cnpj = CNPJ_EMPRESA).
- XMLs: data/notas/AAAA-MM/ -> data/notas/<CNPJ_EMPRESA>/AAAA-MM/.
- Estado do robô: o último NSU do adn_estado.json passa para a linha da empresa, para não baixar tudo de novo.
Pode rodar mais de uma vez: o que já foi migrado fica como está.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from nfse.data import DestinoBanco, EstadoBanco, EstadoCorrompido, EstadoRepository, conectar

_COMPETENCIA = re.compile(r"\d{4}-\d{2}|sem-data")


@dataclass
class ResultadoMigracao:
    pastas_movidas: int = 0
    nsu_migrado: int | None = None


def migrar(destino: DestinoBanco, pasta_notas: Path, arquivo_estado: Path, cnpj: str) -> ResultadoMigracao:
    res = ResultadoMigracao()
    with conectar(DestinoBanco(destino.arquivo, destino.url, cnpj)):
        pass  # preparar() migra a tabela de notas e cria a empresa

    alvo = pasta_notas / cnpj
    if pasta_notas.is_dir():
        for pasta in sorted(pasta_notas.iterdir()):
            if pasta.is_dir() and _COMPETENCIA.fullmatch(pasta.name):
                destino_pasta = alvo / pasta.name
                destino_pasta.mkdir(parents=True, exist_ok=True)
                for arq in pasta.iterdir():
                    if not (destino_pasta / arq.name).exists():
                        shutil.move(str(arq), destino_pasta / arq.name)
                if not any(pasta.iterdir()):
                    pasta.rmdir()
                res.pastas_movidas += 1

    estado_banco = EstadoBanco(destino, cnpj)
    try:
        antigo = EstadoRepository(arquivo_estado).ler()
    except EstadoCorrompido:
        antigo = None
    if antigo and antigo.ultimo_nsu and estado_banco.ler().ultimo_nsu < antigo.ultimo_nsu:
        estado_banco.gravar(antigo)
        res.nsu_migrado = antigo.ultimo_nsu
    return res

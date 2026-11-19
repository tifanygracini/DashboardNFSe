"""Acessórias -> tabela empresas. Pode rodar todo dia: atualiza o que mudou e inativa quem saiu."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from nfse.clients.acessorias import AcessoriasClient, mapear
from nfse.data import DestinoBanco, EmpresasRepository, conectar
from nfse.domain.documentos import so_digitos


@dataclass
class ResultadoSincronizacao:
    lidas: int = 0
    novas: int = 0
    atualizadas: int = 0
    ignoradas: int = 0         # CPF/CAEPF ou identificador inválido
    inativadas: int = 0
    sem_codigo_dominio: int = 0
    avisos: list[str] = field(default_factory=list)


def sincronizar(cliente: AcessoriasClient, destino: DestinoBanco, campo_dominio: str = "") -> ResultadoSincronizacao:
    res = ResultadoSincronizacao()
    registros = list(cliente.listar_ativas())  # lê tudo antes de gravar: falha no meio não inativa ninguém
    presentes: set[str] = set()
    with conectar(destino) as con:
        repo = EmpresasRepository(con)
        for raw in registros:
            res.lidas += 1
            dados = mapear(raw, campo_dominio)
            if dados is None:
                res.ignoradas += 1
                continue
            presentes.add(dados["cnpj"])
            if repo.gravar_do_acessorias(dados):
                res.novas += 1
            else:
                res.atualizadas += 1
        if presentes:
            res.inativadas = repo.inativar_ausentes(presentes)
        res.sem_codigo_dominio = sum(1 for e in repo.listar(so_ativas=True) if not e.codigo_dominio)
    if not presentes:
        res.avisos.append("O Acessórias não devolveu nenhuma empresa ativa; nada foi inativado.")
    return res


def ler_planilha(planilha: Path) -> list[dict[str, str]]:
    """CSV com cabeçalho (separador ; ou ,). Chaves em minúsculas, valores sem espaços nas pontas."""
    linhas = planilha.read_text(encoding="utf-8-sig").splitlines()
    if not linhas:
        return []
    dialeto = csv.Sniffer().sniff(linhas[0], delimiters=";,")
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in linha.items()}
            for linha in csv.DictReader(linhas, dialect=dialeto)]


def importar_codigos_dominio(planilha: Path, destino: DestinoBanco) -> tuple[int, list[str]]:
    """CSV com as colunas cnpj e codigo: para quando o código do Domínio não está no Acessórias.
    Devolve (atualizadas, avisos)."""
    avisos, feitas = [], 0
    with conectar(destino) as con:
        repo = EmpresasRepository(con)
        for n, linha in enumerate(ler_planilha(planilha), start=2):
            cnpj = so_digitos(linha.get("cnpj"))
            codigo = linha.get("codigo") or linha.get("código") or linha.get("codigo_dominio") or ""
            if not cnpj or not codigo:
                avisos.append(f"linha {n}: falta cnpj ou codigo")
            elif repo.definir_codigo_dominio(cnpj, codigo):
                feitas += 1
            else:
                avisos.append(f"linha {n}: CNPJ {cnpj} não está no cadastro (rode a sincronização antes)")
    return feitas, avisos

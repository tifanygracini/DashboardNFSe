"""Senhas candidatas de um certificado, achadas na própria pasta de rede.

Na pasta do escritório, cada empresa tem uma subpasta com o .pfx e a senha anotada de algum destes jeitos:
  - no nome do arquivo:            "EMPRESA X SENHA 123456.pfx"
  - no nome da subpasta:           "EMPRESA X - senha 123456\\certificado.pfx"
  - num .txt ao lado do .pfx:      "senha.txt" contendo "123456" ou "Senha: 123456"
  - no nome de um .txt:            "senha 123456.txt"

Nada disso é tomado como certo: cada candidata só vale se abrir o certificado (quem confere é o
certificados_service). Uma candidata errada simplesmente não abre. As senhas nunca vão para log nem banco.
"""
from __future__ import annotations

import re
from pathlib import Path

# "senha 123", "SENHA: abc", "senha-123", "senha_123", "(senha 123)"; a senha é o texto seguinte, sem espaços
_SENHA = re.compile(r"senha\s*(?:do\s+certificado\s*)?[:=\-_–]?\s*([^\s()\[\]{};,]+)", re.IGNORECASE)
MAX_TXT = 4096          # .txt maiores que isso não são anotação de senha
MAX_CANDIDATAS = 20


def _limpar(s: str) -> str:
    return s.strip().strip(".\"'")


def _do_texto(texto: str) -> list[str]:
    return [_limpar(m.group(1)) for m in _SENHA.finditer(texto) if _limpar(m.group(1))]


def _do_txt(arq: Path) -> list[str]:
    try:
        if arq.stat().st_size > MAX_TXT:
            return []
        dados = arq.read_bytes()
    except OSError:
        return []
    for cod in ("utf-8-sig", "cp1252"):
        try:
            texto = dados.decode(cod)
            break
        except UnicodeDecodeError:
            continue
    else:
        return []
    achadas = _do_texto(texto)
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    if not achadas and len(linhas) == 1 and " " not in linhas[0] and len(linhas[0]) <= 64:
        achadas = [linhas[0]]  # .txt só com a senha
    return achadas + _do_texto(arq.stem)


def senhas_candidatas(arquivo: Path, pasta_raiz: Path | None = None) -> list[str]:
    """Candidatas na ordem: nome do arquivo, .txt da mesma pasta, nomes das pastas até a pasta raiz."""
    candidatas = _do_texto(arquivo.stem)
    try:
        vizinhos = sorted(p for p in arquivo.parent.iterdir() if p.suffix.lower() == ".txt" and p.is_file())
    except OSError:
        vizinhos = []
    for txt in vizinhos:
        candidatas += _do_txt(txt)
    pasta = arquivo.parent
    while pasta_raiz is not None and pasta != pasta_raiz and pasta_raiz in pasta.parents:
        candidatas += _do_texto(pasta.name)
        pasta = pasta.parent
    unicas = list(dict.fromkeys(candidatas))
    return unicas[:MAX_CANDIDATAS]

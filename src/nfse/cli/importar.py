"""Lê os XMLs da pasta de cada empresa (<PASTA_NOTAS>/<cnpj>/) e grava no banco.

Uso:
    nfse-importar                          # todas as empresas que têm pasta de XMLs
    nfse-importar --empresa 12345678000190
"""
import argparse
import sys

from nfse.config.settings import ConfigError, Settings, get_settings
from nfse.data import ERROS_BANCO, XmlStorage
from nfse.domain.documentos import cnpj_valido, so_digitos
from nfse.services.import_service import ImportService


def executar(cfg: Settings, cnpjs: list[str] | None = None) -> int:
    destino = cfg.destino
    print(f"Banco de notas: {destino.descricao()}")
    if not cnpjs:
        pastas = sorted(cfg.pasta_notas.iterdir()) if cfg.pasta_notas.is_dir() else []
        cnpjs = [p.name for p in pastas if p.is_dir() and cnpj_valido(p.name)]
    if not cnpjs:
        print("Nenhuma pasta de empresa em", cfg.pasta_notas, "(se os XMLs ainda estão em AAAA-MM/, rode "
              "nfse-empresas migrar).")
        return 1
    codigo = 0
    for cnpj in cnpjs:
        try:
            res = ImportService(XmlStorage(cfg.pasta_notas / cnpj), destino, cnpj).importar()
        except OSError as e:
            print(f"{cnpj}: ERRO ao ler a pasta de notas: {e}")
            codigo = 1
            continue
        except ERROS_BANCO as e:
            print(f"ERRO no banco de notas: {e}")
            return 1
        print(f"{cnpj}: {res.novas} notas novas, {res.existentes} já existiam, {res.erros} arquivos com erro, "
              f"{res.canceladas} canceladas agora.")
        for msg in res.falhas[:5]:
            print(f"   ERRO em {msg}")
    return codigo


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Importa os XMLs de NFS-e para o banco.")
    ap.add_argument("--empresa", action="append", help="CNPJ (pode repetir)")
    args = ap.parse_args(argv)
    try:
        cfg = get_settings()
    except ConfigError as e:
        print(f"ERRO: {e}")
        return 1
    return executar(cfg, [so_digitos(c) for c in args.empresa or []] or None)


if __name__ == "__main__":
    sys.exit(main())

"""Lê os XMLs da pasta de notas e grava no banco (SQLite local ou PostgreSQL, se NFSE_DATABASE_URL estiver configurada).

Uso:
    nfse-importar            (ou: python -m nfse.cli.importar)
"""
import argparse
import sys

from nfse.config.settings import ConfigError, Settings, get_settings
from nfse.data import ERROS_BANCO, DestinoBanco, XmlStorage
from nfse.services.import_service import ImportService


def executar(cfg: Settings) -> int:
    destino = DestinoBanco(cfg.banco, cfg.database_url)
    print(f"Banco de notas: {destino.descricao()}")
    try:
        res = ImportService(XmlStorage(cfg.pasta_notas), destino, cfg.cnpj_empresa).importar()
    except OSError as e:
        print(f"ERRO ao ler a pasta de notas: {e}")
        return 1
    except ERROS_BANCO as e:
        print(f"ERRO no banco de notas: {e}")
        return 1
    for msg in res.avisos:
        print(f"  AVISO: {msg}")
    for msg in res.falhas:
        print(f"  ERRO em {msg}")
    print(f"Importação: {res.novas} notas novas, {res.existentes} já existiam, {res.erros} arquivos com erro.")
    if res.cancelamentos:
        print(f"Eventos de cancelamento encontrados: {res.cancelamentos} "
              f"({res.canceladas} notas marcadas como CANCELADA agora).")
    return 0


def main(argv=None) -> int:
    argparse.ArgumentParser(description="Importa os XMLs de NFS-e para o banco.").parse_args(argv)
    try:
        cfg = get_settings()
    except ConfigError as e:
        print(f"ERRO: {e}")
        return 1
    return executar(cfg)


if __name__ == "__main__":
    sys.exit(main())

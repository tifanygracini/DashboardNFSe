"""Baixa as NFS-e do ADN para a pasta de notas e importa as novas para o banco.

Uso:
    nfse-baixar                                            # ambiente do .env (ADN_AMBIENTE)
    nfse-baixar --producao-restrita                        # ambiente de testes do ADN
    nfse-baixar --base-url http://127.0.0.1:8787 --sem-certificado --forcar   # simulador
"""
import argparse
import logging
import sys

from nfse.clients.adn.client import AdnClient
from nfse.clients.adn.errors import AdnError
from nfse.config.settings import ConfigError, get_settings
from nfse.config.settings import URLS_ADN
from nfse.data.estado_repository import EstadoCorrompido, EstadoRepository
from nfse.data.xml_storage import XmlStorage
from nfse.services.download_service import MAX_LOTES, DownloadService
from nfse.cli import importar


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Baixa NFS-e do ADN para a pasta de notas (AAAA-MM/).")
    ap.add_argument("--base-url", help="sobrepõe o ambiente do .env (ex.: simulador local)")
    ap.add_argument("--producao-restrita", action="store_true", help=f"usa {URLS_ADN['restrita']}")
    ap.add_argument("--sem-certificado", action="store_true", help="para o simulador local")
    ap.add_argument("--desde-nsu", type=int, help="recomeçar de propósito a partir deste NSU")
    ap.add_argument("--forcar", action="store_true", help="ignora a regra de 1 hora entre consultas")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="  %(message)s")

    try:
        cfg = get_settings()
        base = args.base_url or (URLS_ADN["restrita"] if args.producao_restrita else cfg.adn_base_url)
        certificado = None if args.sem_certificado else cfg.credenciais_certificado()
        servico = DownloadService(AdnClient(base, cfg.cnpj_empresa, certificado=certificado),
                                  EstadoRepository(cfg.arquivo_estado), XmlStorage(cfg.pasta_notas))
        res = servico.executar(
            desde_nsu=args.desde_nsu, forcar=args.forcar,
            ao_iniciar=lambda nsu: print(f"Consultando {base} a partir do NSU {nsu}..."),
            ao_concluir_lote=lambda n, qtd, novos, nsu:
                print(f"  lote {n}: {qtd} documentos ({novos} novos), último NSU {nsu}"))
    except (ConfigError, AdnError, EstadoCorrompido) as e:
        print(f"ERRO: {e}")
        return 1
    except OSError as e:
        print(f"ERRO ao gravar em disco: {e}. O progresso até o último lote completo foi salvo; rode de novo.")
        return 1

    if res.aguardar_ate:
        print(f"O ADN só deve ser consultado de hora em hora. Espere até {res.aguardar_ate:%H:%M} "
              "(ou use --forcar contra o simulador).")
        return 0
    if not res.fila_esgotada:
        print(f"Atingi o limite de {MAX_LOTES} lotes por execução; rode de novo para continuar.")
    print(f"Resumo: {res.lotes} lotes, {res.recebidos} documentos recebidos, {res.novos} novos. "
          f"Último NSU: {res.ultimo_nsu}.")

    if res.novos:
        print("\nImportando para o banco...")
        return importar.executar(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())

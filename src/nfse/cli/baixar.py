"""Baixa as NFS-e do ADN de todas as empresas ativas com certificado e importa as notas novas.

Uso:
    nfse-baixar                                  # todas as empresas ativas
    nfse-baixar --empresa 12345678000190         # só uma (pode repetir --empresa)
    nfse-baixar --producao-restrita              # ambiente de testes do ADN
    nfse-baixar --base-url http://127.0.0.1:8787 --sem-certificado --forcar   # simulador

Antes, uma vez por dia (o scripts/rodar-robo.ps1 já faz):
    nfse-empresas sincronizar     # cadastro do Acessórias
    nfse-empresas certificados    # certificados da pasta de rede
"""
import argparse
import logging
import sys

from nfse.config.cofre import CofreIndisponivel, CofreKeyring, CofreMemoria
from nfse.config.settings import URLS_ADN, ConfigError, get_settings
from nfse.data import ERROS_BANCO
from nfse.domain.documentos import so_digitos
from nfse.services.robo_service import AGUARDANDO, ERRO, OK, SEM_CERTIFICADO, RoboService

SIMBOLOS = {OK: "ok ", AGUARDANDO: "...", SEM_CERTIFICADO: "-- ", ERRO: "ERR"}


def cofre_do_ambiente(cfg):
    """Gerenciador de Credenciais; a CERT_SENHA do .env continua valendo para a empresa do CNPJ_EMPRESA."""
    try:
        principal = CofreKeyring()
    except CofreIndisponivel:
        principal = None
    extra = {cfg.cnpj_empresa: cfg.cert_senha.revelar()} if cfg.cnpj_empresa and cfg.cert_senha else {}
    if principal is None and not extra:
        raise CofreIndisponivel('Falta a biblioteca keyring para ler as senhas dos certificados. '
                                'Rode: pip install -e ".[keyring]"')
    return CofreMemoria(extra, reserva=principal)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Baixa NFS-e do ADN de todas as empresas (pasta <cnpj>/AAAA-MM/).")
    ap.add_argument("--empresa", action="append", help="CNPJ de uma empresa (pode repetir)")
    ap.add_argument("--base-url", help="sobrepõe o ambiente do .env (ex.: simulador local)")
    ap.add_argument("--producao-restrita", action="store_true", help=f"usa {URLS_ADN['restrita']}")
    ap.add_argument("--sem-certificado", action="store_true", help="para o simulador local")
    ap.add_argument("--forcar", action="store_true", help="ignora a regra de 1 hora e reimporta os XMLs")
    ap.add_argument("--paralelo", type=int, help="empresas consultadas ao mesmo tempo (padrão: NFSE_PARALELO ou 4)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="  %(message)s")

    try:
        cfg = get_settings()
        base = args.base_url or (URLS_ADN["restrita"] if args.producao_restrita else cfg.adn_base_url)
        robo = RoboService(cfg.destino, cofre_do_ambiente(cfg), cfg.pasta_notas, base,
                           paralelo=args.paralelo or cfg.paralelo, usar_certificado=not args.sem_certificado)
        cnpjs = [so_digitos(c) for c in args.empresa or []] or None
        print(f"Consultando {base}...")
        resultados = robo.executar(cnpjs, forcar=args.forcar, ao_concluir=lambda r: print(
            f"  [{SIMBOLOS[r.situacao]}] {r.cnpj} {r.nome[:45]:<45} "
            f"{r.novos:>4} novos, {r.importadas:>4} importadas  {r.mensagem}"))
    except (ConfigError, CofreIndisponivel) as e:
        print(f"ERRO: {e}")
        return 1
    except ERROS_BANCO as e:
        print(f"ERRO no banco de notas: {e}")
        return 1

    if not resultados:
        print("Nenhuma empresa ativa no cadastro. Rode antes: nfse-empresas sincronizar")
        return 1
    contagem = {s: sum(1 for r in resultados if r.situacao == s) for s in SIMBOLOS}
    print(f"\nResumo: {len(resultados)} empresa(s) —{contagem[OK]} ok, {contagem[AGUARDANDO]} aguardando a regra de "
          f"1 hora, {contagem[SEM_CERTIFICADO]} sem certificado, {contagem[ERRO]} com erro. "
          f"{sum(r.novos for r in resultados)} XMLs novos, {sum(r.importadas for r in resultados)} notas importadas.")
    return 2 if contagem[ERRO] else 0


if __name__ == "__main__":
    sys.exit(main())

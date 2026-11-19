"""Cadastro das empresas para o robô de NFS-e.

Uso:
    nfse-empresas sincronizar                 # empresas ativas do Acessórias (razão social, regime, código...)
    nfse-empresas certificados                # varre CERT_PASTA (subpastas), coleta as senhas anotadas e liga
                                              # cada empresa ao seu certificado A1 válido
    nfse-empresas certificados --relatorio logs/certificados.csv   # idem, com relatório (varredura mensal)
    nfse-empresas senha 12345678000190        # guarda a senha de um certificado (pergunta na tela)
    nfse-empresas senhas planilha.csv         # várias de uma vez: colunas senha + arquivo (ou cnpj)
    nfse-empresas codigos planilha.csv        # código do Domínio: colunas cnpj + codigo
    nfse-empresas listar [--pendencias]       # situação de cada empresa
    nfse-empresas migrar                      # uma vez: XMLs e estado da versão de uma empresa só

As senhas ficam no Gerenciador de Credenciais do Windows do usuário que roda o robô. Depois de
importar uma planilha de senhas, apague o arquivo.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from nfse.clients.acessorias import AcessoriasClient, ErroAcessorias
from nfse.config.cofre import CofreIndisponivel, CofreKeyring
from nfse.config.settings import ConfigError, get_settings
from nfse.data import ERROS_BANCO, EmpresasRepository, conectar
from nfse.domain.documentos import cnpj_valido, so_digitos
from nfse.services import migracao_service, sincronizar_service
from nfse.services.certificados_service import (NOVO, PERDEU, PRIMEIRO, CertificadoIlegivel, CertificadosService,
                                                escrever_relatorio)


def _listar(itens: list[str], titulo: str, limite: int = 15):
    if not itens:
        return
    print(f"  {titulo} ({len(itens)}):")
    for i in itens[:limite]:
        print(f"    - {i}")
    if len(itens) > limite:
        print(f"    ... e mais {len(itens) - limite}")


def cmd_sincronizar(cfg, args) -> int:
    cliente = AcessoriasClient(cfg.acessorias_api_url, cfg.acessorias_api_token)
    print("Lendo as empresas ativas do Acessórias...")
    r = sincronizar_service.sincronizar(cliente, cfg.destino, cfg.acessorias_campo_dominio)
    print(f"{r.lidas} lidas: {r.novas} novas, {r.atualizadas} atualizadas, {r.ignoradas} ignoradas (CPF/CAEPF), "
          f"{r.inativadas} inativadas.")
    if r.sem_codigo_dominio:
        print(f"  {r.sem_codigo_dominio} empresas ativas sem código do Domínio. Configure ACESSORIAS_CAMPO_DOMINIO "
              "ou importe com: nfse-empresas codigos planilha.csv")
    for a in r.avisos:
        print(f"  AVISO: {a}")
    return 0


def cmd_certificados(cfg, args) -> int:
    if not cfg.cert_pasta:
        print("ERRO: configure CERT_PASTA no .env com a pasta de rede dos certificados.")
        return 1
    extras = [cfg.cert_pfx] if cfg.cert_pfx else []
    r = CertificadosService(cfg.destino, CofreKeyring()).varrer(cfg.cert_pasta, extras)
    print(f"{r.arquivos} arquivos na pasta, {len(r.lidos)} abertos. Empresas ativas: {r.empresas_com_certificado} com "
          f"certificado, {r.empresas_sem_certificado} sem. Senhas novas ou trocadas no cofre: {r.senhas_atualizadas}.")
    print(f"  Mudanças: {r.contagem(NOVO)} certificado(s) novo(s), {r.contagem(PRIMEIRO)} primeiro(s) certificado(s), "
          f"{r.contagem(PERDEU)} empresa(s) que ficaram sem certificado.")
    _listar([f"{m['razao_social'] or m['cnpj']}: válido até {m['validade']}" for m in r.mudancas
             if m["mudanca"] in (NOVO, PRIMEIRO)], "certificados novos em uso")
    _listar([f"{m['razao_social'] or m['cnpj']} (venceu em {m['validade']})" for m in r.mudancas if m["vencido"]],
            "empresas só com certificado vencido (coloque o novo na pasta, com a senha no nome ou num .txt)")
    _listar(r.sem_senha, "sem senha encontrada (anote a senha no nome do arquivo, num .txt ao lado ou use nfse-empresas senha)")
    _listar(r.ilegiveis, "não abriram")
    _listar(r.sem_empresa, "de CNPJ que não é cliente ativo no Acessórias")
    if args.relatorio:
        print(f"Relatório: {escrever_relatorio(r, Path(args.relatorio))}")
    return 0


def cmd_senha(cfg, args) -> int:
    cnpj = so_digitos(args.cnpj)
    if not cnpj_valido(cnpj):
        print("ERRO: CNPJ inválido.")
        return 1
    senha = getpass.getpass(f"Senha do certificado do CNPJ {cnpj} (não aparece na tela): ")
    if not senha:
        print("Nada gravado.")
        return 1
    CofreKeyring().guardar(cnpj, senha)
    print("Senha guardada no Gerenciador de Credenciais do Windows. Rode: nfse-empresas certificados")
    return 0


def cmd_senhas(cfg, args) -> int:
    planilha = Path(args.planilha)
    feitas, avisos = CertificadosService(cfg.destino, CofreKeyring()).importar_senhas(planilha, cfg.cert_pasta)
    print(f"{feitas} senhas guardadas no Gerenciador de Credenciais.")
    _listar(avisos, "linhas com problema", limite=50)
    print(f"Agora apague a planilha ({planilha}) e rode: nfse-empresas certificados")
    return 0 if feitas else 1


def cmd_codigos(cfg, args) -> int:
    feitas, avisos = sincronizar_service.importar_codigos_dominio(Path(args.planilha), cfg.destino)
    print(f"{feitas} códigos do Domínio gravados.")
    _listar(avisos, "linhas com problema", limite=50)
    return 0


def cmd_listar(cfg, args) -> int:
    with conectar(cfg.destino) as con:
        empresas = EmpresasRepository(con).listar(so_ativas=not args.todas)
    print(f"{'CNPJ':<15}{'Domínio':<9}{'Regime':<18}{'Certificado':<13}Razão social")
    for e in empresas:
        cert = e.situacao_certificado if e.cert_validade else "ausente"
        if args.pendencias and cert == "ok":
            continue
        print(f"{e.cnpj:<15}{e.codigo_dominio[:8]:<9}{e.regime[:17]:<18}{cert:<13}{e.razao_social[:60]}")
    print(f"{len(empresas)} empresa(s).")
    return 0


def cmd_migrar(cfg, args) -> int:
    if not cfg.cnpj_empresa:
        print("ERRO: a migração precisa de CNPJ_EMPRESA no .env (o CNPJ das notas que já estão no banco).")
        return 1
    r = migracao_service.migrar(cfg.destino, cfg.pasta_notas, cfg.arquivo_estado, cfg.cnpj_empresa)
    print(f"Banco migrado. {r.pastas_movidas} pastas de competência movidas para {cfg.pasta_notas / cfg.cnpj_empresa}.")
    if r.nsu_migrado:
        print(f"Último NSU ({r.nsu_migrado}) passado para a empresa {cfg.cnpj_empresa}.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cadastro das empresas do robô de NFS-e.")
    sub = ap.add_subparsers(dest="comando", required=True)
    sub.add_parser("sincronizar", help="importa/atualiza as empresas ativas do Acessórias")
    p = sub.add_parser("certificados", help="varre a pasta de certificados (CERT_PASTA) e coleta as senhas anotadas")
    p.add_argument("--relatorio", help="grava um CSV com a situação e as mudanças de cada empresa")
    p = sub.add_parser("senha", help="guarda a senha de um certificado")
    p.add_argument("cnpj")
    p = sub.add_parser("senhas", help="importa senhas de uma planilha CSV (senha + arquivo ou cnpj)")
    p.add_argument("planilha")
    p = sub.add_parser("codigos", help="importa códigos do Domínio de uma planilha CSV (cnpj + codigo)")
    p.add_argument("planilha")
    p = sub.add_parser("listar", help="situação das empresas")
    p.add_argument("--todas", action="store_true", help="inclui as inativas")
    p.add_argument("--pendencias", action="store_true", help="só as com certificado ausente, vencido ou vencendo")
    sub.add_parser("migrar", help="migra os dados da versão de uma empresa só")
    args = ap.parse_args(argv)

    comandos = {"sincronizar": cmd_sincronizar, "certificados": cmd_certificados, "senha": cmd_senha,
                "senhas": cmd_senhas, "codigos": cmd_codigos, "listar": cmd_listar, "migrar": cmd_migrar}
    try:
        return comandos[args.comando](get_settings(), args)
    except (ConfigError, ErroAcessorias, CofreIndisponivel, CertificadoIlegivel, OSError) as e:
        print(f"ERRO: {e}")
        return 1
    except ERROS_BANCO as e:
        print(f"ERRO no banco de notas: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

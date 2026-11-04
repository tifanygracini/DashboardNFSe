"""Diagnóstico do certificado A1 (.pfx) usado pelo robô.

A senha é pedida na tela e NÃO é mostrada, gravada nem enviada para lugar nenhum.
O script só lê o arquivo e diz o que encontrou.

Uso (na raiz do projeto, com o .venv ativo):
    python tools/diagnosticar_certificado.py                      # usa CERT_PFX do .env
    python tools/diagnosticar_certificado.py "S:\\pasta\\arquivo.pfx"
"""
import argparse
import base64
import binascii
import getpass
import os
import platform
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# OIDs (codificados em DER) que aparecem às claras dentro do .pfx
OIDS = {
    bytes.fromhex("060a2a864886f70d010c0106"): "pbeWithSHAAnd40BitRC2-CBC (legado, Windows antigo)",
    bytes.fromhex("060a2a864886f70d010c0103"): "pbeWithSHAAnd3-KeyTripleDES-CBC (3DES, legado)",
    bytes.fromhex("06092a864886f70d01050d"): "PBES2 (moderno)",
    bytes.fromhex("0609608648016503040102"): "AES-128-CBC",
    bytes.fromhex("060960864801650304012a"): "AES-256-CBC",
    bytes.fromhex("06052b0e03021a"): "SHA-1 (MAC de integridade)",
    bytes.fromhex("0609608648016503040201"): "SHA-256 (MAC de integridade)",
}
RC2 = "pbeWithSHAAnd40BitRC2-CBC (legado, Windows antigo)"
problemas: list[str] = []


def ok(msg):
    print(f"   [OK]     {msg}")


def info(msg):
    print(f"   [INFO]   {msg}")


def aviso(msg):
    print(f"   [AVISO]  {msg}")


def falha(msg):
    problemas.append(msg)
    print(f"   [FALHA]  {msg}")


def versao(pacote):
    try:
        return metadata.version(pacote)
    except metadata.PackageNotFoundError:
        return "NÃO INSTALADO"


# ------------------------------------------------------------------ etapas
def ambiente():
    print("\n0) Ambiente")
    info(f"Python {platform.python_version()} ({sys.executable})")
    info(f"cryptography {versao('cryptography')}, requests-pkcs12 {versao('requests-pkcs12')}, "
         f"python-dotenv {versao('python-dotenv')}")
    try:
        from cryptography.hazmat.backends.openssl import backend
        info(backend.openssl_version_text())
    except Exception:
        pass
    if os.environ.get("CRYPTOGRAPHY_OPENSSL_NO_LEGACY"):
        aviso("CRYPTOGRAPHY_OPENSSL_NO_LEGACY está definida: arquivos com RC2/3DES serão recusados.")


def ler_env() -> dict:
    arq = Path(os.getenv("NFSE_ENV_FILE") or RAIZ / ".env")
    try:
        from dotenv import dotenv_values
    except ImportError:
        return {}
    valores = {k: v for k, v in dotenv_values(arq).items() if v is not None} if arq.is_file() else {}
    valores.update({k: os.environ[k] for k in ("CERT_PFX", "CERT_SENHA", "CNPJ_EMPRESA") if k in os.environ})
    return valores


def arquivo(caminho: Path) -> bytes | None:
    print("\n1) Arquivo")
    info(f"caminho: {caminho}")
    if not caminho.exists():
        falha("o arquivo não existe (ou a unidade de rede não está acessível neste usuário/sessão).")
        return None
    if caminho.is_dir():
        falha("o caminho é uma PASTA; aponte para o arquivo .pfx dentro dela.")
        return None
    try:
        dados = caminho.read_bytes()
    except OSError as e:
        falha(f"não consegui ler o arquivo (permissão ou rede): {e}")
        return None
    if not dados:
        falha("o arquivo está vazio (0 bytes). Provavelmente a cópia/sincronização falhou.")
        return None
    ok(f"lido: {len(dados):,} bytes".replace(",", "."))
    if len(dados) < 1500:
        aviso("arquivo pequeno demais para um A1 com chave e cadeia; pode estar incompleto.")

    if dados[:1] != b"\x30":
        inicio = dados.lstrip()[:11]
        if inicio.startswith(b"-----BEGIN"):
            falha("o arquivo é PEM (texto), não PFX. Exporte o certificado novamente em .pfx.")
            return None
        try:
            decod = base64.b64decode(dados, validate=False)
            if decod[:1] == b"\x30":
                falha("o arquivo está em base64 (texto) em vez de binário. Ele foi salvo/convertido errado.")
                return None
        except (binascii.Error, ValueError):
            pass
        falha("o conteúdo não tem o formato de um PFX (não começa como estrutura DER).")
        return None
    ok("formato binário PKCS#12 (DER)")
    return dados


def algoritmos(dados: bytes):
    print("\n2) Criptografia usada no arquivo (lida sem a senha)")
    achados = [nome for oid, nome in OIDS.items() if oid in dados]
    for nome in achados:
        info(nome)
    if not achados:
        aviso("não identifiquei os algoritmos.")
    if RC2 in achados:
        aviso("RC2-40 é legado. O Windows abre, mas algumas instalações do OpenSSL 3 recusam "
              "e respondem como se a senha estivesse errada.")


def origem_da_senha(digitada: str, env: dict):
    print("\n3) De onde o robô tira a senha")
    do_env = env.get("CERT_SENHA") or ""
    if do_env:
        info("CERT_SENHA está preenchida: o robô usa ESSA senha, e não pergunta na tela.")
        if do_env == digitada:
            ok("a senha do .env é igual à que você digitou agora.")
        else:
            falha("a senha do .env é DIFERENTE da que você digitou agora.")
            if do_env.strip() == digitada.strip():
                aviso("a diferença são espaços no começo/fim.")
            elif digitada.startswith(do_env):
                aviso("a senha do .env parece cortada. Se ela tem #, $, aspas, \\ ou espaço, "
                      "escreva entre aspas simples: CERT_SENHA='sua senha'")
            else:
                aviso("se a senha tem #, $, aspas, \\ ou espaço, escreva entre aspas simples: "
                      "CERT_SENHA='sua senha'")
        return
    try:
        import keyring
        guardada = keyring.get_password("nfse-dashboard", "".join(c for c in env.get("CNPJ_EMPRESA", "") if c.isdigit()))
    except Exception:
        guardada = None
    if guardada:
        info("CERT_SENHA vazia, mas há senha no Gerenciador de Credenciais: o robô usa ESSA.")
        if guardada == digitada:
            ok("a senha guardada é igual à digitada.")
        else:
            falha("a senha guardada no Gerenciador de Credenciais é DIFERENTE da digitada. "
                  "Atualize com: keyring set nfse-dashboard <CNPJ>")
    else:
        info("CERT_SENHA vazia e nada no Gerenciador de Credenciais: o robô pergunta a senha na tela.")


def abrir(dados: bytes, senha: str) -> bool:
    print("\n4) Abrir o arquivo com a senha (mesma biblioteca do robô)")
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12
    except ImportError:
        falha("biblioteca cryptography não instalada neste Python.")
        return False
    try:
        chave, cert, extras = pkcs12.load_key_and_certificates(dados, senha.encode("utf-8"))
    except ValueError as e:
        falha(f"a biblioteca recusou o arquivo com essa senha ({e}).")
        alternativas = [("sem espaços nas pontas", senha.strip().encode("utf-8"))]
        if not senha.isascii():
            alternativas.append(("codificada em Latin-1", senha.encode("latin-1", errors="ignore")))
        for nome, tentativa in alternativas:
            if tentativa == senha.encode("utf-8"):
                continue
            try:
                pkcs12.load_key_and_certificates(dados, tentativa)
                aviso(f"MAS abriu com a senha {nome}. Ajuste a senha no .env/teclado nesse formato.")
                return False
            except ValueError:
                pass
        return False
    ok("arquivo aberto com sucesso.")
    if chave is None:
        falha("o arquivo NÃO contém a chave privada, só o certificado. Exporte novamente "
              "marcando 'Sim, exportar a chave privada'.")
    else:
        ok(f"chave privada presente ({type(chave).__name__.replace('_', '')}).")
    if cert is None and extras:  # sem chave, a biblioteca devolve o certificado junto com a cadeia
        cert, extras = extras[0], extras[1:]
    if cert is None:
        falha("o arquivo não contém nenhum certificado.")
        return False
    fim = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after.replace(tzinfo=timezone.utc)
    inicio = getattr(cert, "not_valid_before_utc", None) or cert.not_valid_before.replace(tzinfo=timezone.utc)
    agora = datetime.now(timezone.utc)
    info(f"titular: {cert.subject.rfc4514_string()}")
    info(f"emissor: {cert.issuer.rfc4514_string()}")
    info(f"validade: {inicio:%d/%m/%Y %H:%M} a {fim:%d/%m/%Y %H:%M} (UTC)")
    if fim < agora:
        falha("o certificado está VENCIDO.")
    elif inicio > agora:
        falha("o certificado AINDA NÃO É VÁLIDO (data de início no futuro). Confira o relógio do computador.")
    info(f"certificados da cadeia incluídos: {len(extras)}")
    return chave is not None


def como_o_robo(caminho: Path, senha: str):
    print("\n5) Teste idêntico ao que o robô faz (requests-pkcs12)")
    try:
        from requests_pkcs12 import Pkcs12Adapter
    except ImportError:
        falha("biblioteca requests-pkcs12 não instalada neste Python.")
        return
    try:
        Pkcs12Adapter(pkcs12_filename=str(caminho), pkcs12_password=senha)
    except Exception as e:
        falha(f"{type(e).__name__}: {e}")
    else:
        ok("o robô conseguiria carregar este certificado.")


def diagnosticar(caminho: Path, senha: str, env: dict | None = None) -> list[str]:
    problemas.clear()
    env = env or {}
    ambiente()
    dados = arquivo(caminho)
    if dados is not None:
        algoritmos(dados)
        origem_da_senha(senha, env)
        if abrir(dados, senha):
            como_o_robo(caminho, senha)
    print("\nResultado:", "nenhum problema encontrado." if not problemas else f"{len(problemas)} problema(s) acima.")
    return list(problemas)


def main():
    ap = argparse.ArgumentParser(description="Diagnóstico do certificado A1 (.pfx).")
    ap.add_argument("pfx", nargs="?", help="caminho do .pfx (padrão: CERT_PFX do .env)")
    args = ap.parse_args()
    env = ler_env()
    caminho = (args.pfx or env.get("CERT_PFX") or "").strip().strip('"')
    if not caminho:
        print("Informe o caminho do .pfx ou preencha CERT_PFX no .env.")
        return 1
    senha = getpass.getpass("Senha do certificado (não aparece na tela): ")
    return 1 if diagnosticar(Path(caminho), senha, env) else 0


if __name__ == "__main__":
    sys.exit(main())

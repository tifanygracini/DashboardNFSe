"""Certificados A1 das empresas, na pasta de rede do escritório (CERT_PASTA).

Varredura (nfse-empresas certificados; roda todo dia com o robô e uma vez por mês com relatório):
  1. lista os .pfx/.p12 da pasta (com todas as subpastas);
  2. tenta abrir cada um: primeiro com a senha já guardada no cofre (Gerenciador de Credenciais), depois
     com as senhas anotadas na própria pasta (nome do arquivo, .txt ao lado, nome da subpasta — ver
     coleta_senhas). Só vale a senha que abre o certificado;
  3. lê do próprio certificado o CNPJ titular e a validade — o nome do arquivo é só uma pista;
  4. para cada CNPJ titular fica o melhor certificado (não vencido, validade mais longa) e a senha dele vai
     para o cofre. Assim, quando um certificado vence e o novo é colocado na pasta com a senha anotada,
     o robô passa a usar o novo sozinho, sem ninguém cadastrar nada;
  5. liga cada empresa ativa ao certificado do mesmo CNPJ ou, para filiais, ao da mesma raiz (8 dígitos),
     que o ADN aceita.

O conteúdo do certificado nunca é copiado: o banco guarda só caminho, CNPJ titular e validade.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from nfse.config.cofre import Cofre
from nfse.config.secret import Segredo
from nfse.data import DestinoBanco, EmpresasRepository, conectar
from nfse.domain.documentos import cnpj_valido, so_digitos
from nfse.domain.empresa import Empresa, raiz
from nfse.services.coleta_senhas import senhas_candidatas
from nfse.services.sincronizar_service import ler_planilha

EXTENSOES = (".pfx", ".p12")
OID_CNPJ_ICP = "2.16.76.1.3.3"  # ICP-Brasil: CNPJ da pessoa jurídica titular (SAN otherName)
_CNPJ_NO_TEXTO = re.compile(r"(?<!\d)(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?!\d)")


class CertificadoIlegivel(Exception):
    """Senha errada, arquivo corrompido ou certificado sem CNPJ. Mensagem sem a senha."""


@dataclass(frozen=True)
class InfoCertificado:
    arquivo: Path
    titular: str      # CNPJ
    nome: str
    validade: date

    @property
    def vencido(self) -> bool:
        return self.validade < date.today()


@dataclass
class ResultadoVarredura:
    arquivos: int = 0
    lidos: list[InfoCertificado] = field(default_factory=list)
    sem_senha: list[str] = field(default_factory=list)       # arquivo (sem CNPJ no nome nem senha no cofre)
    ilegiveis: list[str] = field(default_factory=list)       # "arquivo: motivo"
    sem_empresa: list[str] = field(default_factory=list)     # certificados de CNPJ que não é cliente ativo
    empresas_com_certificado: int = 0
    empresas_sem_certificado: int = 0
    senhas_atualizadas: int = 0                              # senhas novas ou trocadas no cofre
    mudancas: list[dict] = field(default_factory=list)       # uma linha por empresa ativa (relatório)

    def contagem(self, mudanca: str) -> int:
        return sum(1 for m in self.mudancas if m["mudanca"] == mudanca)


# rótulos da coluna "mudança" do relatório
NOVO = "certificado novo"
PRIMEIRO = "primeiro certificado"
PERDEU = "ficou sem certificado"
IGUAL = "sem mudança"
SEM = "sem certificado"


def cnpj_no_nome(arquivo: Path) -> str | None:
    """Primeiro CNPJ válido no nome do arquivo (com ou sem pontuação)."""
    for m in _CNPJ_NO_TEXTO.finditer(arquivo.stem):
        cnpj = so_digitos(m.group(1))
        if cnpj_valido(cnpj):
            return cnpj
    return None


def _cnpj_do_certificado(cert) -> str:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        for outro in san.get_values_for_type(x509.OtherName):
            if outro.type_id.dotted_string == OID_CNPJ_ICP:
                cnpj = re.search(rb"\d{14}", outro.value)
                if cnpj and cnpj_valido(cnpj.group().decode()):
                    return cnpj.group().decode()
    except x509.ExtensionNotFound:
        pass
    for attr in cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME):  # "RAZAO SOCIAL:12345678000190"
        m = re.search(r"(\d{14})\s*$", str(attr.value))
        if m and cnpj_valido(m.group(1)):
            return m.group(1)
    return ""


def ler_certificado(arquivo: Path, senha: Segredo) -> InfoCertificado:
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID
    try:
        dados = arquivo.read_bytes()
    except OSError as e:
        raise CertificadoIlegivel(f"não consegui ler o arquivo ({e.strerror or type(e).__name__})") from None
    try:
        _, cert, _ = pkcs12.load_key_and_certificates(dados, senha.revelar().encode())
    except ValueError:
        raise CertificadoIlegivel("senha incorreta ou arquivo .pfx inválido") from None
    if cert is None:
        raise CertificadoIlegivel("o arquivo não contém certificado")
    titular = _cnpj_do_certificado(cert)
    if not titular:
        raise CertificadoIlegivel("certificado sem CNPJ (e-CPF não serve para o robô)")
    cns = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    nome = str(cns[0].value).split(":")[0] if cns else ""
    venc = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
    return InfoCertificado(arquivo, titular, nome, venc.date())


def listar_arquivos(pasta: Path) -> list[Path]:
    if not pasta.is_dir():
        raise CertificadoIlegivel(f"pasta de certificados não encontrada: {pasta}. Confira CERT_PASTA e se a "
                                  "unidade de rede está conectada.")
    return sorted(p for p in pasta.rglob("*") if p.suffix.lower() in EXTENSOES and p.is_file())


def escolher(empresa: Empresa, certificados: list[InfoCertificado]) -> InfoCertificado | None:
    """Mesmo CNPJ primeiro; senão a mesma raiz (matriz/filial). Não vencido antes de vencido; depois o
    de validade mais longa."""
    def melhor(cands):
        return max(cands, key=lambda c: (not c.vencido, c.validade)) if cands else None
    return (melhor([c for c in certificados if c.titular == empresa.cnpj])
            or melhor([c for c in certificados if raiz(c.titular) == raiz(empresa.cnpj)]))


class CertificadosService:
    def __init__(self, destino: DestinoBanco, cofre: Cofre):
        self.destino = destino
        self.cofre = cofre

    def _abrir(self, arq: Path, dono: str | None, pasta: Path) -> tuple[InfoCertificado, Segredo] | str:
        """(certificado, senha que abriu) ou o motivo de não ter aberto."""
        tentativas: list[Segredo] = []
        guardada = self.cofre.obter(dono) if dono else None
        if guardada is not None:
            tentativas.append(guardada)
        tentativas += [Segredo(c) for c in senhas_candidatas(arq, pasta)
                       if guardada is None or c != guardada.revelar()]
        if not tentativas:
            return "sem_senha"
        ultimo_erro = ""
        for senha in tentativas:
            try:
                return ler_certificado(arq, senha), senha
            except CertificadoIlegivel as e:
                ultimo_erro = str(e)
                if "senha incorreta" not in ultimo_erro:
                    break  # arquivo ilegível ou sem CNPJ: outra senha não resolve
        return ultimo_erro

    def varrer(self, pasta: Path, extras: list[Path] = ()) -> ResultadoVarredura:
        res = ResultadoVarredura()
        with conectar(self.destino) as con:
            repo = EmpresasRepository(con)
            empresas = repo.listar(so_ativas=True)
            conhecidos = repo.titulares_conhecidos()

            arquivos = listar_arquivos(pasta) + [p for p in extras if p.is_file()]
            res.arquivos = len(arquivos)
            senhas: dict[str, Segredo] = {}  # arquivo -> senha que abriu (só em memória)
            for arq in arquivos:
                aberto = self._abrir(arq, conhecidos.get(str(arq)) or cnpj_no_nome(arq), pasta)
                if aberto == "sem_senha":
                    res.sem_senha.append(str(arq))
                elif isinstance(aberto, str):
                    res.ilegiveis.append(f"{arq.name}: {aberto}")
                else:
                    info, senha = aberto
                    res.lidos.append(info)
                    senhas[str(arq)] = senha
                    repo.lembrar_certificado(str(arq), info.titular, info.nome, info.validade.isoformat())

            # um certificado por CNPJ titular: o melhor; a senha dele é a que fica no cofre
            melhores: dict[str, InfoCertificado] = {}
            for c in res.lidos:
                atual = melhores.get(c.titular)
                if atual is None or (not c.vencido, c.validade) > (not atual.vencido, atual.validade):
                    melhores[c.titular] = c
            for titular, c in melhores.items():
                senha = senhas[str(c.arquivo)]
                guardada = self.cofre.obter(titular)
                if guardada is None or guardada.revelar() != senha.revelar():
                    self.cofre.guardar(titular, senha.revelar())
                    res.senhas_atualizadas += 1

            raizes = {raiz(e.cnpj) for e in empresas}
            res.sem_empresa = [f"{c.arquivo.name} ({c.titular})" for c in res.lidos if raiz(c.titular) not in raizes]
            for emp in empresas:
                cert = escolher(emp, list(melhores.values()))
                novo = (str(cert.arquivo), cert.validade.isoformat()) if cert else ("", "")
                if cert:
                    repo.definir_certificado(emp.cnpj, novo[0], cert.titular, novo[1])
                    res.empresas_com_certificado += 1
                else:
                    repo.limpar_certificado(emp.cnpj)
                    res.empresas_sem_certificado += 1
                antes = (emp.cert_arquivo, emp.cert_validade)
                mudanca = (IGUAL if antes == novo else NOVO if antes[0] and cert else PRIMEIRO if cert
                           else PERDEU if antes[0] else SEM)
                res.mudancas.append({
                    "cnpj": emp.cnpj, "razao_social": emp.razao_social, "codigo_dominio": emp.codigo_dominio,
                    "mudanca": mudanca, "arquivo": novo[0], "validade": novo[1], "validade_anterior": antes[1],
                    "titular": cert.titular if cert else "", "vencido": bool(cert and cert.vencido)})
        return res

    def credenciais(self, empresa: Empresa) -> tuple[Path, Segredo]:
        """(arquivo, senha) para o robô consultar o ADN por esta empresa."""
        if not empresa.cert_arquivo or not empresa.cert_titular:
            raise CertificadoIlegivel("empresa sem certificado na pasta de rede (rode: nfse-empresas certificados)")
        if empresa.situacao_certificado == "vencido":
            raise CertificadoIlegivel(f"certificado vencido em {empresa.cert_validade}")
        senha = self.cofre.obter(empresa.cert_titular)
        if senha is None:
            raise CertificadoIlegivel(f"senha do certificado {empresa.cert_titular} não está no cofre")
        return Path(empresa.cert_arquivo), senha

    def importar_senhas(self, planilha: Path, pasta: Path | None) -> tuple[int, list[str]]:
        """CSV com as colunas senha e (arquivo ou cnpj). Com arquivo, abre o certificado para descobrir o CNPJ
        titular e confere a senha antes de guardar. Devolve (guardadas, avisos)."""
        guardadas, avisos = 0, []
        lidos: list[InfoCertificado] = []
        for n, linha in enumerate(ler_planilha(planilha), start=2):
            senha = linha.get("senha", "")
            if not senha:
                avisos.append(f"linha {n}: sem senha")
                continue
            if linha.get("arquivo"):
                arq = Path(linha["arquivo"])
                if not arq.is_absolute() and pasta:
                    arq = pasta / arq
                try:
                    info = ler_certificado(arq, Segredo(senha))
                    lidos.append(info)
                    titular = info.titular
                except CertificadoIlegivel as e:
                    avisos.append(f"linha {n} ({arq.name}): {e}")
                    continue
            else:
                titular = so_digitos(linha.get("cnpj"))
                if not cnpj_valido(titular):
                    avisos.append(f"linha {n}: informe a coluna arquivo ou um cnpj válido")
                    continue
            self.cofre.guardar(titular, senha)
            guardadas += 1
        if lidos:  # a próxima varredura já sabe de quem é cada arquivo, mesmo sem CNPJ no nome
            with conectar(self.destino) as con:
                repo = EmpresasRepository(con)
                for c in lidos:
                    repo.lembrar_certificado(str(c.arquivo), c.titular, c.nome, c.validade.isoformat())
        return guardadas, avisos


def escrever_relatorio(res: ResultadoVarredura, arquivo: Path) -> Path:
    """CSV (; e UTF-8 com BOM, abre direto no Excel) com a situação do certificado de cada empresa ativa e o
    que mudou nesta varredura, mais os arquivos que não abriram. Nunca contém senhas."""
    import csv
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    with arquivo.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["CNPJ", "Razão social", "Código Domínio", "Mudança", "Válido até", "Validade anterior",
                    "Vencido", "CNPJ do certificado", "Arquivo"])
        for m in sorted(res.mudancas, key=lambda m: (m["mudanca"] == IGUAL, m["razao_social"])):
            w.writerow([m["cnpj"], m["razao_social"], m["codigo_dominio"], m["mudanca"], m["validade"],
                        m["validade_anterior"], "sim" if m["vencido"] else "", m["titular"], m["arquivo"]])
        for a in res.sem_senha:
            w.writerow(["", "", "", "arquivo sem senha encontrada na pasta", "", "", "", "", a])
        for a in res.ilegiveis:
            w.writerow(["", "", "", "arquivo não abriu", "", "", "", "", a])
    return arquivo

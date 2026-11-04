"""Identidade visual do escritório: lida de assets/marca/ (escritorio.json + logo .png).

Tudo que vem do JSON é validado antes de ir para a tela: cores só no formato #RRGGBB e site só http(s).
Se o JSON faltar ou estiver inválido, o dashboard abre com as cores padrão e mostra um aviso.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from nfse.config.settings import RAIZ_PROJETO

PASTA_PADRAO = RAIZ_PROJETO / "assets" / "marca"
ARQUIVO_JSON = "escritorio.json"
ARQUIVO_LOGO = "logo.png"

_COR_HEX = re.compile(r"#[0-9A-Fa-f]{6}")
PRIMARIA_PADRAO = "#011F48"
DESTAQUE_PADRAO = "#D6A84B"
AZUL_CLARO_ESCURO = "#7BA7F0"  # segunda série do gráfico no modo escuro (o azul-marinho sumiria)


@dataclass(frozen=True)
class Marca:
    escritorio: str = "Dashboard NFS-e"
    cor_primaria: str = PRIMARIA_PADRAO
    cor_destaque: str = DESTAQUE_PADRAO
    light_primary: str = PRIMARIA_PADRAO   # cor de ação (botões, filtros) no modo claro
    dark_primary: str = DESTAQUE_PADRAO    # no modo escuro; o azul-marinho sumiria no fundo escuro
    site: str = ""
    assinatura: str = ""
    logo: Path | None = None
    avisos: tuple[str, ...] = field(default=(), compare=False)

    def suave(self, proporcao: float = 0.93) -> str:
        """Cor primária misturada com branco (fundo da barra lateral)."""
        return misturar(self.cor_primaria, "#FFFFFF", proporcao)

    def paleta(self, modo: str) -> dict[str, str]:
        """Cores do tema do Streamlit para 'light' ou 'dark'."""
        if modo == "dark":
            return {
                "primaryColor": self.dark_primary,
                "backgroundColor": misturar(self.cor_primaria, "#000000", 0.5),
                "secondaryBackgroundColor": misturar(self.cor_primaria, "#FFFFFF", 0.06),
                "textColor": "#EEF2F7",
            }
        return {
            "primaryColor": self.light_primary,
            "backgroundColor": "#F7F8FA",
            "secondaryBackgroundColor": self.suave(),
            "textColor": misturar(self.cor_primaria, "#FFFFFF", 0.08),
        }

    def opcoes_streamlit(self) -> list[str]:
        """Parâmetros --theme.light.* e --theme.dark.* para o 'streamlit run'.

        Com os dois temas definidos, o app segue o modo do sistema e o usuário pode trocar
        em ⋮ > Settings. Não usar --theme.base, que travaria um dos modos.
        """
        return [f"--theme.{modo}.{chave}={valor}"
                for modo in ("light", "dark") for chave, valor in self.paleta(modo).items()]

    def cores_grafico(self, modo: str | None) -> tuple[str, str]:
        """(emitidas, recebidas) com contraste no fundo do modo atual."""
        if modo == "dark":
            return self.dark_primary, AZUL_CLARO_ESCURO
        return self.light_primary, self.cor_destaque

    def cartao_escuro(self) -> str:
        """Fundo dos cartões no modo escuro: um degrau acima do fundo da página."""
        return misturar(self.cor_primaria, "#FFFFFF", 0.1)


def misturar(cor: str, outra: str, proporcao: float) -> str:
    a = [int(cor[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(outra[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * proporcao):02X}" for x, y in zip(a, b))


def _cor(dados: dict, chave: str, padrao: str, avisos: list[str]) -> str:
    valor = dados.get(chave)
    if valor is None:
        return padrao
    if isinstance(valor, str) and _COR_HEX.fullmatch(valor.strip()):
        return valor.strip().upper()
    avisos.append(f"{chave} inválida no JSON (use o formato #RRGGBB). Usando {padrao}.")
    return padrao


def _site(valor) -> str:
    if not isinstance(valor, str) or not valor.strip():
        return ""
    valor = valor.strip()
    if re.fullmatch(r"[\w.-]+\.[a-z]{2,}(/\S*)?", valor, re.I):
        valor = "https://" + valor
    return valor if re.fullmatch(r"https?://[^\s\"'<>]+", valor) else ""


def _texto(valor, padrao: str = "") -> str:
    return valor.strip() if isinstance(valor, str) and valor.strip() else padrao


def carregar_marca(pasta: Path = PASTA_PADRAO) -> Marca:
    avisos: list[str] = []
    dados: dict = {}

    arq = pasta / ARQUIVO_JSON
    if not arq.is_file():
        outros = sorted(pasta.glob("*.json")) if pasta.is_dir() else []
        arq = outros[0] if outros else None
    if arq is None:
        avisos.append(f"Não encontrei {ARQUIVO_JSON} em {pasta}. Usando a identidade padrão.")
    else:
        try:
            lido = json.loads(arq.read_text(encoding="utf-8-sig"))
            if isinstance(lido, dict):
                dados = lido
            else:
                avisos.append(f"{arq.name} precisa ser um objeto {{ ... }}. Usando a identidade padrão.")
        except json.JSONDecodeError as e:
            avisos.append(f"{arq.name} não é um JSON válido (linha {e.lineno}, coluna {e.colno}). "
                          "Atenção: JSON não aceita comentários com #. Usando a identidade padrão.")

    logo = pasta / ARQUIVO_LOGO
    if not logo.is_file():
        pngs = sorted(pasta.glob("*.png")) if pasta.is_dir() else []
        logo = pngs[0] if pngs else None
        if logo is None:
            avisos.append(f"Nenhuma logo .png em {pasta}.")

    primaria = _cor(dados, "corPrimaria", PRIMARIA_PADRAO, avisos)
    destaque = _cor(dados, "corDestaque", DESTAQUE_PADRAO, avisos)
    return Marca(
        escritorio=_texto(dados.get("escritorio"), Marca.escritorio),
        cor_primaria=primaria,
        cor_destaque=destaque,
        light_primary=_cor(dados, "lightPrimary", primaria, avisos),
        dark_primary=_cor(dados, "darkPrimary", destaque, avisos),
        site=_site(dados.get("site")),
        assinatura=_texto(dados.get("assinatura")),
        logo=logo,
        avisos=tuple(avisos),
    )

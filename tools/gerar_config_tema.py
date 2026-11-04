"""Gera .streamlit/config.toml com os temas claro e escuro do escritório (a partir de assets/marca/).

O Streamlit Community Cloud não usa o comando nfse-dashboard, que passa as cores na linha de
comando; lá o tema precisa estar neste arquivo. Rode de novo sempre que mudar o escritorio.json:

    python tools/gerar_config_tema.py
"""
import sys

from nfse.config.settings import RAIZ_PROJETO
from nfse.ui.dashboard.marca import carregar_marca


def gerar() -> str:
    marca = carregar_marca()
    for aviso in marca.avisos:
        print(f"AVISO: {aviso}")
    linhas = [
        "# Gerado por tools/gerar_config_tema.py a partir de assets/marca/. Não edite à mão.",
        "",
        "[client]",
        'toolbarMode = "viewer"  # esconde o menu de desenvolvedor de quem só visualiza',
        "",
        "[browser]",
        "gatherUsageStats = false",
    ]
    for modo in ("light", "dark"):
        linhas += ["", f"[theme.{modo}]"]
        linhas += [f'{chave} = "{valor}"' for chave, valor in marca.paleta(modo).items()]
    return "\n".join(linhas) + "\n"


def main() -> int:
    destino = RAIZ_PROJETO / ".streamlit" / "config.toml"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(gerar(), encoding="utf-8")
    print(f"Gerado: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

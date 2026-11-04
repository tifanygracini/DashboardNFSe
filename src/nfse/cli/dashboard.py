"""Abre o dashboard no navegador, já com as cores do escritório (assets/marca/escritorio.json).

Uso:
    nfse-dashboard           (equivale a: streamlit run src/nfse/ui/dashboard/app.py)
"""
import sys
from pathlib import Path

from nfse.ui.dashboard.marca import carregar_marca

APP = Path(__file__).resolve().parents[1] / "ui" / "dashboard" / "app.py"


def main() -> int:
    from streamlit.web import cli as stcli

    # temas claro e escuro: o app segue o sistema, e dá para trocar em ⋮ > Settings
    sys.argv = ["streamlit", "run", str(APP), *carregar_marca().opcoes_streamlit(), *sys.argv[1:]]
    return stcli.main()


if __name__ == "__main__":
    sys.exit(main())

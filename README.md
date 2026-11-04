# NFS-e → Dashboard

Baixa as NFS-e da empresa no ADN (Ambiente de Dados Nacional), grava num SQLite e mostra num dashboard.

## Instalação (Windows, PowerShell, na raiz do projeto)
```powershell
python -m venv .venv
.venv\Scripts\pip install -e .            # ou: pip install -e ".[keyring,dev]"
copy .env.example .env                    # e preencha
```

## Uso
| Comando | O que faz |
|---|---|
| `nfse-baixar` | baixa do ADN para `data/notas/AAAA-MM/` e importa as novas |
| `nfse-importar` | (re)importa todos os XMLs de `data/notas/` para `data/notas.db` |
| `nfse-dashboard` | abre o dashboard no navegador |
| `.\scripts\agendar.ps1` | agenda o `nfse-baixar` para todo dia às 08:00 |

## Treinar sem certificado
```powershell
python tools\fake_adn.py --xmls tests\fixtures\xml
nfse-baixar --base-url http://127.0.0.1:8787 --sem-certificado --forcar
```
`tools\gerar_notas_exemplo.py <pasta>` gera outro lote de XMLs fictícios.

## Testes
```powershell
pip install -e ".[dev]"
pytest
```

Estrutura e regras de dependência entre camadas: `docs/arquitetura.md`.

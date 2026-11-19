# NFS-e → Dashboard

Baixa as NFS-e de **todas as empresas clientes do escritório** no ADN (Ambiente de Dados Nacional), com o certificado A1 de cada uma, grava no banco e mostra num dashboard com filtros por regime, razão social, CNPJ e código do Domínio. O cadastro das empresas vem do Acessórias. Detalhes: `docs/multiempresa.md`.

## Instalação (Windows, PowerShell, na raiz do projeto)
```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[keyring]"  # ou: pip install -e ".[keyring,dev]"
copy .env.example .env                    # e preencha
```

## Uso
| Comando | O que faz |
|---|---|
| `nfse-empresas sincronizar` | cadastro das empresas ativas do Acessórias |
| `nfse-empresas certificados` | liga cada empresa ao seu certificado A1 da pasta de rede (`CERT_PASTA`) |
| `nfse-empresas senha CNPJ` / `senhas planilha.csv` | guarda senhas de certificados no Gerenciador de Credenciais do Windows |
| `nfse-baixar` | baixa do ADN para `data/notas/<cnpj>/AAAA-MM/` e importa as novas, de todas as empresas |
| `nfse-importar` | (re)importa os XMLs de `data/notas/<cnpj>/` para o banco |
| `.\scripts\agendar.ps1` | agenda o robô completo (Acessórias + certificados + ADN) nos dias úteis |

## Treinar sem certificado
Com `CNPJ_EMPRESA=11223344000186` no `.env` (a empresa entra no cadastro sozinha):
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

## Dashboard web (FastAPI, login do Portal Informe)
`uvicorn nfse.web.asgi:app` abre o painel. Como rodar e publicar no Azure: `docs/web.md`.

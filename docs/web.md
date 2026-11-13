# Dashboard web (FastAPI) com o login do Portal Informe

A interface web (`src/nfse/web/`) substitui a interface Streamlit (`src/nfse/ui/dashboard/`).

Ela usa os mesmos serviços: os totais, rankings e agregações continuam em `services/relatorios_service.py`. Por isso os números são os mesmos nas duas interfaces. O teste `test_web.py` confere o mesmo total de notas que o `test_dashboard.py` conferia no Streamlit.

As duas interfaces convivem durante o piloto. O Streamlit Cloud continua lendo o mesmo banco até a virada.

```
navegador ──► nfse.informecontabil.com (Azure, FastAPI)
                 │  cookie informe_sessao (criado no portal.informecontabil.com)
                 ├─► iam.sessao_valida / iam.permissao_efetiva   (quem é e o que pode)
                 └─► nfse.notas                                    (papel nfse_leitura, só leitura)
robô no escritório ─► nfse.notas (papel nfse_robo)  — sem mudança
```

## O que mudou em relação ao Streamlit

| Streamlit | Web |
|---|---|
| Sem login próprio (lista de convidados do Streamlit Cloud) | Login do portal com código de verificação. A tela exige `nfse:ver` |
| Seleção múltipla de competências | Intervalo **de / até** (padrão: todo o período) |
| Tipo (emitidas/recebidas) | Igual |
| Busca na tabela | Igual. A busca filtra só a tabela, como antes |
| Download CSV embutido na tabela do Streamlit | **Exportar planilha (CSV)** com `;` e vírgula decimal (abre direto no Excel). Exige `nfse:exportar` e fica registrado no histórico de acessos do portal |
| Tabela com todas as colunas | Tela com as colunas principais, 50 notas por página. O CSV traz todas as colunas |
| Gráfico Plotly | O mesmo gráfico, servido localmente (`/_vendor/plotly.min.js`), sem CDN. Acompanha o tema claro/escuro do navegador |
| Cache de 60 s | Igual |

## Rodar no computador

Pré-requisitos:
- o portal rodando em `http://localhost:8000` (repositório informe-portal);
- `informe-auth` instalado no mesmo ambiente.

```powershell
pip install -e ..\..\caminho\informe-portal\informe-auth -e ".[dev]"
$env:NFSE_DATABASE_URL = ""          # vazio = SQLite data/notas.db (não use a URL do robô)
$env:DATABASE_URL = "postgresql://postgres:dev@localhost:55432/portal_dev"   # banco do portal (schema iam)
$env:SESSION_SECRET = "<32+ caracteres aleatórios>"
$env:PORTAL_URL = "http://localhost:8000"
$env:COOKIE_SECURE = "false"
uvicorn nfse.web.asgi:app --port 8001
```

No portal, em **Administração → Sistemas**, aponte o endereço do NFS-e para `http://localhost:8001`.

Em `localhost`, o cookie vale para todas as portas, então o login feito no portal abre o NFS-e direto.

## Azure App Service (`informe-nfse`, plano B2 compartilhado)

| App Setting | Valor |
|---|---|
| `NFSE_DATABASE_URL` | URL do papel **`nfse_leitura`** (Session pooler do Supabase), via Key Vault |
| `CNPJ_EMPRESA` | CNPJ da empresa |
| `SESSION_SECRET` | aleatório, via Key Vault (pode ser diferente do portal) |
| `PORTAL_URL` | `https://portal.informecontabil.com` |
| `INFORME_COOKIE_DOMAIN` | `.informecontabil.com` |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` |

O `DATABASE_URL` não precisa ser definido: sem ele, o app usa o `NFSE_DATABASE_URL`. O papel `nfse_leitura` lê o schema `iam` desde que a migração 001 do portal tenha rodado depois de ele existir. Se não tiver rodado, aplique os GRANTs descritos no README do portal.

**Comando de inicialização:**
```
python -m uvicorn nfse.web.asgi:app --host 0.0.0.0 --port 8000 --workers 2 --proxy-headers --forwarded-allow-ips "*"
```

**Health check:** `/saude`.

**Deploy:** `.github/workflows/web.yml`. Ele precisa de:
- variável `INFORME_PORTAL_REPO`;
- segredos `INFORME_PORTAL_TOKEN` (leitura do repositório do portal), `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` e `AZURE_SUBSCRIPTION_ID`.

O workflow copia o `informe-auth` para `vendor/` e usa o `requirements-web.txt` como `requirements.txt` do App Service. O `requirements.txt` do repositório continua sendo o do Streamlit Cloud.

## Depois da virada
- Remover `src/nfse/ui/dashboard/`, `cli/dashboard.py`, `.streamlit/`, o `tests/integration/test_dashboard.py` e a dependência `streamlit` do `pyproject.toml`. O `formatters.py` e o `marca.py` são usados pela interface web: mova-os para `nfse/web/` antes de apagar a pasta.
- Apagar o app no Streamlit Cloud.

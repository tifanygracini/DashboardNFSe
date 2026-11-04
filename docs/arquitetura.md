# Arquitetura

```
ui/dashboard  cli
      \       /
      services            download_service · import_service · relatorios_service
     /    |    \
clients  data  parsers    adn/client · sqlite, xml_storage, estado · nfse/evento/codec
     \    |    /
      domain              Nota, TipoNota, StatusNota, regras
config  (usada por cli/ui para montar as peças; a senha só chega ao clients)
```

| Camada | Pode importar | Não pode |
|---|---|---|
| `domain` | nada do projeto | I/O, pandas, requests |
| `parsers` | `domain` | banco, rede |
| `clients/adn` | `config.Segredo` | banco, arquivos de notas |
| `data` | `domain` | rede, pandas |
| `services` | `clients`, `data`, `parsers`, `domain` | streamlit, print |
| `cli`, `ui` | tudo acima + `config` | regra de negócio |

## Fluxos
- **Baixar**: `cli/baixar` → `DownloadService` → `AdnClient.consultar(nsu)` → `XmlStorage.gravar` → `EstadoRepository.gravar` → (se houver novos) `cli/importar`.
- **Importar**: `ImportService` → `XmlStorage.listar` → `parsers` → `NotasRepository` (INSERT OR IGNORE pela chave) → cancelamentos.
- **Dashboard**: `relatorios_service.carregar_notas` → `recortar` → `totais`/`mensal`/`ranking` → componentes Streamlit.

## Configuração
`nfse.config.get_settings()` lê variáveis de ambiente e `.env` (nessa prioridade), valida o CNPJ e
resolve caminhos relativos a partir da raiz do projeto. `.env` alternativo: `NFSE_ENV_FILE=...`.

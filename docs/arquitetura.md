# Arquitetura

```
ui/dashboard  cli
      \       /
      services            robo · download · import · relatorios · certificados · sincronizar · migracao
     /    |    \
clients  data  parsers    adn/client, acessorias · banco, empresas, xml_storage · nfse/evento/codec
     \    |    /
      domain              Nota, TipoNota, StatusNota, regras
config  (usada por cli/ui para montar as peças; a senha só chega ao clients)
```

| Camada | Pode importar | Não pode |
|---|---|---|
| `domain` | nada do projeto | I/O, pandas, requests |
| `config.cofre` | keyring | banco (as senhas dos certificados nunca vão para o banco) |
| `parsers` | `domain` | banco, rede |
| `clients/adn` | `config.Segredo` | banco, arquivos de notas |
| `data` | `domain` | rede, pandas |
| `services` | `clients`, `data`, `parsers`, `domain` | streamlit, print |
| `cli`, `ui` | tudo acima + `config` | regra de negócio |

## Fluxos
- **Cadastro**: `cli/empresas sincronizar` → `AcessoriasClient.listar_ativas` → `mapear` (regime normalizado) → `EmpresasRepository`.
- **Certificados**: `cli/empresas certificados` → `CertificadosService.varrer` → cofre (senha) → `ler_certificado` (CNPJ e validade) → empresa ↔ certificado (mesmo CNPJ ou mesma raiz).
- **Baixar**: `cli/baixar` → `RoboService` → por empresa, em paralelo: `DownloadService` (`AdnClient` com o certificado dela, `EstadoBanco`, `XmlStorage(<pasta>/<cnpj>)`) → depois, uma por vez, `ImportService`.
- **Importar**: `ImportService(empresa)` → `XmlStorage.listar` → `parsers` → `NotasRepository(empresa)` (ignora (empresa, chave) repetida) → cancelamentos.
- **Dashboard web**: carteira = `carregar_empresas` + `carregar_resumo` (agregado no banco) → `carteira`; empresa = `carregar_notas(cnpj)` → `recortar` → `totais`/`mensal`/`ranking`.

Visão geral da versão multiempresa: `docs/multiempresa.md`.

## Configuração
`nfse.config.get_settings()` lê variáveis de ambiente e `.env` (nessa prioridade), valida o CNPJ e
resolve caminhos relativos a partir da raiz do projeto. `.env` alternativo: `NFSE_ENV_FILE=...`.

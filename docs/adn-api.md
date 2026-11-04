# API do ADN (Ambiente de Dados Nacional) — distribuição de DF-e da NFS-e

> ATENÇÃO: este arquivo foi reconstruído a partir do que consta na apostila. O `adn-api.md`
> original do professor não veio no anexo. Se você tiver o original, SUBSTITUA este arquivo por ele.

## Endereços
- Produção: `https://adn.nfse.gov.br`
- Produção restrita: `https://adn.producaorestrita.nfse.gov.br`

## Autenticação
mTLS com certificado digital A1 (.pfx + senha). Não há usuário e senha.
O CNPJ raiz do certificado deve ser o mesmo do CNPJ consultado.

## Consulta
`GET {base}/contribuintes/DFe/{nsu}?cnpjConsulta={cnpj}`  (atenção: "contribuinte**s**")
- Devolve documentos com NSU maior que `{nsu}`, até 50 por chamada.
- Para continuar, repetir com o maior NSU do lote anterior.
- Quando não há mais nada: HTTP 404 com JSON `StatusProcessamento = NENHUM_DOCUMENTO_LOCALIZADO` (não é erro).
- Depois de esgotar a fila, esperar 1 hora antes de consultar de novo.

## Resposta (200)
Campos usados pelo robô:
- `StatusProcessamento`
- `LoteDFe[]`: `NSU`, `ChaveAcesso`, `TipoDocumento` (`NFSE` ou `EVENTO`), `TipoEvento` (em eventos), `ArquivoXml`, `DataHoraGeracao`
- `ArquivoXml`: XML compactado com gzip e codificado em base64 (às vezes base64 duplo)

## Erros
| Código | Significado |
|---|---|
| Falha de TLS | sem certificado, senha errada, certificado vencido ou A3 |
| 403 | certificado de outro CNPJ raiz |
| 404 sem JSON | URL errada (`/contribuinte/` sem o "s") |
| 400 com `E2242` | certificado de pessoa física (e-CPF): consultar sem o parâmetro de CNPJ |
| 429 | limite de chamadas: esperar e tentar de novo |
| 5xx | instabilidade do ADN: tentar de novo mais tarde |

## Pontos do XML da NFS-e (padrão nacional)
- `infNFSe/@Id` = `NFS` + chave de 50 dígitos
- `infNFSe/valores`: `vBC`, `pAliqAplic`, `vISSQN`, `vTotalRet`, `vLiq`
- `infNFSe/DPS/infDPS`: `dhEmi`, `prest/CNPJ`, `toma/CNPJ`, `serv/cServ/cTribNac`, `serv/cServ/xDescServ`
- `infDPS/valores`: `vServPrest/vServ`, `vDescCondIncond/vDescIncond`, `trib/tribMun/tpRetISSQN`
- Evento de cancelamento: elemento `e101101`; `chNFSe` aponta para a nota; data em `dhEvento`

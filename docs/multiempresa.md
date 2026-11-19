# NFS-e de todas as empresas do escritório

A partir da versão 0.4, o robô e o dashboard trabalham com **todas as empresas clientes**, e não só com a Informe.

```
Acessórias (API) ──► nfse-empresas sincronizar ──► nfse.empresas   razão social, fantasia, CNPJ, regime, código Domínio
pasta de rede     ──► nfse-empresas certificados ─► nfse.empresas   certificado de cada empresa (caminho, titular, validade)
  \\servidor\certificados\*.pfx                     nfse.certificados (de quem é cada arquivo)
Gerenciador de Credenciais do Windows: senha de cada certificado (nunca no banco nem no .env)

ADN ──► nfse-baixar (paralelo, uma consulta por empresa) ──► data/notas/<cnpj>/AAAA-MM/*.xml ──► nfse.notas
                                                                                     (empresa_cnpj, chave)
dashboard web:  /                 todas as empresas, com filtros
                /empresa/<cnpj>   o dashboard de sempre, de uma empresa
```

## O que muda no banco

| Tabela | Conteúdo |
|---|---|
| `notas` | ganhou `empresa_cnpj`. A chave primária passou a ser `(empresa_cnpj, chave)`: uma nota entre dois clientes do escritório é **emitida** para um e **recebida** para o outro |
| `empresas` (nova) | cadastro vindo do Acessórias + certificado + estado do robô no ADN (último NSU, última consulta, situação e mensagem da última execução) |
| `certificados` (nova) | caminho, CNPJ titular e validade de cada certificado já aberto. Não guarda o conteúdo nem a senha |

A migração é automática na primeira execução do robô (`nfse-empresas migrar`): as notas que já estão no banco passam a ser da empresa do `CNPJ_EMPRESA`.
O estado do robô deixou o `data/adn_estado.json` e passou para a tabela `empresas` (uma linha por empresa). A migração copia o último NSU.

No Supabase, o papel `nfse_robo` é dono das tabelas, e o `nfse_leitura` (dashboard) só lê. As tabelas novas recebem o `SELECT` sozinhas, pelos privilégios padrão do `sql/setup_postgres.sql`.

## Configuração (.env do computador do robô)

| Variável | Para quê |
|---|---|
| `CERT_PASTA` | pasta de rede com os certificados A1 (`.pfx`/`.p12`), com subpastas. Ex.: `\\servidor\certificados` ou `S:\Certificados` |
| `ACESSORIAS_API_TOKEN` | token da API do Acessórias (o mesmo da Auditoria de Folha e do Alerta de Pendências) |
| `ACESSORIAS_CAMPO_DOMINIO` | nome do campo do Acessórias que tem o código da empresa no Domínio (veja abaixo) |
| `NFSE_PARALELO` | quantas empresas o robô consulta no ADN ao mesmo tempo (padrão 4, máximo 16) |
| `CNPJ_EMPRESA` | agora é opcional: só serve para a migração (dono das notas antigas) |
| `CERT_PFX` / `CERT_SENHA` | continuam valendo para a empresa do `CNPJ_EMPRESA` durante a transição |

### Código do Domínio

A API do Acessórias não traz o código do Domínio num campo padrão. Há dois caminhos:
- se o escritório guarda o código num campo do Acessórias, informe o nome dele em `ACESSORIAS_CAMPO_DOMINIO` (use `ID` se o código do Acessórias for o mesmo do Domínio);
- senão, importe uma planilha CSV com as colunas `cnpj;codigo`: `nfse-empresas codigos codigos.csv` (exportada do Domínio, por exemplo).
A sincronização nunca apaga um código que já está gravado.

### Senhas dos certificados

Os certificados vencem e são trocados com frequência. Para ninguém precisar recadastrar senha a cada troca, o robô **coleta as senhas da própria pasta de rede**. Em cada subpasta, a senha pode estar anotada de qualquer um destes jeitos:

| Onde | Exemplo |
|---|---|
| no nome do arquivo | `EMPRESA X SENHA 123456.pfx` |
| num `.txt` ao lado do certificado | `senha.txt` contendo `123456` ou `Senha: 123456` |
| no nome de um `.txt` | `SENHA 123456.txt` |
| no nome da subpasta | `EMPRESA X - senha 123456\certificado.pfx` |

Cada senha encontrada só é aceita se **abrir o certificado**. Uma anotação errada não estraga nada: o arquivo aparece no relatório como "não abriu". Para cada empresa, fica o certificado válido de validade mais longa, e a senha dele vai para o **Gerenciador de Credenciais do Windows** (serviço `nfse-dashboard`, uma senha por CNPJ). As senhas nunca vão para o banco, para o log nem para o relatório.

Quando um certificado vence e o novo é colocado na subpasta da empresa com a senha anotada, o robô passa a usar o novo sozinho na varredura seguinte. A varredura roda:
- **todo dia útil**, dentro do robô (`scripts\rodar-robo.ps1`), para que um certificado novo entre em uso no mesmo dia;
- **uma vez por mês** (tarefa `nfse-certificados-mensal`, criada pelo `scripts\agendar.ps1`, dia 1 às 06:30 por padrão), com o relatório `logs\certificados-AAAA-MM.csv`: para cada empresa, se ganhou certificado novo, se ficou sem, a validade atual e a anterior; e no fim, os arquivos sem senha encontrada e os que não abriram.

Se a senha não estiver anotada na pasta, continuam valendo os jeitos manuais:
- uma de cada vez: `nfse-empresas senha 12345678000190` (pergunta a senha sem mostrar na tela);
- várias de uma vez: CSV com as colunas `arquivo;senha` (caminho relativo à `CERT_PASTA`) ou `cnpj;senha`, e `nfse-empresas senhas senhas.csv`. **Apague o CSV depois.**

Quem manda é o certificado: o CNPJ titular e a validade são lidos de dentro dele, não do nome do arquivo. Uma filial usa o certificado da própria filial ou, se não houver, o da matriz (mesma raiz de 8 dígitos), como o ADN permite. Certificado de pessoa física (e-CPF) não serve.

## Comandos

| Comando | O que faz |
|---|---|
| `nfse-empresas sincronizar` | empresas ativas do Acessórias → banco. Quem sai da lista de ativas é marcado como inativa e o robô para de consultar |
| `nfse-empresas certificados` | varre todas as subpastas da `CERT_PASTA`, coleta as senhas anotadas, liga cada empresa ao seu certificado válido e lista o que mudou ou está pendente |
| `nfse-empresas certificados --relatorio arquivo.csv` | o mesmo, gravando o relatório em CSV (é o que a tarefa mensal roda) |
| `nfse-empresas listar --pendencias` | empresas com certificado ausente, vencido ou vencendo em 30 dias |
| `nfse-baixar` | ADN de todas as empresas ativas com certificado. Um erro numa empresa não para as outras |
| `nfse-baixar --empresa 12345678000190` | só uma empresa (pode repetir) |
| `nfse-importar [--empresa ...]` | reimporta os XMLs da pasta de cada empresa |
| `nfse-empresas migrar` | uma vez, na passagem da versão de uma empresa só |

O `scripts\rodar-robo.ps1` (chamado pela Tarefa Agendada) roda, nesta ordem: `sincronizar`, `certificados` e `nfse-baixar`.

## Dashboard

**Tela inicial — todas as empresas**
- busca por razão social, nome fantasia, CNPJ (inteiro, com máscara ou pedaço) ou código do Domínio; sem diferença de acentos e maiúsculas;
- filtro por regime tributário, em botões com a quantidade de empresas de cada um. O texto livre do Acessórias é agrupado em Simples Nacional, MEI, Lucro Presumido, Lucro Real, Imunes e isentas e Outros. O texto original aparece ao passar o mouse;
- situação: com notas no período, sem notas, certificado com pendência, robô com erro;
- período (padrão: últimos 12 meses com notas) e ordenação (faturamento, razão social, código do Domínio, nº de notas);
- totais da seleção, gráfico mensal da seleção e a tabela de empresas, com a situação do certificado e da última consulta ao ADN;
- **Exportar lista (CSV)** com a seleção (permissão `nfse:exportar`, fica no histórico do portal).

**Uma única empresa** — escolhendo uma empresa no seletor **Empresa** (que já aplica ao escolher), ou quando a busca e os filtros deixam só uma, a tela se adapta: some a tabela e os botões de regime, e entram a ficha da empresa, métricas próprias (faturamento no período e notas emitidas com a variação contra o período anterior de mesmo tamanho, ticket médio por nota, média mensal e receita dos últimos 12 meses, a base do RBT12 do Simples) e três gráficos:
- **Evolução do faturamento**: faturamento mês a mês (meses sem nota aparecem com zero) e média móvel de 3 meses;
- **Notas emitidas por mês**: quantidade de notas e, no eixo da direita, o ticket médio;
- **Faturamento acumulado no ano**: uma linha por ano (até 3), para comparar o ano atual com os anteriores.
O botão "Ver notas e rankings" abre a tela da empresa no mesmo período.

**Tela da empresa** — os mesmos três gráficos de evolução, e o dashboard que já existia (totais, gráfico, rankings, notas, exportação), com a ficha da empresa no topo: código do Domínio, regime, certificado e última consulta ao ADN (com a mensagem de erro, quando houver). O "← Todas as empresas" volta para a lista com os mesmos filtros.

## Passo a passo da virada

1. No computador do robô: `git pull`, `venv\Scripts\pip install -e ".[keyring]"`.
2. No `.env`: `CERT_PASTA`, `ACESSORIAS_API_TOKEN` e, se for o caso, `ACESSORIAS_CAMPO_DOMINIO`. Mantenha o `CNPJ_EMPRESA`.
3. `nfse-empresas migrar` (banco, XMLs e último NSU da Informe).
4. `nfse-empresas sincronizar`.
5. Senhas: confira se estão anotadas nas subpastas (nome do arquivo ou `.txt`). As que não estiverem: `nfse-empresas senhas senhas.csv` e apague o CSV.
6. `nfse-empresas certificados` e resolva o que aparecer como sem senha / não abriu.
7. Opcional: `nfse-empresas codigos codigos.csv`.
8. `nfse-baixar` à mão uma vez (a primeira carga de cada empresa baixa todo o histórico disponível no ADN, 20 lotes de 50 documentos por execução; empresas com muitas notas completam nas execuções seguintes).
9. `powershell -ExecutionPolicy Bypass -File scripts\agendar.ps1`: cria a tarefa diária do robô e a mensal dos certificados.
10. Publicar a nova versão do dashboard web (`.github/workflows/web.yml`). Ela lê o banco já migrado; antes da migração, mostra um aviso pedindo para rodar o passo 3.

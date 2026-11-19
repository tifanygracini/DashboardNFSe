# Deploy: banco PostgreSQL + robô no escritório + painel web no Azure

```
[computador do escritório]                 [nuvem]
 tarefa agendada 08:00                      PostgreSQL (Supabase, região São Paulo)
 nfse-baixar ──► ADN (com o certificado)       ▲  usuário nfse_robo (grava)
     │                                         │
     └─► nfse-importar ────────────────────────┘
                                               │  usuário nfse_leitura (só lê)
                                               ▼
                                     Painel web (Azure App Service, login do Portal Informe)
```

O certificado A1 e os XMLs **nunca saem do escritório**. Na nuvem ficam só os dados das notas,
e o painel usa um usuário que não consegue alterar nada.

---

## 1. Criar o banco (Supabase)
1. Em supabase.com, crie um projeto. **Região: South America (São Paulo)** — os dados ficam no Brasil.
   Guarde a senha do banco (é a do administrador `postgres`).
2. Em **Project Settings → Data API**, confira que o esquema `nfse` **não** está em *Exposed schemas*
   (por padrão não está). O sistema usa esse esquema justamente para ficar fora da API pública.

> Neon (neon.tech) também serve: é PostgreSQL puro. Os passos 2 a 6 são iguais; muda só o formato da URL.

## 2. Criar os usuários (uma vez)
1. Abra o [sql/setup_postgres.sql](../sql/setup_postgres.sql) num editor.
2. Troque as duas senhas por senhas fortes e **diferentes**. Guarde-as num gerenciador de senhas.
3. No Supabase, **SQL Editor → New query**, cole e rode. Não salve o arquivo com as senhas reais.
   O script pode ser rodado de novo sem problema (por exemplo, para trocar as senhas).

## 3. Montar as URLs de conexão
No Supabase, **Connect → Session pooler** (use o pooler: a conexão direta é só IPv6
e nem todo serviço na nuvem a alcança). O formato é:

```
postgresql://USUARIO.ID-DO-PROJETO:SENHA@aws-0-sa-east-1.pooler.supabase.com:5432/postgres
```

| Para | Usuário na URL |
|---|---|
| Robô (escritório) | `nfse_robo.ID-DO-PROJETO` |
| Painel web (nuvem) | `nfse_leitura.ID-DO-PROJETO` |

Se a senha tiver `@ : / ? # %`, troque por `%40 %3A %2F %3F %23 %25` dentro da URL.
O sistema liga a criptografia (`sslmode=require`) sozinho para endereços fora da máquina.

## 4. Computador do escritório (robô)
1. Atualize o projeto com os arquivos novos e reinstale (traz o driver do PostgreSQL):
   ```
   venv\Scripts\python -m pip install -e .
   ```
2. No `.env`, acrescente a URL **do robô**, entre aspas simples:
   ```
   NFSE_DATABASE_URL='postgresql://nfse_robo.ID-DO-PROJETO:SENHA@aws-0-sa-east-1.pooler.supabase.com:5432/postgres'
   ```
3. Envie para o banco as notas que já estão baixadas (pode rodar quantas vezes quiser, não duplica):
   ```
   venv\Scripts\nfse-importar
   ```
   A primeira linha deve dizer `Banco de notas: PostgreSQL (...)`.
4. Crie a tarefa agendada (PowerShell normal, na pasta do projeto):
   ```
   powershell -ExecutionPolicy Bypass -File scripts\agendar.ps1 -Hora 07:00 -TestarAgora
   ```
   Ela roda o `nfse-baixar` todo dia, com o seu usuário do Windows (precisa estar com a sessão aberta,
   mesmo com a tela bloqueada). Quando encontra notas novas, já importa direto para o PostgreSQL.
   Cada execução fica registrada em `logs\robo-AAAA-MM-DD.log`.

Para voltar ao SQLite local, basta apagar a linha `NFSE_DATABASE_URL` do `.env`.

## 5. Repositório no GitHub (privado)
1. Crie um repositório **privado** e envie o projeto. Antes do primeiro commit, rode `git status` e
   confira que **não aparecem**: `.env`, arquivos `.pfx`, a pasta `data\` e a pasta `venv\`.
   O `.gitignore` já exclui todos eles.
2. Devem ir: `src/`, `assets/marca/` (logo e JSON), `requirements*.txt`, `pyproject.toml`.

## 6. Painel web (Azure App Service)
O painel é o app FastAPI de `src/nfse/web/`, com o login do Portal Informe. Ele usa a URL **de leitura**
(`nfse_leitura`). Como configurar e publicar: [docs/web.md](web.md).

## 7. Conferência
- O painel abre com a logo, as cores e os mesmos totais do painel local.
- No Supabase (SQL Editor): `SELECT count(*) FROM nfse.notas;` bate com o número de notas importadas.
- Depois da próxima execução da tarefa agendada, as notas novas aparecem no painel em até 1 minuto
  (tempo do cache).

## Problemas comuns

| Mensagem | Causa | O que fazer |
|---|---|---|
| `permission denied to change default privileges` (no SQL Editor) | versão antiga do `setup_postgres.sql` | use a versão atual, que torna o `postgres` membro do robô durante o comando |
| `password authentication failed` | senha errada, ou usuário sem `.ID-DO-PROJETO` no pooler | refaça a URL do passo 3 |
| `permission denied for table notas` (no `nfse-importar`) | a tabela foi criada por outro usuário (ex.: `postgres`) | rode o [sql/corrigir_dono_tabela.sql](../sql/corrigir_dono_tabela.sql) no SQL Editor |
| `permission denied for schema nfse` | robô usando a URL de leitura | no `.env` do escritório vai a URL do `nfse_robo` |
| Painel diz que o banco está vazio | robô ainda não importou | rode `nfse-importar` no escritório |
| Projeto do Supabase "pausado" | plano gratuito pausa após 7 dias sem uso | a tarefa diária evita; se pausar, reative no painel |

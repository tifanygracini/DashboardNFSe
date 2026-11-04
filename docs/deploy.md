# Deploy: dashboard no Streamlit Cloud + banco PostgreSQL + robô no escritório

```
[computador do escritório]                 [nuvem]
 tarefa agendada 08:00                      PostgreSQL (Supabase, região São Paulo)
 nfse-baixar ──► ADN (com o certificado)       ▲  usuário nfse_robo (grava)
     │                                         │
     └─► nfse-importar ────────────────────────┘
                                               │  usuário nfse_leitura (só lê)
                                               ▼
                                     Streamlit Community Cloud (app privado)
```

O certificado A1 e os XMLs **nunca saem do escritório**. Na nuvem ficam só os dados das notas,
e o dashboard usa um usuário que não consegue alterar nada.

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
No Supabase, **Connect → Session pooler** (use o pooler: o Streamlit Cloud não acessa a conexão direta,
que é só IPv6). O formato é:

```
postgresql://USUARIO.ID-DO-PROJETO:SENHA@aws-0-sa-east-1.pooler.supabase.com:5432/postgres
```

| Para | Usuário na URL |
|---|---|
| Robô (escritório) | `nfse_robo.ID-DO-PROJETO` |
| Dashboard (nuvem) | `nfse_leitura.ID-DO-PROJETO` |

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
1. Gere o tema para a nuvem (rode de novo sempre que mudar o `escritorio.json`):
   ```
   venv\Scripts\python tools\gerar_config_tema.py
   ```
2. Crie um repositório **privado** e envie o projeto. Antes do primeiro commit, rode `git status` e
   confira que **não aparecem**: `.env`, arquivos `.pfx`, a pasta `data\` e a pasta `venv\`.
   O `.gitignore` já exclui todos eles.
3. Devem ir: `src/`, `assets/marca/` (logo e JSON), `.streamlit/config.toml`, `requirements.txt`,
   `pyproject.toml`.

## 6. Streamlit Community Cloud
1. Em share.streamlit.io, conecte sua conta do GitHub (autorizando acesso a repositórios privados),
   clique em **Create app** e escolha o repositório.
   - **Branch:** `main`
   - **Main file path:** `src/nfse/ui/dashboard/app.py`
2. **Advanced settings:**
   - **Python version:** 3.12
   - **Secrets** (com a URL **de leitura**):
     ```toml
     CNPJ_EMPRESA = "11223344000186"
     NFSE_DATABASE_URL = "postgresql://nfse_leitura.ID-DO-PROJETO:SENHA@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
     ```
3. **Deploy.** Depois, em **Share → Who can view this app**, deixe **Only specific people** e convide
   os e-mails autorizados. O dashboard mostra faturamento e dados de clientes: ele não pode ficar público.

## 7. Conferência
- O dashboard abre com a logo, as cores e os mesmos totais do dashboard local.
- No Supabase (SQL Editor): `SELECT count(*) FROM nfse.notas;` bate com o número de notas importadas.
- Depois da próxima execução da tarefa agendada, as notas novas aparecem no dashboard em até 1 minuto
  (tempo do cache).

## Problemas comuns

| Mensagem | Causa | O que fazer |
|---|---|---|
| `permission denied to change default privileges` (no SQL Editor) | versão antiga do `setup_postgres.sql` | use a versão atual, que torna o `postgres` membro do robô durante o comando |
| `No module named 'nfse'` (no Cloud) | falta `-e .` no `requirements.txt` | confira a última linha do arquivo |
| `password authentication failed` | senha errada, ou usuário sem `.ID-DO-PROJETO` no pooler | refaça a URL do passo 3 |
| `permission denied for table notas` (no `nfse-importar`) | a tabela foi criada por outro usuário (ex.: `postgres`) | rode o [sql/corrigir_dono_tabela.sql](../sql/corrigir_dono_tabela.sql) no SQL Editor |
| `permission denied for schema nfse` | robô usando a URL de leitura | no `.env` do escritório vai a URL do `nfse_robo` |
| Dashboard diz que o banco está vazio | robô ainda não importou | rode `nfse-importar` no escritório |
| Cores padrão do Streamlit no Cloud | falta `.streamlit/config.toml` no repositório | passo 5.1 e commit |
| Projeto do Supabase "pausado" | plano gratuito pausa após 7 dias sem uso | a tarefa diária evita; se pausar, reative no painel |

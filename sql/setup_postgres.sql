-- Preparação do PostgreSQL para o dashboard de NFS-e. Rodar como administrador do banco
-- (Supabase: SQL Editor, usuário "postgres"; Neon: SQL Editor do console).
-- Pode ser rodado de novo sem problema: não duplica nada e atualiza as senhas.
--
-- ANTES DE RODAR: troque as duas senhas abaixo por senhas fortes e diferentes, e guarde-as num
-- gerenciador de senhas. Não salve este arquivo com as senhas reais no Git.

-- 1) Esquema próprio, fora do "public" (no Supabase, o "public" é exposto pela API REST do projeto)
CREATE SCHEMA IF NOT EXISTS nfse;

-- 2) Usuários: ROBÔ (escritório, grava) e DASHBOARD (Streamlit Cloud, só lê)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nfse_robo') THEN
    CREATE ROLE nfse_robo LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nfse_leitura') THEN
    CREATE ROLE nfse_leitura LOGIN;
  END IF;
END $$;
ALTER ROLE nfse_robo    PASSWORD 'TROQUE-ESTA-SENHA-DO-ROBO';
ALTER ROLE nfse_leitura PASSWORD 'TROQUE-ESTA-SENHA-DO-DASHBOARD';

GRANT USAGE, CREATE ON SCHEMA nfse TO nfse_robo;
GRANT USAGE ON SCHEMA nfse TO nfse_leitura;

-- 3) Tudo que o robô criar no esquema nfse fica legível (e só legível) para o dashboard.
--    No Supabase o "postgres" não é superusuário: para definir os privilégios padrão de outro
--    usuário ele precisa ser membro dele. Entra como membro só durante estes comandos e sai em
--    seguida (a regra continua valendo depois).
GRANT nfse_robo TO CURRENT_USER;
ALTER DEFAULT PRIVILEGES FOR ROLE nfse_robo IN SCHEMA nfse GRANT SELECT ON TABLES TO nfse_leitura;
-- se a tabela já existir (por exemplo, criada antes com outro usuário), passa a ser do robô
ALTER TABLE IF EXISTS nfse.notas OWNER TO nfse_robo;
-- e libera a leitura nas tabelas que já existirem
GRANT SELECT ON ALL TABLES IN SCHEMA nfse TO nfse_leitura;
REVOKE nfse_robo FROM CURRENT_USER;

-- 4) Conferência (rodar depois da primeira importação do robô):
--    SELECT count(*) FROM nfse.notas;
--    SELECT grantee, privilege_type FROM information_schema.role_table_grants WHERE table_schema = 'nfse';

-- Corrige "permission denied for table notas" no nfse-importar: a tabela nfse.notas foi criada por
-- outro usuário (geralmente o "postgres") e o robô não consegue gravar nela.
-- Rodar no SQL Editor do Supabase. Não mexe nas senhas nem apaga notas.

-- antes: de quem é a tabela?
SELECT tableowner FROM pg_tables WHERE schemaname = 'nfse' AND tablename = 'notas';

GRANT nfse_robo TO CURRENT_USER;            -- necessário para passar a tabela ao robô
ALTER TABLE nfse.notas OWNER TO nfse_robo;   -- o robô passa a ser o dono (grava e atualiza)
GRANT SELECT ON nfse.notas TO nfse_leitura;  -- o dashboard continua só lendo
REVOKE nfse_robo FROM CURRENT_USER;

-- depois: deve mostrar nfse_robo
SELECT tableowner FROM pg_tables WHERE schemaname = 'nfse' AND tablename = 'notas';

-- Ordem do dono (29/08/2026): todos os serviços passam a se referir a "Dudu Castro".
-- Idempotente: só age enquanto a linha ainda carrega o nome antigo.
UPDATE access_users
SET display_name = 'Dudu Castro', updated_at = now()
WHERE role = 'owner' AND display_name = 'Eduardo Castro';

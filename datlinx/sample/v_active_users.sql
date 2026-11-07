CREATE VIEW v_active_users AS
SELECT
    user_id,
    user_name,
    email,
    created_at
FROM m_users
WHERE status = 'ACTIVE'
  AND is_deleted = 0;

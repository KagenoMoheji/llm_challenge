CREATE PROCEDURE sp_refresh_daily_kpi
AS
BEGIN
    SET NOCOUNT ON;

    -- Daily KPI calculation from user order summary and active users
    SELECT
        CAST(GETDATE() AS DATE) AS calculation_date,
        COUNT(DISTINCT u.user_id) AS active_user_count,
        SUM(s.total_spent) AS daily_turnover
    FROM v_active_users u
    JOIN v_user_order_summary s
        ON u.user_id = s.user_id;
END;

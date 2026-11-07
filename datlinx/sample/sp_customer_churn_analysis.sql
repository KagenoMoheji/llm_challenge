CREATE PROCEDURE sp_customer_churn_analysis
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        u.user_id,
        u.user_name,
        MAX(o.order_date) AS last_order_date,
        DATEDIFF(day, MAX(o.order_date), GETDATE()) AS days_since_last_order
    FROM v_active_users u
    LEFT JOIN t_orders o
        ON u.user_id = o.user_id
    GROUP BY
        u.user_id,
        u.user_name
    HAVING
        DATEDIFF(day, MAX(o.order_date), GETDATE()) > 90;
END;

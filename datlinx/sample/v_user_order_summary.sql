CREATE VIEW v_user_order_summary AS
SELECT
    u.user_id,
    u.user_name,
    COUNT(d.order_id) AS total_orders,
    SUM(d.subtotal) AS total_spent
FROM v_active_users u
LEFT JOIN v_order_details d
    ON u.user_id = d.user_id
GROUP BY
    u.user_id,
    u.user_name;

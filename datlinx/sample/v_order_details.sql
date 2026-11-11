CREATE VIEW dbo.v_order_details AS
SELECT
    o.order_id,
    o.user_id,
    o.order_date,
    oi.product_id,
    p.product_name,
    oi.quantity,
    oi.unit_price,
    (oi.quantity * oi.unit_price) AS subtotal
FROM
    dbo.t_orders o
INNER JOIN dbo.t_order_items oi
    ON o.order_id = oi.order_id
LEFT JOIN
    dbo.m_products p
    ON oi.product_id = p.product_id;

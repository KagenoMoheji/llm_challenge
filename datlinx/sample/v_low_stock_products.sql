CREATE VIEW v_low_stock_products AS
SELECT
    p.product_id,
    p.product_name,
    i.current_stock,
    i.safety_stock
FROM
    m_products p
JOIN
    t_inventory i
    ON p.product_id = i.product_id
WHERE
    i.current_stock < i.safety_stock;

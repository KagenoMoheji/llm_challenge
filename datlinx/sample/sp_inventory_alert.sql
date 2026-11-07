CREATE PROCEDURE sp_inventory_alert
AS
BEGIN
    SET NOCOUNT ON;

    -- Extract low stock products needing immediate reorder
    SELECT
        product_id,
        product_name,
        current_stock,
        safety_stock,
        (safety_stock - current_stock) AS reorder_quantity
    FROM
        v_low_stock_products
    WHERE current_stock <= safety_stock;
END;

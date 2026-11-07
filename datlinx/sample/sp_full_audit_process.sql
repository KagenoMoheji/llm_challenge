CREATE PROCEDURE dbo.sp_full_audit_process
AS
BEGIN
    SET NOCOUNT ON;

    -- Full audit joining order details, users, and inventory
    SELECT
        d.order_id,
        d.product_name,
        d.quantity,
        i.current_stock,
        u.user_name
    FROM
        dbo.v_order_details d
    INNER JOIN
        dbo.v_active_users u
        ON d.user_id = u.user_id
    INNER JOIN
        dbo.t_inventory i
        ON d.product_id = i.product_id;
END;

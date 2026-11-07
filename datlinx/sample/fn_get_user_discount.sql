CREATE FUNCTION dbo.fn_get_user_discount (
    @user_id INT
)
RETURNS DECIMAL(5, 2)
AS
BEGIN
    DECLARE @discount DECIMAL(5, 2) = 0.00;

    SELECT
        @discount = CASE
            WHEN total_spent > 100000 THEN 0.15
            WHEN total_spent > 50000  THEN 0.10
            ELSE 0.05
        END
    FROM dbo.v_user_order_summary
    WHERE user_id = @user_id;

    RETURN @discount;
END;

CREATE PROCEDURE dbo.sp_generate_monthly_sales_report
    @target_year INT,
    @target_month INT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        d.product_id,
        d.product_name,
        COUNT(d.order_id) AS monthly_order_count,
        SUM(d.subtotal) AS total_monthly_sales
    FROM
        dbo.v_order_details d
    INNER JOIN
        dbo.v_user_order_summary s
        ON d.user_id = s.user_id
    WHERE
        YEAR(d.order_date) = @target_year
        AND MONTH(d.order_date) = @target_month
    GROUP BY
        d.product_id,
        d.product_name;
END;

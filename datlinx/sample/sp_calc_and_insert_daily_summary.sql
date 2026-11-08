CREATE PROCEDURE dbo.sp_calc_and_insert_daily_summary
AS
BEGIN
    SET NOCOUNT ON;

    -- 日次売上集計を計算し、daily_sales_summaryテーブルへ投入
    INSERT INTO dbo.daily_sales_summary (summary_date, product_id, product_name, total_sales, order_count)
    SELECT
        CAST(d.order_date AS DATE) AS summary_date,
        d.product_id,
        d.product_name,
        SUM(d.subtotal) AS total_sales,
        COUNT(d.order_id) AS order_count
    FROM
        dbo.v_order_details d
    INNER JOIN
        dbo.v_active_users u
        ON d.user_id = u.user_id
    GROUP BY
        CAST(d.order_date AS DATE),
        d.product_id,
        d.product_name;
END;

CREATE VIEW dbo.v_daily_sales_dashboard AS
SELECT
    s.summary_date,
    s.product_id,
    s.product_name,
    s.total_sales,
    s.order_count,
    CASE
        WHEN s.total_sales >= 100000 THEN 'TARGET_ACHIEVED'
        ELSE 'IN_PROGRESS'
    END AS sales_status
FROM
    dbo.daily_sales_summary s
WHERE
    s.summary_date >= DATEADD(day, -30, CAST(GETDATE() AS DATE));

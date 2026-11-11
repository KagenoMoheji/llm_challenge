CREATE TABLE dbo.daily_sales_summary (
    summary_date DATE NOT NULL,
    product_id INT NOT NULL,
    product_name NVARCHAR(100),
    total_sales DECIMAL(18, 2),
    order_count INT,
    created_at DATETIME DEFAULT GETDATE()
);

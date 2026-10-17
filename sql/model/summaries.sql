CREATE OR REPLACE TABLE dws_daily_state AS
SELECT purchase_date, customer_state,
       CAST(sum(product_amount) AS DECIMAL(18,2)) AS product_amount,
       count(*) AS order_count
FROM dwd_orders WHERE order_status='delivered'
GROUP BY purchase_date, customer_state;

CREATE OR REPLACE VIEW ads_overview AS
SELECT CAST(sum(product_amount) AS DECIMAL(18,2)) AS completed_product_amount,
       count(*) AS completed_order_count,
       CAST(sum(product_amount)/nullif(count(*),0) AS DECIMAL(18,2)) AS completed_average_order_value,
       count(DISTINCT customer_unique_id) AS completed_unique_customer_count
FROM dwd_orders WHERE order_status='delivered';

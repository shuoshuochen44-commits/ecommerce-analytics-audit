CREATE OR REPLACE TABLE dwd_order_payments AS
SELECT order_id, count(*) AS payment_count,
       CAST(sum(CAST(payment_value AS DECIMAL(18,2))) AS DECIMAL(18,2)) AS payment_amount
FROM raw_payments GROUP BY order_id;

CREATE OR REPLACE TABLE dwd_orders AS
WITH items AS (
    SELECT order_id, count(*) AS item_count,
           CAST(sum(price) AS DECIMAL(18,2)) AS product_amount,
           CAST(sum(freight_value) AS DECIMAL(18,2)) AS freight_amount
    FROM dwd_order_items GROUP BY order_id
)
SELECT o.order_id, o.customer_id, c.customer_unique_id,
       c.customer_state, c.customer_city, o.order_status,
       CAST(o.order_purchase_timestamp AS TIMESTAMP) AS purchase_timestamp,
       CAST(o.order_purchase_timestamp AS DATE) AS purchase_date,
       try_cast(o.order_delivered_customer_date AS TIMESTAMP) AS delivered_timestamp,
       try_cast(o.order_estimated_delivery_date AS TIMESTAMP) AS estimated_delivery_timestamp,
       c.customer_id IS NULL AS missing_customer,
       coalesce(i.item_count, 0) AS item_count,
       i.product_amount, i.freight_amount,
       coalesce(p.payment_count, 0) AS payment_count,
       p.payment_amount,
       CAST(p.payment_amount-i.product_amount-i.freight_amount AS DECIMAL(18,2)) AS payment_difference,
       CASE WHEN i.order_id IS NULL AND p.order_id IS NULL THEN 'missing_both'
            WHEN i.order_id IS NULL THEN 'missing_items'
            WHEN p.order_id IS NULL THEN 'missing_payment'
            WHEN abs(p.payment_amount-i.product_amount-i.freight_amount)<=0.01 THEN 'matched'
            ELSE 'mismatch' END AS reconciliation_status
FROM raw_orders o
LEFT JOIN dim_customer_mapping c USING (customer_id)
LEFT JOIN items i USING (order_id)
LEFT JOIN dwd_order_payments p USING (order_id);

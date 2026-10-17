CREATE OR REPLACE TABLE dwd_order_items AS
SELECT i.order_id, CAST(i.order_item_id AS INTEGER) AS order_item_id,
       i.product_id, i.seller_id,
       try_cast(i.shipping_limit_date AS TIMESTAMP) AS shipping_limit_date,
       CAST(i.price AS DECIMAL(18,2)) AS price,
       CAST(i.freight_value AS DECIMAL(18,2)) AS freight_value,
       p.product_category_name,
       o.order_id IS NULL AS missing_order,
       p.product_id IS NULL AS missing_product
FROM raw_order_items i
LEFT JOIN raw_orders o USING (order_id)
LEFT JOIN dim_products p USING (product_id);

SELECT count(DISTINCT c.customer_unique_id) AS completed_unique_customer_count
FROM raw_orders AS o
INNER JOIN raw_customers AS c USING (customer_id)
WHERE o.order_status = 'delivered';

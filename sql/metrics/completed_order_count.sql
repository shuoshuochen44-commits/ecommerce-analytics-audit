SELECT count(DISTINCT order_id) AS completed_order_count
FROM raw_orders
WHERE order_status = 'delivered';

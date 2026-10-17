SELECT count(DISTINCT order_id) AS completed_order_count
FROM orders
WHERE order_status = 'delivered';

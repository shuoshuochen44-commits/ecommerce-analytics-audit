SELECT CAST(
    sum(i.price) / nullif(count(DISTINCT o.order_id), 0)
    AS DECIMAL(18, 2)
) AS completed_average_order_value
FROM raw_order_items AS i
INNER JOIN raw_orders AS o USING (order_id)
WHERE o.order_status = 'delivered';

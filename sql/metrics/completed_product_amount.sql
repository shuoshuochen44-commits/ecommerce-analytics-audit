SELECT CAST(sum(CAST(i.price AS DECIMAL(18, 2))) AS DECIMAL(18, 2)) AS completed_product_amount
FROM order_items AS i
INNER JOIN orders AS o USING (order_id)
WHERE o.order_status = 'delivered';

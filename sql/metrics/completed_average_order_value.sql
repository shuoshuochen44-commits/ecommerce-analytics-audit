WITH completed_amount AS (
    SELECT sum(CAST(i.price AS DECIMAL(18, 2))) AS product_amount
    FROM raw_order_items AS i
    INNER JOIN raw_orders AS o USING (order_id)
    WHERE o.order_status = 'delivered'
),
completed_orders AS (
    SELECT count(DISTINCT order_id) AS order_count
    FROM raw_orders
    WHERE order_status = 'delivered'
)
SELECT CAST(
    a.product_amount / nullif(o.order_count, 0)
    AS DECIMAL(18, 2)
) AS completed_average_order_value
FROM completed_amount AS a
CROSS JOIN completed_orders AS o;

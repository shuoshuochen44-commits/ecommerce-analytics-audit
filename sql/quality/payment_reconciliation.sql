WITH item_totals AS (
    SELECT
        order_id,
        CAST(sum(price + freight_value) AS DECIMAL(18, 2)) AS item_and_freight_total
    FROM raw_order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        CAST(sum(payment_value) AS DECIMAL(18, 2)) AS payment_total
    FROM raw_payments
    GROUP BY order_id
)
SELECT
    coalesce(i.order_id, p.order_id) AS order_id,
    i.item_and_freight_total,
    p.payment_total,
    CAST(p.payment_total - i.item_and_freight_total AS DECIMAL(18, 2)) AS difference,
    CASE
        WHEN i.order_id IS NULL THEN 'missing_items'
        WHEN p.order_id IS NULL THEN 'missing_payment'
        WHEN abs(p.payment_total - i.item_and_freight_total) <= 0.01 THEN 'matched'
        ELSE 'mismatch'
    END AS reconciliation_status
FROM item_totals AS i
FULL OUTER JOIN payment_totals AS p USING (order_id)
ORDER BY order_id;

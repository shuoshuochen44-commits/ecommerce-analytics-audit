CREATE OR REPLACE TABLE dim_customer_mapping AS
SELECT customer_id, nullif(trim(customer_unique_id), '') AS customer_unique_id,
       customer_zip_code_prefix, customer_city, customer_state
FROM raw_customers;

CREATE OR REPLACE TABLE dim_products AS
SELECT product_id, nullif(trim(product_category_name), '') AS product_category_name
FROM raw_products;

# 原始数据

数据来源：[Olist Brazilian E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)。

从发布页面下载并解压后，把以下文件放入 `data/raw/olist/`：

- `olist_orders_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_customers_dataset.csv`
- `olist_products_dataset.csv`
- `olist_order_payments_dataset.csv`

`data/raw/` 不进入 Git。下载后记录页面显示的版本、下载日期，并用下面的命令计算哈希：

```powershell
Get-FileHash -Algorithm SHA256 data/raw/olist/*.csv
```

测试与持续集成使用 `tests/fixtures/olist_mini/`，不依赖原始文件。

app_name = "woocommerce_connector"
app_title = "WooCommerce Connector"
app_publisher = "Your Name"
app_description = "Sync products and orders between ERPNext and WooCommerce"
app_icon = "octicon octicon-globe"
app_color = "blue"
app_email = "you@example.com"
app_license = "MIT"

# ربط الأحداث
doc_events = {
    "Item": {
        "after_insert": "woocommerce_connector.sync_products.sync_product",
        "on_update": "woocommerce_connector.sync_products.sync_product"
    }
}

# مهام مجدولة
scheduler_events = {
    "all": [
        "woocommerce_connector.sync_orders.sync_orders"
    ]
}

doc_events = {
    "Item": {
        "after_insert": "woocommerce_connector.sync_products.sync_product",
        "on_update": "woocommerce_connector.sync_products.sync_product"
    }
}

scheduler_events = {
    "all": [
        "woocommerce_connector.sync_orders.sync_orders"
    ]
}

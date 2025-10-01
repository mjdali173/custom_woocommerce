import frappe
from .woocommerce_requests import post_request, put_request

def sync_product(item_code):
    """Sync single product from ERPNext to WooCommerce"""
    item = frappe.get_doc("Item", item_code)

    product_data = {
        "name": item.item_name,
        "sku": item.item_code,
        "regular_price": str(item.standard_rate or 0),
        "description": item.description or "",
        "status": "publish" if item.is_sales_item else "draft"
    }

    if item.woocommerce_product_id:
        put_request(f"products/{item.woocommerce_product_id}", product_data)
    else:
        res = post_request("products", product_data)
        frappe.db.set_value("Item", item.name, "woocommerce_product_id", res.get("id"))
        frappe.db.commit()
import frappe
from frappe.utils import nowdate, flt
from .woocommerce_requests import get_request
from .sync_products import sync_product

def sync_orders():
    orders = get_request("orders")
    for order in orders:
        create_sales_order(order)

def create_sales_order(order):
    fixed_customer = "woocommerce_customer@example.com"

    if not frappe.db.exists("Customer", fixed_customer):
        frappe.throw(f"Customer {fixed_customer} not found!")

    existing = frappe.db.get_value("Sales Order", {"woocommerce_order_id": order["id"]}, "name")
    if existing:
        return

    billing = order.get("billing") or {}
    shipping = order.get("shipping") or {}

    so = frappe.get_doc({
        "doctype": "Sales Order",
        "woocommerce_order_id": order["id"],
        "customer": fixed_customer,
        "delivery_date": nowdate(),
        "items": [
            {
                "item_code": get_item_code(line),
                "rate": flt(line.get("price") or 0),
                "qty": flt(line.get("quantity") or 1)
            }
            for line in order.get("line_items", [])
            if get_item_code(line)
        ],
        "customer_address": create_address("Billing", billing, fixed_customer, order["id"]),
        "shipping_address_name": create_address("Shipping", shipping, fixed_customer, order["id"]),
        "transaction_date": order.get("date_created")[:10]
    })
    if not so.grand_total:
        so.grand_total = 0

    so.flags.ignore_mandatory = True
    so.save(ignore_permissions=True)
    so.submit()

def get_item_code(line):
    product_id = line.get("product_id")
    return frappe.db.get_value("Item", {"woocommerce_product_id": product_id}, "item_code")

def create_address(address_type, data, customer, order_id):
    if not data:
        return None
    address = frappe.get_doc({
        "doctype": "Address",
        "address_title": f"{customer}_{order_id}_{address_type}",
        "address_type": address_type,
        "address_line1": data.get("address_1") or "Address 1",
        "city": data.get("city") or "City",
        "state": data.get("state"),
        "pincode": data.get("postcode"),
        "country": data.get("country"),
        "phone": data.get("phone"),
        "email_id": data.get("email"),
        "links": [{
            "link_doctype": "Customer",
            "link_name": customer
        }]
    }).insert(ignore_permissions=True)
    return address.name

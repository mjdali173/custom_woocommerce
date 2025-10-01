from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import nowdate, flt, cint
from .utils import make_woocommerce_log
from .woocommerce_requests import get_woocommerce_orders, get_woocommerce_tax
from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
import requests.exceptions

def sync_orders(woocommerce_settings=None):
    # إذا لم تُمرّر الإعدادات، جلبها من قاعدة البيانات
    if not woocommerce_settings:
        woocommerce_settings = frappe.get_doc("WooCommerce Config", "WooCommerce Config")

    try:
        orders = get_woocommerce_orders(woocommerce_settings)
        for woocommerce_order in orders:
            create_sales_order(woocommerce_order, woocommerce_settings)

    except requests.exceptions.RequestException as e:
        make_woocommerce_log(
            title=str(e),
            status="Error",
            method="sync_orders",
            message=frappe.get_traceback(),
            request_data={},
            exception=True
        )
def create_sales_order(woocommerce_order, woocommerce_settings):
    """إنشاء Sales Order لكل طلب من WooCommerce"""
    customer = "woocommerce@alsharaa-dent.com"  # عميل ثابت

    # التأكد من وجود العميل الثابت
    if not frappe.db.exists("Customer", customer):
        frappe.throw(_("Fixed Customer {0} does not exist").format(customer))

    # التأكد إذا كان الطلب موجود مسبقًا
    so_name = frappe.db.get_value("Sales Order", {"woocommerce_order_id": woocommerce_order.get("id")}, "name")
    if not so_name:
        shipping_address = create_customer_address('Shipping', woocommerce_order, customer)
        billing_address = create_customer_address('Billing', woocommerce_order, customer)

        # الحصول على ضريبة الطلب
        tax_rules = frappe.get_all("WooCommerce Tax Rule", filters={'currency': woocommerce_order.get("currency")}, fields=['tax_rule'])
        if not tax_rules:
            tax_rules = frappe.get_all("WooCommerce Tax Rule", filters={'currency': "%"}, fields=['tax_rule'])
        tax_rules = tax_rules[0]['tax_rule'] if tax_rules else ""

        so = frappe.get_doc({
            "doctype": "Sales Order",
            "naming_series": woocommerce_settings.sales_order_series or "SO-woocommerce-",
            "woocommerce_order_id": woocommerce_order.get("id"),
            "woocommerce_payment_method": woocommerce_order.get("payment_method_title"),
            "customer": customer,
            "customer_group": woocommerce_settings.customer_group,
            "delivery_date": nowdate(),
            "company": woocommerce_settings.company,
            "selling_price_list": woocommerce_settings.price_list,
            "ignore_pricing_rule": 1,
            "items": get_order_items(woocommerce_order.get("line_items"), woocommerce_settings),
            "taxes": get_order_taxes(woocommerce_order, woocommerce_settings),
            "currency": woocommerce_order.get("currency"),
            "taxes_and_charges": tax_rules,
            "customer_address": billing_address,
            "shipping_address_name": shipping_address,
            "transaction_date": woocommerce_order.get("date_created")[:10]
        })

        so.flags.ignore_mandatory = True
        so.save(ignore_permissions=True)
        so.submit()

    else:
        so = frappe.get_doc("Sales Order", so_name)

    frappe.db.commit()

    make_woocommerce_log(
        title="create sales order",
        status="Success",
        method="create_sales_order",
        message="Sales Order created for fixed customer with dynamic addresses",
        request_data=woocommerce_order,
        exception=False
    )
    return so


def create_customer_address(address_type, woocommerce_order, customer):
    """إنشاء عنوان Billing أو Shipping جديد"""
    address_record = woocommerce_order.get(address_type.lower())
    if not address_record:
        return None

    country = get_country_name(address_record.get("country"))

    try:
        address = frappe.get_doc({
            "doctype": "Address",
            "woocommerce_address_id": f"{address_type}_{woocommerce_order.get('id')}",
            "woocommerce_company_name": address_record.get("company") or '',
            "address_title": f"{customer}_{woocommerce_order.get('id')}",
            "address_type": address_type,
            "address_line1": address_record.get("address_1") or "Address 1",
            "address_line2": address_record.get("address_2"),
            "city": address_record.get("city") or "City",
            "state": address_record.get("state"),
            "pincode": address_record.get("postcode"),
            "country": country,
            "phone": address_record.get("phone"),
            "email_id": address_record.get("email"),
            "links": [{
                "link_doctype": "Customer",
                "link_name": customer
            }],
            "woocommerce_first_name": address_record.get("first_name"),
            "woocommerce_last_name": address_record.get("last_name")
        }).insert()
        return address.name

    except Exception as e:
        make_woocommerce_log(
            title=str(e),
            status="Error",
            method="create_customer_address",
            message=frappe.get_traceback(),
            request_data=woocommerce_order,
            exception=True
        )
        return None


def get_order_items(order_items, woocommerce_settings):
    items = []
    for woocommerce_item in order_items:
        item_code = get_item_code(woocommerce_item)
        if not item_code:
            continue  # تجاهل المنتجات غير الموجودة
        items.append({
            "item_code": item_code,
            "rate": flt(woocommerce_item.get("price")),
            "delivery_date": nowdate(),
            "qty": flt(woocommerce_item.get("quantity")),
            "warehouse": woocommerce_settings.warehouse
        })
    return items


def get_item_code(woocommerce_item):
    if cint(woocommerce_item.get("variation_id")) > 0:
        return frappe.db.get_value("Item", {"woocommerce_product_id": woocommerce_item.get("variation_id")}, "item_code")
    else:
        return frappe.db.get_value("Item", {"woocommerce_product_id": woocommerce_item.get("product_id")}, "item_code")


def get_order_taxes(woocommerce_order, woocommerce_settings):
    taxes = []
    for tax in woocommerce_order.get("tax_lines", []):
        woocommerce_tax = get_woocommerce_tax(tax.get("rate_id"))
        rate = flt(woocommerce_tax.get("rate") or 0)
        name = woocommerce_tax.get("name") or woocommerce_tax.get("method_title") or "Tax"

        taxes.append({
            "charge_type": "Actual",
            "account_head": get_tax_account_head(name),
            "description": "{0} - {1}%".format(name, rate),
            "rate": rate,
            "tax_amount": flt(tax.get("tax_total") or 0) + flt(tax.get("shipping_tax_total") or 0),
            "included_in_print_rate": 0,
            "cost_center": woocommerce_settings.cost_center
        })
    return taxes


def get_country_name(code):
    if not code:
        return "Switzerland"
    return frappe.db.get_value("Country", {"code": code}, "country_name") or "Switzerland"


def get_tax_account_head(tax_name):
    tax_account = frappe.db.get_value(
        "WooCommerce Tax Account",
        {"parent": "WooCommerce Config", "woocommerce_tax": tax_name},
        "tax_account"
    )
    if not tax_account:
        frappe.throw(_("Tax Account not specified for WooCommerce Tax {0}").format(tax_name))
    return tax_account



def close_synced_woocommerce_orders():
    for woocommerce_order in get_woocommerce_orders():
        status = woocommerce_order.get("status") or ""
        if status.lower() != "cancelled":
            order_data = {"status": "completed"}
            try:
                put_request(f"orders/{woocommerce_order.get('id')}", order_data)
            except requests.exceptions.HTTPError as e:
                make_woocommerce_log(
                    title=str(e),
                    status="Error",
                    method="close_synced_woocommerce_orders",
                    message=frappe.get_traceback(),
                    request_data=woocommerce_order,
                    exception=True
                )

def close_synced_woocommerce_order(wooid):
    order_data = {"status": "completed"}
    try:
        put_request(f"orders/{wooid}", order_data)
    except requests.exceptions.HTTPError as e:
        make_woocommerce_log(
            title=str(e),
            status="Error",
            method="close_synced_woocommerce_order",
            message=frappe.get_traceback(),
            request_data={"order_id": wooid},
            exception=True
        )

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import nowdate, flt, cint
from .utils import make_woocommerce_log
from .woocommerce_requests import get_woocommerce_orders, get_woocommerce_tax, put_request
from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
import requests.exceptions


def create_sales_order(woocommerce_order, woocommerce_settings, company=None):
    # 👇 عميل ثابت
    customer = "woocommerce@alsharaa-dent.com"

    # تأكد من وجود العميل الثابت
    if not frappe.db.exists("Customer", customer):
        frappe.throw(_("Fixed Customer {0} does not exist").format(customer))

    # تحقق إذا كان الـ Order موجود من قبل
    so = frappe.db.get_value("Sales Order", {"woocommerce_order_id": woocommerce_order.get("id")}, "name")
    if not so:
        # 🔹 أنشئ عنوان جديد (Billing + Shipping) لهذا الـ Order
        shipping_address = create_customer_address('Shipping', woocommerce_order, customer)
        billing_address = create_customer_address('Billing', woocommerce_order, customer)

        # 🔹 الضرائب
        tax_rules = frappe.get_all("WooCommerce Tax Rule", filters={'currency': woocommerce_order.get("currency")}, fields=['tax_rule'])
        if not tax_rules:
            tax_rules = frappe.get_all("WooCommerce Tax Rule", filters={'currency': "%"}, fields=['tax_rule'])
        if tax_rules:
            tax_rules = tax_rules[0]['tax_rule']
        else:
            tax_rules = ""

        # 🔹 إنشاء Sales Order
        so = frappe.get_doc({
            "doctype": "Sales Order",
            "naming_series": woocommerce_settings.sales_order_series or "SO-woocommerce-",
            "woocommerce_order_id": woocommerce_order.get("id"),
            "woocommerce_payment_method": woocommerce_order.get("payment_method_title"),
            "customer": customer,  # 👈 عميل ثابت
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
            "transaction_date": woocommerce_order.get("date_created")[:10]  # تاريخ الطلب من WooCommerce
        })

        so.flags.ignore_mandatory = True
        so.save(ignore_permissions=True)
        so.submit()

    else:
        so = frappe.get_doc("Sales Order", so)

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


def create_customer_address(type, woocommerce_order, customer):
    """إنشاء عنوان Billing/Shipping جديد لكل Order"""
    address_record = woocommerce_order[type.lower()]
    if not address_record:
        return None

    country = get_country_name(address_record.get("country"))
    if not frappe.db.exists("Country", country):
        country = "Switzerland"

    try:
        address = frappe.get_doc({
            "doctype": "Address",
            "woocommerce_address_id": f"{type}_{woocommerce_order.get('id')}",
            "woocommerce_company_name": address_record.get("company") or '',
            "address_title": f"{customer}_{woocommerce_order.get('id')}",
            "address_type": type,
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
        items.append({
            "item_code": item_code,
            "rate": woocommerce_item.get("price"),
            "delivery_date": nowdate(),
            "qty": woocommerce_item.get("quantity"),
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
    for tax in woocommerce_order.get("tax_lines"):
        woocommerce_tax = get_woocommerce_tax(tax.get("rate_id"))
        rate = woocommerce_tax.get("rate")
        name = woocommerce_tax.get("name")

        taxes.append({
            "charge_type": "Actual",
            "account_head": get_tax_account_head(woocommerce_tax),
            "description": "{0} - {1}%".format(name, rate),
            "rate": rate,
            "tax_amount": flt(tax.get("tax_total") or 0) + flt(tax.get("shipping_tax_total") or 0),
            "included_in_print_rate": 0,
            "cost_center": woocommerce_settings.cost_center
        })
    return taxes


def get_country_name(code):
    country_name = ''
    query = """SELECT `country_name` FROM `tabCountry` WHERE `code` = '{0}'""".format(code.lower())
    for row in frappe.db.sql(query, as_dict=1):
        country_name = row.country_name
    return country_name


def get_tax_account_head(tax):
    tax_title = tax.get("name").encode("utf-8") or tax.get("method_title").encode("utf-8")
    tax_account = frappe.db.get_value("woocommerce Tax Account",
                                      {"parent": "WooCommerce Config", "woocommerce_tax": tax_title}, "tax_account")
    if not tax_account:
        frappe.throw("Tax Account not specified for woocommerce Tax {0}".format(tax.get("name")))
    return tax_account

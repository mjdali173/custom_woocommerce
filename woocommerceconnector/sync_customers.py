from __future__ import unicode_literals
import frappe
from frappe import _
import requests.exceptions
from .woocommerce_requests import get_woocommerce_customers
from .utils import make_woocommerce_log


def sync_customers():
    """Sync all WooCommerce customers to a single fixed Customer in ERPNext"""
    woocommerce_customer_list = []
    sync_woocommerce_customers(woocommerce_customer_list)
    frappe.local.form_dict.count_dict["customers"] = len(woocommerce_customer_list)


def create_customer(*args, **kwargs):
    # Deprecated: We no longer create WooCommerce customers.
    return None

def sync_woocommerce_customers(woocommerce_customer_list):
    for woocommerce_customer in get_woocommerce_customers():
        try:
            create_customer_contact_and_address(woocommerce_customer)
            woocommerce_customer_list.append(woocommerce_customer.get("id"))

        except Exception as e:
            make_woocommerce_log(
                title=e,
                status="Error",
                method="sync_woocommerce_customers",
                message=frappe.get_traceback(),
                request_data=woocommerce_customer,
                exception=True,
            )


def create_customer_contact_and_address(woocommerce_customer):
    """Always link WooCommerce customers to the fixed ERPNext Customer"""
    import frappe.utils.nestedset

    fixed_customer = "woocommerce@alsharaa-dent.com"

    # تأكد أن العميل موجود
    if not frappe.db.exists("Customer", fixed_customer):
        woocommerce_settings = frappe.get_doc("WooCommerce Config", "WooCommerce Config")
        customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": fixed_customer,
            "name": fixed_customer,
            "woocommerce_customer_id": fixed_customer,
            "sync_with_woocommerce": 0,
            "customer_group": woocommerce_settings.customer_group,
            "territory": frappe.utils.nestedset.get_root_of("Territory"),
            "customer_type": _("Individual")
        })
        customer.flags.ignore_mandatory = True
        customer.insert()

    # أنشئ/حدّث العنوان
    create_customer_address(fixed_customer, woocommerce_customer)

    # أنشئ/حدّث الكونتاكت
    create_customer_contact(fixed_customer, woocommerce_customer)


def create_customer_address(customer, woocommerce_customer):
    billing_address = woocommerce_customer.get("billing")
    shipping_address = woocommerce_customer.get("shipping")

    if billing_address and billing_address.get("address_1"):
        try:
            frappe.get_doc({
                "doctype": "Address",
                "address_title": customer,
                "address_type": "Billing",
                "address_line1": billing_address.get("address_1"),
                "address_line2": billing_address.get("address_2") or "",
                "city": billing_address.get("city") or "City",
                "state": billing_address.get("state"),
                "pincode": billing_address.get("postcode"),
                "country": get_country_name(billing_address.get("country")),
                "phone": billing_address.get("phone"),
                "email_id": billing_address.get("email"),
                "links": [{
                    "link_doctype": "Customer",
                    "link_name": customer
                }],
            }).insert(ignore_permissions=True)
        except Exception:
            pass

    if shipping_address and shipping_address.get("address_1"):
        try:
            frappe.get_doc({
                "doctype": "Address",
                "address_title": customer,
                "address_type": "Shipping",
                "address_line1": shipping_address.get("address_1"),
                "address_line2": shipping_address.get("address_2") or "",
                "city": shipping_address.get("city") or "City",
                "state": shipping_address.get("state"),
                "pincode": shipping_address.get("postcode"),
                "country": get_country_name(shipping_address.get("country")),
                "phone": shipping_address.get("phone"),
                "email_id": shipping_address.get("email"),
                "links": [{
                    "link_doctype": "Customer",
                    "link_name": customer
                }],
            }).insert(ignore_permissions=True)
        except Exception:
            pass


def create_customer_contact(customer, woocommerce_customer):
    billing = woocommerce_customer.get("billing") or {}
    try:
        new_contact = frappe.get_doc({
            "doctype": "Contact",
            "first_name": billing.get("first_name") or "Woo",
            "last_name": billing.get("last_name") or "Commerce",
            "links": [{
                "link_doctype": "Customer",
                "link_name": customer
            }]
        })

        if billing.get("email"):
            new_contact.append("email_ids", {
                "email_id": billing.get("email"),
                "is_primary": 1
            })

        if billing.get("phone"):
            new_contact.append("phone_nos", {
                "phone": billing.get("phone"),
                "is_primary_phone": 1
            })

        new_contact.insert(ignore_permissions=True)

    except Exception:
        pass


def get_country_name(code):
    if not code:
        return "Switzerland"
    res = frappe.db.sql(
        """SELECT `country_name` FROM `tabCountry` WHERE `code` = %s""",
        code.lower(), as_dict=1
    )
    return res[0].country_name if res else "Switzerland"

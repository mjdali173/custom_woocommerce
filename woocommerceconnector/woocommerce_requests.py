import requests
import frappe

def get_woocommerce_settings():
    return frappe.get_doc("WooCommerce Config", "WooCommerce Config")

def get_wc_session():
    settings = get_woocommerce_settings()
    return settings.woocommerce_api_url, settings.api_key, settings.api_secret

def get_request(endpoint):
    url, key, secret = get_wc_session()
    res = requests.get(f"{url}/{endpoint}", auth=(key, secret))
    res.raise_for_status()
    return res.json()

def post_request(endpoint, data):
    url, key, secret = get_wc_session()
    res = requests.post(f"{url}/{endpoint}", json=data, auth=(key, secret))
    res.raise_for_status()
    return res.json()

def put_request(endpoint, data):
    url, key, secret = get_wc_session()
    res = requests.put(f"{url}/{endpoint}", json=data, auth=(key, secret))
    res.raise_for_status()
    return res.json()

# -*- coding: utf-8 -*-
# COPYRIGHT (C) 2011-2014 MOBICAGE NV
# ALL RIGHTS RESERVED.
#
# ALTHOUGH YOU MAY BE ABLE TO READ THE CONTENT OF THIS FILE, THIS FILE
# CONTAINS CONFIDENTIAL INFORMATION OF MOBICAGE NV. YOU ARE NOT ALLOWED
# TO MODIFY, REPRODUCE, DISCLOSE, PUBLISH OR DISTRIBUTE ITS CONTENT,
# EMBED IT IN OTHER SOFTWARE, OR CREATE DERIVATIVE WORKS, UNLESS PRIOR
# WRITTEN PERMISSION IS OBTAINED FROM MOBICAGE NV.
#
# THE COPYRIGHT NOTICE ABOVE DOES NOT EVIDENCE ANY ACTUAL OR INTENDED
# PUBLICATION OF SUCH SOURCE CODE.
#
# @@license_version:1.7@@

import argparse, urllib2, json, erppeek
from datetime import datetime

ROGERTHAT_SECRET = 'bnzxlhvyq0 ry;tuyv q345y tpiow5ehuer589ycpqt9uy4t-pm9tq34y,;iouaehjwr092457y98r5ut9-q34yt2w9485hyt08y0^~0*~^'
ODOO_USERNAME = "arno@mobicage.com"
ODOO_PASSWORD = "khdgvxzbadfiuhcopasdbc;dksvjo jdasn;kejs qdadsp"

ACCOUNT_ID_CLIENTS = 403
CURRENCY_EUR = 1
CURRENCY_USD = 3
CURRENCY = dict(EUR=CURRENCY_EUR, USD=CURRENCY_USD)
FISCAL_POSITION_NATIONAL = 1
FISCAL_POSITION_OUTSIDE_EUROPE = 2
FISCAL_POSITION_INSIDE_EUROPE = 3
OSA_JOURNAL = 9
PAYMENT_TERM = 1
ACCOUNT_ID_SALES_IN_BELGIUM = 815
ACCOUNT_ID_SALES_OUTSIDE_EUROPE = 817
ACCOUNT_ID_SALES_INSIDE_EUROPE = 816
TAX_RATE_SERVICES_BELGIUM = 1
TAX_RATE_SERVICES_OUTSIDE_EUROPE = 13
TAX_RATE_SERVICES_INSIDE_EUROPE = 10
TOM_VAN_HECKE = 9

def export_invoices(year, month):
    if year < 100:
        year += 2000
    opener = urllib2.build_opener()
    opener.addheaders = [('X-Rogerthat-Secret', ROGERTHAT_SECRET)]
    url = "https://rogerth.at/shop/invoices/export?year=%s&month=%s" % (year, month)
    return json.load(opener.open(url))

def export_products():
    opener = urllib2.build_opener()
    opener.addheaders = [('X-Rogerthat-Secret', ROGERTHAT_SECRET)]
    url = "https://rogerth.at/shop/products/export"
    return json.load(opener.open(url))

def process_products(data, ep_client, default_company):
    product = erppeek.Model(ep_client, 'product.product')
    products = dict()
    for p in data:
        description = p['description']
        name = p['product_code']
        print "Processing", name, description
        price = p['price'] / 100.0
        osa_reference = p['_key']
        odoo_products = product.browse([['x_osa_reference', '=', p['_key']]])
        if len(odoo_products) > 0:
            odoo_product = odoo_products[0]
            odoo_product.write(dict(description=description, list_price=price))
        else:
            odoo_product = product.create(dict(company_id=default_company, x_osa_reference=osa_reference,
                                               description=description, list_price=price, name=name))
        products[name] = odoo_product
    return products

def process_invoices(data, ep_client, default_company, products):
    for invoice in data:
        print "Processing invoice %s of %s" % (invoice['invoice_number'], invoice['customer']['name'])
        odoo_customer_id = get_customer_id(ep_client, invoice['contact'], invoice['customer'], default_company, invoice['manager'])
        store_invoice(ep_client, invoice, odoo_customer_id, default_company, products, invoice['manager'])

def get_customer_id(ep_client, contact, customer, default_company, manager):
    cust_ref = customer['_key']
    partner_reference = erppeek.Model(ep_client, 'x_partner_reference')
    partner = erppeek.Model(ep_client, 'res.partner')
    refs = partner_reference.browse([['x_osa_reference', '=', cust_ref]])
    if len(refs) == 0:
        # Create customer in odoo
        odoo_customer = put_customer_in_odoo(ep_client, partner, customer, default_company, manager)
    else:
        # Update customer in odoo
        odoo_customer = partner.browse(refs[0].x_partner_id)
        put_customer_in_odoo(ep_client, partner, customer, default_company, manager, odoo_customer)
    # Add / update contact
    contacts = partner.browse([['x_osa_reference', '=', contact['_key']]])
    if len(contacts) == 0:
        odoo_contact = put_contact_in_odoo(ep_client, partner, odoo_customer, customer, contact, default_company, manager)
    else:
        odoo_contact = contacts[0]
        put_contact_in_odoo(ep_client, partner, odoo_customer, customer, contact, default_company, manager, odoo_contact)
    # Add contact as a child of customer
    odoo_contact.parent_id = odoo_customer.id
    return odoo_customer.id

def get_country_by_code(ep_client, code):
    country = erppeek.Model(ep_client, 'res.country')
    countries = country.browse([['code', '=', code]])
    if len(countries) == 0:
        raise Exception('Country with code %s not found in Odoo' % code)
    return countries[0]

def put_contact_in_odoo(ep_client, partner, odoo_customer, customer, contact, default_company, manager, odoo_contact=None):
    address1 = customer['address1']
    address2 = customer['address2']
    zip_code = customer['zip_code']
    city = customer['city']
    partner_name = "%s %s" % (contact['first_name'], contact['last_name'])
    country_code = customer['country']
    email = contact['email']
    osa_reference = contact['_key']
    phone_number = contact['phone_number']
    if odoo_contact is None:
        return create_partner_in_odoo(ep_client, partner, default_company, country_code, address1, address2, zip_code, city, partner_name, None, manager, commercial_partner_id=odoo_customer.id, email=email, osa_reference=osa_reference, phone_number=phone_number)
    else:
        update_odoo_object(odoo_contact, name=partner_name, street=address1, street2=address2, zip=zip_code,
                           vat=None, email=email, phone=phone_number)
        return odoo_contact

def put_customer_in_odoo(ep_client, partner, customer, default_company, manager, odoo_customer=None):
    address1 = customer['address1']
    address2 = customer['address2']
    zip_code = customer['zip_code']
    city = customer['city']
    partner_name = customer['name']
    vat = customer['vat']
    country_code = customer['country']
    if country_code not in ('BE', 'CD', 'US', 'FR', 'ES'):
        raise Exception("Non BE customers ARE NOT SUPPORTED yet.")
    if odoo_customer is not None:
        update_odoo_object(odoo_customer, name=partner_name, street=address1, street2=address2, zip=zip_code,
                           vat=vat)
        return odoo_customer
    else:
        # First check if there is not already a customer with the same VAT
        partners = partner.browse([['vat', '=', customer['vat'].upper()]]) if customer['vat'] else []
        if len(partners) > 0:
            new_partner = partners[0]
            update_odoo_object(new_partner, name=partner_name, street=address1, street2=address2, zip=zip_code,
                               vat=vat)
        else:
            # Create partner
            new_partner = create_partner_in_odoo(ep_client, partner, default_company, country_code, address1, address2, zip_code, city, partner_name, vat, manager)
        partner_reference = erppeek.Model(client, 'x_partner_reference')
        partner_reference.create(dict(x_osa_reference=customer['_key'], x_partner_id=new_partner.id))
        return new_partner

def update_odoo_object(odoo_object, **values):
    odoo_object.write(values)

def create_partner_in_odoo(ep_client, partner, default_company, country_code, address1, address2, zip_code, city, partner_name, vat, manager, commercial_partner_id=None, email=None, osa_reference=None, phone_number=None):
    country = get_country_by_code(ep_client, country_code)
    data = dict(active=True, company_id=default_company,
        country_id=country.id, customer='True', name=partner_name,
        is_company=True if vat else False,
        street=address1, street2=address2, supplier=False,
        tz='Europe/Brussels', zip=zip_code, city=city,
        user_id=get_user_id(ep_client, manager),
        vat=vat, vat_subjected=True if vat else False,
        ##### TECHNICAL PROPERTIES ####
        property_account_payable=484, property_account_position=1,
        property_account_receivable=403, property_payment_term=1,
        property_product_pricelist=1, property_supplier_payment_term=False)
    if commercial_partner_id is not None:
        data['commercial_partner_id'] = commercial_partner_id
    if email:
        data['email'] = email
    if osa_reference:
        data['x_osa_reference'] = osa_reference
    if phone_number:
        data['phone'] = phone_number
    return partner.create(data)

def store_invoice(ep_client, osa_invoice, odoo_customer_id, default_company, products, manager):
    invoice = erppeek.Model(ep_client, 'account.invoice')
    invoices = invoice.browse([['number', '=', osa_invoice['invoice_number']]])
    if len(invoices) > 0:
        return False
    if osa_invoice['customer']['country'] == 'BE':
        fiscal_position = FISCAL_POSITION_NATIONAL
        account_id = ACCOUNT_ID_SALES_IN_BELGIUM
        tax_rate = TAX_RATE_SERVICES_BELGIUM
    elif osa_invoice['customer']['country'] in ('CD', 'US'):
        fiscal_position = FISCAL_POSITION_OUTSIDE_EUROPE
        account_id = ACCOUNT_ID_SALES_OUTSIDE_EUROPE
        tax_rate = TAX_RATE_SERVICES_OUTSIDE_EUROPE
    elif osa_invoice['customer']['country'] in ('FR', 'ES'):
        fiscal_position = FISCAL_POSITION_INSIDE_EUROPE
        account_id = ACCOUNT_ID_SALES_INSIDE_EUROPE
        tax_rate = TAX_RATE_SERVICES_INSIDE_EUROPE
    else:
        raise Exception("Oops, do not know what to do here ...")
    invoice_date = datetime.utcfromtimestamp(osa_invoice['date'])
    odoo_invoice = invoice.create(dict(commercial_partner_id=odoo_customer_id, company_id=default_company,
                        account_id=ACCOUNT_ID_CLIENTS,  # Clients
                        currency_id=CURRENCY[osa_invoice['currency_code']],  # EUR
                        fiscal_position=fiscal_position,  # National
                        journal_id=OSA_JOURNAL,  # Test City App (EUR)
                        partner_id=odoo_customer_id,
                        user_id=get_user_id(ep_client, manager),
                        payment_term=PAYMENT_TERM,
                        date_invoice="%s-%02d-%02d" % (invoice_date.year, invoice_date.month, invoice_date.day),
                        number=osa_invoice['invoice_number'],
                        type='out_invoice'))
    invoice_line = erppeek.Model(ep_client, 'account.invoice.line')
    for item in osa_invoice['order_items']:
        data = dict(account_id=account_id,  # Ventes en Belgique
            company_id=default_company,
            invoice_id=odoo_invoice.id,
            name=item['product_code'],
            partner_id=odoo_customer_id,
            price_unit=item['price'] / 100.0,
            product_id=products[item['product_code']].id,
            invoice_line_tax_id=[tax_rate],  # 21% for services in Belgium
            quantity=item['count'] * 1.0)
        invoice_line.create(data)
    client.execute('account.invoice', 'button_reset_taxes', odoo_invoice.id)
    odoo_invoice.refresh()
    odoo_amount = round(odoo_invoice.amount_total * 100)
    osa_amount = osa_invoice['total_amount']
    if odoo_amount != osa_amount and abs(int(odoo_amount) - osa_amount) > 1:
        raise Exception('Total of invoice in Odoo (%s) does not match total of invoice in OSA (%s).' % (odoo_amount, osa_amount))
    # client.execute('account.invoice', 'invoice_validate', odoo_invoice.id)
    client.exec_workflow('account.invoice', 'invoice_open', odoo_invoice.id)
    odoo_invoice.refresh()
    if odoo_invoice.number != osa_invoice['invoice_number']:
        raise Exception('''Odoo supplied invoice number does not match OSA assigned invoice number!
Odoo invoice: %s
OSA invoice: %s''' % (odoo_invoice.number, osa_invoice['invoice_number']))

user_cache = dict()
def get_user_id(ep_client, email):
    if not email:
        return TOM_VAN_HECKE
    if email == "customers@shop":
        email = "customers@mobicage.com"
    if email in user_cache:
        return user_cache[email]
    res_users = erppeek.Model(ep_client, 'res.users')
    users = res_users.browse([['email', '=', email]])
    if len(users) > 0:
        user_id = users[0].id
        user_cache[email] = user_id
        return user_id
    raise Exception("No user account for %s" % email)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("year", type=int)
    parser.add_argument("month", help="The month to export (January = 1)", type=int)
    parser.add_argument("odoo_server", type=str)
    parser.add_argument("odoo_database", type=str)
    parser.add_argument("odoo_username", type=str)
    parser.add_argument("odoo_password", type=str)
    parser.add_argument("default_company", type=str, default="Mobicage NV")
    args = parser.parse_args()
    # client = erppeek.Client(args.odoo_server, args.odoo_database, args.odoo_username, args.odoo_password)
    client = erppeek.Client(args.odoo_server, "production", ODOO_USERNAME, ODOO_PASSWORD)

    # Get default company id
    company = erppeek.Model(client, 'res.company')
    companies = company.browse([['name', '=', args.default_company]])
    if len(companies) == 0:
        raise Exception("Could not find default company")
    default_company = companies[0].id

    data = export_products()
    print data
    products = process_products(data, client, default_company)
    data = export_invoices(args.year, args.month)
    process_invoices(data, client, default_company, products)

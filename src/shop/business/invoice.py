# -*- coding: utf-8 -*-
# Copyright 2017 Mobicage NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# @@license_version:1.2@@

from datetime import datetime
import logging
import time

from babel.dates import format_datetime
from babel.numbers import format_currency

from google.appengine.ext import db
from mcfw.rpc import arguments, returns
from rogerthat.bizz.job import run_job
from rogerthat.dal import put_and_invalidate_cache
from rogerthat.models.utils import allocate_id
from rogerthat.settings import get_server_settings
from rogerthat.utils import now, send_mail
from rogerthat.utils.transactions import run_in_xg_transaction
from shop import SHOP_JINJA_ENVIRONMENT, SHOP_TEMPLATES_FOLDER
from shop.business.i18n import SHOP_DEFAULT_LANGUAGE
from shop.dal import get_mobicage_legal_entity
from shop.models import Invoice, Customer, OrderItem, Product, LegalEntity, Order, Charge, OrderNumber, ChargeNumber, \
    RegioManagerTeam, InvoiceNumber
from solution_server_settings import get_solution_server_settings
from xhtml2pdf import pisa


try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


def export_reseller_invoices(start_date, end_date, do_send_email):
    run_job(qry, [], create_reseller_invoice_for_legal_entity, [start_date, end_date, do_send_email])


def qry():
    return LegalEntity.list_billable()


@returns()
@arguments(legal_entity=LegalEntity, start_date=(int, long), end_date=(int, long), do_send_email=bool)
def create_reseller_invoice_for_legal_entity(legal_entity, start_date, end_date, do_send_email=True):
    """
    Args:
        legal_entity (LegalEntity) 
        start_date (long)
        end_date (long)
        do_send_email (bool)
    """
    if legal_entity.is_mobicage:
        # To avoid a composite index we don't filter on is_mobicage
        return
    solution_server_settings = get_solution_server_settings()
    from_email = solution_server_settings.shop_no_reply_email
    to_emails = solution_server_settings.shop_payment_admin_emails
    mobicage_legal_entity = get_mobicage_legal_entity()
    logging.info('Exporting reseller invoices for legal entity %s(id %d) from %s(%s) to %s(%s)', legal_entity.name,
                 legal_entity.id, start_date, time.ctime(start_date), end_date, time.ctime(end_date))
    invoices = list(Invoice.all()
                    .filter('legal_entity_id', legal_entity.id)
                    .filter('paid_timestamp >', start_date)
                    .filter('paid_timestamp <', end_date)
                    .filter('paid', True)
                    .filter('payment_type IN', (Invoice.PAYMENT_MANUAL, Invoice.PAYMENT_MANUAL_AFTER)))
    start_time = time.strftime('%m/%d/%Y', time.gmtime(int(start_date)))
    end_time = time.strftime('%m/%d/%Y', time.gmtime(int(end_date)))
    if not invoices:
        message = 'No new invoices for reseller %s for period %s - %s' % (legal_entity.name, start_time, end_time)
        logging.info(message)
        if do_send_email:
            send_mail(from_email, to_emails, message, message)
        return
    items_per_customer = {}
    customers_to_get = set()
    products = {p.code: p for p in Product.list_by_legal_entity(legal_entity.id)}
    for invoice in invoices:
        # get all subscription order items
        order_items = list(OrderItem.list_by_order(invoice.order_key))
        for item in reversed(order_items):
            product = products[item.product_code]
            # We're only interested in subscription items
            if product.is_subscription or product.is_subscription_extension or product.is_subscription_discount:
                if invoice.customer_id not in items_per_customer:
                    items_per_customer[invoice.customer_id] = []
                    customers_to_get.add(Customer.create_key(invoice.customer_id))
                items_per_customer[invoice.customer_id].append(item)
            else:
                order_items.remove(item)
    if not customers_to_get:
        message = 'No new invoices containing subscriptions for reseller %s for period %s - %s' % (
            legal_entity.name, start_time, end_time)
        logging.info(message)
        if do_send_email:
            send_mail(from_email, to_emails, message, message)
        return
    customers = {c.id: c for c in db.get(customers_to_get)}
    product_totals = {}
    for customer_id in items_per_customer:
        items = items_per_customer[customer_id]
        for item in items:
            if item.product_code not in product_totals:
                product_totals[item.product_code] = {'count': 0,
                                                     'price': int(item.price * legal_entity.revenue_percent)}
            product_totals[item.product_code]['count'] += item.count
    total_amount = 0
    for product in product_totals:
        p = product_totals[product]
        price = p['count'] * p['price']
        p['total_price'] = format_currency(price / 100., legal_entity.currency_code,
                                           locale=mobicage_legal_entity.country_code)
        total_amount += price
    total_amount_formatted = format_currency(total_amount / 100., legal_entity.currency_code,
                                             locale=mobicage_legal_entity.country_code)
    vat_amount = total_amount / mobicage_legal_entity.vat_percent if mobicage_legal_entity.country_code == legal_entity.country_code else 0
    vat_amount_formatted = format_currency(vat_amount / 100., legal_entity.currency_code,
                                           locale=mobicage_legal_entity.country_code)
    from_date = format_datetime(datetime.utcfromtimestamp(start_date), locale=SHOP_DEFAULT_LANGUAGE,
                                format='dd/MM/yyyy HH:mm')
    until_date = format_datetime(datetime.utcfromtimestamp(end_date), locale=SHOP_DEFAULT_LANGUAGE,
                                 format='dd/MM/yyyy HH:mm')
    
    solution_server_settings = get_solution_server_settings()
    template_variables = {
        'products': products,
        'customers': customers,
        'invoices': invoices,
        'items_per_customer': items_per_customer,
        'product_totals': product_totals.items(),
        'mobicage_legal_entity': mobicage_legal_entity,
        'legal_entity': legal_entity,
        'language': SHOP_DEFAULT_LANGUAGE,
        'from_date': from_date,
        'until_date': until_date,
        'revenue_percent': legal_entity.revenue_percent,
        'vat_amount_formatted': vat_amount_formatted,
        'total_amount_formatted': total_amount_formatted,
        'logo_path': '../html/img/osa_white_en_250.jpg',
        'tos_link': '<a href="%s">%s</a>' % (solution_server_settings.shop_privacy_policy_url,
                                             solution_server_settings.shop_privacy_policy_url)
    }
    source_html = SHOP_JINJA_ENVIRONMENT.get_template('invoice/reseller_invoice.html').render(template_variables)
    output_stream = StringIO()
    pisa.CreatePDF(src=source_html, dest=output_stream, path='%s/invoice' % SHOP_TEMPLATES_FOLDER)
    invoice_pdf_contents = output_stream.getvalue()
    output_stream.close()
    # Create an order, order items, charge and invoice.
    _now = now()
    customer = legal_entity.get_or_create_customer()
    mobicage_team = RegioManagerTeam.get_mobicage()

    def trans():
        to_put = list()
        order_number = OrderNumber.next(mobicage_legal_entity)
        order_key = db.Key.from_path(Order.kind(), order_number, parent=customer.key())
        order = Order(key=order_key)
        order.contact_id = legal_entity.contact_id
        order.date = _now
        order.vat_pct = mobicage_legal_entity.vat_percent if legal_entity.country_code == mobicage_legal_entity.country_code else 0
        order.amount = int(round(total_amount))
        order.vat = int(round(vat_amount))
        order.total_amount = int(round(total_amount + vat_amount))
        order.is_subscription_order = False
        order.is_subscription_extension_order = False
        order.team_id = mobicage_team.id
        order.manager = customer.manager
        order.status = Order.STATUS_SIGNED
        to_put.append(order)

        for i, (product_code, item) in enumerate(product_totals.iteritems()):
            order_item = OrderItem(parent=order_key)
            order_item.number = i + 1
            order_item.comment = products[product_code].default_comment(SHOP_DEFAULT_LANGUAGE)
            order_item.product_code = product_code
            order_item.count = item['count']
            order_item.price = item['price']
            to_put.append(order_item)

        charge_key = Charge.create_key(allocate_id(Charge), order_number, customer.id)
        charge = Charge(key=charge_key)
        charge.date = _now
        charge.type = Charge.TYPE_ORDER_DELIVERY
        charge.amount = order.amount
        charge.vat_pct = order.vat_pct
        charge.vat = order.vat
        charge.total_amount = order.total_amount
        charge.manager = order.manager
        charge.team_id = order.team_id
        charge.charge_number = ChargeNumber.next(mobicage_legal_entity)
        charge.currency_code = legal_entity.currency_code
        to_put.append(charge)

        invoice_number = InvoiceNumber.next(mobicage_legal_entity)
        invoice = Invoice(key_name=invoice_number,
                          parent=charge,
                          amount=charge.amount,
                          vat_pct=charge.vat_pct,
                          vat=charge.vat,
                          total_amount=charge.total_amount,
                          currency_code=legal_entity.currency_code,
                          date=_now,
                          payment_type=Invoice.PAYMENT_MANUAL_AFTER,
                          operator=charge.manager,
                          paid=False,
                          legal_entity_id=mobicage_legal_entity.id,
                          pdf=invoice_pdf_contents)
        charge.invoice_number = invoice_number
        to_put.append(invoice)
        put_and_invalidate_cache(*to_put)
        return order, charge, invoice

    order, charge, invoice = run_in_xg_transaction(trans)

    if do_send_email:
        serving_url = '%s/internal/shop/invoice/pdf?customer_id=%d&order_number=%s&charge_id=%d&invoice_number=%s' % (
            get_server_settings().baseUrl, customer.id, order.order_number, charge.id, invoice.invoice_number)
        subject = 'New reseller invoice for %s, %s - %s' % (legal_entity.name, start_time, end_time)
        body_text = 'A new invoice is available for reseller %s for period %s to %s here: %s' % (
        legal_entity.name, start_time, end_time, serving_url)

        send_mail(from_email, to_emails, subject, body_text)

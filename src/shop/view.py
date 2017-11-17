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

import base64
import csv
import datetime
import json
import logging
import os
import re
import urllib
from cgi import FieldStorage
from collections import namedtuple
from datetime import date, timedelta
from types import NoneType

import webapp2
from google.appengine.api import urlfetch, users as gusers
from google.appengine.ext import db, deferred
from google.appengine.ext.webapp import template

from PIL.Image import Image  # @UnresolvedImport
from PyPDF2.merger import PdfFileMerger
from add_1_monkey_patches import DEBUG, APPSCALE
from babel.dates import format_date
from googleapiclient.discovery import build
from mcfw.cache import cached
from mcfw.consts import MISSING
from mcfw.properties import azzert
from mcfw.restapi import rest
from mcfw.rpc import arguments, returns, serialize_complex_value
from rogerthat.bizz import channel
from rogerthat.bizz.gcs import upload_to_gcs
from rogerthat.bizz.profile import create_user_profile
from rogerthat.bizz.session import switch_to_service_identity, create_session
from rogerthat.consts import FAST_QUEUE, OFFICIALLY_SUPPORTED_COUNTRIES, ROGERTHAT_ATTACHMENTS_BUCKET
from rogerthat.dal import put_and_invalidate_cache
from rogerthat.dal.app import get_apps
from rogerthat.dal.profile import get_service_profile, get_profile_info
from rogerthat.dal.service import get_default_service_identity
from rogerthat.exceptions import ServiceExpiredException
from rogerthat.models import App, ServiceProfile
from rogerthat.rpc import users
from rogerthat.rpc.service import BusinessException
from rogerthat.settings import get_server_settings
from rogerthat.to import ReturnStatusTO, RETURNSTATUS_TO_SUCCESS
from rogerthat.to.app import AppInfoTO
from rogerthat.utils import now, send_mail
from rogerthat.utils.channel import broadcast_via_iframe_result
from rogerthat.utils.cookie import set_cookie
from rogerthat.utils.service import create_service_identity_user
from rogerthat.utils.transactions import on_trans_committed, allow_transaction_propagation
from shop import SHOP_JINJA_ENVIRONMENT
from shop.bizz import search_customer, create_or_update_customer, \
    audit_log, generate_order_or_invoice_pdf, generate_transfer_document_image, TROPO_SESSIONS_URL, \
    PaymentFailedException, list_prospects, set_prospect_status, find_city_bounds, \
    put_prospect, put_regio_manager, is_admin, is_payment_admin, dict_str_for_audit_log, link_prospect_to_customer, \
    list_history_tasks, put_hint, delete_hint, \
    get_invoices, get_regiomanager_statistics, get_prospect_history, get_payed, put_surrounding_apps, \
    create_contact, create_order, export_customers_csv, put_service, update_contact, put_regio_manager_team, \
    user_has_permissions_to_team, get_regiomanagers_by_app_id, delete_contact, cancel_order, \
    finish_on_site_payment, send_payment_info, manual_payment, post_app_broadcast, shopOauthDecorator, \
    regio_manager_has_permissions_to_team, get_customer_charges, is_team_admin, user_has_permissions_to_question, \
    put_app_signup_enabled, sign_order
from shop.business.charge import cancel_charge
from shop.business.creditcard import link_stripe_to_customer
from shop.business.expired_subscription import set_expired_subscription_status, delete_expired_subscription
from shop.business.i18n import shop_translate, get_languages, CURRENCIES
from shop.business.legal_entities import put_legal_entity
from shop.business.order import get_customer_subscription_length, cancel_subscription, get_subscription_order, \
    set_next_charge_date
from shop.business.product import list_products
from shop.business.prospect import search_prospects, generate_prospect_export_excel
from shop.business.qr import generate_unassigned_qr_codes_zip_for_app
from shop.constants import OFFICIALLY_SUPPORTED_LANGUAGES, COUNTRY_DEFAULT_LANGUAGES, \
    LOGO_LANGUAGES, PROSPECT_CATEGORY_KEYS, STORE_MANAGER
from shop.dal import get_shop_loyalty_slides, get_shop_loyalty_slides_new_order, get_mobicage_legal_entity
from shop.exceptions import DuplicateCustomerNameException, ReplaceBusinessException, NoSubscriptionFoundException, \
    CustomerNotFoundException, NoPermissionException
from shop.jobs.migrate_service import migrate_and_create_user_profile
from shop.jobs.migrate_user import migrate as migrate_user
from shop.jobs.prospects import find_prospects, get_grid
from shop.jobs.remove_regio_manager import remove_regio_manager
from shop.models import Customer, Contact, normalize_vat, Order, Invoice, Charge, RegioManager, Prospect, \
    ProspectInteractions, ShopLoyaltySlide, ShopApp, \
    ProspectRejectionReason, ShopTask, ShopLoyaltySlideNewOrder, RegioManagerTeam, RegioManagerStatistic, \
    ExpiredSubscription, LegalEntity
from shop.to import CustomerTO, ContactTO, OrderItemTO, CompanyTO, CustomerServiceTO, CustomerReturnStatusTO, \
    ContactReturnStatusTO, CreateOrderReturnStatusTO, JobReturnStatusTO, JobStatusTO, SignOrderReturnStatusTO, \
    CityBoundsReturnStatusTO, ShopAppTO, PointTO, ProspectsMapTO, TaskListTO, ProspectDetailsTO, ProspectReturnStatusTO, \
    RegioManagerReturnStatusTO, RegioManagerTeamsTO, AppRightsTO, ModulesReturnStatusTO, OrderAndInvoiceTO, \
    RegioManagerStatisticTO, ProspectHistoryTO, SimpleAppTO, TaskTO, ProductTO, RegioManagerTeamTO, \
    ProspectTO, RegioManagerTO, SubscriptionLengthReturnStatusTO, OrderReturnStatusTO, LegalEntityTO, \
    LegalEntityReturnStatusTO, CustomerChargesTO
from solution_server_settings import get_solution_server_settings
from solutions.common.bizz import SolutionModule, get_all_existing_broadcast_types
from solutions.common.bizz.city_vouchers import put_city_voucher_settings, put_city_voucher_user, \
    delete_city_voucher_user
from solutions.common.bizz.locations import create_new_location
from solutions.common.bizz.loyalty import update_all_user_data_admins
from solutions.common.bizz.qanda import re_index_question
from solutions.common.dal import get_solution_settings
from solutions.common.dal.cityapp import get_service_user_for_city, invalidate_service_user_for_city
from solutions.common.dal.hints import get_all_solution_hints, get_solution_hints
from solutions.common.models.city_vouchers import SolutionCityVoucherSettings
from solutions.common.models.qanda import Question, QuestionReply
from solutions.common.to import ProvisionReturnStatusTO
from solutions.common.to.hints import SolutionHintTO
from solutions.common.to.loyalty import LoyaltySlideTO, LoyaltySlideNewOrderTO
from solutions.common.utils import get_extension_for_content_type
from xhtml2pdf import pisa

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


@returns(ReturnStatusTO)
def wrap_with_result_status(f, *args, **kwargs):
    try:
        f(*args, **kwargs)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException as e:
        return ReturnStatusTO.create(False, e.message)


def _get_solution_modules():
    return SolutionModule.shop_modules()


def _get_default_modules():
    return (SolutionModule.AGENDA,
            SolutionModule.ASK_QUESTION,
            SolutionModule.BROADCAST,
            SolutionModule.BULK_INVITE,
            SolutionModule.QR_CODES,
            SolutionModule.WHEN_WHERE,
            SolutionModule.BILLING,
            SolutionModule.STATIC_CONTENT
            )


def get_current_http_host(with_protocol=False):
    host = os.environ.get('HTTP_X_FORWARDED_HOST') or os.environ.get('HTTP_HOST')
    if with_protocol:
        return u'%s://%s' % (os.environ['wsgi.url_scheme'], host)
    return host


def _get_apps():
    return sorted(get_apps([App.APP_TYPE_ROGERTHAT, App.APP_TYPE_CITY_APP]),
                  key=lambda app: app.name)


def _get_default_organization_types():
    # organization_type value, description, selected by default
    organization_types = [(ServiceProfile.ORGANIZATION_TYPE_CITY, 'Community Service', False),
                          (ServiceProfile.ORGANIZATION_TYPE_EMERGENCY, 'Care', False),
                          (ServiceProfile.ORGANIZATION_TYPE_NON_PROFIT, 'Association', False),
                          (ServiceProfile.ORGANIZATION_TYPE_PROFIT, 'Merchant', True),
                          ]
    return sorted(organization_types, key=lambda x: x[1])


def authorize_manager():
    user = gusers.get_current_user()

    if is_admin(user):
        return True

    manager = RegioManager.get_by_key_name(user.email())
    return bool(manager)


@cached(1, request=True, memcache=False)
@returns(RegioManager)
@arguments(user=users.User)
def get_regional_manager(user):
    user = user or gusers.get_current_user()
    regio_manager = RegioManager.get(RegioManager.create_key(user.email()))
    return regio_manager


def get_shop_context(**kwargs):
    user = gusers.get_current_user()
    solution_server_settings = get_solution_server_settings()

    team_admin = False
    if is_admin(user):
        current_user_apps = _get_apps()
    else:
        manager = get_regional_manager(user)
        team_admin = manager and manager.admin
        regio_manager_team = manager.team
        current_user_apps_unfiltered = App.get([App.create_key(app_id) for app_id in regio_manager_team.app_ids])
        current_user_apps = sorted([app for app in current_user_apps_unfiltered if app.visible], key=lambda app: app.name)

    # These are the variables used in base.html
    js_templates = kwargs.pop('js_templates', dict())
    if 'prospect_comment' not in js_templates:
        js_templates.update(render_js_templates(['prospect_comment', 'prospect_types', 'prospect_task_history']))
    ctx = dict(stripePublicKey=solution_server_settings.stripe_public_key,
               modules=_get_solution_modules(),
               default_modules=_get_default_modules(),
               static_modules=SolutionModule.STATIC_MODULES,
               current_user_apps=current_user_apps,
               admin=is_admin(user),
               team_admin=team_admin,
               payment_admin=is_payment_admin(user),
               broadcast_types=get_all_existing_broadcast_types(),
               js_templates=json.dumps(js_templates),
               prospect_reasons_json=u"[]",
               disabled_reasons_json=json.dumps(Customer.DISABLED_REASONS),
               appointment_types=sorted(ShopTask.APPOINTMENT_TYPES.iteritems(), key=lambda (k, v): v),
               languages=sorted(OFFICIALLY_SUPPORTED_LANGUAGES.iteritems(), key=lambda (k, v): v),
               languages_json=json.dumps(OFFICIALLY_SUPPORTED_LANGUAGES),
               countries=sorted(OFFICIALLY_SUPPORTED_COUNTRIES.iteritems(), key=lambda (k, v): v),
               countries_json=json.dumps(OFFICIALLY_SUPPORTED_COUNTRIES),
               default_languages_json=json.dumps(COUNTRY_DEFAULT_LANGUAGES),
               logo_languages_json=json.dumps(LOGO_LANGUAGES),
               PROSPECT_CATEGORIES=PROSPECT_CATEGORY_KEYS,
               CURRENCIES=json.dumps(CURRENCIES),
               prospect_status_type_strings=json.dumps(Prospect.STATUS_TYPES),
               DEBUG=DEBUG,
               APPSCALE=APPSCALE,
               organization_types=_get_default_organization_types(),
               )
    ctx.update(kwargs)
    return ctx


def render_js_templates(tmpl_names, is_folders=False):
    templates = dict()
    if is_folders:
        for folder in tmpl_names:
            path = os.path.join(os.path.dirname(__file__), 'templates', 'js', folder)
            for template_file in os.listdir(path):
                with open(os.path.join(path, template_file)) as f:
                    templates[template_file.replace('.html', '').replace('.tmpl', '')] = f.read()
    else:
        for tmpl in tmpl_names:
            with open(os.path.join(os.path.dirname(__file__), 'templates', 'js', '%s.html' % tmpl)) as f:
                templates[tmpl] = f.read()
    return templates


class BizzManagerHandler(webapp2.RequestHandler):
    def dispatch(self):
        if not authorize_manager():
            self.abort(401)
        return super(BizzManagerHandler, self).dispatch()


class BizzAdminHandler(BizzManagerHandler):
    @shopOauthDecorator.oauth_required
    def get(self, *args, **kwargs):
        credentials = shopOauthDecorator.credentials  # type: Credentials

        try:
            http_auth = credentials.authorize(shopOauthDecorator.http())
            calendar_service = build('calendar', 'v3', http=http_auth)
            now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
            calendar_service.events().list(calendarId='primary', timeMin=now, maxResults=10, singleEvents=True, orderBy='startTime').execute()
        except Exception, e:
            logging.error('An error occurred while loading events: %s', e)

        user = gusers.get_current_user()
        regiomanager = RegioManager.get(RegioManager.create_key(user.email()))
        # always save the latest credentials in the datastore.
        if regiomanager:
            logging.info('Setting google credentials for user %s' % user.nickname())
            regiomanager.credentials = credentials
            regiomanager.put()

        if self.request.get('iframe', 'false') != 'true':
            # loads admin.html in an iframe
            path = os.path.join(os.path.dirname(__file__), 'html', 'index.html')
            context = dict(DEBUG=DEBUG,
                           APPSCALE=APPSCALE,
                           )
            channel.append_firebase_params(context)
        else:
            path = os.path.join(os.path.dirname(__file__), 'html', 'admin.html')
            context = get_shop_context()
        self.response.out.write(template.render(path, context))

class ShopLogoutHandler(webapp2.RequestHandler):

    def get(self):
        self.redirect(gusers.create_logout_url("/internal/shop"))

class OrdersHandler(BizzManagerHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'html', 'orders.html')
        user = gusers.get_current_user()
        orders = Order.all().filter("status =", 0)
        manager = RegioManager.get(RegioManager.create_key(user.email()))
        if manager and manager.admin:
            orders.filter("team_id =", manager.team_id)
        elif not is_admin(user):
            orders.filter("manager =", user)
        orders.order("-date")
        filtered_orders = list()
        to_get = list()
        for order in orders:
            if order.order_number != Order.CUSTOMER_STORE_ORDER_NUMBER:
                filtered_orders.append(order)
                to_get.append(order.customer_key)
        customers = db.get(to_get)
        context = get_shop_context(orders=zip(filtered_orders, customers), managers=RegioManager.all().order("name"))
        self.response.out.write(template.render(path, context))


class OrderPdfHandler(BizzManagerHandler):
    def get(self):
        customer_id = long(self.request.get("customer_id"))
        order_number = self.request.get("order_number")
        download = self.request.get("download", "false") == "true"

        self.response.headers['Content-Type'] = 'application/pdf'
        self.response.headers['Content-Disposition'] = str('%s; filename=order_%s.pdf' % ("attachment" if download else "inline", order_number))

        customer = Customer.get_by_id(customer_id)
        order = Order.get_by_key_name(order_number, parent=customer)

        # Audit
        if download:
            audit_log(customer_id, "Downloaded order")
        else:
            audit_log(customer_id, "Viewed order")

        if order.pdf:
            self.response.out.write(order.pdf)
        else:
            generate_order_or_invoice_pdf(self.response.out, customer, order)


class ChargesHandler(BizzManagerHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'html', 'charges.html')
        context = get_shop_context(js_templates=render_js_templates(['charge']))
        self.response.out.write(template.render(path, context))


class InvoicePdfHandler(BizzManagerHandler):
    def get(self):
        customer_id = long(self.request.get("customer_id"))
        order_number = self.request.get("order_number")
        charge_id = long(self.request.get("charge_id"))
        invoice_number = self.request.get("invoice_number")
        download = self.request.get("download", "false") == "true"

        self.response.headers['Content-Type'] = 'application/pdf'
        self.response.headers['Content-Disposition'] = str('%s; filename=invoice_%s.pdf' % ("attachment" if download else "inline", invoice_number))

        # Audit
        if download:
            audit_log(customer_id, "Downloaded invoice")
        else:
            audit_log(customer_id, "Viewed invoice")


        customer, order, charge = db.get([Customer.create_key(customer_id), Order.create_key(customer_id, order_number), Charge.create_key(charge_id, order_number, customer_id)])

        invoice = db.get(Invoice.create_key(customer_id, order_number, charge_id, invoice_number)) if invoice_number else None

        if invoice:
            logging.info("Invoice found, serving existing invoice.")
            if not invoice.pdf:
                logging.error("Attempt to download invoice without pdf.")
                self.error(500)
            self.response.out.write(invoice.pdf)
        else:
            logging.info("Invoice not found, generating PRO Forma invoice.")
            charge = db.get(Charge.create_key(long(charge_id), order_number, customer_id))
            img = generate_transfer_document_image(charge)
            payment_note = "data:image/png;base64,%s" % base64.b64encode(img.getvalue())
            generate_order_or_invoice_pdf(self.response.out, customer, order, invoice, True, payment_note,
                                          charge=charge)


class OpenInvoicesHandler(BizzManagerHandler):
    def get(self):
        current_user = gusers.get_current_user()
        if not is_admin(current_user):
            self.abort(403)
        invoices = list(Invoice.all().filter("payment_type =", Invoice.PAYMENT_MANUAL_AFTER).filter("paid =", False).order("-date"))
        charges = db.get([i.parent_key() for i in invoices])
        orders = db.get([c.parent_key() for c in charges])
        customers = db.get([o.parent_key() for o in orders])
        items = [dict(zip(['invoice', 'charge', 'order', 'customer'], x))
                 for x in zip(invoices, charges, orders, customers)]

        today = date.today()

        # Monkey patch problem in PIL
        merger = PdfFileMerger()
        orig_to_bytes = getattr(Image, "tobytes", None)
        try:
            if orig_to_bytes is None:
                Image.tobytes = Image.tostring
            html_dir = os.path.join(os.path.dirname(__file__), 'html')
            for data in items:
                customer = data['customer']
                data['today'] = format_date(today, locale=customer.language, format='full')
                data['until'] = format_date(today + timedelta(days=7), locale=customer.language, format='full')
                data['language'] = customer.language
                source_html = SHOP_JINJA_ENVIRONMENT.get_template('invoice_letter_pdf.html').render(data)
                stream = StringIO()
                pisa.CreatePDF(src=source_html, dest=stream, path=html_dir)
                stream.seek(0)
                merger.append(stream)
                stream = StringIO(data['invoice'].pdf)
                merger.append(stream)
        finally:
            if orig_to_bytes is None:
                delattr(Image, "tobytes")

        self.response.headers['Content-Type'] = 'application/pdf'
        self.response.headers['Content-Disposition'] = str('attachment; filename=invoices.pdf')

        stream = StringIO()
        merger.write(stream)
        merger.close()
        self.response.out.write(stream.getvalue())


class QuestionsHandler(BizzManagerHandler):
    def get(self):
        current_user = gusers.get_current_user()
        manager = RegioManager.get(RegioManager.create_key(current_user.email()))
        admin = is_admin(current_user)
        if not admin:
            if not (manager and manager.admin):
                return self.abort(403)

        team_id = self.request.get('team')
        team_id = long(team_id) if team_id else None
        questions_qry = Question.all().order('-timestamp')
        if not admin:
            # show only the team questions to the manager
            questions_qry.filter('team_id =', manager.team.id)
        else:
            # filter if team id is provided for admin
            if team_id:
                questions_qry.filter('team_id =', int(team_id))

        questions = []
        teams = {team.id: team for team in RegioManagerTeam.all()}
        for question in questions_qry:  # type: Question
            question.team = teams[question.team_id]
            questions.append(question)
        path = os.path.join(os.path.dirname(__file__), 'html', 'questions.html')
        show_team_switcher = admin or manager.team.is_mobicage
        context = get_shop_context(questions=questions,
                                   show_team_switcher=show_team_switcher,
                                   teams=teams,
                                   selected_team=team_id,
                                   js_templates=render_js_templates(['teams_select_modal']))
        self.response.out.write(template.render(path, context))


class QuestionsDetailHandler(BizzManagerHandler):
    def get(self, question_id):
        current_user = gusers.get_current_user()
        question = Question.get_by_id(long(question_id))
        if not user_has_permissions_to_question(current_user, question):
            return self.abort(403)

        path = os.path.join(os.path.dirname(__file__), 'html', 'questions_detail.html')
        context = get_shop_context(question=question)
        self.response.out.write(template.render(path, context))


class RegioManagersHandler(BizzManagerHandler):
    def get(self):
        current_user = gusers.get_current_user()
        if not is_admin(current_user):
            self.abort(403)
        path = os.path.join(os.path.dirname(__file__), 'html', 'regio_managers.html')
        context = get_shop_context(js_templates=render_js_templates(['regio_manager_list',
                                                                     'regio_manager_team_apps',
                                                                     'regio_manager_app_rights']),
                                   legal_entities=LegalEntity.list_all())
        self.response.out.write(template.render(path, context))


class TasksHandler(BizzManagerHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'html', 'tasks.html')
        prospect_reasons = sorted((x.reason for x in ProspectRejectionReason.all()),
                                  key=lambda r: r.lower(),
                                  reverse=True)
        current_user = gusers.get_current_user()
        if is_admin(current_user):
            app_ids = [app_key.name() for app_key in App.all(keys_only=True).filter('type =', App.APP_TYPE_CITY_APP)]
        else:
            manager = RegioManager.get(RegioManager.create_key(current_user.email()))
            app_ids = manager.app_ids
        context = get_shop_context(js_templates=render_js_templates(['task_list']),
                                   current_user=gusers.get_current_user(),
                                   prospect_reasons_json=json.dumps(prospect_reasons),
                                   task_types=ShopTask.TYPE_STRINGS.items(),
                                   apps=app_ids)
        self.response.out.write(template.render(path, context))


class HistoryTasksHandler(BizzManagerHandler):
    def get(self):
        current_user = gusers.get_current_user()
        if not is_admin(current_user):
            self.abort(403)
        path = os.path.join(os.path.dirname(__file__), 'html', 'history_tasks.html')
        context = get_shop_context(js_templates=render_js_templates(['history_tasks']))
        self.response.out.write(template.render(path, context))


class ProspectsHandler(BizzManagerHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'html', 'prospects.html')
        prospect_reasons = sorted((x.reason for x in ProspectRejectionReason.all()),
                                  key=lambda r: r.lower(),
                                  reverse=True)

        google_user = gusers.get_current_user()
        if is_admin(google_user):
            shop_apps = ShopApp.all()
        else:
            regio_manager = RegioManager.get(RegioManager.create_key(google_user.email()))
            regio_manager_team = RegioManagerTeam.get_by_id(regio_manager.team_id)
            shop_apps = [shop_app for shop_app in ShopApp.all() if shop_app.app_id in regio_manager_team.app_ids]

        context = get_shop_context(shop_apps=shop_apps,
                                   current_user=google_user,
                                   js_templates=render_js_templates(
                                       ['prospect_list_view_row', 'prospect_task_history']),
                                   prospect_reasons_json=json.dumps(prospect_reasons))
        self.response.out.write(template.render(path, context))


class FindProspectsHandler(BizzManagerHandler):
    def get(self):
        current_user = gusers.get_current_user()
        if not is_admin(current_user):
            self.abort(403)
        path = os.path.join(os.path.dirname(__file__), 'html', 'prospects_find.html')
        context = get_shop_context(COUNTRY_STRINGS=sorted(OFFICIALLY_SUPPORTED_COUNTRIES.iteritems(),
                                                          key=lambda (k, v): v))
        self.response.out.write(template.render(path, context))


class LoginAsCustomerHandler(BizzManagerHandler):
    def get(self):
        google_user = gusers.get_current_user()
        customer_id = int(self.request.get("customer_id"))
        layout_only = bool(self.request.get("layout_only"))

        if is_admin(google_user):
            access = RegioManager.ACCESS_FULL
            customer = Customer.get_by_id(customer_id)
            service_identity_user = create_service_identity_user(users.User(customer.service_email))
        else:
            regio_manager, customer = db.get((RegioManager.create_key(google_user.email()),
                                              Customer.create_key(customer_id)))
            service_identity_user = create_service_identity_user(users.User(customer.service_email))
            # service_identity = get_service_identity(service_identity_user)
            if not regio_manager:
                access = RegioManager.ACCESS_NO
            else:
                access = regio_manager.has_access(customer.team_id)

        if access == RegioManager.ACCESS_NO:
            self.response.out.write("Access denied!")
            logging.critical("%s tried to login to dashboard of %s (customer_id: %s)",
                             google_user.email(), customer.name, customer_id)
        else:
            session = users.get_current_session()
            if not session or session.type != session.TYPE_ROGERTHAT:
                rogerthat_user = users.User(google_user.email())
                profile_info = get_profile_info(rogerthat_user)
                if not profile_info:
                    create_user_profile(rogerthat_user, google_user.email().replace("@", " at "))
                try:
                    secret, session = create_session(rogerthat_user, ignore_expiration=True)
                except ServiceExpiredException:
                    return self.redirect('/service_expired')
                server_settings = get_server_settings()
                set_cookie(self.response, server_settings.cookieSessionName, secret)
            switch_to_service_identity(session, service_identity_user, access == RegioManager.ACCESS_READ_ONLY,
                                       shop=True, layout_only=layout_only)
            self.redirect("/")


class ProspectsUploadHandler(BizzManagerHandler):
    def post(self):
        app_id = self.request.get("appId")
        logging.info("uploading new prospect for app_id: %s", app_id)
        new_prospects_file = self.request.get("newProspects")
        csv_reader = csv.reader(new_prospects_file.split('\n'), delimiter=',', quotechar='"')

        new_prospects = list()
        currect_phone_numbers = set()
        for p in Prospect().all():
            currect_phone_numbers.add(p.phone)

        for row in csv_reader:
            try:
                name, type_, address, phone, website = row
                phone_ = re.sub('[ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz\-./ ]', '', phone)
                if phone_ not in currect_phone_numbers:
                    p = Prospect()
                    p.app_id = app_id
                    p.name = name
                    p.type = type_.split('|')
                    p.address = address
                    p.phone = phone_
                    p.website = website
                    new_prospects.append(p)
            except:
                logging.warning('Error occurred while validating row %s "%s" in csv prospects list' % (len(new_prospects), row), exc_info=True)
        logging.info("added %s new prospects" % len(new_prospects))
        if new_prospects:
            db.put(new_prospects)


class ExportEmailAddressesHandler(BizzManagerHandler):
    def get(self):
        azzert(is_admin(gusers.get_current_user()))

        Export = namedtuple('Export', 'email first_name last_name')

        result = dict()
        for contact in Contact.all():
            result[contact.email.strip().lower()] = Export(contact.email, contact.first_name, contact.last_name)

        for prospect in Prospect.all().filter("email > ", None):
            first_name, last_name = (prospect.name + " ").split(' ', 1)
            result[prospect.email.strip().lower()] = Export(prospect.email, first_name, last_name.strip())

        self.response.headers['Content-Type'] = 'application/vnd.ms-excel'
        self.response.headers['Content-Disposition'] = str('attachment; filename=contacts_export_%s.csv' % now())
        writer = csv.writer(self.response.out, dialect='excel')
        for export in result.values():
            writer.writerow((export.email.encode("utf-8"),
                             export.first_name.encode("utf-8"),
                             export.last_name.encode("utf-8")))


class ExpiredSubscriptionsHandler(BizzManagerHandler):
    def get(self):
        current_user = gusers.get_current_user()
        if not is_admin(current_user):
            self.abort(403)
        path = os.path.join(os.path.dirname(__file__), 'html', 'expired_subscriptions.html')
        expired_subscriptions = list(ExpiredSubscription.list_all())
        to_get = list()
        for expired_sub in expired_subscriptions:
            to_get.append(expired_sub.customer_id)
        customers = list(Customer.get_by_id(to_get))
        statuses = ExpiredSubscription.STATUSES.iteritems()
        context = get_shop_context(expired_subscriptions=zip(expired_subscriptions, customers), statuses=statuses)
        self.response.out.write(template.render(path, context))


class LegalEntityHandler(BizzManagerHandler):
    def get(self):
        current_user = gusers.get_current_user()
        if not is_admin(current_user):
            self.abort(403)
        solution_server_settings = get_solution_server_settings()
        path = os.path.join(os.path.dirname(__file__), 'html', 'legal_entities.html')
        js_templates = render_js_templates(['legal_entities'], True)
        terms_of_use_translated = dict()
        tos_link = '<a href="%s">%s</a>' % (solution_server_settings.shop_privacy_policy_url,
                                            solution_server_settings.shop_privacy_policy_url)

        for language in get_languages():
            terms_of_use_translated[language] = shop_translate(language, 'tos_15', tos_link=tos_link) \
                .replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') \
                .replace("'", "\\'").replace('"', '\\"').replace('15. ', '')
        self.response.out.write(template.render(path, get_shop_context(
            js_templates=js_templates,
            TERMS_OF_USE=json.dumps(terms_of_use_translated))))


@rest('/internal/shop/rest/legal_entity/list', 'get')
@returns([LegalEntityTO])
@arguments()
def rest_get_legal_entities():
    return [LegalEntityTO.from_model(entity) for entity in LegalEntity.list_all()]


@rest('/internal/shop/rest/legal_entity/put', 'post')
@returns(LegalEntityReturnStatusTO)
@arguments(entity=LegalEntityTO)
def rest_put_legal_entity(entity):
    azzert(is_admin(gusers.get_current_user()))
    try:
        entity = put_legal_entity(entity.id if entity.id is not MISSING else None, entity.name, entity.address,
                                  entity.postal_code, entity.city, entity.country_code, entity.phone,
                                  entity.email, entity.vat_percent, entity.vat_number, entity.currency_code, entity.iban,
                                  entity.bic, entity.terms_of_use, entity.revenue_percentage)
        return LegalEntityReturnStatusTO.create(True, None, entity)
    except BusinessException as exception:
        return LegalEntityReturnStatusTO.create(False, exception)


@rest('/internal/shop/rest/legal_entity', 'get')
@returns(LegalEntityTO)
@arguments()
def rest_get_legal_entity():
    manager = RegioManager.get(RegioManager.create_key(gusers.get_current_user().email()))
    if not manager:
        legal_entity = get_mobicage_legal_entity()
    else:
        legal_entity = RegioManagerTeam.get_by_id(manager.team_id).legal_entity
    return LegalEntityTO.from_model(legal_entity)


@rest("/internal/shop/rest/customers/export", "get")
@returns(ReturnStatusTO)
@arguments()
def export_customers():
    google_user = gusers.get_current_user()
    azzert(is_admin(google_user))
    deferred.defer(export_customers_csv, google_user)
    return RETURNSTATUS_TO_SUCCESS


@rest("/internal/shop/rest/customers/expired_subscriptions/set_status", "post")
@returns(ReturnStatusTO)
@arguments(customer_id=(int, long), status=(int, long))
def rest_set_expired_subscription_status(customer_id, status):
    try:
        set_expired_subscription_status(customer_id, status)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, exception:
        return ReturnStatusTO.create(False, exception.message)


@rest("/internal/shop/rest/customers/expired_subscriptions/delete", "post")
@returns(ReturnStatusTO)
@arguments(customer_id=(int, long))
def rest_delete_expired_subscription(customer_id):
    try:
        if is_admin(users.get_current_user()):
            delete_expired_subscription(customer_id)
        else:
            raise NoPermissionException('delete expired subscription')
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, exception:
        return ReturnStatusTO.create(False, exception.message)


class CustomersHandler(BizzManagerHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'html', 'customers.html')
        cur_user = gusers.get_current_user()
        context = get_shop_context(customers=Customer.list_by_manager(cur_user, is_admin(cur_user)))
        self.response.out.write(template.render(path, context))


class SalesStatisticsHandler(BizzManagerHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'html', 'sales_stats.html')
        self.response.out.write(template.render(path, get_shop_context()))


class HintsHandler(BizzManagerHandler):
    def get(self):
        current_user = gusers.get_current_user()
        if not is_admin(current_user):
            self.abort(403)
        path = os.path.join(os.path.dirname(__file__), 'html', 'hints.html')
        context = get_shop_context(js_templates=render_js_templates(['hints']))
        self.response.out.write(template.render(path, context))


class OrderableAppsHandler(BizzManagerHandler):
    def get(self):
        current_user = gusers.get_current_user()
        if not is_admin(current_user):
            self.abort(403)
        path = os.path.join(os.path.dirname(__file__), 'html', 'apps.html')
        context = get_shop_context(shop_apps=ShopApp.all(),
                                   js_templates=render_js_templates(['apps']))
        self.response.out.write(template.render(path, context))


class SignupAppsHandler(BizzManagerHandler):
    def get(self):
        current_user = gusers.get_current_user()
        if not is_admin(current_user):
            self.abort(403)

        # List all shop apps, joined with all city apps
        shop_apps = list(ShopApp.all())
        shop_app_ids = [a.app_id for a in shop_apps]
        for city_app in get_apps([App.APP_TYPE_CITY_APP]):
            if city_app.app_id in shop_app_ids:
                shop_app = shop_apps[shop_app_ids.index(city_app.app_id)]
            else:
                shop_app = ShopApp(key=ShopApp.create_key(city_app.app_id),
                                   name=city_app.name)
                shop_apps.append(shop_app)

            shop_app.main_service = city_app.main_service  # just setting this property for the template

        shop_apps.sort(key=lambda a: a.name and a.name.lower())

        path = os.path.join(os.path.dirname(__file__), 'html', 'signup_apps.html')
        context = get_shop_context(shop_apps=shop_apps)
        self.response.out.write(template.render(path, context))


@rest("/internal/shop/rest/salesstats/load", "get")
@returns([RegioManagerStatisticTO])
@arguments()
def sales_stats():
    google_user = gusers.get_current_user()
    if is_admin(google_user):
        stats = list(get_regiomanager_statistics())
        regio_managers = db.get([RegioManager.create_key(stat.manager) for stat in stats])
    else:
        regio_manager = RegioManager.get(RegioManager.create_key(google_user.email()))
        regio_manager_team = RegioManagerTeam.get_by_id(regio_manager.team_id)
        stats = []
        regio_managers = []
        for rm in db.get([RegioManager.create_key(rm_email) for rm_email in regio_manager_team.regio_managers]):
            if rm:
                rm_stats = db.get(RegioManagerStatistic.create_key(rm.email))
                if rm_stats:
                    regio_managers.append(rm)
                    stats.append(rm_stats)

    return [RegioManagerStatisticTO.create(s, r) for s, r in zip(stats, regio_managers) if s and r]


@rest("/internal/shop/rest/hints/load", "get")
@returns([SolutionHintTO])
@arguments()
def hints_load():
    azzert(is_admin(gusers.get_current_user()))
    return [SolutionHintTO.fromModel(h) for h in get_all_solution_hints(get_solution_hints().hint_ids)]


@rest('/internal/shop/rest/hints/put', 'post')
@returns(ReturnStatusTO)
@arguments(hint_id=(int, long, NoneType), tag=unicode, language=unicode, text=unicode, modules=[unicode])
def hints_put(hint_id, tag, language, text, modules):
    google_user = gusers.get_current_user()
    azzert(is_admin(google_user))
    try:
        put_hint(google_user, hint_id, tag, language, text, modules)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, be:
        return ReturnStatusTO.create(False, be.message)


@rest('/internal/shop/rest/hints/delete', 'post')
@returns(ReturnStatusTO)
@arguments(hint_id=(int, long))
def hints_delete(hint_id):
    google_user = gusers.get_current_user()
    azzert(is_admin(google_user))
    try:
        delete_hint(google_user, hint_id)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, be:
        return ReturnStatusTO.create(False, be.message)


@rest('/internal/shop/rest/prospect/put', 'post')
@returns(ProspectReturnStatusTO)
@arguments(prospect_id=unicode, name=unicode, phone=unicode, address=unicode, email=unicode, website=unicode,
           comment=unicode, types=[unicode], categories=[unicode], app_id=unicode)
def prospect_put(prospect_id, name, phone, address, email, website, comment=None, types=None, categories=None,
                 app_id=None):
    try:
        prospect = put_prospect(gusers.get_current_user(), prospect_id, name, phone, address, email, website,
                                comment, types, categories, app_id)
        audit_log(prospect.customer_id, u'Save prospect', prospect_id=prospect_id)
        return ProspectReturnStatusTO.create(prospect=prospect)
    except BusinessException, be:
        return ProspectReturnStatusTO.create(False, be.message)


@rest('/internal/shop/rest/prospect/link_to_customer', 'post')
@returns(ProspectReturnStatusTO)
@arguments(prospect_id=unicode, customer_id=(int, long))
def prospect_link_to_customer(prospect_id, customer_id):
    try:
        prospect = link_prospect_to_customer(gusers.get_current_user(), prospect_id, customer_id)
        audit_log(customer_id, u'Linked prospect to customer', prospect_id=prospect_id)
        return ProspectReturnStatusTO.create(prospect=prospect)
    except BusinessException, be:
        return ProspectReturnStatusTO.create(False, be.message)


@rest('/internal/shop/rest/prospect/findbycustomer', 'get')
@returns(ProspectDetailsTO)
@arguments(customer_id=(int, long))
def prospect_find_by_customer(customer_id):
    audit_log(customer_id, u'Get prospect by customer', None, gusers.get_current_user(), None)
    customer = Customer.get_by_id(customer_id)
    if customer.prospect_id is not None:
        prospect = Prospect.get_by_key_name(customer.prospect_id)
    else:
        prospect = None
    return ProspectDetailsTO.from_model(prospect, RegioManager.list_by_app_id(prospect.app_id)) if prospect else None


@rest('/internal/shop/rest/prospect/task_history', 'get')
@returns([TaskTO])
@arguments(id=unicode)
def prospect_task_history(id):  # @ReservedAssignment
    prospect = Prospect.get(Prospect.create_key(id))
    return [TaskTO.from_model(s, prospect)
            for s in ShopTask.get_all_history(id)]


@rest('/internal/shop/rest/prospects/export', 'post', silent=True)
@returns(ReturnStatusTO)
@arguments(prospect_ids=[unicode])
def rest_prospect_export(prospect_ids):
    if not prospect_ids:
        return ReturnStatusTO.create(False, 'No prospects to export')
    deferred.defer(generate_prospect_export_excel, prospect_ids, True, [gusers.get_current_user().email()],
                   _queue=FAST_QUEUE)
    return RETURNSTATUS_TO_SUCCESS


@rest('/internal/shop/rest/prospects/detail', 'get')
@returns(ProspectTO)
@arguments(prospect_id=unicode)
def prospects_detail(prospect_id):
    audit_log(None, u'Get prospect', prospect_id=prospect_id)
    prospect = Prospect.get_by_key_name(prospect_id)
    return ProspectTO.from_model(prospect) if prospect else None


@rest('/internal/shop/rest/prospects/map', 'get', silent_result=True)
@returns(ProspectsMapTO)
@arguments(app_id=unicode, category=unicode, cursor=unicode)
def prospects_map(app_id, category, cursor=None):
    audit_log(None, u'Load prospects by app')
    import time
    start = time.time()
    prospects, new_cursor = list_prospects(app_id, category, cursor)
    regio_managers = RegioManager.list_by_app_id(app_id)
    all_prospects = ProspectsMapTO.from_model(new_cursor, prospects, regio_managers)
    logging.info(
        'Took %s seconds to load prospects filtered on app %s and category %s' % (
        time.time() - start, app_id, category))
    return all_prospects


@rest('/internal/shop/rest/prospects/search', 'get')
@returns([ProspectTO])
@arguments(query=unicode)
def prospects_search(query):
    audit_log(None, u'Search prospect')
    return [ProspectTO.from_model(p) for p in search_prospects(query)]


@rest('/internal/shop/rest/prospects/set_status', 'post')
@returns(ProspectReturnStatusTO)
@arguments(prospect_id=unicode, status=(int, long), reason=unicode, action_timestamp=(int, long, NoneType),
           assignee=unicode, comment=unicode, certainty=(int, long, NoneType), subscription=(int, long, NoneType),
           email=unicode, invite_language=unicode, appointment_type=(int, long, NoneType))
def prospects_set_status(prospect_id, status, reason=None, action_timestamp=None, assignee=None, comment=None,
                         certainty=None, subscription=None, email=None, invite_language=None,
                         appointment_type=None):
    try:
        prospect, calendar_error = set_prospect_status(gusers.get_current_user(), prospect_id, status,
                                                       reason and reason.strip(), action_timestamp, assignee,
                                                       comment and comment.strip(),
                                                       certainty=certainty,
                                                       subscription=subscription, email=email,
                                                       invite_language=invite_language,
                                                       appointment_type=appointment_type)
        audit_log(prospect.customer_id, u'Set prospect status', prospect_id=prospect_id)
        return ProspectReturnStatusTO.create(prospect=prospect, calendar_error=calendar_error)
    except BusinessException, be:
        return ProspectReturnStatusTO.create(False, be.message)


@rest('/internal/shop/rest/prospects/find', 'post')
@returns(ReturnStatusTO)
@arguments(app_id=unicode, postal_codes=unicode, sw_lat=float, sw_lon=float, ne_lat=float, ne_lon=float, radius=int,
           city_name=unicode, check_phone_number=bool)
def prospects_find(app_id, postal_codes, sw_lat, sw_lon, ne_lat, ne_lon, radius, city_name, check_phone_number):
    audit_log(None, u'Find new prospects')
    postal_codes = filter(None, postal_codes.strip().replace(' ', '').split(','))
    try:
        find_prospects(app_id, postal_codes, sw_lat, sw_lon, ne_lat, ne_lon, city_name, check_phone_number, radius)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, be:
        return ReturnStatusTO.create(False, be.message)


@rest('/internal/shop/rest/prospects/find_city_bounds', 'post')
@returns(CityBoundsReturnStatusTO)
@arguments(city=unicode, country=unicode)
def prospects_find_city_bounds(city, country):
    azzert(is_admin(gusers.get_current_user()))
    try:
        bounds = find_city_bounds(city, country)
        return CityBoundsReturnStatusTO.create(bounds=bounds)
    except BusinessException, be:
        return CityBoundsReturnStatusTO.create(False, be.message)


@rest('/internal/shop/rest/prospects/grid', 'get')
@returns([PointTO])
@arguments(sw_lat=float, sw_lon=float, ne_lat=float, ne_lon=float, radius=(int, long))
def prospects_get_grid(sw_lat, sw_lon, ne_lat, ne_lon, radius=200):
    azzert(is_admin(gusers.get_current_user()))
    points = get_grid(sw_lat, sw_lon, ne_lat, ne_lon, radius)
    return [PointTO.create(*p) for p in points]


@rest('/internal/shop/rest/shopapp/save_postal_codes', 'post')
@returns(ReturnStatusTO)
@arguments(app_id=unicode, postal_codes=[unicode])
def save_app_postal_codes(app_id, postal_codes):
    shop_app_key = ShopApp.create_key(app_id)
    app = ShopApp.get(shop_app_key)
    if not app:
        app = ShopApp(key=shop_app_key)
    app.postal_codes = postal_codes
    app.put()
    return RETURNSTATUS_TO_SUCCESS


@rest('/internal/shop/rest/prospects/shop_app', 'get')
@returns(ShopAppTO)
@arguments(app_id=unicode)
def prospects_get_shop_app(app_id):
    azzert(is_admin(gusers.get_current_user()))
    try:
        shop_app = db.get(ShopApp.create_key(app_id))
        return ShopAppTO.from_model(shop_app) if shop_app else None
    except BusinessException, be:
        return CityBoundsReturnStatusTO.create(False, be.message)


@rest('/internal/shop/rest/history/tasks', 'get')
@returns([TaskListTO])
@arguments(date_from=int, date_to=int)
def history_tasks(date_from, date_to):
    azzert(is_admin(gusers.get_current_user()))
    audit_log(None, u'Load tasks history')
    regio_manager_dict = {r.email: r for r in RegioManager.all()}
    tasks_dict = list_history_tasks(date_from, date_to)
    task_lists = list()
    to_get = set()
    for email, tasks in tasks_dict.iteritems():
        for task in tasks:
            to_get.add(task.parent_key())
    prospects = {p.key().name(): p for p in Prospect.get(list(to_get))}
    for email, tasks in tasks_dict.iteritems():
        regio_manager = regio_manager_dict.get(email)
        task_lists.append(TaskListTO.create(email, regio_manager, tasks, prospects))
    return task_lists


@rest('/internal/shop/rest/task/list', 'post', silent_result=True)
@returns([TaskListTO])
@arguments(assignees=[unicode], app_id=unicode, task_type=(int, long, None))
def tasks_list(assignees, app_id=None, task_type=None):
    current_user = gusers.get_current_user()
    audit_log(None, u'Load tasks')

    regio_manager_dict = dict()
    manager = RegioManager.get(RegioManager.create_key(current_user.email()))
    if manager and manager.admin:
        regio_manager_dict = {r.email: r for r in RegioManager.all().filter("team_id =", manager.team_id)}
    elif not is_admin(current_user):
        regio_manager_dict = {current_user.email(): manager}
    else:
        regio_manager_dict = {r.email: r for r in RegioManager.all()}

    regio_manager_emails = None if is_admin(current_user) else regio_manager_dict.keys()
    if assignees and regio_manager_emails:
        # filter out tasks we do not want
        for regio_manager_email in reversed(regio_manager_emails):
            if regio_manager_email not in assignees:
                regio_manager_emails.remove(regio_manager_email)
                del regio_manager_dict[regio_manager_email]

    if app_id == 'all':
        app_id = None
    if task_type:
        azzert(task_type in ShopTask.TYPE_STRINGS, 'Invalid task type')
    tasks_dict = ShopTask.group_by_assignees(regio_manager_emails, app_id, task_type)
    task_lists = list()
    to_get = set()
    for email, tasks in tasks_dict.iteritems():
        for task in tasks:
            to_get.add(task.parent_key())
    prospects = {p.key().name(): p for p in Prospect.get(list(to_get))}
    for email, tasks in tasks_dict.iteritems():
        regio_manager = regio_manager_dict.get(email)
        task_lists.append(TaskListTO.create(email, regio_manager, tasks, prospects))

    task_lists.sort(key=lambda l: (l.assignee != current_user.email(),  # your own agenda first
                                   l.assignee_name.lower()))
    return task_lists


@rest("/internal/shop/rest/regio_manager/get_all_by_app", "get")
@returns([RegioManagerTO])
@arguments(app_id=unicode)
def get_all_by_app(app_id):
    return [RegioManagerTO.from_model(m) for m in get_regiomanagers_by_app_id(app_id)]


@rest('/internal/shop/rest/regio_manager/list', 'get')
@returns(RegioManagerTeamsTO)
@arguments()
def regio_manager_list():
    azzert(is_admin(gusers.get_current_user()))
    audit_log(None, u'Load RegioManagers')
    regio_manager_teams = sorted(RegioManagerTeam.all(), key=lambda x: x.name.lower())
    regio_managers = sorted((r for r in RegioManager.all() if r.user != STORE_MANAGER), key=lambda x: x.name.lower())
    return RegioManagerTeamsTO.from_model(regio_manager_teams, regio_managers, _get_apps())


@rest("/internal/shop/rest/regio_manager_team/list", "get", silent_result=True)
@returns([RegioManagerTeamTO])
@arguments()
def regio_manager_team_list():
    regio_manager_teams = sorted(RegioManagerTeam.all(), key=lambda x: x.name.lower())
    return [RegioManagerTeamTO.from_model(regio_manager_team, []) for regio_manager_team in regio_manager_teams]


@rest('/internal/shop/rest/regio_manager_team/put', 'post')
@returns(ReturnStatusTO)
@arguments(team_id=(int, long, NoneType), name=unicode, legal_entity_id=(int, long, NoneType), app_ids=[unicode])
def rest_put_regio_manager_team(team_id, name, legal_entity_id, app_ids):
    azzert(is_admin(gusers.get_current_user()))
    try:
        put_regio_manager_team(team_id, name, legal_entity_id, app_ids)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, be:
        return ReturnStatusTO.create(False, be.message)


@rest('/internal/shop/rest/regio_manager/apps', 'get')
@returns([AppInfoTO])
@arguments()
def regio_manager_apps():
    cur_user = gusers.get_current_user()
    if is_admin(cur_user):
        current_user_apps = get_apps([App.APP_TYPE_CITY_APP, App.APP_TYPE_ROGERTHAT], True)
    else:
        regio_manager = RegioManager.get(RegioManager.create_key(cur_user.email()))
        regio_manager_team = RegioManagerTeam.get_by_id(regio_manager.team_id)
        current_user_apps = App.get([App.create_key(app_id) for app_id in regio_manager_team.app_ids])
    return [AppInfoTO.fromModel(app) for app in current_user_apps]

@rest('/internal/shop/rest/regio_manager/put', 'post')
@returns(RegioManagerReturnStatusTO)
@arguments(email=unicode, name=unicode, phone=unicode, app_rights=[AppRightsTO], show_in_stats=bool, is_support=bool, team_id=(int, long), admin=bool)
def regio_manager_put(email, name, phone, app_rights, show_in_stats, is_support, team_id, admin):
    azzert(is_admin(gusers.get_current_user()))
    try:
        regio_manager = put_regio_manager(gusers.get_current_user(), email, name, phone, app_rights, show_in_stats,
                                          is_support, team_id, admin)
        variables = dict(locals())
        variables['app_rights'] = serialize_complex_value(app_rights, AppRightsTO, True)
        audit_log(None, u'Update RegioManager', variables=dict_str_for_audit_log(variables))
        return RegioManagerReturnStatusTO.create(regio_manager=regio_manager)
    except BusinessException, be:
        return RegioManagerReturnStatusTO.create(False, be.message)


@rest('/internal/shop/rest/regio_manager/delete', 'post')
@returns(ReturnStatusTO)
@arguments(email=unicode)
def regio_manager_delete(email):
    google_user = gusers.get_current_user()
    azzert(is_admin(google_user))
    try:
        remove_regio_manager(email)
        audit_log(None, u'Delete RegioManager')
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException as be:
        return ReturnStatusTO.create(False, be.message)


@rest("/internal/shop/rest/order/set_manager", "post")
@returns()
@arguments(customer_id=(int, long), order_number=unicode, manager=unicode)
def set_manager(customer_id, order_number, manager):
    audit_log(customer_id, u"Set manager.")
    azzert(is_admin(gusers.get_current_user()))
    regio_manager = RegioManager.get_by_key_name(manager)
    azzert(regio_manager)

    def trans():
        order, customer = db.get([Order.create_key(customer_id, order_number), Customer.create_key(customer_id)])
        customer.manager = gusers.User(manager)
        customer.team_id = regio_manager.team_id
        order.manager = gusers.User(manager)
        order.team_id = regio_manager.team_id
        put_and_invalidate_cache(customer, order)

    db.run_in_transaction(trans)


@rest("/internal/shop/rest/order/get_subscription_order", "get")
@returns(OrderReturnStatusTO)
@arguments(customer_id=(int, long))
def rest_get_subscription_order(customer_id):
    audit_log(customer_id, u'Get subscription order')
    try:
        return OrderReturnStatusTO.create(True, None, get_subscription_order(customer_id))
    except BusinessException, exception:
        return OrderReturnStatusTO.create(False, exception.message)


@rest("/internal/shop/rest/customer/set_next_charge_date", "post")
@returns(ReturnStatusTO)
@arguments(customer_id=(int, long), next_charge_date=(int, long))
def rest_set_next_charge_date(customer_id, next_charge_date):
    audit_log(customer_id, u'Set next charge date')
    manager = RegioManager.get(RegioManager.create_key(gusers.get_current_user().email()))
    is_reseller = manager and not manager.team.legal_entity.is_mobicage
    try:
        if is_reseller:
            customer = Customer.get_by_id(customer_id)
            if not regio_manager_has_permissions_to_team(manager, customer.team_id):
                raise NoPermissionException('Set next charge date of customer \'{}\''.format(customer.name))
        elif not is_admin(gusers.get_current_user()):
            raise NoPermissionException('Set next charge date')
        set_next_charge_date(customer_id, next_charge_date)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException as exception:
        return ReturnStatusTO.create(False, exception.message)


@rest("/internal/shop/rest/question/title", "post")
@returns()
@arguments(question_id=(int, long), title=unicode)
def set_question_title(question_id, title):
    question = Question.get_by_id(question_id)
    user = gusers.get_current_user()
    azzert(user_has_permissions_to_question(user, question))
    def trans(q):
        q.title = title
        q.put()
        deferred.defer(re_index_question, q.key(), _transactional=True)

    db.run_in_transaction(trans, question)


@rest("/internal/shop/rest/question/modules", "post")
@returns()
@arguments(question_id=(int, long), modules=[unicode])
def set_question_modules(question_id, modules):
    question = Question.get_by_id(question_id)
    user = gusers.get_current_user()
    azzert(user_has_permissions_to_question(user, question))
    def trans(q):
        q.modules = modules
        q.put()
        deferred.defer(re_index_question, q.key(), _transactional=True)

    db.run_in_transaction(trans, question)


@rest("/internal/shop/rest/question/visible", "post")
@returns()
@arguments(question_id=(int, long), question_reply_id=(int, long, NoneType), visible=bool)
def set_question_visible(question_id, question_reply_id, visible):
    question = Question.get_by_id(question_id)
    user = gusers.get_current_user()
    azzert(user_has_permissions_to_question(user, question))
    def trans(q):
        if not question_reply_id:
            q.visible = visible
            q.put()
        else:
            qr = QuestionReply.get_by_id(question_reply_id, q)
            qr.visible = visible
            qr.put()
        deferred.defer(re_index_question, q.key(), _transactional=True)

    db.run_in_transaction(trans, question)


@rest("/internal/shop/rest/question/reply", "post")
@returns()
@arguments(question_id=(int, long), description=unicode, author_name=unicode)
def send_reply(question_id, description, author_name):
    question = Question.get_by_id(question_id)
    user = gusers.get_current_user()
    azzert(user_has_permissions_to_question(user, question))

    @db.non_transactional
    def get_customer(q):
        return Customer.get_by_service_email(q.author.email())

    settings = get_server_settings()

    def trans(q):
        q.answered = True

        qr = QuestionReply(parent=q)
        qr.author = gusers.get_current_user()
        qr.timestamp = now()
        qr.description = description
        qr.author_role = QuestionReply.ROLE_STAFF
        qr.author_name = author_name
        qr.visible = True

        db.put([q, qr])
        deferred.defer(re_index_question, q.key(), _transactional=True)
        to_email = q.author.email()
        customer = get_customer(q)
        if customer:
            to_email = customer.user_email

        service_user = users.User(q.author.email())
        sln_settings = get_solution_settings(service_user)
        subject = "RE: %s" % q.title
        message = """Dear,

please login on %s to see the reply for your question titled '%s'.

Kind regards,

The Rogerthat team.""" % (sln_settings.login.email() if sln_settings.login else q.author.email(), q.title)
        send_mail(settings.senderEmail, to_email, subject, message, transactional=True)
    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans, question)


@rest("/internal/shop/rest/question/assign", "post")
@returns(ReturnStatusTO)
@arguments(question_id=int, team_id=int)
def assign_team_to_question(question_id, team_id):
    question = Question.get_by_id(question_id)
    user = gusers.get_current_user()
    azzert(user_has_permissions_to_question(user, question))
    team = RegioManagerTeam.get_by_id(team_id)
    settings = get_server_settings()
    def trans(q, t):
        q.team_id = t.id
        q.put()

        support_manager = t.get_support()
        if support_manager:
            support_email = support_manager.user.email()
            name = q.get_author_name()
            message = """Please reply to %s (%s) with the following link:
%s/internal/shop/questions

Title:
%s

Description:
%s""" % (name, q.author, settings.baseUrl, q.title, q.description)
            send_mail(settings.senderEmail, support_email, q.title, message, transactional=True)

    try:
        xg_on = db.create_transaction_options(xg=True)
        db.run_in_transaction_options(xg_on, trans, question, team)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException as e:
        return ReturnStatusTO.create(False, e.message)


@rest("/internal/shop/rest/customer/put", "post")
@returns(CustomerReturnStatusTO)
@arguments(customer_id=(int, long, NoneType), name=unicode, address1=unicode, address2=unicode, zip_code=unicode,
           city=unicode, country=unicode, language=unicode, vat=unicode, organization_type=(int, long),
           prospect_id=unicode, force=bool, team_id=(int, long, NoneType))
def put_customer(customer_id, name, address1, address2, zip_code, city, country, language, vat, organization_type,
                 prospect_id=None, force=False, team_id=None):
    try:
        customer = create_or_update_customer(gusers.get_current_user(), customer_id, vat, name, address1, address2,
                                             zip_code, city, country, language, organization_type, prospect_id, force, team_id)
        audit_log(customer.id, u"Save Customer.", prospect_id=prospect_id)
    except DuplicateCustomerNameException, ex:
        return CustomerReturnStatusTO.create(False, warning=ex.message)
    except BusinessException, be:
        return CustomerReturnStatusTO.create(False, be.message)

    return CustomerReturnStatusTO.create(customer=CustomerTO.fromCustomerModel(customer, True, is_admin(gusers.get_current_user())))


@rest("/internal/shop/rest/customer/find", "get")
@returns([CustomerTO])
@arguments(search_string=unicode, find_all=bool)
def find_customer(search_string, find_all=False):
    audit_log(-1, u"Customer lookup.")
    user = gusers.get_current_user()
    if is_admin(user):
        app_ids = None
        team_id = None
        has_admin_permissions = True
    else:
        regio_manager = RegioManager.get(RegioManager.create_key(user.email()))
        app_ids = regio_manager.app_ids
        team_id = regio_manager.team_id
        has_admin_permissions = False

    customers = []
    for c in search_customer(search_string, None if find_all else app_ids, None if find_all else team_id):
        can_edit = team_id is None or team_id == c.team_id
        admin = has_admin_permissions or (team_id == c.team_id and regio_manager.admin)
        customers.append(CustomerTO.fromCustomerModel(c, can_edit, admin))
    return sorted(customers, key=lambda c: c.name.lower())

@rest("/internal/shop/rest/customer", "get")
@returns(CustomerReturnStatusTO)
@arguments(customer_id=(int, long))
def get_customer_details(customer_id):
    audit_log(customer_id, u"Loading customer details.")
    try:
        customer = db.run_in_transaction(Customer.get_by_id, customer_id)
    except CustomerNotFoundException, exception:
        return CustomerReturnStatusTO.create(False, errormsg=exception.message)

    user = gusers.get_current_user()
    can_edit = True
    if is_admin(user):
        has_admin_permissions = True
    else:
        regio_manager = RegioManager.get(RegioManager.create_key(user.email()))
        if regio_manager.team_id and regio_manager.team_id != customer.team_id:
            can_edit = False
        has_admin_permissions = False

    return CustomerReturnStatusTO.create(True, customer=CustomerTO.fromCustomerModel(customer, can_edit, has_admin_permissions))


@rest("/internal/shop/rest/customer/link_stripe", "post")
@returns(unicode)
@arguments(customer_id=(int, long), stripe_token=unicode, stripe_token_created=(int, long), contact_id=(int, long))
def rest_link_stripe_to_customer(customer_id, stripe_token, stripe_token_created, contact_id):
    audit_log(customer_id, u"Linking credit card.")
    try:
        link_stripe_to_customer(customer_id, stripe_token, stripe_token_created, contact_id)
    except BusinessException, exception:
        return exception.message


@rest("/internal/shop/rest/contact/new", "post")
@returns(ContactReturnStatusTO)
@arguments(customer_id=(int, long), first_name=unicode, last_name=unicode, email_address=unicode,
           phone_number=unicode)
def new_contact(customer_id, first_name, last_name, email_address, phone_number):
    try:
        contact = create_contact(customer_id, first_name, last_name, email_address, phone_number)
        return ContactReturnStatusTO.create(contact=ContactTO.fromContactModel(contact))
    except BusinessException as ex:
        return ContactReturnStatusTO.create(False, ex)


@rest("/internal/shop/rest/contact/update", "post")
@returns(ContactReturnStatusTO)
@arguments(customer_id=(int, long), contact_id=(int, long), first_name=unicode, last_name=unicode, email_address=unicode,
           phone_number=unicode)
def save_contact(customer_id, contact_id, first_name, last_name, email_address, phone_number):
    try:
        contact = update_contact(customer_id, contact_id, first_name, last_name, email_address, phone_number)
        return ContactReturnStatusTO.create(contact=ContactTO.fromContactModel(contact))
    except BusinessException, ex:
        return ContactReturnStatusTO.create(False, ex)


@rest("/internal/shop/rest/contact/delete", "post")
@returns(ReturnStatusTO)
@arguments(customer_id=(int, long), contact_id=(int, long))
def delete_contact_rest(customer_id, contact_id):
    try:
        delete_contact(customer_id, contact_id)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, ex:
        return ReturnStatusTO.create(False, ex)


@rest("/internal/shop/rest/contact/find", "get")
@returns([ContactTO])
@arguments(customer_id=(int, long))
def list_contacts(customer_id):
    audit_log(customer_id, u"Listing contacts")
    return [ContactTO.fromContactModel(c) for c in Contact.list(Customer.create_key(customer_id))]


@rest("/internal/shop/rest/customer/get_default_modules", "get")
@returns(ModulesReturnStatusTO)
@arguments(customer_id=(int, long))
def get_default_modules(customer_id):
    customer = Customer.get_by_id(customer_id)
    if customer.subscription_order_number:
        if customer.subscription_type == Customer.SUBSCRIPTION_TYPE_STATIC:
            # order is static; return default static modules
            # success variable stands for static or not
            return ModulesReturnStatusTO.create(success=True, modules=list(SolutionModule.STATIC_MODULES), errormsg=None)
        else:
            return ModulesReturnStatusTO.create(success=False, modules=_get_default_modules(), errormsg=None)
    else:
        return ModulesReturnStatusTO.create(
            success=False,
            errormsg=u"This customer does not have an order yet. First create an order for this customer."
        )


@rest("/internal/shop/rest/order/contact", "get")
@returns(ContactTO)
@arguments(customer_id=(int, long), order_number=unicode)
def get_order_contact(customer_id, order_number):
    audit_log(customer_id, u"Get order contact")
    customer, order = db.get((Customer.create_key(customer_id), Order.create_key(customer_id, order_number)))
    contact = Contact.get_by_contact_id(customer, order.contact_id)
    if contact:
        return ContactTO.fromContactModel(contact)
    return None


@rest("/internal/shop/rest/order/contact", "post")
@returns(unicode)
@arguments(customer_id=(int, long), order_number=unicode, contact_id=(int, long))
def rest_put_order_contact(customer_id, order_number, contact_id):
    audit_log(customer_id, u"Put order contact")
    order, contact = db.get((Order.create_key(customer_id, order_number),
                             Contact.create_key(contact_id, customer_id)))
    if not contact:
        return u'New contact could not be found'
    if order.status == Order.STATUS_SIGNED:
        return u'You may not change the contact of an order that has already been signed'
    order.contact_id = contact_id
    order.put()


@rest("/internal/shop/rest/order/new", "post")
@returns(CreateOrderReturnStatusTO)
@arguments(customer_id=(int, long), contact_id=(int, long), items=[OrderItemTO], replace=bool)
def create_new_order(customer_id, contact_id, items, replace=False):
    try:
        create_order(customer_id, contact_id, items, replace, regio_manager_user=gusers.get_current_user())
        return CreateOrderReturnStatusTO.create(True)
    except ReplaceBusinessException, e:
        return CreateOrderReturnStatusTO.create(False, e.message, True)
    except BusinessException, e:
        return CreateOrderReturnStatusTO.create(False, e.message)


@rest("/internal/shop/rest/order/cancel", "post")
@returns(unicode)
@arguments(customer_id=(int, long), order_number=unicode, confirm=bool)
def rest_cancel_order(customer_id, order_number, confirm=False):
    audit_log(customer_id, u"Cancel order.")
    try:
        customer = Customer.get_by_id(customer_id)
        azzert(user_has_permissions_to_team(gusers.get_current_user(), customer.team_id))
        cancel_order(customer, order_number, confirm, True)
    except BusinessException, e:
        return e.message


@rest('/internal/shop/rest/order/subscription_order_length', 'get')
@returns(SubscriptionLengthReturnStatusTO)
@arguments(customer_id=(int, long))
def rest_get_subscription_order_length(customer_id):
    try:
        return SubscriptionLengthReturnStatusTO.create(True, None, get_customer_subscription_length(customer_id))
    except NoSubscriptionFoundException:
        return SubscriptionLengthReturnStatusTO.create(False, None, 0)
    except BusinessException, exception:
        return SubscriptionLengthReturnStatusTO.create(False, exception.message)


@rest("/internal/shop/rest/order/cancel_subscription", "post")
@returns(ReturnStatusTO)
@arguments(customer_id=(int, long), cancel_reason=unicode)
def rest_cancel_subscription(customer_id, cancel_reason):
    audit_log(customer_id, u'Cancel subscription')
    manager = RegioManager.get(RegioManager.create_key(gusers.get_current_user().email()))
    is_reseller = manager and not manager.team.legal_entity.is_mobicage
    try:
        if is_reseller:
            customer = Customer.get_by_id(customer_id)
            if not regio_manager_has_permissions_to_team(manager, customer.team_id):
                raise NoPermissionException('cancel the subscription of customer \'{}\''.format(customer.name))
        elif not is_admin(gusers.get_current_user()):
            raise NoPermissionException('cancel a subscription')

        cancel_subscription(customer_id, cancel_reason)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException as exception:
        return ReturnStatusTO.create(False, exception.message)


@rest("/internal/shop/rest/charge/send_payment_info", "post")
@returns(unicode)
@arguments(customer_id=(int, long), order_number=unicode, charge_id=(int, long))
def rest_send_payment_info(customer_id, order_number, charge_id):
    audit_log(customer_id, u"Send payment info.")
    send_payment_info(customer_id, order_number, charge_id, gusers.get_current_user())


@rest("/internal/shop/rest/charge/set_po_number", "post")
@returns(ReturnStatusTO)
@arguments(customer_id=(int, long), order_number=unicode, charge_id=(int, long), customer_po_number=unicode)
def set_po_number(customer_id, order_number, charge_id, customer_po_number):
    audit_log(customer_id, u"Set PO number.")
    from shop.bizz import set_po_number as bizz_set_po_number
    return wrap_with_result_status(bizz_set_po_number, customer_id, order_number, charge_id, customer_po_number)


@rest("/internal/shop/rest/charge/set_advance_payment", "post")
@returns(ReturnStatusTO)
@arguments(customer_id=(int, long), order_number=unicode, charge_id=(int, long), amount=(int, long))
def set_charge_advance_payment(customer_id, order_number, charge_id, amount):
    audit_log(customer_id, u"Set invoice saldo.")
    from shop.bizz import set_charge_advance_payment as bizz_set_charge_advance_payment
    return wrap_with_result_status(bizz_set_charge_advance_payment, gusers.get_current_user(), customer_id,
                                   order_number, charge_id, amount)


@rest("/internal/shop/rest/charge/execute_stripe", "post")
@returns(unicode)
@arguments(customer_id=(int, long), order_number=unicode, charge_id=(int, long))
def get_payed_through_stripe(customer_id, order_number, charge_id):
    audit_log(customer_id, u"Execute charge via stripe.")

    try:
        get_payed(customer_id, order_number, charge_id)
        return ""
    except PaymentFailedException, pfe:
        return pfe.message


@rest("/internal/shop/rest/charge/execute_manual", "post")
@returns(unicode)
@arguments(customer_id=(int, long), order_number=unicode, charge_id=(int, long), paid=bool)
def rest_manual_payment(customer_id, order_number, charge_id, paid):
    audit_log(customer_id, u"Execute charge manual.")
    current_user = gusers.get_current_user()
    try:
        manual_payment(current_user, customer_id, order_number, charge_id, paid)
        return ""
    except PaymentFailedException, pfe:
        return pfe.message


@rest("/internal/shop/rest/charge/cancel", "post")
@returns(ReturnStatusTO)
@arguments(customer_id=(int, long), order_number=unicode, charge_id=(int, long))
def rest_cancel_charge(customer_id, order_number, charge_id):
    audit_log(customer_id, u'Cancel charge')
    try:
        cancel_charge(customer_id, order_number, charge_id)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, exception:
        return ReturnStatusTO.create(False, exception.message)


def parseDataDotBeAddressBE(address):
    address = address.split(',')
    if len(address) == 1:
        address1 = address2 = ''
    else:
        address1 = address[0].strip()
        address2 = address[1].strip()
    zip_code, city = address[-1].strip().split(' ', 1)
    return address1, address2, zip_code.strip(), city.strip()


@rest("/internal/shop/rest/company/discover", "get")
@returns([CompanyTO])
@arguments(lat=float, lon=float)
def get_companies_at_location(lat, lon):
    audit_log(-1, u"Discover companies")
    solution_server_settings = get_solution_server_settings()
    url = 'https://api.data.be/1.0/search/geo?lat=%s&lng=%s&max=50&api_id=%s&api_key=%s' % \
        (lat, lon, solution_server_settings.data_be_app_id, solution_server_settings.data_be_app_key)
    logging.info(url)
    response = urlfetch.fetch(url, deadline=10)
    if response.status_code != 200:
        logging.error(response.content)
        return None
    logging.info(response.content)
    data = json.loads(response.content)
    if not data['success']:
        return None

    def toCompanyTO(company):
        c = CompanyTO()
        c.name = company['company-name'].split(u'\u003Cbr/\u003E')[0]  # remove metadata: split by <br>
        c.address1, c.address2, c.zip_code, c.city = parseDataDotBeAddressBE(company['address-nl'])
        c.country = company['vat-formatted'][:2]
        c.vat = normalize_vat(c.country, company['vat-formatted'])
        c.organization_type = ServiceProfile.ORGANIZATION_TYPE_PROFIT
        return c

    return map(toCompanyTO, data['data']['companies'])


@rest("/internal/shop/rest/order/sign", "post")
@returns(SignOrderReturnStatusTO)
@arguments(customer_id=(int, long), order_number=unicode, signature=unicode)
def rest_sign_order(customer_id, order_number, signature):
    has_admin_permissions = is_admin(gusers.get_current_user())
    try:
        r = sign_order(customer_id, order_number, signature)
        if r is None:
            customer, charge = None, None
        else:
            customer, charge = r

        return SignOrderReturnStatusTO.create(customer=customer, charge=charge, has_admin_permissions=has_admin_permissions)
    except BusinessException, be:
        return SignOrderReturnStatusTO.create(False, be.message, has_admin_permissions=has_admin_permissions)


@rest('/internal/shop/rest/charge/finish_on_site_payment', 'post')
@returns(ReturnStatusTO)
@arguments(customer_id=(int, long), charge_reference=unicode)
def rest_finish_on_site_payment(customer_id, charge_reference):
    try:
        finish_on_site_payment(gusers.get_current_user(), customer_id, charge_reference)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, be:
        return ReturnStatusTO.create(False, be.message)


def check_only_one_city_service(customer_id, service):
    if SolutionModule.CITY_APP in service.modules:
        customer = Customer.get_by_id(customer_id)
        invalidate_service_user_for_city(service.apps[0])
        city_service_user = get_service_user_for_city(service.apps[0])
        if city_service_user and city_service_user.email() != customer.service_email:
            raise BusinessException('City app module cannot be enabled for more than one service per app')


@rest("/internal/shop/rest/service/put", "post")
@returns(ProvisionReturnStatusTO)
@arguments(customer_id=(int, long), service=CustomerServiceTO)
def save_service(customer_id, service):
    try:
        check_only_one_city_service(customer_id, service)
        xg_on = db.create_transaction_options(xg=True)
        service = allow_transaction_propagation(db.run_in_transaction_options, xg_on, put_service, customer_id, service,
                                                broadcast_to_users=[gusers.get_current_user()])
        return ProvisionReturnStatusTO.create(True, None, service)
    except BusinessException, ex:
        logging.warn(ex, exc_info=1)
        return ProvisionReturnStatusTO.create(False, ex)
    except:
        logging.error("Failed to create service", exc_info=1)
        return ProvisionReturnStatusTO.create(False, "An unknown error has occurred. Please call Mobicage support.")


@rest("/internal/shop/rest/customer/service/get", "get")
@returns(CustomerServiceTO)
@arguments(customer_id=long)
def get_service(customer_id):
    audit_log(customer_id, u"Get service")

    customer = Customer.get_by_id(customer_id)
    azzert(user_has_permissions_to_team(gusers.get_current_user(), customer.team_id))
    service_user = users.User(customer.service_email)

    settings = get_solution_settings(service_user)
    svc = CustomerServiceTO()
    svc.name = settings.name
    svc.email = customer.user_email
    svc.address = settings.address
    svc.phone_number = settings.phone_number
    svc.language = settings.main_language
    svc.currency = settings.currency
    svc.modules = settings.modules
    svc.broadcast_types = settings.broadcast_types
    svc.apps = get_default_service_identity(service_user).sorted_app_ids
    svc.organization_type = get_service_profile(service_user).organizationType

    service_apps = App.get([App.create_key(app_id) for app_id in svc.apps])
    svc.app_infos = [AppInfoTO.fromModel(app) for app in service_apps]

    regio_manager_team = RegioManagerTeam.get_by_id(customer.team_id)
    current_user_apps = App.get([App.create_key(app_id) for app_id in regio_manager_team.app_ids])
    svc.current_user_app_infos = [AppInfoTO.fromModel(app) for app in current_user_apps]
    svc.managed_organization_types = customer.managed_organization_types if customer.managed_organization_types else []
    return svc


@rest("/internal/shop/rest/service/change_email", "post")
@returns(JobReturnStatusTO)
@arguments(customer_id=(long, int), email=unicode)
def change_service_email(customer_id, email):
    audit_log(customer_id, u"Change service e-mail")

    customer = Customer.get_by_id(customer_id)
    azzert(user_has_permissions_to_team(gusers.get_current_user(), customer.team_id))
    logging.info('Changing customer.user_email from "%s" to "%s"', customer.user_email, email)

    to_user = users.User(email)
    try:
        if customer.user_email == customer.service_email:
            from_service_user = users.User(customer.service_email)
            job = migrate_and_create_user_profile(gusers.get_current_user(), from_service_user, to_user)
            return JobReturnStatusTO.create(job_key=unicode(job.key()))
        else:
            from_user = users.User(customer.user_email)
            migrate_user(users.get_current_user(), from_user, to_user, customer.service_email, customer_id=customer_id)
            return JobReturnStatusTO.create()
    except BusinessException, e:
        logging.warn(e, exc_info=1)
        return JobReturnStatusTO.create(False, e.message)
    except:
        logging.exception("Failed to start the email migration job")
        return JobReturnStatusTO.create(False, "An unknown error has occurred. Please call Mobicage support.")


@rest("/internal/shop/rest/location/add", "post")
@returns(ReturnStatusTO)
@arguments(customer_id=(long, int), name=unicode)
def add_location(customer_id, name):
    current_user = gusers.get_current_user()
    azzert(is_admin(current_user) or is_team_admin(current_user))
    audit_log(customer_id, u"Add location")
    customer = Customer.get_by_id(customer_id)
    azzert(user_has_permissions_to_team(current_user, customer.team_id))
    create_new_location(customer.service_user, name, broadcast_to_users=[gusers.get_current_user()])
    return ReturnStatusTO.create()


@rest("/internal/shop/rest/job/get_status", "get")
@returns(JobStatusTO)
@arguments(job=unicode)
def get_job_status(job):
    job_model = db.get(job)
    return JobStatusTO.from_model(job_model)


@returns(ReturnStatusTO)
@arguments(prospect_key=(str, db.Key))
def invite_prospect(prospect_key):
    prospect = db.get(prospect_key)
    if not prospect:
        logging.warn("Could not find prospect with id %s", prospect_key)
        return ReturnStatusTO.create(False, 'Could not find prospect')

    prospect_interation = ProspectInteractions(parent=prospect)
    prospect_interation.type = ProspectInteractions.TYPE_INVITE
    prospect_interation.timestamp = now()
    prospect_interation.put()

    solution_server_settings = get_solution_server_settings()

    url = '%s?%s' % (TROPO_SESSIONS_URL, urllib.urlencode((('action', 'create'),
                                                           ('invite', 'true'),
                                                           ('token', solution_server_settings.tropo_token),
                                                           ('phone_number', prospect.phone),
                                                           ('prospect_id', prospect_interation.str_key),
                                                           ('mp3', prospect.app_id + "-invitation.mp3"))))

    logging.info(url)
    response = urlfetch.fetch(url, deadline=10)
    status_code = response.status_code
    if status_code != 200:
        logging.warn('Tropo returned status code "%s" on inviting prospect', status_code)
        return ReturnStatusTO.create(False, 'Tropo returned status code "%s" on inviting prospect' % status_code)

    logging.info(response.content)
    prospect.invite_code = Prospect.INVITE_CODE_IN_CALL
    prospect.put()

    return ReturnStatusTO.create()


@rest("/internal/shop/rest/loyalty/slides/delete", "post")
@returns(ReturnStatusTO)
@arguments(slide_id=(int, long))
def delete_loyalty_slide(slide_id):
    azzert(is_admin(gusers.get_current_user()))
    try:
        def trans():
            sli = ShopLoyaltySlide.get_by_id(slide_id)
            if sli:
                sli.deleted = True
                sli.put()
                on_trans_committed(update_all_user_data_admins, sli.apps if sli.has_apps else [])

        db.run_in_transaction(trans)

        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/internal/shop/rest/loyalty/slides/new_order/delete", "post")
@returns(ReturnStatusTO)
@arguments(slide_id=unicode)
def delete_loyalty_slide_new_order(slide_id):
    azzert(is_admin(gusers.get_current_user()))
    try:
        sli_key = ShopLoyaltySlideNewOrder.create_key(slide_id)
        sli = ShopLoyaltySlideNewOrder.get(sli_key)
        if sli:
            update_all_user_data_admins([sli.app_id])
            db.delete(sli_key)

        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


class LoyaltySlidesHandler(BizzManagerHandler):
    def get(self):
        current_user = gusers.get_current_user()
        if not is_admin(current_user):
            self.abort(403)
        path = os.path.join(os.path.dirname(__file__), 'html', 'loyalty_slides.html')
        context = get_shop_context(slides=[LoyaltySlideTO.fromSolutionLoyaltySlideObject(c, include_apps=True)
                                           for c in get_shop_loyalty_slides()])
        self.response.out.write(template.render(path, context))


class LoyaltySlidesNewOrderHandler(BizzManagerHandler):
    def get(self):
        current_user = gusers.get_current_user()
        if not is_admin(current_user):
            self.abort(403)
        path = os.path.join(os.path.dirname(__file__), 'html', 'loyalty_slides_new_order.html')
        context = get_shop_context(slides=[LoyaltySlideNewOrderTO.fromSlideObject(c)
                                           for c in get_shop_loyalty_slides_new_order()])
        self.response.out.write(template.render(path, context))


class UploadLoyaltySlideHandler(BizzManagerHandler):
    def post(self):
        current_user = gusers.get_current_user()
        if not is_admin(current_user):
            self.abort(403)
        slide_id = self.request.get("slide_id", "")
        slide_name = self.request.get("slide_name", "")
        try:
            slide_time = long(self.request.get("slide_time", 10))
        except:
            self.response.out.write(broadcast_via_iframe_result(u"rogerthat.internal.shop.loyalty.slide.post_result",
                                                                    error=u"Please fill in valid time!"))
            return
        slide_function_dependencies = long(self.request.get("slide_function_dependencies", 0))
        slide_apps = self.request.get("slide_apps", "[]")

        if slide_id == "":
            slide_id = None
        else:
            slide_id = long(slide_id)

        apps = json.loads(slide_apps)

        uploaded_file = self.request.POST.get('slide_file')  # type: FieldStorage
        if not slide_id and not isinstance(uploaded_file, FieldStorage):
            self.response.out.write(broadcast_via_iframe_result(u"rogerthat.internal.shop.loyalty.slide.post_result",
                                                                    error=u"Please select a picture!"))
            return

        gcs_filename = None
        content_type = None
        if isinstance(uploaded_file, FieldStorage):
            content_type = uploaded_file.type
            if not content_type.startswith("image/"):
                self.response.out.write(broadcast_via_iframe_result(u"rogerthat.internal.shop.loyalty.slide.post_result",
                                                                        error=u"The uploaded file is not an image!"))
                return

            date = datetime.datetime.now().strftime('%Y-%m-%d_%H:%M:%S')
            gcs_filename = '%s/oca/shop/loyalty/slides/%s_%s.%s' % (ROGERTHAT_ATTACHMENTS_BUCKET,
                                                                    date,
                                                                    uploaded_file.filename,
                                                                    get_extension_for_content_type(content_type))
            upload_to_gcs(uploaded_file.value, content_type, gcs_filename)

        def trans():
            if slide_id:
                sli = ShopLoyaltySlide.get_by_id(slide_id)
            else:
                sli = ShopLoyaltySlide()
                sli.timestamp = now()

            sli.deleted = False
            sli.name = slide_name
            sli.time = slide_time
            if gcs_filename:
                sli.gcs_filename = gcs_filename
            if content_type:
                sli.content_type = content_type
            if apps:
                sli.has_apps = True
            else:
                sli.has_apps = False
            sli.apps = apps
            sli.function_dependencies = slide_function_dependencies
            sli.put()
            on_trans_committed(update_all_user_data_admins, sli.apps if sli.has_apps else [])

        db.run_in_transaction(trans)

        self.response.out.write(broadcast_via_iframe_result(u"rogerthat.internal.shop.loyalty.slide.post_result"))


class UploadLoyaltySlideNewOrderHandler(BizzManagerHandler):
    def post(self):
        current_user = gusers.get_current_user()
        if not is_admin(current_user):
            self.abort(403)
        slide_id = self.request.get("slide_id", "")
        try:
            slide_time = long(self.request.get("slide_time", 10))
        except:
            self.response.out.write(broadcast_via_iframe_result(u"rogerthat.internal.shop.loyalty.slide.new_order.post_result",
                                                                    error=u"Please fill in valid time!"))
            return
        slide_app_id = self.request.get("slide_app", "")
        if slide_app_id == "":
            slide_app_id = None

        if slide_id == "":
            slide_id = None

        uploaded_file = self.request.POST.get('slide_file')  # type: FieldStorage
        if not slide_id and not isinstance(uploaded_file, FieldStorage):
            self.response.out.write(broadcast_via_iframe_result(u"rogerthat.internal.shop.loyalty.slide.new_order.post_result",
                                                                    error=u"Please select a picture!"))
            return

        gcs_filename = None
        content_type = None
        if isinstance(uploaded_file, FieldStorage):
            content_type = uploaded_file.type
            if not content_type.startswith("image/"):
                self.response.out.write(broadcast_via_iframe_result(u"rogerthat.internal.shop.loyalty.slide.post_result",
                                                                        error=u"The uploaded file is not an image!"))
                return

            date = datetime.datetime.now().strftime('%Y-%m-%d_%H:%M:%S')
            gcs_filename = '%s/oca/shop/loyalty/new_order_slides/%s_%s.%s' % (ROGERTHAT_ATTACHMENTS_BUCKET,
                                                                              date,
                                                                              uploaded_file.filename,
                                                                              get_extension_for_content_type(content_type))
            upload_to_gcs(uploaded_file.value, content_type, gcs_filename)

        def trans():
            if slide_id:
                sli = ShopLoyaltySlideNewOrder.get(ShopLoyaltySlideNewOrder.create_key(slide_id))
            else:
                if slide_app_id is None:
                    self.response.out.write(broadcast_via_iframe_result(u"rogerthat.internal.shop.loyalty.slide.new_order.post_result",
                                                                        error=u"Missing app"))
                    return
                sli = ShopLoyaltySlideNewOrder(key=ShopLoyaltySlideNewOrder.create_key(slide_app_id))
                sli.timestamp = now()

            sli.time = slide_time
            if gcs_filename:
                sli.gcs_filename = gcs_filename
            if content_type:
                sli.content_type = content_type
            sli.put()
            on_trans_committed(update_all_user_data_admins, [sli.app_id])

        db.run_in_transaction(trans)

        self.response.out.write(broadcast_via_iframe_result(u"rogerthat.internal.shop.loyalty.slide.new_order.post_result"))

class CityVouchersHandler(BizzManagerHandler):
    def get(self):
        current_user = gusers.get_current_user()
        if not is_admin(current_user):
            self.abort(403)
        path = os.path.join(os.path.dirname(__file__), 'html', 'city_vouchers.html')
        context = get_shop_context(city_voucher_settings=SolutionCityVoucherSettings.all())
        self.response.out.write(template.render(path, context))


@rest("/internal/shop/rest/city/vouchers/settings/put", "post")
@returns(ReturnStatusTO)
@arguments(app_id=unicode)
def rest_put_city_vouchers_settings(app_id):
    try:
        if is_admin(users.get_current_user()):
            put_city_voucher_settings(app_id)
        else:
            raise NoPermissionException('put city voucher settings')
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, exception:
        return ReturnStatusTO.create(False, exception.message)


@rest("/internal/shop/rest/city/vouchers/user/put", "post")
@returns(ReturnStatusTO)
@arguments(app_id=unicode, username=unicode, pincode=unicode)
def rest_put_city_vouchers_user(app_id, username, pincode):
    try:
        if is_admin(users.get_current_user()):
            put_city_voucher_user(app_id, username, pincode)
        else:
            raise NoPermissionException('put city voucher users')
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, exception:
        return ReturnStatusTO.create(False, exception.message)


@rest("/internal/shop/rest/city/vouchers/user/delete", "post")
@returns(ReturnStatusTO)
@arguments(app_id=unicode, username=unicode)
def rest_delete_city_vouchers_user(app_id, username):
    try:
        if is_admin(users.get_current_user()):
            delete_city_voucher_user(app_id, username)
        else:
            raise NoPermissionException('delete city voucher users')
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, exception:
        return ReturnStatusTO.create(False, exception.message)

@rest("/internal/shop/log_error", "post")
@returns(NoneType)
@arguments(description=unicode, errorMessage=unicode, timestamp=int, user_agent=unicode)
def log_error(description, errorMessage, timestamp, user_agent):
    from rogerthat.bizz.system import logErrorBizz
    from rogerthat.to.system import LogErrorRequestTO
    request = LogErrorRequestTO()
    request.description = description
    request.errorMessage = errorMessage
    request.mobicageVersion = u"web"
    request.platform = 0
    request.platformVersion = user_agent
    request.timestamp = timestamp
    return logErrorBizz(request, gusers.get_current_user(), session=users.get_current_session(), shop=True)


@rest("/internal/shop/orders/load_all", "get")
@returns(OrderAndInvoiceTO)
@arguments(customer_id=(int, long))
def load_unsigned_orders_by_customer(customer_id):
    # Loads the signed/unsigned orders and the invoices from a single customer.
    customer_key = Customer.create_key(customer_id)
    orders = Order.list(customer_key)
    invoices = get_invoices(customer_key)
    return OrderAndInvoiceTO.create(orders, invoices)


@rest("/internal/shop/prospect/history", "get")
@returns([ProspectHistoryTO])
@arguments(prospect_id=unicode)
def load_prospect_history(prospect_id):
    return [ProspectHistoryTO.create(h) for h in get_prospect_history(prospect_id)]


@rest("/internal/shop/rest/signup_apps", "get")
@returns([ShopAppTO])
@arguments()
def load_signup_apps():
    return [ShopAppTO.from_model(a) for a in ShopApp.all()]


@rest("/internal/shop/rest/apps/signup_enabled", "post")
@returns(ReturnStatusTO)
@arguments(app_id=unicode, enabled=bool)
def set_app_signup_enabled(app_id, enabled):
    azzert(is_admin(gusers.get_current_user()))
    put_app_signup_enabled(app_id, enabled)
    return RETURNSTATUS_TO_SUCCESS


@rest("/internal/shop/rest/apps/all", "get")
@returns([SimpleAppTO])
@arguments()
def load_all_apps():
    return [SimpleAppTO.create(a) for a in get_apps([App.APP_TYPE_CITY_APP], only_visible=False)]


@rest("/internal/shop/rest/apps/set", "post")
@returns(ReturnStatusTO)
@arguments(app=SimpleAppTO)
def set_surrounding_apps(app):
    azzert(is_admin(gusers.get_current_user()))
    put_surrounding_apps(app)
    return RETURNSTATUS_TO_SUCCESS


@rest("/internal/shop/rest/product/translations", "get", silent_result=True)
@returns([ProductTO])
@arguments(language=unicode)
def get_product_translations(language):
    guser = gusers.get_current_user()
    return [ProductTO.create(p, language) for p in list_products(google_user=guser)]


@rest("/internal/shop/rest/customers/generate_qr_codes", "get")
@returns(ReturnStatusTO)
@arguments(app_id=unicode, amount=(int, long), mode=unicode)
def rest_generate_qr_codes(app_id, amount, mode):
    return wrap_with_result_status(generate_unassigned_qr_codes_zip_for_app, app_id, amount, mode)


@rest("/internal/shop/rest/customer/app_broadcast", "post")
@returns(ReturnStatusTO)
@arguments(service=unicode, app_ids=[unicode], message=unicode)
def app_broadcast(service, app_ids, message):
    return wrap_with_result_status(post_app_broadcast, service, app_ids, message)


@rest("/internal/shop/rest/customer/test_app_broadcast", "post")
@returns(ReturnStatusTO)
@arguments(service=unicode, app_ids=[unicode], message=unicode, tester=unicode)
def test_app_broadcast(service, app_ids, message, tester):
    return wrap_with_result_status(post_app_broadcast, service, app_ids, message, tester)


@rest("/internal/shop/customer/charges", "get")
@returns(CustomerChargesTO)
@arguments(paid=bool, cursor=unicode)
def rest_get_customer_charges(paid=False, cursor=None):
    user = gusers.get_current_user()
    return get_customer_charges(user, paid, cursor=cursor)

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
from collections import OrderedDict
from contextlib import closing
import csv
import datetime
from functools import partial
import hashlib
import json
import logging
import os
import sys
from types import NoneType
import urllib
import urlparse

from PIL.Image import Image
from dateutil.relativedelta import relativedelta

from apiclient.discovery import build
from apiclient.errors import HttpError
from babel.dates import format_datetime, get_timezone, format_date
from google.appengine.api import search, images, users as gusers
from google.appengine.ext import deferred, db
import httplib2
from mcfw.cache import cached
from mcfw.properties import azzert
from mcfw.rpc import returns, arguments, serialize_complex_value
from mcfw.utils import normalize_search_string, chunks
from oauth2client.appengine import OAuth2Decorator
from oauth2client.client import HttpAccessTokenRefreshError
from rogerthat.bizz.app import get_app
from rogerthat.bizz.job.app_broadcast import test_send_app_broadcast, send_app_broadcast
from rogerthat.bizz.rtemail import EMAIL_REGEX
from rogerthat.consts import WEEK, SCHEDULED_QUEUE, FAST_QUEUE, \
    OFFICIALLY_SUPPORTED_COUNTRIES, MC_DASHBOARD, DEBUG
from rogerthat.dal import put_and_invalidate_cache
from rogerthat.dal.app import get_app_settings, get_app_by_id
from rogerthat.dal.profile import get_service_or_user_profile
from rogerthat.dal.service import get_default_service_identity
from rogerthat.exceptions.login import AlreadyUsedUrlException, InvalidUrlException, ExpiredUrlException
from rogerthat.models import App, ServiceIdentity, ServiceIdentityStatistic, ServiceProfile, UserProfile
from rogerthat.restapi.user import get_reset_password_url_params
from rogerthat.rpc import users
from rogerthat.rpc.rpc import rpc_items
from rogerthat.settings import get_server_settings
from rogerthat.to.service import UserDetailsTO
from rogerthat.translations import DEFAULT_LANGUAGE
from rogerthat.utils import bizz_check, now, channel, get_epoch_from_datetime, send_mail
from rogerthat.utils.app import create_app_user_by_email
from rogerthat.utils.crypto import encrypt, decrypt
from rogerthat.utils.location import geo_code, GeoCodeStatusException, GeoCodeZeroResultsException, \
    address_to_coordinates, GeoCodeException
from rogerthat.utils.service import create_service_identity_user, add_slash_default
from rogerthat.utils.transactions import run_in_transaction, run_in_xg_transaction
from shop import SHOP_JINJA_ENVIRONMENT, SHOP_TEMPLATES_FOLDER
from shop.business.i18n import shop_translate
from shop.business.legal_entities import get_vat_pct
from shop.business.service import set_service_enabled
from shop.constants import PROSPECT_CATEGORIES, OFFICIALLY_SUPPORTED_LANGUAGES, LOGO_LANGUAGES
from shop.exceptions import BusinessException, CustomerNotFoundException, ContactNotFoundException, \
    NoProductsSelectedException, ProductNotFoundException, InvalidProductAmountException, ProductNotAllowedException, \
    ReplaceBusinessException, TooManyAppsException, InvalidEmailFormatException, EmptyValueException, NoOrderException, \
    InvalidAppCountException, InvalidServiceEmailException, InvalidLanguageException, ModulesNotAllowedException, \
    InvalidProductQuantityException, MissingProductDependencyException, DuplicateCustomerNameException, \
    NotOperatingInCountryException, ContactHasOrdersException, ContactHasCreditCardException, \
    OrderAlreadyCanceledException, NoSupportManagerException, NoPermissionException, ServiceNameTooBigException
from shop.models import Customer, Contact, normalize_vat, Invoice, AuditLog, Order, Charge, OrderItem, Product, \
    StructuredInfoSequence, ChargeNumber, InvoiceNumber, Prospect, ShopTask, ProspectRejectionReason, RegioManager, \
    RegioManagerStatistic, ProspectHistory, OrderNumber, RegioManagerTeam, CreditCard, LegalEntity, CustomerSignup, \
    ShopApp
from shop.to import CustomerChargeTO, CustomerChargesTO, BoundsTO, ProspectTO, AppRightsTO, SimpleAppTO, \
    CustomerServiceTO, OrderItemTO, CompanyTO, CustomerTO
from solution_server_settings import get_solution_server_settings
from solution_server_settings.consts import SHOP_OAUTH_CLIENT_ID, SHOP_OAUTH_CLIENT_SECRET
from solutions import SOLUTION_COMMON, translate as common_translate
from solutions.common.bizz import SolutionModule, common_provision
from solutions.common.bizz.grecaptcha import recaptcha_verify
from solutions.common.bizz.jobs import delete_solution
from solutions.common.bizz.service import new_inbox_message, send_signup_update_messages
from solutions.common.bizz.messaging import send_inbox_forwarders_message
from solutions.common.dal import get_solution_settings, get_solution_settings_or_identity_settings
from solutions.common.dal.hints import get_solution_hints
from solutions.common.models import SolutionInboxMessage
from solutions.common.models.hints import SolutionHint
from solutions.common.models.qanda import Question
from solutions.common.models.statistics import AppBroadcastStatistics
from solutions.common.to import ProvisionResponseTO, SolutionInboxMessageTO
from solutions.flex.bizz import create_flex_service
import stripe
from xhtml2pdf import pisa


try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


shopOauthDecorator = OAuth2Decorator(
    client_id=SHOP_OAUTH_CLIENT_ID,
    client_secret=SHOP_OAUTH_CLIENT_SECRET,
    scope=u'https://www.googleapis.com/auth/calendar',
    callback_path=u'/shop/oauth2callback',)


TROPO_URL = 'https://api.tropo.com/1.0'
TROPO_SESSIONS_URL = '%s/sessions' % TROPO_URL
CUSTOMER_INDEX = 'CUSTOMER_INDEX'


class PaymentFailedException(Exception):
    pass


@returns(bool)
@arguments(user=users.User)
def is_admin(user):
    solutions_server_settings = get_solution_server_settings()
    return user in [gusers.User(email) for email in solutions_server_settings.shop_bizz_admin_emails]


@returns(bool)
@arguments(user=users.User)
def is_admin_or_other_legal_entity(user):
    if not is_admin(user):
        manager = RegioManager.get(RegioManager.create_key(user.email()))
        if not manager or manager.team.legal_entity.is_mobicage:
            return False
    return True


@returns(bool)
@arguments(user=users.User)
def is_payment_admin(user):
    solutions_server_settings = get_solution_server_settings()
    return user in [gusers.User(email) for email in solutions_server_settings.shop_payment_admin_emails]


@returns(bool)
@arguments(user=users.User)
def is_team_admin(user):
    manager = RegioManager.get(RegioManager.create_key(user.email()))
    return manager is not None and manager.admin


@returns(bool)
@arguments(user=users.User, team_id=(int, long))
def user_has_permissions_to_team(user, team_id):

    @db.non_transactional
    def _get_regio_manager(email):
        return RegioManager.get(RegioManager.create_key(email))

    if is_admin(user):
        return True
    regio_manager = _get_regio_manager(user.email())
    if regio_manager:
        return regio_manager_has_permissions_to_team(regio_manager, team_id)
    logging.error("has_permissions_to_team failed for user '%s' and team '%s'", user, team_id)
    return False


@returns(bool)
@arguments(regio_manager=RegioManager, team_id=(int, long))
def regio_manager_has_permissions_to_team(regio_manager, team_id):
    return regio_manager.team_id == team_id if regio_manager else False


@returns(bool)
@arguments(user=users.User, question=Question)
def user_has_permissions_to_question(user, question):
    if is_admin(user):
        return True

    key = RegioManager.create_key(user.email())
    manager = RegioManager.get(key)
    if manager:
        if manager.admin and manager.team_id == question.team_id:
            return True

    return False


def dict_str_for_audit_log(variables_dict):
    return u"\n".join((u"%s=%s" % (var, value) for var, value in variables_dict.iteritems()))


@db.non_transactional
def audit_log(customer_id, message, variables=None, user=None, prospect_id=None):
    al = AuditLog()
    al.customer_id = customer_id
    al.prospect_id = prospect_id
    al.date = now()
    if user:
        al.user = user
    else:
        al.user = gusers.get_current_user() or users.get_current_user()
    al.message = message
    if variables:
        al.variables = variables
    else:
        al.variables = dict_str_for_audit_log(sys._getframe(2).f_locals)
    rpc_items.append(db.put_async(al), audit_log, customer_id, message, al.variables, al.user, al.prospect_id)


@returns([Customer])
@arguments(search_string=unicode, app_ids=[unicode], team_id=(int, long, NoneType), limit=(int, long))
def search_customer(search_string, app_ids, team_id, limit=20):
    customer_index = search.Index(name=CUSTOMER_INDEX)
    q = normalize_search_string(search_string)
    if team_id:
        if not q.strip():
            return []

        team_qry = 'customer_team_id:"%s"' % unicode(team_id)
        if q:
            q += u' AND %s' % team_qry
        else:
            q = team_qry
    if app_ids:
        if not q.strip():
            return []

        or_query = ''
        for app_id in app_ids:
            if or_query:
                or_query += ' OR "%s"' % app_id
            else:
                or_query = '"%s"' % app_id
        if q:
            q += ' AND app_ids:(%s)' % or_query
        else:
            q = 'app_ids:(%s)' % or_query

    query = search.Query(query_string=q, options=search.QueryOptions(limit=limit))

    search_result = customer_index.search(query)
    customer_keys = [result.doc_id for result in search_result.results]
    tmp_customers = Customer.get(customer_keys)
    customers = []
    for i, c in enumerate(tmp_customers):
        if not c:
            # cleanup any previous index entry
            try:
                customer_index.delete(customer_keys[i])
            except ValueError:
                pass  # no index found for this customer yet
        else:
            customers.append(c)
    return customers


@returns()
@arguments(customer_key=db.Key)
def re_index_customer(customer_key):
    customer_index = search.Index(name=CUSTOMER_INDEX)

    # cleanup any previous index entry
    try:
        customer_index.delete([str(customer_key)])
    except ValueError:
        pass  # no index found for this customer yet

    # re-add index
    customer = Customer.get(customer_key)
    bizz_check(customer)

    fields = [search.AtomField(name='customer_key', value=str(customer_key)),
              search.TextField(name='customer_id', value=str(customer_key.id())),
              search.TextField(name='customer_name', value=customer.name),
              search.TextField(name='customer_address', value=" ".join(
                  [customer.address1 or '', customer.address2 or ''])),
              search.TextField(name='customer_zip_code', value=customer.zip_code),
              search.TextField(name='customer_city', value=customer.city),
              search.TextField(name='customer_team_id', value=unicode(customer.team_id))
              ]

    for contact in Contact.list(customer):
        contact_id = contact.key().id()
        fields.extend([search.TextField(name='contact_phone_%s' % contact_id, value=contact.phone_number),
                       search.TextField(name='contact_email_%s' % contact_id, value=contact.email),
                       search.TextField(name='contact_first_name_%s' % contact_id, value=contact.first_name),
                       search.TextField(name='contact_last_name_%s' % contact_id, value=contact.last_name),
                       ])
    if customer.service_email:
        si = get_default_service_identity(users.User(customer.service_email))
        fields.extend([search.TextField(name='service_name', value=si.name),
                       search.TextField(name='user_email', value=customer.user_email),
                       search.TextField(name='app_ids', value=" ".join(si.appIds)),
                       search.AtomField(name='service_email', value=normalize_search_string(customer.service_email))
                       ])

    customer_index.put(search.Document(doc_id=str(customer_key), fields=fields))


@returns(Customer)
@arguments(current_user=users.User, customer_id=(int, long, NoneType), vat=unicode, name=unicode, address1=unicode,
           address2=unicode, zip_code=unicode, city=unicode, country=unicode, language=unicode,
           organization_type=(int, long), prospect_id=unicode, force=bool, team_id=(int, long, NoneType),
           website=unicode, facebook_page=unicode)
def create_or_update_customer(current_user, customer_id, vat, name, address1, address2, zip_code, city, country,
                              language, organization_type, prospect_id, force=False, team_id=None,
                              website=None, facebook_page=None):
    is_in_transaction = db.is_in_transaction()
    name = name.strip()
    if not name:
        raise EmptyValueException('first_name')
    if not country:
        raise EmptyValueException('country')
    if not language:
        raise EmptyValueException('Language')
    if not organization_type:
        raise EmptyValueException('organization_type')
    if country not in OFFICIALLY_SUPPORTED_COUNTRIES:
        raise NotOperatingInCountryException(country)
    if language not in OFFICIALLY_SUPPORTED_LANGUAGES:
        raise InvalidLanguageException(language)

    regio_manager = RegioManager.get(RegioManager.create_key(current_user.email())) if current_user else None
    customer_team_id = regio_manager.team_id if regio_manager else team_id
    if not customer_team_id:
        if is_admin(current_user):
            customer_team_id = RegioManagerTeam.get_by_app_id(App.APP_ID_ROGERTHAT).id
        else:
            raise EmptyValueException('team')

    if customer_id:
        customer = Customer.get_by_id(customer_id)
        if not customer.manager:
            customer.manager = current_user
        if not customer.team_id:
            customer.team_id = customer_team_id

        if is_admin(current_user):
            customer.team_id = team_id
        elif regio_manager:
            azzert(regio_manager_has_permissions_to_team(regio_manager, customer.team_id))

    else:
        customer = Customer(creation_time=now(),
                            team_id=customer_team_id,
                            manager=current_user)

    if not force:
        @db.non_transactional
        def list_customers_by_name(*args):
            return Customer.list_by_name(*args)

        try:
            customer_key = customer.key()
        except db.NotSavedError:
            customer_key = None

        for other_customer in list_customers_by_name(name, 2 if customer_key else 1):
            if customer_key != other_customer.key():
                raise DuplicateCustomerNameException(name)

    if vat:
        vat = normalize_vat(country, vat)
    customer.vat = vat
    customer.name = name
    customer.normalized_name = Customer.normalize_name(name)
    customer.address1 = address1
    customer.address2 = address2
    customer.zip_code = zip_code
    customer.city = city
    customer.country = country
    customer.language = language
    customer.organization_type = organization_type
    customer.website = website
    customer.facebook_page = facebook_page
    if prospect_id is not None:
        customer.prospect_id = prospect_id
    customer.put()

    if prospect_id is not None:
        def trans():
            prospect = Prospect.get_by_key_name(prospect_id)
            _link_prospect_to_customer(current_user, prospect, customer)

        if is_in_transaction:
            trans()
        else:
            run_in_xg_transaction(trans)

    deferred.defer(re_index_customer, customer.key(), _transactional=is_in_transaction, _queue=FAST_QUEUE)

    return customer


@returns(Order)
@arguments(customer_or_id=(Customer, int, long), contact_or_id=(Contact, int, long), items=[OrderItemTO], replace=bool,
           skip_app_check=bool, regio_manager_user=gusers.User)
def create_order(customer_or_id, contact_or_id, items, replace=False, skip_app_check=False, regio_manager_user=None):
    if isinstance(customer_or_id, Customer):
        audit_log(customer_or_id.id, u"Creating new order.")
        customer = customer_or_id
    else:
        audit_log(customer_or_id, u"Creating new order.")
        customer = Customer.get_by_id(customer_or_id)
    google_user = gusers.get_current_user()
    team = RegioManagerTeam.get_by_id(customer.team_id)
    if google_user:
        azzert(user_has_permissions_to_team(google_user, customer.team_id))
    customer_id = customer.id

    if isinstance(contact_or_id, Contact):
        contact = contact_or_id
    else:
        contact = Contact.get_by_contact_id(customer, contact_or_id)
        if not contact:
            raise ContactNotFoundException(contact_or_id)
    contact_id = contact.id

    vat_pct = get_vat_pct(customer, team)
    total = 0.0
    if not (len(items) > 0):
        raise NoProductsSelectedException()

    _order_items_signed_orders = list()

    def get_order_items_signed_orders():
        if _order_items_signed_orders:
            return _order_items_signed_orders
        for order in Order.list_signed(customer.key()):
            _order_items_signed_orders.extend(list(OrderItem.list_by_order(order.key())))
        return _order_items_signed_orders

    is_subscription = False
    is_subscription_extension_order = False

    @db.non_transactional
    def get_products():
        return {p.code: p for p in Product.list_by_legal_entity(team.legal_entity_id)}

    all_products = get_products()
    for item in items:
        product = all_products[item.product]
        if not product:
            raise ProductNotFoundException(item.product)
        elif item.count < 1 or (product.possible_counts and item.count not in product.possible_counts):
            raise InvalidProductAmountException(item.count, item.product)
        if product.is_subscription:
            is_subscription = True
        if product.is_subscription_extension:
            is_subscription_extension_order = True
        total += product.price * item.count
        item.price = product.price
        if product.organization_types and not customer.organization_type in product.organization_types:
            raise ProductNotAllowedException(product.description(DEFAULT_LANGUAGE))
        if product.product_dependencies:
            for dependency in product.product_dependencies:
                dependency_found = False
                dependencies_product_codes = []
                for dependency in dependency.split('|'):
                    dependency_count = item.count
                    if ':' in dependency:
                        dependency, dependency_count = dependency.split(":")
                        dependency_count = int(dependency_count)
                    dependencies_product_codes.append(dependency)

                    for oi in items:
                        if oi.product == dependency and (dependency_count <= 0 or oi.count == item.count):
                            dependency_found = True
                            break
                    else:
                        # Dependency not found in this order
                        if dependency_count < 0:
                            for oi in get_order_items_signed_orders():
                                if oi.product_code == dependency and (dependency_count <= 0 or oi.number == item.count):
                                    dependency_found = True
                                    break

                if not dependency_found:
                    # for legal entities it is possible that not all possible dependencies exist. so here I take
                    # the first existing dependency to make sure the next lines don't raise a KeyError
                    # it is intentional that it raises a KeyError if none of the dependency products exist
                    for dependency in dependencies_product_codes:
                        if dependency in all_products:
                            break
                    if dependency_count > 0:
                        raise InvalidProductQuantityException(product.description(DEFAULT_LANGUAGE),
                                                              all_products[dependency].description(DEFAULT_LANGUAGE))
                    else:
                        raise MissingProductDependencyException(product.description(DEFAULT_LANGUAGE),
                                                                all_products[dependency].description(DEFAULT_LANGUAGE))

    vat = vat_pct * total / 100
    total_vat_incl = total + vat

    # get all city apps, -1 to exclude the default app
    if not skip_app_check:
        total_extra_app_count = App.all().filter('type', App.APP_TYPE_CITY_APP).filter('visible', True).count() - 1

    def trans():
        if isinstance(customer_or_id, Customer):
            customer = customer_or_id
        else:
            # ensure the latest version of the customer object is used
            customer = Customer.get_by_id(customer_id)
        # In case of subscription order, check if this customer does not already own a subscription, only 1 is supported
        if is_subscription and customer.subscription_order_number:
            if replace:
                customer = cancel_order(customer, customer.subscription_order_number, False, False)
                if customer.service_email:
                    # Limit service modules according new subscription
                    deferred.defer(vacuum_service_modules_by_subscription, customer_id, _transactional=True)
            else:
                raise ReplaceBusinessException(customer.subscription_order_number)

        order = Order(key_name=OrderNumber.next(team.legal_entity_key), parent=customer)
        order.contact_id = contact_id
        order.date = now()
        order.vat_pct = vat_pct
        order.amount = int(round(total))
        order.vat = int(round(vat))
        order.total_amount = int(round(total_vat_incl))
        order.is_subscription_order = is_subscription
        order.is_subscription_extension_order = is_subscription_extension_order
        regio_manager = None
        if regio_manager_user:
            regio_manager = RegioManager.get(RegioManager.create_key(regio_manager_user.email()))
            if not regio_manager:
                azzert(is_admin(regio_manager_user))

        if regio_manager:
            order.team_id = regio_manager.team_id
            order.manager = regio_manager.user
        else:
            order.team_id = customer.team_id
            order.manager = customer.manager

        def has_product(order_item, product_code):
            # legal entities have their product code prefixed
            return order_item.product == product_code or order_item.product.endswith('_' + product_code)

        number = 0
        extra_apps_count = 0
        for item in items:
            number += 1
            order_item = OrderItem(parent=order)
            order_item.number = number
            order_item.comment = item.comment
            order_item.product_code = item.product
            order_item.count = item.count
            order_item.price = item.price
            order_item.put()

            if has_product(item, Product.PRODUCT_EXTRA_CITY):
                extra_apps_count += 1
            elif has_product(item, Product.PRODUCT_ACTION_3_EXTRA_CITIES):
                extra_apps_count += 3
            elif any(has_product(item, product_code) for product_code in ('MSSU', 'SUBY', Product.PRODUCT_FREE_PRESENCE)):
                customer.subscription_type = Customer.SUBSCRIPTION_TYPE_STATIC
            elif any(has_product(item, product_code) for product_code in ('MSUP', 'SUBX')):
                customer.subscription_type = Customer.SUBSCRIPTION_TYPE_DYNAMIC
            elif any(has_product(item, product_code) for product_code in ('LOYA', 'LSUP')):
                customer.has_loyalty = True

        if is_subscription:
            customer.subscription_order_number = order.key().name()
            customer.manager = order.manager
            customer.team_id = order.team_id

        if not customer.extra_apps_count:
            customer.extra_apps_count = 0
        customer.extra_apps_count += extra_apps_count
        # check if the customer did not select more extra apps than there are extra apps available
        if not skip_app_check:
            if customer.extra_apps_count > total_extra_app_count:
                raise TooManyAppsException(customer.extra_apps_count, total_extra_app_count)

        if customer.creation_time == 0:
            customer.creation_time = now()

        put_and_invalidate_cache(order, customer)

        # sign orders that cost nothing.
        if total_vat_incl == 0.0:
            deferred.defer(sign_order, customer_id, order.order_number, u'', True, _countdown=2, _transactional=True,
                           _queue=FAST_QUEUE)

        return order

    def sign_demo_order(o_number):
        if customer.prospect_id:
            app = App.get(App.create_key(Prospect.get(Prospect.create_key(customer.prospect_id)).app_id))
            if app.demo:
                # sign the order and do not create a charge
                sign_order(customer_id, o_number, u'', no_charge=True)

    order = run_in_transaction(trans, True)
    if not skip_app_check:
        sign_demo_order(order.order_number)
    return order


@arguments(service=CustomerServiceTO)
def validate_service(service):
    if not EMAIL_REGEX.match(service.email):
        raise InvalidEmailFormatException(service.email)
    if not service.language:
        raise EmptyValueException('language')
    if not service.name:
        raise EmptyValueException('first_name')
    if len(service.name) > 50:
        raise ServiceNameTooBigException()
    if not service.organization_type:
        raise EmptyValueException('organization_type')
    if not service.phone_number:
        raise EmptyValueException('phone_number')
    service.email = users.User(service.email).email()


@returns(ProvisionResponseTO)
@arguments(customer_or_id=(int, long, Customer), service=CustomerServiceTO, skip_module_check=bool,
           search_enabled=bool, skip_email_check=bool, broadcast_to_users=[users.User])
def put_service(customer_or_id, service, skip_module_check=False, search_enabled=False, skip_email_check=False,
                broadcast_to_users=None):
    """
    Args:
        customer_or_id (Customer or int)
        service (CustomerServiceTO)
        skip_module_check (bool)
        search_enabled (bool)
        skip_email_check (bool)
        broadcast_to_users (list of users.User)
    """
    validate_service(service)

    if isinstance(customer_or_id, Customer):
        customer = customer_or_id
    else:
        customer = Customer.get_by_id(customer_or_id)
    google_user = gusers.get_current_user()
    if google_user:
        azzert(user_has_permissions_to_team(google_user, customer.team_id),
               'manager %s has no permission update a service from team %s ' % (google_user.email(), customer.team_id))

    customer_id = customer.id
    is_demo = False
    audit_log(customer_id, u"Update or create service")
    # Check if there is an order for this customer with a subscription license.
    module_sets = set()
    products = set()
    if not skip_module_check:
        for order in Order.all().ancestor(customer).filter("is_subscription_order =", True).filter("status <",
                                                                                                   Order.STATUS_CANCELED):
            for order_item in OrderItem.all().ancestor(order):
                products.add(order_item.product_code)
        is_demo = Product.PRODUCT_DEMO in products
        for product in db.get([Product.create_key(code) for code in products]):
            if product.is_subscription and product.module_set:
                module_sets.add(product.module_set)
        if not module_sets:
            raise NoOrderException()

        # Check if this customer can order these modules.
        if 'ALL' not in module_sets:
            module_set = set()
            for ms in module_sets:
                for m in getattr(SolutionModule, ms):
                    module_set.add(m)
            service_modules = set(service.modules)
            if not service_modules.issubset(module_set):
                raise ModulesNotAllowedException(sorted([m for m in service_modules if m not in module_set]))

    has_loyalty = True if SolutionModule.LOYALTY in service.modules else False
    if customer.has_loyalty != has_loyalty:
        customer.has_loyalty = has_loyalty
    customer.managed_organization_types = service.managed_organization_types
    customer.put()
    redeploy = bool(customer.service_email)
    user_existed = False

    if not customer.extra_apps_count:
        customer.extra_apps_count = 0

    # customer should have the same amount of active apps as he paid for
    # Ensure all services are present in the rogerthat app (for non-demo services)
    if not is_demo:
        is_demo = get_app(service.apps[0]).demo
    if App.APP_ID_ROGERTHAT not in service.apps and not is_demo:
        service.apps.append(App.APP_ID_ROGERTHAT)
    app_list = list(service.apps)
    if App.APP_ID_OSA_LOYALTY in app_list:
        app_list.remove(App.APP_ID_OSA_LOYALTY)

    if not is_demo and not (len(app_list) == 0):
        if len(app_list) != customer.extra_apps_count + 2:  # + 2 because of the default app and rogerthat
            raise InvalidAppCountException(customer.extra_apps_count + 2)
    if redeploy:
        if customer.user_email != service.email and not skip_email_check:
            raise InvalidServiceEmailException(customer.user_email)
    else:
        p = get_service_or_user_profile(users.User(service.email))
        user_existed = p and isinstance(p, UserProfile)

    modules = service.modules
    if redeploy:
        sln_settings = get_solution_settings(users.User(customer.service_email))
        hidden_modules = SolutionModule.hidden_modules()
        for m in sln_settings.modules:
            if m in hidden_modules and m not in modules:
                modules.append(m)

    r = create_flex_service(customer.service_email if redeploy else service.email, service.name, service.address,
                            service.phone_number, [service.language], service.currency, modules,
                            service.broadcast_types, service.apps, redeploy, service.organization_type,
                            search_enabled, qualified_identifier=service.email, broadcast_to_users=broadcast_to_users)

    r.auto_login_url = customer.auto_login_url

    deferred.defer(_after_service_saved, customer.key(), service.email, r, bool(redeploy or user_existed), service.apps,
                   broadcast_to_users, _transactional=db.is_in_transaction(), _queue=FAST_QUEUE)
    return r


@arguments(customer_key=db.Key, user_email=unicode, r=ProvisionResponseTO, is_redeploy=bool, app_ids=[unicode],
           broadcast_to_users=[users.User])
def _after_service_saved(customer_key, user_email, r, is_redeploy, app_ids, broadcast_to_users):
    """
    Args:
        customer_key (db.Key)
        user_email (unicode)
        r (ProvisionResponseTO)
        is_redeploy (bool)
        app_ids (list of unicode)
        broadcast_to_users (list of users.User)
    """

    def trans():
        customer = Customer.get(customer_key)
        updated = False
        to_put = []
        if customer.app_ids != app_ids:
            sln_settings = get_solution_settings(users.User(r.login))
            new_default_app_id = app_ids[0]
            if SolutionModule.CITY_APP in sln_settings.modules:
                old_default_app = App.get_by_key_name(customer.default_app_id) if customer.default_app_id else None
                new_default_app = App.get_by_key_name(new_default_app_id)  # type: App
                if old_default_app and customer.default_app_id != new_default_app_id and r.login in old_default_app.admin_services:
                    # remove from admin service
                    old_default_app.admin_services.remove(r.login)
                    to_put.append(old_default_app)
                # add to admin service
                new_default_app.admin_services.append(r.login)
                to_put.append(new_default_app)
                if not is_redeploy:
                    app_settings = get_app_settings(new_default_app_id)
                    app_settings.birthday_message = common_translate(sln_settings.main_language, SOLUTION_COMMON,
                                                                     u'birthday_message_default_text')
                    to_put.append(app_settings)
            customer.default_app_id = new_default_app_id
            customer.app_ids = app_ids
            updated = True

        if not customer.service_email:
            customer.user_email = user_email
            customer.service_email = r.login
            updated = True

        if updated:
            to_put.append(customer)

        deferred.defer(re_index_customer, customer_key, _transactional=True, _queue=FAST_QUEUE)

        if broadcast_to_users:
            channel.send_message(broadcast_to_users, 'shop.provision.success', customer_id=customer.id)

        if not is_redeploy:
            settings = get_server_settings()
            contact = Contact.get_one(customer_key)

            # get the login url that matches the /customers/signin path
            # from settings customSigninPaths for now
            login_url = settings.baseUrl
            for url, path in chunks(settings.customSigninPaths, 2):
                if path.startswith('/customers/signin'):
                    login_url = 'https://' + url

            parsed_login_url = urlparse.urlparse(login_url)
            action = shop_translate(customer.language, 'password_reset')
            url_params = get_reset_password_url_params(customer.name, users.User(user_email), action=action)
            reset_password_link = '%s://%s%s?%s' % (parsed_login_url.scheme, parsed_login_url.netloc,
                                                    '/customers/setpassword', url_params)

            # TODO: email with OSA style in header, footer
            params = {
                'language': customer.language,
                'name': contact.first_name + ' ' + contact.last_name,
                'login_url': login_url,
                'user_email': user_email,
                'password': r.password,
                'reset_password_link': reset_password_link
            }

            text_body = SHOP_JINJA_ENVIRONMENT.get_template('emails/login_information_email.tmpl').render(params)
            html_body = SHOP_JINJA_ENVIRONMENT.get_template('emails/login_information_email_html.tmpl').render(params)

            # TODO: Change the new customer password handling, sending passwords via email is a serious security issue.

            subject = '%s - %s' % (common_translate(customer.language, SOLUTION_COMMON, 'our-city-app'),
                                   common_translate(customer.language, SOLUTION_COMMON, 'login_information'))
            app = get_app_by_id(customer.app_id)
            from_email = '%s <%s>' % (app.name, app.get_contact_email_address())

            send_mail(from_email, user_email, subject, text_body, html=html_body)
        if to_put:
            db.put(to_put)

    run_in_xg_transaction(trans)


@returns([Invoice])
@arguments(customer_or_key=(db.Key, Customer))
def get_invoices(customer_or_key):
    return Invoice.all().ancestor(customer_or_key).order('-date')


@returns(Contact)
@arguments(customer_or_id=(int, long, Customer), first_name=unicode, last_name=unicode, email_address=unicode,
           phone_number=unicode)
def create_contact(customer_or_id, first_name, last_name, email_address, phone_number):
    first_name = first_name.strip()
    last_name = last_name.strip()
    phone_number = phone_number.strip()
    if not first_name:
        raise EmptyValueException('first_name')
    if not email_address:
        raise EmptyValueException('email_address')
    if not phone_number:
        raise EmptyValueException('Phone number')
    if not EMAIL_REGEX.match(email_address):
        raise InvalidEmailFormatException(email_address)

    if isinstance(customer_or_id, Customer):
        customer = customer_or_id
    else:
        customer = Customer.get_by_id(customer_or_id)

    audit_log(customer.id, u"Creating new contact.")
    contact = Contact(parent=customer)
    contact.first_name = first_name
    contact.last_name = last_name
    contact.email = email_address
    contact.phone_number = phone_number
    contact.put()

    deferred.defer(re_index_customer, customer.key(), _transactional=db.is_in_transaction(), _queue=FAST_QUEUE)
    return contact


@returns(Contact)
@arguments(customer_id=(int, long), contact_id=(int, long), first_name=unicode, last_name=unicode,
           email_address=unicode, phone_number=unicode)
def update_contact(customer_id, contact_id, first_name, last_name, email_address, phone_number):
    first_name = first_name.strip()
    last_name = last_name.strip()
    phone_number = phone_number.strip()
    if not first_name:
        raise EmptyValueException('first_name')
    if not email_address:
        raise EmptyValueException('email_address')
    if not phone_number:
        raise EmptyValueException('Phone number')

    def trans():
        customer, contact = db.get([Customer.create_key(customer_id), Contact.create_key(contact_id, customer_id)])
        if not customer:
            raise CustomerNotFoundException(customer_id)
        if not contact:
            raise ContactNotFoundException(contact_id)
        contact.first_name = first_name
        contact.last_name = last_name
        contact.email = email_address
        contact.phone_number = phone_number
        contact.put()
        deferred.defer(re_index_customer, customer.key(), _transactional=True, _queue=FAST_QUEUE)
        return contact

    return run_in_transaction(trans)


@returns()
@arguments(customer_id=(int, long), contact_id=(int, long))
def delete_contact(customer_id, contact_id):
    customer, contact = db.get([Customer.create_key(customer_id), Contact.create_key(contact_id, customer_id)])
    if not customer:
        raise CustomerNotFoundException(customer_id)
    if contact:
        if Order.list_by_contact_id(contact_id).get():
            raise ContactHasOrdersException(contact_id)
        if CreditCard.list_by_contact_id(contact_id).get():
            raise ContactHasCreditCardException(contact_id)
        contact.delete()


@returns(tuple)
@arguments(customer_id=(int, long), order_number=unicode, signature=unicode, no_charge=bool)
def sign_order(customer_id, order_number, signature, no_charge=False):
    audit_log(customer_id, u"Sign order")

    if not no_charge:
        _, png_in_base64 = signature.split(',', 1)
        png = base64.decodestring(png_in_base64)
        img = images.Image(png)
        img.im_feeling_lucky()
        jpg = img.execute_transforms(output_encoding=images.JPEG)
    products = Product.get_products_dict()

    def trans():
        order_key = Order.create_key(customer_id, order_number)
        customer, order = db.get((Customer.create_key(customer_id), order_key))
        bizz_check(order, "Order not found!")

        bizz_check(not order.signature, "Already signed order!")
        cur_google_user = gusers.get_current_user()
        if cur_google_user:
            azzert(user_has_permissions_to_team(cur_google_user, customer.team_id))

        if not no_charge:
            order.signature = jpg
        with closing(StringIO()) as pdf:
            generate_order_or_invoice_pdf(pdf, customer, order)
            order.pdf = pdf.getvalue()
        order.status = Order.STATUS_SIGNED
        order.date_signed = now()

        order_items = list(OrderItem.list_by_order(order.key()))
        if order.is_subscription_order:
            months = 0

            for item in order_items:
                product = products[item.product_code]
                if product.is_subscription and product.price > 0:
                    months += item.count
                if not product.is_subscription and product.extra_subscription_months > 0:
                    months += product.extra_subscription_months

            if months > 0:
                next_charge_datetime = datetime.datetime.utcfromtimestamp(now()) + relativedelta(months=months)
                order.next_charge_date = get_epoch_from_datetime(next_charge_datetime)
            else:
                order.next_charge_date = Order.default_next_charge_date()

            # reconnect all previous connected friends if the service was disabled in the past
            if customer.service_disabled_at != 0:
                deferred.defer(set_service_enabled, customer.id, _queue=FAST_QUEUE)
        else:
            extra_months = 0
            for item in order_items:
                product = products[item.product_code]
                if not product.is_subscription and product.extra_subscription_months > 0:
                    extra_months += product.extra_subscription_months

            sub_order = None
            if extra_months > 0:
                sub_order = Order.get_by_order_number(customer_id, customer.subscription_order_number)
                next_charge_datetime = datetime.datetime.utcfromtimestamp(
                    sub_order.next_charge_date) + relativedelta(months=extra_months)
                sub_order.next_charge_date = get_epoch_from_datetime(next_charge_datetime)
                sub_order.put()

            is_subscription_extension_order = False
            for item in order_items:
                product = products[item.product_code]
                if product.is_subscription_extension:
                    is_subscription_extension_order = True
                    break
            order.is_subscription_extension_order = is_subscription_extension_order
            if is_subscription_extension_order:
                sub_order = sub_order or Order.get_by_order_number(customer.id, customer.subscription_order_number)
                order.next_charge_date = sub_order.next_charge_date

        order.put()

        if not no_charge:
            deferred.defer(send_order_email, order_key, gusers.get_current_user(), _transactional=True,
                           _queue=FAST_QUEUE)

            if order.total_amount > 0:
                charge = Charge(parent=order_key)
                charge.date = now()
                charge.type = Charge.TYPE_ORDER_DELIVERY
                charge.amount = order.amount
                charge.vat_pct = order.vat_pct
                charge.vat = order.vat
                charge.total_amount = order.total_amount
                charge.manager = order.manager
                charge.team_id = order.team_id
                charge.charge_number = ChargeNumber.next(customer.team.legal_entity_key)
                charge.currency_code = customer.team.legal_entity.currency_code
                charge.put()

                # Update the regio manager statistics
                deferred.defer(update_regiomanager_statistic, gained_value=order.amount / 100, manager=order.manager,
                               _transactional=True)
                channel_data = {
                    'customer': customer.name,
                    'manager': order.manager.nickname() if order.manager else 'unknown',
                    'amount': charge.amount / 100,
                    'currency': charge.currency
                }
                server_settings = get_server_settings()
                send_to = server_settings.supportWorkers
                send_to.append(MC_DASHBOARD.email())
                channel.send_message(map(users.User, server_settings.supportWorkers), 'shop.monitoring.signed_order',
                                     info=channel_data, skip_dashboard_user=False)
                return customer, charge

        return None, None

    return run_in_transaction(trans, True)


def send_order_email(order_key, google_user):
    order = db.run_in_transaction(db.get, order_key)

    customer = db.get(order.customer_key)
    if not customer.user_email:
        logging.info('There is no service yet for Customer %s (%s). Waiting with sending order %s...',
                     customer.id, customer.name, order.order_number)
        deferred.defer(send_order_email, order_key, google_user, _countdown=60, _queue=SCHEDULED_QUEUE)
        return

    solution_server_settings = get_solution_server_settings()
    contact = order.contact

    subject = shop_translate(customer.language, 'osa_order_email_subject', order_number=order.order_number)

    # TODO: (?) Email with OSA styling (header, footer)
    with closing(StringIO()) as sb:
        sb.write(shop_translate(customer.language, 'dear_name',
                                name=contact.first_name + ' ' + contact.last_name).encode('utf-8'))
        sb.write('\n\n')
        sb.write(shop_translate(customer.language, 'thanks_for_order').encode('utf-8'))
        sb.write('\n\n')
        sb.write(shop_translate(customer.language, 'goto_dashboard_to_download_invoice').encode('utf-8'))
        sb.write('\n- ')
        sb.write(shop_translate(customer.language, 'login_with_email', email=customer.user_email).encode('utf-8'))
        sb.write('\n- ')
        sb.write(shop_translate(customer.language, 'navigate_to_settings').encode('utf-8'))
        sb.write('\n- ')
        sb.write(shop_translate(customer.language, 'select_billing').encode('utf-8'))
        sb.write('\n\n')
        sb.write(shop_translate(customer.language, 'with_regards').encode('utf-8'))
        sb.write('\n\n')
        sb.write(shop_translate(customer.language, 'the_osa_team').encode('utf-8'))
        body = sb.getvalue()

    to_ = [contact.email]
    if google_user:
        to_.append(google_user.email())
    send_mail(solution_server_settings.shop_billing_email, to_, subject, body)


@returns()
@arguments(current_user=users.User, customer_id=(int, long), charge_reference=unicode)
def finish_on_site_payment(current_user, customer_id, charge_reference):
    audit_log(customer_id, u"Finish on site payment")

    def trans():
        customer = Customer.get_by_id(customer_id)
        if not customer.team.legal_entity.is_mobicage:
            raise BusinessException('On site payment can only be used in the mobicage team.')
        azzert(user_has_permissions_to_team(current_user, customer.team_id))
        charge = Charge.get_by_reference(charge_reference, customer)
        azzert(charge, "Charge not found")

        if charge.status == Charge.STATUS_EXECUTED:
            logging.warn('Charge %s already has status EXECUTED', charge_reference)
            return

        _mark_charge_as_executed(current_user, customer_id, charge.order_number, charge, Invoice.PAYMENT_ON_SITE)

    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans)


@returns()
@arguments(current_user=users.User, customer_id=(int, long), order_number=unicode, charge_id=(int, long), paid=bool)
def manual_payment(current_user, customer_id, order_number, charge_id, paid):
    manager = RegioManager.get(RegioManager.create_key(current_user.email()))

    # Only allow priviliged people, change this logic and get fired :), * Geert
    if not (is_payment_admin(current_user) or (manager and manager.team.legal_entity.is_reseller)):
        raise NoPermissionException()

    def trans():
        charge = db.get(Charge.create_key(charge_id, order_number, customer_id))
        if not charge:
            raise PaymentFailedException("Received incorrect request")
        _mark_charge_as_executed(current_user, customer_id, order_number, charge,
                                 Invoice.PAYMENT_MANUAL if paid else Invoice.PAYMENT_MANUAL_AFTER)

    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans)


def _mark_charge_as_executed(current_user, customer_id, order_number, charge, payment_type):
    azzert(db.is_in_transaction())

    if charge.status == Charge.STATUS_EXECUTED:

        if payment_type == Invoice.PAYMENT_MANUAL_AFTER:
            raise PaymentFailedException("Do not know what to do.")

        invoices = list(Invoice.all().ancestor(charge))
        if len(invoices) == 0:
            raise PaymentFailedException("Failed to find invoice of executed payment.")
        elif len(invoices) == 1:
            invoice = invoices[0]
            invoice.paid = True
            invoice.paid_timestamp = now()
            invoice.put()
            logging.info('Invoice %s marked as paid', invoice.invoice_number)
        else:
            raise PaymentFailedException("Multiple invoices found for executed payment.")

    else:
        # Update the charge
        charge.status = Charge.STATUS_EXECUTED
        charge.date_executed = now()
        charge.put()

        invoice_number = InvoiceNumber.next(Customer.get_by_id(customer_id).team.legal_entity_key)
        deferred.defer(create_invoice, customer_id, order_number, charge.id, invoice_number, current_user, payment_type,
                       _transactional=True, _queue=FAST_QUEUE)


@returns(unicode)
@arguments(customer_id=(int, long), order_number=unicode, charge_id=(int, long), invoice_number=unicode,
           operator=gusers.User, payment_type=int)
def create_invoice(customer_id, order_number, charge_id, invoice_number, operator, payment_type):
    def trans():
        customer_key = Customer.create_key(customer_id)
        order_key = Order.create_key(customer_id, order_number)
        charge_key = Charge.create_key(charge_id, order_number, customer_id)
        invoice_key = Invoice.create_key(customer_id, order_number, charge_id, invoice_number)

        customer, order, charge, invoice = db.get((customer_key, order_key, charge_key, invoice_key))
        contact = order.contact
        azzert(order and contact and charge and customer)

        if not charge.structured_info:
            charge.structured_info = StructuredInfoSequence.next()

        if invoice is None:
            invoice = Invoice(key_name=invoice_number, parent=charge, amount=charge.amount, vat_pct=charge.vat_pct,
                              vat=charge.vat, total_amount=charge.total_amount, date=now(), payment_type=payment_type,
                              operator=operator, paid=False)
            invoice.legal_entity_id = customer.legal_entity.id
        else:
            invoice.payment_type = payment_type
        azzert(invoice.legal_entity_id, 'invoice has no legal_entity_id')
        if payment_type == Invoice.PAYMENT_MANUAL_AFTER:
            buf = generate_transfer_document_image(charge)
            transfer_doc_png = buf.getvalue()
            payment_note = "data:image/png;base64,%s" % base64.b64encode(transfer_doc_png)
            invoice.payment_term = now() + WEEK
        else:
            transfer_doc_png = None
            payment_note = None
            invoice.paid = True
            invoice.paid_timestamp = now()

        with closing(StringIO()) as pdf:
            generate_order_or_invoice_pdf(pdf, customer, order, invoice, payment_type=payment_type,
                                          payment_note=payment_note, charge=charge)
            invoice.pdf = pdf.getvalue()

        if charge.invoice_number and charge.invoice_number != invoice.invoice_number:
            raise BusinessException('Charge %s already has another invoice: %s' % (charge_id, invoice.invoice_number))
        charge.invoice_number = invoice.invoice_number
        db.put([invoice, charge])

        if customer.service_email:
            channel.send_message(users.User(customer.service_email), 'common.billing.invoices.update')

        deferred.defer(send_invoice_email, customer.key(), invoice.key(), contact.key(), payment_type, transfer_doc_png,
                       _transactional=True)

    run_in_xg_transaction(trans)


def send_invoice_email(customer_key, invoice_key, contact_key, payment_type, transfer_doc_png):
    customer, invoice, contact = db.run_in_transaction(db.get, (customer_key, invoice_key, contact_key))
    if not customer.user_email:
        logging.info('There is no service yet for Customer %s (%s). Waiting with sending invoice %s...',
                     customer.id, customer.name, invoice.invoice_number)
        deferred.defer(send_invoice_email, customer_key, invoice_key, contact_key, payment_type, transfer_doc_png,
                       _countdown=60, _queue=SCHEDULED_QUEUE)
        return

    solution_server_settings = get_solution_server_settings()

    subject = shop_translate(customer.language, 'osa_new_invoice')
    if payment_type != Invoice.PAYMENT_MANUAL_AFTER:
        payment_notice = shop_translate(customer.language, 'payment_already_satisfied')
    else:
        payment_notice = shop_translate(customer.language, 'maximum_payment_date', date=invoice.payment_term_formatted)

    # TODO: email with OSA styling (header, footer)

    with closing(StringIO()) as sb:
        sb.write(shop_translate(customer.language, 'dear_name', name="%s %s" %
                                (contact.first_name, contact.last_name)).encode('utf-8'))
        sb.write('\n\n')
        sb.write(
            shop_translate(customer.language, 'invoice_is_available', invoice=invoice.invoice_number).encode('utf-8'))
        sb.write('\n')
        sb.write(payment_notice.encode('utf-8'))
        sb.write('\n\n')
        sb.write(shop_translate(customer.language, 'goto_dashboard_to_download_invoice').encode('utf-8'))
        sb.write('\n- ')
        sb.write(shop_translate(customer.language, 'login_with_email', email=customer.user_email).encode('utf-8'))
        sb.write('\n- ')
        sb.write(shop_translate(customer.language, 'navigate_to_settings').encode('utf-8'))
        sb.write('\n- ')
        sb.write(shop_translate(customer.language, 'select_billing').encode('utf-8'))
        sb.write('\n')
        sb.write(
            shop_translate(customer.language, 'for_questions_contact_us', contact_email=solution_server_settings.shop_reply_to_email).encode('utf-8'))
        sb.write('\n\n')
        sb.write(shop_translate(customer.language, 'thx_for_doing_business').encode('utf-8'))
        sb.write('\n\n')
        sb.write(shop_translate(customer.language, 'with_regards').encode('utf-8'))
        sb.write('\n')
        sb.write(shop_translate(customer.language, 'the_osa_team').encode('utf-8'))
        body = sb.getvalue()

    attachments = None
    if payment_type in (Invoice.PAYMENT_STRIPE, Invoice.PAYMENT_ON_SITE, Invoice.PAYMENT_MANUAL):
        pass
    elif payment_type == Invoice.PAYMENT_MANUAL_AFTER:
        attachments = []
        attachments.append(("invoice-%s.pdf" % invoice.invoice_number,
                            base64.b64encode(invoice.pdf)))

        if customer.legal_entity.is_mobicage:
            attachments.append(("payment.png",
                                base64.b64encode(transfer_doc_png)))
    else:
        raise ValueError("Unknown payment_type received.")

    to = [contact.email]
    to.extend(solution_server_settings.shop_payment_admin_emails)
    send_mail(solution_server_settings.shop_billing_email, to, subject, body, attachments=attachments)


def vacuum_service_modules_by_subscription(customer_id):
    def trans():
        customer = Customer.get_by_id(customer_id)
        products = set()
        order = Order.get_by_order_number(customer_id, customer.subscription_order_number)
        for order_item in OrderItem.all().ancestor(order):
            products.add(order_item.product_code)
        module_sets = set()
        for product in db.get([Product.create_key(code) for code in products]):
            if product.is_subscription:
                module_sets.add(product.module_set)
        if 'ALL' in module_sets:
            return
        module_set = set()
        for ms in module_sets:
            for m in getattr(SolutionModule, ms):
                module_set.add(m)
        service_modules = list(module_set)

        service_user = users.User(customer.service_email)
        sln_settings = get_solution_settings(service_user)
        sln_settings.modules = service_modules
        put_and_invalidate_cache(sln_settings)
        deferred.defer(common_provision, service_user, _transactional=True, _queue=FAST_QUEUE)

    run_in_xg_transaction(trans)


@returns(Customer)
@arguments(customer_or_id=(int, long, Customer), order_number=unicode, confirm=bool, delete_service=bool,
           charge_id=(int, long))
def cancel_order(customer_or_id, order_number, confirm=False, delete_service=False, charge_id=None):

    def trans():
        logging.info('Canceling order %s', order_number)
        service_deleted = False
        to_put = list()
        if isinstance(customer_or_id, Customer):
            customer = customer_or_id
            order = db.get(Order.create_key(customer_or_id.id, order_number))
        else:
            customer_id = customer_or_id
            customer, order = db.get((Customer.create_key(customer_id),
                                      Order.create_key(customer_id, order_number)))  # type: Customer, Order

        if order.status == Order.STATUS_CANCELED:
            raise OrderAlreadyCanceledException(order)
        if delete_service and order.is_subscription_order and customer.service_email:
            if confirm:
                delete_solution(users.User(customer.service_email), True)
                service_deleted = True
            else:
                raise BusinessException(
                    "confirm:This will delete the associated application of " + customer.user_email + ". Are you sure you want to continue?")

        order_items = order.list_items()
        products = {p.code: p for p in db.get([Product.create_key(i.product_code) for i in order_items])}
        for item in order_items:
            product = products[item.product_code]
            if product.is_subscription_extension:
                if product.code == Product.PRODUCT_EXTRA_CITY:
                    customer.extra_apps_count -= 1
        azzert(customer.extra_apps_count >= 0)
        if order.status == Order.STATUS_SIGNED:
            if charge_id:
                charge = Charge.get(Charge.create_key(charge_id, order_number, customer.id))
                if not charge:
                    raise BusinessException('Charge with id %s not found' % charge_id)
                if charge.status == Charge.STATUS_EXECUTED:
                    raise BusinessException(
                        'Charge with id %s has already been executed so it cannot be canceled' % charge_id)
                if charge.invoice_number != '':
                    raise BusinessException(
                        'Charge with id %s already has an invoice so it cannot be canceled' % charge_id)
                charge.status = Charge.STATUS_CANCELLED
                charge.date_cancelled = now()
                to_put.append(charge)
            else:
                for charge in Charge.all().ancestor(order).filter("status =", Charge.STATUS_PENDING):
                    charge.status = Charge.STATUS_CANCELLED
                    charge.date_cancelled = now()
                    to_put.append(charge)
            if not order.is_subscription_order:
                extra_months = 0
                for item in order_items:
                    product = products[item.product_code]
                    if not product.is_subscription and product.extra_subscription_months > 0:
                        extra_months += product.extra_subscription_months

                if extra_months > 0:
                    logging.info('Substracting %d months from %s\'s subscription' % (extra_months, customer.name))
                    sub_order = Order.get_by_order_number(customer.id, customer.subscription_order_number)
                    next_charge_datetime = datetime.datetime.utcfromtimestamp(
                        sub_order.next_charge_date) - relativedelta(
                            months=extra_months)
                    sub_order.next_charge_date = get_epoch_from_datetime(next_charge_datetime)
                    to_put.append(sub_order)

        order.status = Order.STATUS_CANCELED
        order.date_canceled = now()
        to_put.append(order)
        if order.is_subscription_order:
            if service_deleted:
                customer.service_email = None
                customer.user_email = None
                customer.app_ids = []
            customer.subscription_order_number = None
        to_put.append(customer)
        db.put(to_put)
        return customer

    return run_in_transaction(trans, xg=True)


@arguments(charge=Charge)
def generate_transfer_document_image(charge):
    from PIL import Image  # @Reimport
    from PIL import ImageDraw
    from PIL import ImageFont
    sepa_templates_path = os.path.join(os.path.dirname(__file__), "sepa_templates")
    font = ImageFont.truetype(os.path.join(sepa_templates_path, 'Courier New Bold.ttf'), 50)
    text_img = Image.new('RGBA', (2480, 1176), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_img)
    amount_str = " ".join(list(("% 11.2f" % (charge.total_amount / 100.0)))).replace('.', ' ')
    draw.text((1795, 290), amount_str, font=font, fill=(0, 0, 0, 255))
    if charge.structured_info:
        structured_info = " ".join(list(charge.structured_info))
        draw.text((415, 1095), structured_info, font=font, fill=(0, 0, 0, 255))
    background = Image.open(os.path.join(sepa_templates_path, "SEPA_NF.png"))
    background.paste(text_img, (0, 0), text_img)
    buf = StringIO()
    background.save(buf, "PNG")
    return buf


@returns()
@arguments(customer_id=(int, long), order_number=unicode, charge_id=(int, long), customer_po_number=unicode)
def set_po_number(customer_id, order_number, charge_id, customer_po_number):
    def trans():
        charge = db.get(Charge.create_key(charge_id, order_number, customer_id))
        azzert(charge)
        charge.customer_po_number = customer_po_number
        charge.put()

    return db.run_in_transaction(trans)


@returns()
@arguments(google_user=gusers.User, customer_id=(int, long), order_number=unicode, charge_id=(int, long),
           amount=(int, long))
def set_charge_advance_payment(google_user, customer_id, order_number, charge_id, amount):
    # Only admins and managers in non-mobicage legal entities have access to this function
    if not is_admin_or_other_legal_entity(google_user):
        raise NoPermissionException()

    def trans():
        charge = db.get(Charge.create_key(charge_id, order_number, customer_id))
        azzert(charge)
        charge.amount_paid_in_advance = amount
        charge.put()

    return db.run_in_transaction(trans)


@returns(NoneType)
@arguments(customer_id=(int, long), order_number=unicode, charge_id=(int, long), google_user=gusers.User)
def send_payment_info(customer_id, order_number, charge_id, google_user):
    # Only admins and managers in non-mobicage legal entities have access to this function
    if not is_admin_or_other_legal_entity(google_user):
        raise NoPermissionException()

    def trans():
        charge = db.get(Charge.create_key(charge_id, order_number, customer_id))
        if not charge.structured_info:
            charge.structured_info = StructuredInfoSequence.next()
        else:
            charge.payment_reminders += 1
        charge.last_notification = now()
        charge.put()
        return charge

    xg_on = db.create_transaction_options(xg=True)
    charge = db.run_in_transaction_options(xg_on, trans)

    buf = generate_transfer_document_image(charge)

    transfer_doc_png = buf.getvalue()

    order, customer = db.get((Order.create_key(customer_id, order_number), Customer.create_key(customer_id)))
    contact = order.contact
    to = contact.email
    subject = shop_translate(customer.language, 'oca_charge', order_number=order_number, charge_id=charge.key().id())
    if charge.payment_reminders > 0:
        subject = shop_translate(customer.language, 'oca_reminder', payment_reminder_number=charge.payment_reminders,
                                 subject=subject)

    solution_server_settings = get_solution_server_settings()

    with closing(StringIO()) as sb:
        sb.write(shop_translate(customer.language, 'dear_name', name=(
            contact.first_name + ' ' + contact.last_name)).encode('utf-8'))
        sb.write('\n\n')
        sb.write(shop_translate(customer.language, 'pro_forma_in_attachment').encode('utf-8'))
        sb.write('\n')
        sb.write(shop_translate(customer.language, 'final_invoice_after_payment').encode('utf-8'))
        sb.write('\n\n')
        sb.write(shop_translate(customer.language, 'can_still_opt_for_cc').encode('utf-8'))
        sb.write('\n')
        sb.write(shop_translate(customer.language, 'cc_no_wasted_time').encode('utf-8'))
        sb.write('\n')
        sb.write(shop_translate(customer.language, 'howto_configure_cc').encode('utf-8'))
        sb.write('\n- ')
        sb.write(shop_translate(customer.language, 'login_with_email', email=customer.user_email).encode('utf-8'))
        sb.write('\n- ')
        sb.write(shop_translate(customer.language, 'navigate_to_settings').encode('utf-8'))
        sb.write('\n- ')
        sb.write(shop_translate(customer.language, 'select_billing').encode('utf-8'))
        sb.write('\n- ')
        sb.write(shop_translate(customer.language, 'use_manage_cc_function').encode('utf-8'))
        sb.write('\n\n')
        sb.write(shop_translate(customer.language, 'with_regards').encode('utf-8'))
        sb.write('\n')
        sb.write(shop_translate(customer.language, 'the_osa_team').encode('utf-8'))
        body = sb.getvalue()

    attachments = []
    with closing(StringIO()) as pdf_stream:
        generate_order_or_invoice_pdf(pdf_stream, customer, order, None, True,
                                      "data:image/png;base64,%s" % base64.b64encode(transfer_doc_png),
                                      charge=charge)
        attachments.append(("pro-forma-invoice.pdf",
                             base64.b64encode(pdf_stream.getvalue())))

    attachments.append(("payment.png",
                        base64.b64encode(transfer_doc_png)))

    send_mail(solution_server_settings.shop_billing_email, to, subject, body, attachments=attachments)


def generate_order_or_invoice_pdf(output_stream, customer, order, invoice=None, pro_forma=False,
                                  payment_note=None, payment_type=None, charge=None):
    order_item_qry = OrderItem.all().ancestor(order)
    recurrent = charge and charge.is_recurrent
    if invoice or pro_forma:
        path = 'invoice_pdf.html'
    else:
        path = 'order_pdf.html'

    products = Product.get_products_dict()
    order_items = list()
    for item in order_item_qry:
        if recurrent:
            product = products[item.product_code]
            if product.is_subscription or product.is_subscription_discount or product.is_subscription_extension:
                order_items.append(item)
        else:  # new order
            order_items.append(item)

    if recurrent and charge.subscription_extension_order_item_keys:
        recurrent_order_items = db.get(charge.subscription_extension_order_item_keys)
        order_items.extend(recurrent_order_items)

    for item in order_items:
        item.product_description = products[item.product_code].description(customer.language).replace('\n', '<br />')
        item.product_comment = item.comment or products[item.product_code].default_comment(customer.language) \
            .replace('\n', '<br />')

    if customer.language in LOGO_LANGUAGES:
        logo_path = 'html/img/osa_white_%s_250.jpg' % customer.language
    else:
        logo_path = 'html/img/osa_white_en_250.jpg'

    solution_server_settings = get_solution_server_settings()

    variables = {
        "customer": customer,
        'language': customer.language,
        "charge": charge,
        "invoice": invoice,
        "order": order,
        "payment_note": payment_note,
        "payment_type": payment_type,
        "order_items": sorted(order_items, key=lambda x: x.number),
        "recurrent": recurrent,
        'tos_link': '<a href="%s">%s</a>' % (solution_server_settings.shop_privacy_policy_url,
                                             solution_server_settings.shop_privacy_policy_url),
        'logo_path': logo_path
    }
    source_html = SHOP_JINJA_ENVIRONMENT.get_template(path).render(variables)
    # Monkey patch problem in PIL
    orig_to_bytes = getattr(Image, "tobytes", None)
    try:
        if orig_to_bytes is None:
            Image.tobytes = Image.tostring
        pisa.CreatePDF(src=source_html, dest=output_stream, path=SHOP_TEMPLATES_FOLDER)
    finally:
        if orig_to_bytes is None:
            delattr(Image, "tobytes")


@returns(tuple)
@arguments(app_id=unicode, category=unicode, cursor=unicode)
def list_prospects(app_id, category, cursor=None):
    qry = Prospect.all()
    qry.filter('app_id =', app_id)
    if category != 'all':
        qry.filter('categories =', category)
    qry.order("address")
    qry.with_cursor(cursor)
    prospects = qry.fetch(500)
    if not prospects:
        return [], None
    return prospects, unicode(qry.cursor())


@returns(dict)
@arguments(date_from=int, date_to=int)
def list_history_tasks(date_from, date_to):
    return ShopTask.history(date_from, date_to)


@returns(BoundsTO)
@arguments(city=unicode, country=unicode)
def find_city_bounds(city, country):
    address = "%s,%s" % (city, country)
    try:
        result = geo_code(address)
    except GeoCodeStatusException, e:
        raise BusinessException('Got unexpected geo-code status: %s' % e.message)
    except GeoCodeZeroResultsException, e:
        raise BusinessException('No results found for %s' % address)

    bounds_dict = result['geometry'].get('bounds') or result['geometry'].get('viewport')

    bounds = BoundsTO.create(bounds_dict['southwest']['lat'],
                             bounds_dict['southwest']['lng'],
                             bounds_dict['northeast']['lat'],
                             bounds_dict['northeast']['lng'])
    return bounds


@returns(Prospect)
@arguments(current_user=users.User, prospect_id=unicode, name=unicode, phone=unicode, address=unicode, email=unicode,
           website=unicode, new_comment=unicode, prospect_types=[unicode], categories=[unicode], app_id=unicode,
           status_code=(int, long, NoneType), invite_code=(int, long, NoneType))
def put_prospect(current_user, prospect_id, name, phone, address, email, website, new_comment, prospect_types=None,
                 categories=None, app_id=None, status_code=None, invite_code=None):
    if not name:
        raise EmptyValueException('name')
    if not address:
        raise EmptyValueException('address')
    if not categories:
        raise EmptyValueException('categories')
    for c in categories:
        if c not in PROSPECT_CATEGORIES:
            raise BusinessException('Invalid category \"%s\"' % c)

    is_update = bool(prospect_id)

    must_resolve_address = True
    if is_update:
        if not phone:
            raise EmptyValueException('phone')

        prospect = Prospect.get_by_key_name(prospect_id)
        must_resolve_address = prospect.address != address
    else:
        if not app_id:
            raise EmptyValueException('app')
        if not prospect_types:
            raise EmptyValueException('type')
    formatted_address = None
    if must_resolve_address:
        try:
            lat, lon, google_place_id, postal_code, formatted_address = address_to_coordinates(address,
                                                                                               postal_code_required=False)
            if not postal_code:
                # if Google didn't know the postal code, then the formatted address will propably be incomplete
                formatted_address = None
            if not is_update:
                prospect_id = google_place_id
        except GeoCodeStatusException, e:
            logging.debug('Got unexpected status %s', e.message, exc_info=True)
            raise Exception('Got unexpected status %s' % e.message)
        except (GeoCodeZeroResultsException, GeoCodeException), e:
            raise BusinessException('We could not find %s.\nMake sure your search is spelled correctly. '
                                    'Try adding a city, state, or zip code.' % address)
        geo_point = db.GeoPt(lat, lon)

    else:
        geo_point = None

    def trans():
        if is_update:
            prospect = Prospect.get_by_key_name(prospect_id)
        else:
            azzert(prospect_id)
            prospect = Prospect(key_name=prospect_id, app_id=app_id)

        prospect.name = name
        prospect.phone = phone
        prospect.address = formatted_address or address
        prospect.email = email
        prospect.website = website
        prospect.categories = categories
        if geo_point:
            prospect.geo_point = geo_point

        to_put = list()
        if new_comment:
            prospect.add_comment(new_comment, current_user)
            # Create a history object
            # this here rarely happens though.
            p_history = ProspectHistory(executed_by=current_user.email(), created_time=now(),
                                        type=ProspectHistory.TYPE_ADDED_COMMENT, comment=new_comment,
                                        status=status_code,
                                        reason=None, parent=prospect.key())
            to_put.append(p_history)

        if prospect_types is not None:
            prospect.type = sorted(prospect_types)

        if status_code is not None:
            prospect.status = status_code

        if invite_code is not None:
            prospect.invite_code = invite_code

        to_put.append(prospect)
        db.put(to_put)

        deferred.defer(broadcast_prospect_update if is_update else broadcast_prospect_creation,
                       current_user, prospect, _transactional=True, _queue=FAST_QUEUE)
        from shop.business.prospect import re_index_prospect
        deferred.defer(re_index_prospect, prospect, _transactional=True, _queue=FAST_QUEUE)
        return prospect

    prospect = db.run_in_transaction(trans)
    return prospect


def _link_prospect_to_customer(current_user, prospect, customer):
    azzert(db.is_in_transaction())

    customer.prospect_id = prospect.id
    prospect.customer_id = customer.id
    prospect.status = Prospect.STATUS_CUSTOMER

    to_put = [prospect, customer]
    updated_task_lists = set()
    # Check if we need to close a current VISIT/CALL task
    _close_existing_prospect_tasks(prospect, to_put, updated_task_lists)

    deferred.defer(broadcast_prospect_update, current_user, prospect, _transactional=True, _queue=FAST_QUEUE)
    if updated_task_lists:
        deferred.defer(broadcast_task_updates, filter(None, updated_task_lists), _transactional=True, _queue=FAST_QUEUE)

    put_and_invalidate_cache(*to_put)


@returns(Prospect)
@arguments(current_user=users.User, prospect_id=unicode, customer_id=(int, long))
def link_prospect_to_customer(current_user, prospect_id, customer_id):
    def trans():
        customer, prospect = db.get([Customer.create_key(customer_id), Prospect.create_key(prospect_id)])
        azzert(customer and prospect)

        if customer.prospect_id is not None and customer.prospect_id != prospect_id:
            logging.info('Customer %s is already linked to prospect %s', customer_id, customer.prospect_id)
            raise BusinessException(u'This customer is already linked to a prospect')

        if prospect.customer_id is not None and prospect.customer_id != customer_id:
            logging.info('Prospect %s is already linked to customer %s', prospect_id, prospect.customer_id)
            raise BusinessException(u'This prospect is already linked to a customer')

        _link_prospect_to_customer(current_user, prospect, customer)
        return prospect

    xg_on = db.create_transaction_options(xg=True)
    return db.run_in_transaction_options(xg_on, trans)


def _close_existing_prospect_tasks(prospect, to_put, updated_task_lists):
    existing_tasks = ShopTask.list_by_prospect(prospect,
                                               [ShopTask.TYPE_CALL, ShopTask.TYPE_VISIT],
                                               [ShopTask.STATUS_NEW]).fetch(None)
    for existing_task in existing_tasks:
        logging.debug('Closing existing task: %s', db.to_dict(existing_task))
        existing_task.status = ShopTask.STATUS_CLOSED
        existing_task.closed_by = '<auto>'
        existing_task.closed_time = now()
        to_put.append(existing_task)
        updated_task_lists.add(existing_task.assignee)


@returns(tuple)
@arguments(current_user=users.User, prospect_id=unicode, status=(int, long), reason=unicode,
           action_timestamp=(int, long, NoneType), assignee=unicode, comment=unicode, customer_id=(int, long, NoneType),
           certainty=(int, long, NoneType), subscription=(int, long, NoneType), email=unicode, invite_language=unicode,
           appointment_type=(int, long, NoneType))
def set_prospect_status(current_user, prospect_id, status, reason=None, action_timestamp=None, assignee=None,
                        comment=None, customer_id=None, certainty=None, subscription=None, email=None,
                        invite_language=None, appointment_type=None):
    ACTION_STATUSES = (Prospect.STATUS_CALL_BACK, Prospect.STATUS_APPOINTMENT_MADE)
    REASON_STATUSES = (Prospect.STATUS_IRRELEVANT, Prospect.STATUS_NOT_INTERESTED)

    bizz_check(reason or status not in REASON_STATUSES, u'Reason is required')
    bizz_check(action_timestamp or status not in ACTION_STATUSES, u'Action timestamp is required')

    if action_timestamp is not None:
        bizz_check(action_timestamp > now(), u'Action timestamp must be in the future')

    if invite_language and not invite_language in OFFICIALLY_SUPPORTED_LANGUAGES:
        raise InvalidLanguageException(invite_language)

    def trans():
        prospect = Prospect.get(Prospect.create_key(prospect_id))
        azzert(prospect)

        to_put = [prospect]
        updated_task_lists = set()

        # Check if we need to close a current VISIT/CALL task
        _close_existing_prospect_tasks(prospect, to_put, updated_task_lists)

        prospect.status = status
        prospect.reason = reason
        prospect.assignee = assignee
        prospect.certainty = certainty
        prospect.subscription = subscription
        if email and not prospect.email:
            prospect.email = email

        if status in ACTION_STATUSES:
            task_type = ShopTask.type_from_prospect_status(status)
            task = create_task(current_user.email(), prospect, assignee, action_timestamp, task_type, prospect.app_id,
                               address=prospect.address, certainty=certainty, subscription=subscription)
            to_put.append(task)
            updated_task_lists.add(task.assignee)

            prospect.action_timestamp = action_timestamp

        else:
            prospect.action_timestamp = None
            task_type = None

        if comment:
            prospect.add_comment(comment, current_user)

        if customer_id is not None:
            prospect.customer_id = customer_id

        put_and_invalidate_cache(*to_put)
        if updated_task_lists:
            deferred.defer(broadcast_task_updates, filter(None, updated_task_lists), _transactional=True,
                           _queue=FAST_QUEUE)
        deferred.defer(broadcast_prospect_update, current_user, prospect, _transactional=True, _queue=FAST_QUEUE)
        # Create a history object
        p_history = ProspectHistory(executed_by=current_user.email(), created_time=now(), type=task_type,
                                    comment=comment, status=status, reason=reason, parent=prospect.key())
        p_history.put()

        return prospect

    def create_google_calendar_event(prospect):
        """
        Creates a task in the Google calendar of the assigned manager.
        Google will then send an invitation email to the prospect

        Returns:
            calendar_error(unicode): The error that occurred, if any.
        """
        calendar_error = None
        # If we don't have access to the calendar of the manager or something else goes wrong,
        # the ShopTask will still be created but the invitation will have to be send manually.
        if email is not None and email != u'':
            manager = RegioManager.get_by_key_name(assignee)
            if manager.credentials is None or manager.credentials.invalid:
                logging.warn(
                    'Not creating a calendar event for %s as we don\'t have permission to user their calendar' % manager.name)
                calendar_error = 'Could not automatically create a calendar event for this visit because no' \
                                 ' permission to use the calendar of %s was granted.' \
                                 ' Please create the event manually.' % manager.name

            else:
                http = manager.credentials.authorize(httplib2.Http(timeout=15))
                calendar_service = build('calendar', 'v3')
                tz = 'Europe/Brussels'
                appointment_date = datetime.datetime.fromtimestamp(action_timestamp,
                                                                   tz=get_timezone(tz))
                appointment_hdate = format_datetime(appointment_date, locale='nl_BE',
                                                    format='EEEE d/M/yyyy H:mm')

                with closing(StringIO()) as sb:
                    sb.write(shop_translate(invite_language, 'dear_name', name='').encode('utf-8'))
                    sb.write('\n\n')
                    sb.write(shop_translate(invite_language, 'appointment_confirmed_via_phone',
                                            date=appointment_hdate).encode('utf-8'))
                    sb.write('\n\n')
                    if appointment_type == ShopTask.APPOINTMENT_TYPE_LOYALTY_EXPLANATION:
                        sb.write(shop_translate(invite_language, 'loyalty_explanation').encode('utf-8'))
                        sb.write('\n')
                    if appointment_type == ShopTask.APPOINTMENT_TYPE_LOYALTY_INSTALATION:
                        sb.write(shop_translate(invite_language, 'loyalty_installation').encode('utf-8'))
                        sb.write('\n')
                        sb.write(shop_translate(invite_language, 'loyalty_installation_preparations').encode('utf-8'))
                        sb.write('\n- ')
                        sb.write(shop_translate(invite_language, 'loyalty_installation_space').encode('utf-8'))
                        sb.write('\n- ')
                        sb.write(shop_translate(invite_language, 'loyalty_installation_wifi').encode('utf-8'))
                        sb.write('\n- ')
                        sb.write(shop_translate(invite_language, 'loyalty_installation_power').encode('utf-8'))
                        sb.write('\n')
                    sb.write('\n')
                    sb.write(shop_translate(invite_language, 'with_regards').encode('utf-8'))
                    sb.write('\n\n')
                    sb.write(manager.name.encode('utf-8'))
                    sb.write('\n')
                    sb.write(manager.email.encode('utf-8'))
                    if manager.phone:
                        sb.write('\n')
                        sb.write(shop_translate(invite_language, 'telephone_abbr').encode('utf-8'))
                        sb.write(': ')
                        sb.write(manager.phone.encode('utf-8'))
                    description = sb.getvalue()

                event = {
                    'summary': shop_translate(invite_language, 'appointment_with_osa',
                                              prospect_name=prospect.name),
                    'location': u'%s' % prospect.address,
                    'start': {
                        'dateTime': appointment_date.isoformat('T'),
                        'timeZone': tz
                    },
                    'end': {
                        'dateTime': datetime.datetime.fromtimestamp(
                            action_timestamp + ShopTask.VISIT_DURATION * 60, tz=get_timezone(tz)).isoformat(
                            'T'),
                        'timeZone': tz
                    },
                    'attendees': [
                        {'email': assignee, 'displayName': manager.name, 'responseStatus': 'accepted'},
                        {'email': email, 'displayName': prospect.name}
                    ],
                    'visibility': 'public',
                    'email_reminders': {
                        'useDefault': False,
                        'overrides': [
                            {'method': 'popup', 'minutes': 30},
                        ],
                    },
                    'description': description
                }
                logging.debug('Creating Google calendar event %s', event)
                try:
                    # sendNotifications sends an email when the event is created.
                    # If the email address doesn't exist Google will send an email to the regiomanager.
                    calendar_service.events().insert(calendarId='primary', body=event,
                                                     sendNotifications=True).execute(http=http)
                except HttpAccessTokenRefreshError as e:
                    logging.warning(u'Could not create calendar event for user %s: %s', assignee, e.message)
                    manager.credentials.revoke(httplib2.Http(timeout=15))
                    calendar_error = u'Task created, but could not automatically create an event in the manager his' \
                                     u' calendar (error was \"%s\").' \
                                     u' Please refresh the page to prevent this error in the future.' % e.message
                except HttpError, error:
                    # This can happen when for example the email address was invalid (e.g test@examplecom)
                    logging.warning(
                        u'Could not create calendar event for user %s: %s' % (assignee, error._get_reason()))
                    calendar_error = u'Task created, but could not automatically create an event in the manager his' \
                                     u' calendar (error was \"%s\").' \
                                     u' Please create this event manually.' % error._get_reason()

        else:
            calendar_error = u'Task created, but could not automatically create an event in Google Calendar' \
                             u'because no email address for the potential customer was specified.' \
                             u' Please manually create this event and send a confirmation email to the prospect'
        return calendar_error

    xg_on = db.create_transaction_options(xg=True)
    prospect = db.run_in_transaction_options(xg_on, trans)

    calendar_error = None
    if status == Prospect.STATUS_APPOINTMENT_MADE:
        calendar_error = create_google_calendar_event(prospect)

    if reason and status in REASON_STATUSES:
        # Store the reason if not yet existing
        if not ProspectRejectionReason.all().filter('reason', reason).get():
            ProspectRejectionReason(reason=reason).put()

    return prospect, calendar_error


@returns(ShopTask)
@arguments(created_by=unicode, prospect_or_key=(Prospect, db.Key), assignee=unicode, execution_time=(int, long),
           task_type=int, app_id=unicode, status=int, address=unicode, comment=unicode, certainty=(int, long, NoneType),
           subscription=(int, long, NoneType), notify_by_email=bool)
def create_task(created_by, prospect_or_key, assignee, execution_time, task_type, app_id, status=ShopTask.STATUS_NEW,
                address=None, comment=None, certainty=None, subscription=None, notify_by_email=False):
    if not assignee:
        raise BusinessException('No assignee specified for task')

    if notify_by_email:
        subject = u'You have been assigned a new task: %s' % ShopTask.TYPE_STRINGS[task_type]
        send_mail(get_server_settings().dashboardEmail, assignee, subject, body=(comment or u''))

    return ShopTask(parent=prospect_or_key,
                    created_by=created_by,
                    status=status,
                    assignee=assignee,
                    creation_time=now(),
                    execution_time=execution_time,
                    type=task_type,
                    address=address,
                    comment=comment,
                    certainty=certainty,
                    subscription=subscription,
                    app_id=app_id)


@returns()
@arguments(assignees=[unicode])
def broadcast_task_updates(assignees):
    target_users = set(map(users.User, assignees))
    solutions_server_settings = get_solution_server_settings()
    target_users.update([gusers.User(email) for email in solutions_server_settings.shop_bizz_admin_emails])
    channel.send_message(target_users, 'shop.task.updated', assignees=assignees)


@returns()
@arguments(current_user=users.User, prospect=Prospect)
def broadcast_prospect_update(current_user, prospect):
    target_users = {users.User(k.name()) for k in RegioManager.all(keys_only=True)}
    target_users.add(current_user)
    solutions_server_settings = get_solution_server_settings()
    target_users.update([gusers.User(email) for email in solutions_server_settings.shop_bizz_admin_emails])
    channel.send_message(target_users, 'shop.prospect.updated',
                         prospect=serialize_complex_value(ProspectTO.from_model(prospect), ProspectTO, False))


@returns()
@arguments(current_user=users.User, prospect=Prospect)
def broadcast_prospect_creation(current_user, prospect):
    target_users = {users.User(k.name()) for k in RegioManager.all(keys_only=True)}
    if current_user:
        target_users.add(current_user)
    solutions_server_settings = get_solution_server_settings()
    target_users.update([gusers.User(email) for email in solutions_server_settings.shop_bizz_admin_emails])
    channel.send_message(target_users, 'shop.prospect.created',
                         prospect=serialize_complex_value(ProspectTO.from_model(prospect), ProspectTO, False))


@returns(RegioManagerTeam)
@arguments(team_id=(int, long, NoneType), name=unicode, legal_entity_id=(int, long, NoneType),
           app_ids=[unicode])
def put_regio_manager_team(team_id, name, legal_entity_id, app_ids):
    if not name:
        raise EmptyValueException('name')
    if not legal_entity_id:
        raise EmptyValueException('legal_entity')
    entity = LegalEntity.get_by_id(legal_entity_id)
    if not entity:
        raise BusinessException('Legal identity with id %d does not exist' % legal_entity_id)

    def trans():
        if team_id:
            rmt = RegioManagerTeam.get_by_id(team_id)
        else:
            rmt = RegioManagerTeam()

        rmt.deleted = False
        rmt.name = name
        rmt.legal_entity_id = legal_entity_id
        rmt.app_ids = app_ids
        rmt.put()
        return rmt

    return db.run_in_transaction(trans)


@returns(RegioManager)
@arguments(current_user=users.User, email=unicode, name=unicode, phone=unicode, app_rights=[AppRightsTO],
           show_in_stats=bool, is_support=bool, team_id=(int, long), admin=bool)
def put_regio_manager(current_user, email, name, phone, app_rights, show_in_stats, is_support, team_id, admin):
    bizz_check(email, 'Email is required')
    bizz_check(name, 'Name is required')
    bizz_check(phone, 'Phone number is required')
    bizz_check(team_id, 'Team is required')

    def trans():
        regio_manager, rmt = db.get([RegioManager.create_key(email), RegioManagerTeam.create_key(team_id)])
        if not regio_manager:
            bizz_check(EMAIL_REGEX.match(email), u'Invalid email')
            regio_manager = RegioManager(key=RegioManager.create_key(email))
            deferred.defer(create_stats_for_new_manager, _transactional=True, email=email)

        for r in app_rights:
            if r.access == RegioManager.ACCESS_NO:
                regio_manager.revoke(r.app_id)
            elif r.access in (RegioManager.ACCESS_READ_ONLY, RegioManager.ACCESS_FULL):
                regio_manager.grant(r.app_id, r.access)
            else:
                azzert(False, 'Unexpected access type %s for app_id %s' % (r.access, r.app_id))
        regio_manager.show_in_stats = show_in_stats
        regio_manager.name = name
        regio_manager.phone = phone
        regio_manager.internal_support = is_support
        regio_manager.admin = admin

        to_put = {regio_manager}
        if regio_manager.team_id != team_id:
            if regio_manager.team_id:
                raise BusinessException('Changing team is not supported')

            regio_manager.team_id = team_id
            rmt.regio_managers.append(email)
            to_put.add(rmt)

        # There can be only one support manager per team. For now at least.
        if is_support:
            if rmt.support_manager != email:
                try:
                    support_manager = rmt.get_support()
                    support_manager.internal_support = False
                    to_put.add(support_manager)
                except NoSupportManagerException:
                    pass
                rmt.support_manager = email
                to_put.add(rmt)
        else:
            if rmt.support_manager == email:
                rmt.support_manager = None
                to_put.add(rmt)

        put_and_invalidate_cache(*list(to_put))
        return regio_manager

    xg_on = db.create_transaction_options(xg=True)
    regio_manager = db.run_in_transaction_options(xg_on, trans)

    # todo channel update to update this regiomanager

    return regio_manager


@returns(RegioManagerStatistic)
@arguments(email=unicode)
def create_stats_for_new_manager(email):
    month_list = list()
    now = datetime.datetime.now()
    year = now.year
    month = now.month
    for i in xrange(2015, year + 1):
        if i == 2015:
            if now.year == 2015:
                for j in xrange(3, month + 1):  # sales started in march 2015
                    month_list.append(datetime.date(i, j, 1))
            else:
                for j in xrange(3, 13):  # sales started in march 2015
                    month_list.append(datetime.date(i, j, 1))
        else:
            for j in xrange(1, month + 1):
                month_list.append(datetime.date(i, j, 1))

    st = RegioManagerStatistic(key=RegioManagerStatistic.create_key(email))
    st.month_revenue = list()
    for date in month_list:
        month_amount = 0
        st.month_revenue.append(int(date.strftime('%Y%m')))
        st.month_revenue.append(month_amount)
    st.put()
    return st


@returns()
@arguments(current_user=users.User, hint_id=(int, long, NoneType), tag=unicode, language=unicode, text=unicode,
           modules=[unicode])
def put_hint(current_user, hint_id, tag, language, text, modules):
    hints = get_solution_hints()
    if hint_id:
        sh = SolutionHint.get_by_id(hint_id)
        bizz_check(sh is not None, u"Can't update a hint that was already deleted")
    else:
        sh = SolutionHint()
    sh.tag = tag
    sh.language = language
    sh.text = text
    sh.modules = modules
    sh.put()
    if sh.id not in hints.hint_ids:
        hints.hint_ids.append(sh.id)
        put_and_invalidate_cache(hints)

    target_users = {users.User(k.name()) for k in RegioManager.all(keys_only=True)}
    target_users.add(current_user)
    solutions_server_settings = get_solution_server_settings()
    target_users.update([gusers.User(email) for email in solutions_server_settings.shop_bizz_admin_emails])
    channel.send_message(target_users, 'shop.hints.updated')


@returns()
@arguments(current_user=users.User, hint_id=(int, long))
def delete_hint(current_user, hint_id):
    hints = get_solution_hints()
    sh = SolutionHint.get_by_id(hint_id)
    bizz_check(sh is not None, u"Can't delete a hint that was already deleted")

    if sh.id in hints.hint_ids:
        hints.hint_ids.remove(sh.id)
        put_and_invalidate_cache(hints)
    sh.delete()

    target_users = {users.User(k.name()) for k in RegioManager.all(keys_only=True)}
    target_users.add(current_user)
    solutions_server_settings = get_solution_server_settings()
    target_users.update([gusers.User(email) for email in solutions_server_settings.shop_bizz_admin_emails])
    channel.send_message(target_users, 'shop.hints.updated')


@returns([RegioManagerStatistic])
@arguments()
def get_regiomanager_statistics():
    return RegioManagerStatistic.all()


@returns()
@arguments(gained_value=(int, long), manager=gusers.User)
def update_regiomanager_statistic(gained_value, manager):
    if not manager:
        return

    statistic = db.get(RegioManagerStatistic.create_key(manager.email()))
    if not statistic:
        statistic = create_stats_for_new_manager(manager.email())

    month_date = int(datetime.datetime.now().strftime('%Y%m'))
    try:
        index = statistic.month_revenue.index(month_date)  # throws error when it doesn't exist yet
        statistic.month_revenue[index + 1] += gained_value
    except ValueError:
        # not in the list yet, add it.
        statistic.month_revenue.append(month_date)
        statistic.month_revenue.append(gained_value)
    statistic.put()


@returns([ProspectHistory])
@arguments(prospect_id=unicode)
def get_prospect_history(prospect_id):
    return ProspectHistory.all().ancestor(Prospect.create_key(prospect_id))


@returns()
@arguments(customer_id=(int, long), order_or_number=(unicode, Order), charge_or_id=(int, long, Charge))
def get_payed(customer_id, order_or_number, charge_or_id):
    solution_server_settings = get_solution_server_settings()

    def trans():
        invoice = None

        customer = Customer.get_by_id(customer_id)
        if not (customer.stripe_id and customer.stripe_id_created and customer.stripe_credit_card_id):
            raise PaymentFailedException("Insufficient payment information present")

        guser = gusers.get_current_user()
        if guser:
            azzert(user_has_permissions_to_team(guser, customer.team_id))
        if isinstance(charge_or_id, Charge):
            charge = charge_or_id
            charge_id = charge.id
        else:
            # Check if this is the oldest pending charge for this customer
            charge_id = charge_or_id
            charge = Charge.all().ancestor(customer).filter("status =", Charge.STATUS_PENDING).order("date").get()
            if not charge or not charge.key().id() == charge_id:
                charge = Charge.all().ancestor(customer).filter("status =", Charge.STATUS_EXECUTED).order("date").get()
                if not charge or not charge.key().id() == charge_id:
                    raise PaymentFailedException("There is an older unpaid charge for this customer.")
                else:
                    invoices = list(Invoice.all().ancestor(charge))
                    if len(invoices) == 0:
                        raise PaymentFailedException("Could not find invoice for executed charge.")
                    elif len(invoices) > 1:
                        raise PaymentFailedException("Found multiple invoices for executed charge.")
                    invoice = invoices[0]
                    if invoice.paid:
                        raise PaymentFailedException("Trying to execute payment for paid invoice.")

        if isinstance(order_or_number, Order):
            order = order_or_number
            order_number = order.order_number
        else:
            order_number = order_or_number
            order = Order.get_by_order_number(customer_id, order_number)

        # Check if charge is the charge requested to be paid
        if not charge.order_number == order_number:
            raise PaymentFailedException("Received incorrect request")

        # Check if we need to add CRED product
        if charge.type == Charge.TYPE_ORDER_DELIVERY \
                and order.is_subscription_order \
                and invoice is None \
                and customer.team.legal_entity.is_mobicage:
            discount = None
            max_number = 0
            for item in OrderItem.all().ancestor(order):
                if item.number > max_number:
                    max_number = item.number
                if item.product_code == Product.PRODUCT_ONE_TIME_CREDIT_CARD_PAYMENT_DISCOUNT:
                    discount = item
                    break
            if not discount:
                product = Product.get_by_code(Product.PRODUCT_ONE_TIME_CREDIT_CARD_PAYMENT_DISCOUNT)
                discount = OrderItem(parent=order)
                discount.number = max_number + 1
                discount.comment = product.default_comment(customer.language)
                discount.product_code = Product.PRODUCT_ONE_TIME_CREDIT_CARD_PAYMENT_DISCOUNT
                discount.count = 1
                discount.price = product.price
                discount.put()
                charge.amount += discount.price
                charge.vat = charge.amount * charge.vat_pct / 100
                charge.total_amount = charge.amount + charge.vat
                charge.put()

        if invoice is None:
            invoice_number = InvoiceNumber.next(customer.team.legal_entity_key)
        else:
            invoice_number = invoice.invoice_number

        # Check if we can find a payment with this description
        stripe_charge_match = None
        stripe_charges = stripe.Charge.all(
            api_key=solution_server_settings.stripe_secret_key, customer=customer.stripe_id)
        for stripe_charge in stripe_charges.data:
            if stripe_charge.metadata.osa_charge_id and long(
                    stripe_charge.metadata.osa_charge_id) == charge_id and stripe_charge.status != 'failed':
                stripe_charge_match = stripe_charge
                break

        # Analyze the results and act on them
        charge_executed = False
        if stripe_charge_match:
            stripe_charge = stripe_charge_match
            if not stripe_charge.amount == charge.total_amount:
                raise PaymentFailedException(
                    "BUG!!!! Found a Stripe charge with identical charge id but different amount!!!!")
            if stripe_charge.captured:
                charge_executed = True
        else:
            try:
                stripe_charge = stripe.Charge.create(api_key=solution_server_settings.stripe_secret_key,
                                                     amount=charge.total_amount,
                                                     currency="eur",
                                                     customer=customer.stripe_id,
                                                     description=invoice_number,
                                                     capture=False,
                                                     metadata=dict(osa_charge_id=charge_id,
                                                                   osa_customer_id=customer_id,
                                                                   osa_order_number=order_number,
                                                                   osa_invoice_number=invoice_number),
                                                     statement_descriptor=invoice_number,
                                                     source=customer.stripe_credit_card_id)
            except Exception as e:
                logging.exception(e)
                raise PaymentFailedException("Failed to create charge with message: %s" % e.message)
        if not charge_executed:
            try:
                stripe_charge.capture()
            except Exception as e:
                logging.exception(e)
                logging.info(stripe_charge)
                raise PaymentFailedException("Failed to capture charge with message: %s" % e.message)

        # Update the charge
        charge.status = Charge.STATUS_EXECUTED
        charge.date_executed = now()
        charge.put()

        deferred.defer(create_invoice, customer_id, order_number, charge_id, invoice_number, guser,
                       Invoice.PAYMENT_STRIPE, _transactional=True, _queue=FAST_QUEUE)

    run_in_transaction(trans, True)


@returns(bool)
@arguments(app=SimpleAppTO)
def put_surrounding_apps(app):
    to_update = db.get(App.create_key(app.id))
    to_update.orderable_app_ids = app.orderable_app_ids
    to_update.put()
    return True


@returns()
@arguments(app_id=unicode, enabled=bool)
def put_app_signup_enabled(app_id, enabled):
    def trans():
        key = ShopApp.create_key(app_id)
        shop_app = ShopApp.get(key) or ShopApp(key=key,
                                               name=get_app_by_id(app_id).name)
        shop_app.signup_enabled = enabled
        shop_app.put()
    run_in_transaction(trans, xg=True)


@cached(2, lifetime=0, request=True, memcache=True, datastore=False)
@returns(bool)
@arguments(app_id=unicode)
def is_signup_enabled(app_id):
    if not app_id:
        return False
    shop_app = ShopApp.get(ShopApp.create_key(app_id))
    return shop_app is not None and shop_app.signup_enabled


@returns(db.Query)
@arguments()
def get_all_customers():
    return Customer.all().order('-creation_time')


def export_customers_csv(google_user):
    result = list()
    properties = ['name', 'address1', 'address2', 'zip_code', 'country']

    qry = get_all_customers()
    while True:
        customers = qry.fetch(300)
        if not customers:
            break
        logging.debug('Fetched %s customers', len(customers))
        qry.with_cursor(qry.cursor())
        si_stats_keys = list()

        for customer in customers:
            if customer.service_email:
                service_user = users.User(email=customer.service_email)
                service_identity_user = create_service_identity_user(service_user)
                si_stats_keys.append(ServiceIdentityStatistic.create_key(service_identity_user))
            else:
                si_stats_keys.append(None)

        total_users = []
        # get the ServiceIdentityStatistics in chunks of 50 because these objects can be big
        for chunk in chunks(si_stats_keys, 50):
            total_users += [si_stat.number_of_users if si_stat else 0
                            for si_stat in db.get(filter(None, chunk))]
        for i, key in enumerate(si_stats_keys):
            if not key:
                total_users.insert(i, 0)

        i = 0
        for customer in customers:
            d = OrderedDict()
            d['Email'] = customer.user_email
            d['Has credit card'] = 'Yes' if customer.stripe_valid else 'No'
            d['Customer since'] = format_datetime(customer.creation_time, 'yyyy-MM-dd HH:mm:ss',
                                                  tzinfo=get_timezone('Europe/Brussels'))
            for p in properties:
                d[p] = getattr(customer, p)
            d['Subscription type'] = Customer.SUBSCRIPTION_TYPES[customer.subscription_type]
            d['Has terminal'] = u'Yes' if customer.has_loyalty else u'No'
            d['Total users'] = total_users[i]
            contact = Contact.get_one(customer)
            d['Telephone'] = contact.phone_number if contact else u''
            result.append(d)
            if len(customer.app_ids) != 0:
                d['App'] = customer.app_id
            else:
                d['App'] = ''
            d['Language'] = customer.language

            for p, v in d.items():
                if v and isinstance(v, unicode):
                    d[p] = v.encode('utf-8')
            i += 1

    result.sort(key=lambda d: d['Language'])
    logging.debug('Creating csv with %s customers', len(result))
    fieldnames = ['name', 'Email', 'Customer since', 'address1', 'address2', 'zip_code', 'country', 'Telephone',
                  'Subscription type', 'Has terminal', 'Total users', 'Has credit card', 'App', 'Language']
    with closing(StringIO()) as csv_string:
        writer = csv.DictWriter(csv_string, dialect='excel', fieldnames=fieldnames)
        writer.writeheader()
        for row in result:
            writer.writerow(row)
        current_date = format_date(datetime.date.today(), locale=DEFAULT_LANGUAGE)

        solution_server_settings = get_solution_server_settings()
        subject = 'Customers export %s' % current_date
        message = u'The exported customer list of %s can be found in the attachment of this email.' % current_date

        attachments = []
        attachments.append(('Customers export %s.csv' % current_date,
                            base64.b64encode(csv_string.getvalue())))

        send_mail(solution_server_settings.shop_export_email, [google_user.email()], subject, message,
                  attachments=attachments)
        if DEBUG:
            logging.info(csv_string.getvalue())


@returns([RegioManager])
@arguments(app_id=unicode)
def get_regiomanagers_by_app_id(app_id):
    azzert(app_id)
    return RegioManager.list_by_app_id(app_id)


@returns()
@arguments(service=unicode, app_ids=[unicode], message=unicode, tester=unicode)
def post_app_broadcast(service, app_ids, message, tester=None):
    azzert(is_admin(gusers.get_current_user()))
    service_user = users.User(service)
    service_identity_user = add_slash_default(service_user)
    identifier = str(now())

    def trans():
        if tester:
            test_send_app_broadcast(service_identity_user, app_ids, message, identifier, tester)
        else:
            stats_key = AppBroadcastStatistics.create_key(service_identity_user)
            stats = db.get(stats_key) or AppBroadcastStatistics(key=stats_key)
            tag = send_app_broadcast(service_identity_user, app_ids, message, identifier)
            stats.tags.append(tag)
            stats.messages.append(message)
            stats.put()

    run_in_transaction(trans, xg=True)


def create_customer_service_to(name, address1, address2, city, zip_code, email, language, currency, phone_number,
                               organization_type, app_id, broadcast_types, modules):
    service = CustomerServiceTO()

    service.name = name
    service.address = address1
    if address2:
        service.address += '\n' + address2
    service.address += '\n' + zip_code + ' ' + city
    service.email = email and email.lower()
    service.language = language
    service.currency = currency
    service.phone_number = phone_number

    service.organization_type = organization_type
    service.apps = [app_id, App.APP_ID_ROGERTHAT]
    service.broadcast_types = list(set(broadcast_types))
    service.modules = modules
    service.app_infos = []
    service.current_user_app_infos = []
    service.managed_organization_types = []

    validate_service(service)
    return service


def put_customer_with_service(service, name, address1, address2, zip_code, city, country, language,
                              organization_type, vat, team_id, product_code, customer_id=None,
                              website=None, facebook_page=None, force=False):
    def trans1():
        email_has_changed = False
        is_new = False
        customer = create_or_update_customer(current_user=None, customer_id=customer_id, vat=vat, name=name,
                                             address1=address1, address2=address2, zip_code=zip_code,
                                             country=country, language=language, city=city,
                                             organization_type=organization_type, prospect_id=None,
                                             force=force, team_id=team_id, website=website, facebook_page=facebook_page)

        customer.put()
        if customer_id:
            # Check if this city has access to this association
            if customer.app_id not in service.apps:
                logging.warn('Tried to save service information for service %s (%s)', customer.name, customer.app_ids)
                raise NoPermissionException('Create association')

            # save the service.
            if service.email != customer.service_email:
                if service.email != customer.user_email:
                    email_has_changed = True

            update_contact(customer.id, Contact.get_one(customer.key()).id,
                           customer.name, u'', service.email, service.phone_number)
        else:
            is_new = True
            # create a new service. Name of the customer, contact, and service will all be the same.

            contact = create_contact(customer, name, u'', service.email, service.phone_number)

            # Create an order with only one order item
            order_items = list()
            item = OrderItemTO()
            item.product = product_code
            item.count = Product.get_by_code(product_code).default_count
            item.comment = u''
            order_items.append(item)
            order = create_order(customer, contact, order_items, skip_app_check=True)
            order.status = Order.STATUS_SIGNED
            with closing(StringIO()) as pdf:
                generate_order_or_invoice_pdf(pdf, customer, order)
                order.pdf = db.Blob(pdf.getvalue())

            order.next_charge_date = Order.default_next_charge_date()
            order.put()
        return customer, email_has_changed, is_new

    customer, email_changed, is_new_association = run_in_xg_transaction(trans1)
    return customer, email_changed, is_new_association


def get_signup_summary(lang, customer_signup):
    """Get a translated signup summary.

    Args:
        lang (unicode)
        customer_signup(CustomerSignup)
    """
    def trans(term, *args, **kwargs):
        return common_translate(lang, SOLUTION_COMMON, unicode(term), *args, **kwargs)

    org_type = customer_signup.company_organization_type
    org_type_name = ServiceProfile.localized_singular_organization_type(
        org_type, lang, customer_signup.city_customer.app_id)

    summary = u'{}\n\n'.format(trans('signup_application'))
    summary += u'{}\n'.format(trans('signup_inbox_message_header',
                                    name=customer_signup.company_name,
                                    org_type_name=org_type_name.lower()))

    summary += u'\n{}\n'.format(org_type_name)
    summary += u'{}: {}\n'.format(trans('organization_type'), org_type_name)
    summary += u'{}: {}\n'.format(trans('reservation-name'), customer_signup.company_name)
    summary += u'{}: {}\n'.format(trans('address'), customer_signup.company_address1)
    summary += u'{}: {}\n'.format(trans('zip_code'), customer_signup.company_zip_code)
    summary += u'{}: {}\n'.format(trans('Email'), customer_signup.company_email)
    summary += u'{}: {}\n'.format(trans('Phone number'), customer_signup.company_telephone)
    summary += u'{}: {}\n'.format(trans('city'), customer_signup.company_city)
    summary += u'{}: {}\n'.format(trans('vat'), customer_signup.company_vat)
    summary += u'{}: {}\n'.format(trans('Website'), customer_signup.company_website)
    summary += u'{}: {}\n'.format(trans('Facebook page'), customer_signup.company_facebook_page)

    summary += u'\n{}\n'.format(trans('business-manager'))
    summary += u'{}: {}\n'.format(trans('reservation-name'), customer_signup.customer_name)
    summary += u'{}: {}\n'.format(trans('address'), customer_signup.customer_address1)
    summary += u'{}: {}\n'.format(trans('zip_code'), customer_signup.customer_zip_code)
    summary += u'{}: {}\n'.format(trans('city'), customer_signup.customer_city)
    summary += u'{}: {}\n'.format(trans('Email'), customer_signup.customer_email)
    summary += u'{}: {}\n'.format(trans('Phone number'), customer_signup.customer_telephone)

    return summary


def _send_new_customer_signup_message(service_user, customer_signup):
    signup_key = unicode(customer_signup.key())
    sln_settings = get_solution_settings(service_user)
    summary = get_signup_summary(sln_settings.main_language, customer_signup)

    message = new_inbox_message(sln_settings, summary,
                                category=SolutionInboxMessage.CATEGORY_CUSTOMER_SIGNUP,
                                category_key=signup_key)

    app_user = create_app_user_by_email(service_user.email(), customer_signup.city_customer.app_id)
    send_inbox_forwarders_message(service_user, ServiceIdentity.DEFAULT, app_user, summary, {
        'if_name': customer_signup.customer_name,
        'if_email': customer_signup.customer_email
    }, message_key=message.solution_inbox_message_key, reply_enabled=message.reply_enabled)

    send_signup_update_messages(sln_settings, message)
    return message.solution_inbox_message_key


def calculate_signup_url_digest(data):
    alg = hashlib.sha256()
    alg.update(data['c'].encode('utf-8'))
    alg.update(data['s'].encode('utf-8'))
    return alg.hexdigest()


def send_signup_verification_email(city_customer, signup, host=None):
    from solutions.common.handlers import JINJA_ENVIRONMENT

    data = dict(c=city_customer.service_user.email(), s=unicode(signup.key()), t=signup.timestamp)
    user = users.User(signup.customer_email)
    data['d'] = calculate_signup_url_digest(data)
    data = encrypt(user, json.dumps(data))
    url_params = urllib.urlencode({'email': signup.customer_email, 'data': base64.b64encode(data)})

    lang = city_customer.language
    translate = partial(common_translate, lang, SOLUTION_COMMON)

    link = '{}/customers/signup?{}'.format(host or get_server_settings().baseUrl, url_params)
    subject = city_customer.name + ' - ' + translate('signup')
    params = {
        'language': lang,
        'name': signup.customer_name,
        'link_text': translate('verify'),
        'link': link
    }
    message = JINJA_ENVIRONMENT.get_template('emails/signup_verification.tmpl').render(params)
    html_message = JINJA_ENVIRONMENT.get_template('emails/signup_verification_html.tmpl').render(params)
    city_from = '%s <%s>' % (city_customer.name, city_customer.user_email)
    send_mail(city_from, signup.customer_email, subject, message, html=html_message)


@returns()
@arguments(city_customer_id=int, company=CompanyTO, customer=CustomerTO, recaptcha_token=unicode, domain=unicode)
def create_customer_signup(city_customer_id, company, customer, recaptcha_token, domain=None):
    if not recaptcha_verify(recaptcha_token):
        raise BusinessException('Cannot verify recaptcha response')

    city_customer = Customer.get_by_id(city_customer_id)
    user_email = company.user_email.strip().lower()
    signup = CustomerSignup(parent=city_customer)

    signup.company_name = company.name
    signup.company_organization_type = company.organization_type
    signup.company_address1 = company.address1
    signup.company_zip_code = company.zip_code
    signup.company_city = company.city
    signup.company_email = user_email
    signup.company_telephone = company.telephone
    signup.company_website = company.website
    signup.company_facebook_page = company.facebook_page

    try:
        signup.company_vat = company.vat and normalize_vat(city_customer.country, company.vat)
    except BusinessException:
        raise BusinessException('vat_invalid')

    signup.customer_name = customer.name
    signup.customer_address1 = customer.address1
    signup.customer_zip_code = customer.zip_code
    signup.customer_city = customer.city
    signup.customer_email = customer.user_email.strip().lower()
    signup.customer_telephone = customer.telephone

    for other_signup in CustomerSignup.list_pending_by_customer_email(user_email):
        # check if the same information has been used in a pending signup
        if signup.is_same_signup(other_signup):
            message = shop_translate(customer.language, 'signup_same_information_used')
            raise BusinessException(message)

    signup.timestamp = now()
    signup.put()
    send_signup_verification_email(city_customer, signup, domain)


@returns()
@arguments(email=unicode, data=str)
def complete_customer_signup(email, data):
    try:
        user = users.User(email)
        data = base64.decodestring(data)
        data = json.loads(decrypt(user, data))
        azzert(data['d'] == calculate_signup_url_digest(data))
    except:
        raise InvalidUrlException

    signup = CustomerSignup.get(data['s'])
    if not signup:
        raise InvalidUrlException

    timestamp = signup.timestamp
    if not (timestamp < now() < timestamp + 24 * 3600):
        raise ExpiredUrlException

    if signup.inbox_message_key:
        raise AlreadyUsedUrlException

    service_user = users.User(data['c'])
    signup.inbox_message_key = _send_new_customer_signup_message(service_user, signup)
    signup.put()


def _get_charges_with_sent_invoice(is_reseller, manager):
    """Will fetch the charges with STATUS_EXECUTED that have a sent invoice"""
    charge_keys = []

    invoice_qry = Invoice.all(keys_only=True) \
        .filter('payment_type', Invoice.PAYMENT_MANUAL_AFTER) \
        .filter('paid', False)
    if is_reseller:
        invoice_qry = invoice_qry.filter('legal_entity_id', manager.team.legal_entity_id)
    for invoice_key in invoice_qry:
        if invoice_key.parent() not in charge_keys:
            charge_keys.append(invoice_key.parent())

    return charge_keys


@returns(CustomerChargesTO)
@arguments(user=users.User, paid=bool, limit=int, cursor=unicode)
def get_customer_charges(user, paid, limit=50, cursor=None):
    if paid:
        status = Charge.STATUS_EXECUTED
    else:
        status = Charge.STATUS_PENDING

    charges_qry = Charge.all(keys_only=True).with_cursor(cursor).filter("status =", status).order('-date')
    manager = RegioManager.get(RegioManager.create_key(user.email()))
    user_is_admin = is_admin(user)
    if manager and manager.admin:
        charges_qry.filter("team_id =", manager.team_id)
    elif not user_is_admin:
        charges_qry = charges_qry.filter("manager =", user)

    charge_keys = []
    is_reseller = manager and not manager.team.legal_entity.is_mobicage
    payment_admin = is_payment_admin(user)
    if not paid and not cursor:
        # fetch all the charges with sent invoices once (if cursor is not provided)
        if payment_admin or is_reseller:
            charge_keys.extend(_get_charges_with_sent_invoice(is_reseller, manager))

    charge_keys.extend(charges_qry.fetch(limit))
    cursor = charges_qry.cursor()

    customer_keys = []
    for charge_key in charge_keys:
        customer_key = charge_key.parent().parent()
        if customer_key not in customer_keys:
            customer_keys.append(customer_key)

    results = db.get(customer_keys + charge_keys)
    customers = {customer.id: customer for customer in results[:len(customer_keys)]}

    def sort_charges(charge):
        return charge.status != Charge.STATUS_EXECUTED, -charge.date

    if not paid:
        # sort it this way for unpaid charges only
        charges = sorted(results[len(customer_keys):], key=sort_charges)
    else:
        charges = results[len(customer_keys):]

    # to filter the charges as paid/unpaid, we get the invoices first
    # then set the charge to paid if the invoice is paid
    invoice_keys = []
    for charge in charges:
        if charge.invoice_number:
            invoice_key = Invoice.create_key(charge.customer_id, charge.order_number, charge.id, charge.invoice_number)
            invoice_keys.append(invoice_key)

    invoices = {invoice.charge_id: invoice for invoice in db.get(invoice_keys)}
    mapped_customers = []
    filtered_charges = []
    for charge in charges:
        invoice = invoices.get(charge.id)
        invoice_is_paid = invoice.paid if invoice else False
        if invoice_is_paid == paid:
            charge.paid = invoice_is_paid
            filtered_charges.append(charge)
            mapped_customers.append(customers[charge.customer_id])

    customer_charges = []
    for charge, customer in zip(filtered_charges, mapped_customers):
        customer_charges.append(CustomerChargeTO.from_model(charge, customer))

    result = CustomerChargesTO()
    result.is_admin = user_is_admin
    result.is_reseller = is_reseller
    result.is_payment_admin = payment_admin
    result.customer_charges = customer_charges
    result.cursor = unicode(cursor)
    return result


@returns([tuple])
@arguments(customer=Customer, language=unicode)
def get_organization_types(customer, language):
    if not customer:
        return []
    return [(org_type, ServiceProfile.localized_plural_organization_type(org_type, language, customer.app_id))
            for org_type in customer.editable_organization_types]

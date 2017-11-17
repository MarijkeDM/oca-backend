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
import datetime
import json
import logging
import re
import time
import urllib

from babel import Locale
from babel.dates import format_date, get_timezone
from babel.numbers import get_currency_symbol, format_currency
from dateutil.relativedelta import relativedelta

from google.appengine.api import users as gusers, images
from google.appengine.ext import db, blobstore
from mcfw.cache import CachedModelMixIn, invalidate_cache
from mcfw.properties import azzert
from mcfw.serialization import deserializer, ds_model, serializer, s_model, register
from mcfw.utils import chunks
from oauth2client.appengine import CredentialsProperty
from rogerthat.bizz.gcs import get_serving_url
from rogerthat.models import ServiceProfile
from rogerthat.rpc import users
from rogerthat.utils import bizz_check, get_epoch_from_datetime, now
from shop.business.i18n import SHOP_DEFAULT_LANGUAGE, shop_translate
from shop.constants import PROSPECT_CATEGORIES
from shop.exceptions import CustomerNotFoundException, NoSupportManagerException
from shop.model_properties import ProspectCommentsProperty, ProspectComments, ProspectComment
from solutions.common.bizz import OrganizationType, SolutionModule


def _normalize_vat_be(vat):
    vat = vat.strip().upper()
    country_code = vat[:2]
    bizz_check(country_code == "BE", "This is not a Belgian VAT number (BE 0123 456 789).")
    vat = vat[2:]
    vat = "".join((c for c in vat if c in "1234567890"))
    if len(vat) == 9:
        vat = '0' + vat
    vat = country_code + vat
    bizz_check(len(vat) == 12, "This vat number could not be validated for Belgium (BE 0123 456 789).")
    return vat


def _normalize_vat_nl(vat):
    vat = vat.strip().upper()
    country_code = vat[:2]
    bizz_check(country_code == "NL", "This is not a Dutch VAT number (NL999999999B99).")
    logging.info("vat: " + vat)
    vat = vat[2:]
    logging.info("vat: " + vat)
    vat = "".join((c for c in vat if c in "1234567890B"))
    logging.info("vat: " + vat)
    vat = country_code + vat
    bizz_check(re.match("NL[1234567890]{9,9}B[1234567890]{2,2}", vat),
               "This vat number could not be validated for the Netherlands (NL999999999B99).")
    return vat


def _normalize_vat_fr(vat):
    vat = vat.strip().upper()
    country_code = vat[:2]
    bizz_check(country_code == "FR", "This is not a French VAT number (FR99 999999999).")
    vat = vat[2:]
    vat = "".join((c for c in vat if c in "1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    vat = country_code + vat
    bizz_check(len(vat) == 13, "This vat number could not be validated for France (FR99 999999999).")
    return vat


def _normalize_vat_es(vat):
    vat = vat.strip().upper()
    country_code = vat[:2]
    bizz_check(country_code == "ES", "This is not a Spanish VAT number (ES99 999999999).")
    vat = vat[2:]
    vat = "".join((c for c in vat if c in "1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    vat = country_code + vat
    bizz_check(len(vat) == 11, "This vat number could not be validated for Spain (ES99 999999999).")
    return vat

_vat_validators = dict(BE=_normalize_vat_be,
                       NL=_normalize_vat_nl,
                       FR=_normalize_vat_fr,
                       ES=_normalize_vat_es)


def normalize_vat(country, vat):
    bizz_check(country in _vat_validators, "VAT validation is not supported for country " + country)
    return _vat_validators[country](vat)


class RegioManagerTeam(db.Model):
    name = db.StringProperty(indexed=False)
    app_ids = db.StringListProperty(indexed=True)
    regio_managers = db.StringListProperty(indexed=False)
    support_manager = db.StringProperty(indexed=False)
    legal_entity_id = db.IntegerProperty(indexed=True)
    is_mobicage = db.BooleanProperty(default=False)

    @property
    def id(self):
        return self.key().id()

    @property
    def legal_entity(self):
        if not hasattr(self, '_legal_entity'):
            if self.legal_entity_id is None:
                self._legal_entity = LegalEntity.get_mobicage()
            else:
                self._legal_entity = LegalEntity.get_by_id(self.legal_entity_id)

        return self._legal_entity

    @property
    def legal_entity_key(self):
        return LegalEntity.create_key(
            self.legal_entity_id) if self.legal_entity_id else LegalEntity.get_mobicage().key()

    @classmethod
    def create_key(cls, team_id):
        return db.Key.from_path(cls.kind(), team_id)

    @classmethod
    def get_by_app_id(cls, app_id):
        return cls.all().filter('app_ids =', app_id).get()

    def get_support(self):
        if not self.support_manager:
            raise NoSupportManagerException(self)
        return RegioManager.get(RegioManager.create_key(self.support_manager))

    @classmethod
    def get_mobicage(cls):
        return cls.all().filter('is_mobicage', True).get()

    @classmethod
    def list_all(cls):
        return cls.all()


class RegioManager(db.Model):
    """
    Note:
        Key is the email of this manager.
    """
    ACCESS_NO = "no"
    ACCESS_READ_ONLY = "read-only"
    ACCESS_FULL = "full"

    name = db.StringProperty()
    app_ids = db.StringListProperty()  # complete list with supported app_ids
    read_only_app_ids = db.StringListProperty()  # subset of app_ids
    show_in_stats = db.BooleanProperty(default=True, indexed=False)
    internal_support = db.BooleanProperty(default=False)
    phone = db.StringProperty(indexed=False)
    credentials = CredentialsProperty(indexed=False)  # type: Credentials
    team_id = db.IntegerProperty(indexed=True)
    admin = db.BooleanProperty(default=False, indexed=False)

    @property
    def user(self):
        return gusers.User(self.email)

    @property
    def email(self):
        return self.key().name()

    @property
    def full_app_ids(self):
        return [app_id for app_id in self.app_ids if app_id not in self.read_only_app_ids]

    @classmethod
    def list_by_app_id(cls, app_id):
        return cls.all().filter('app_ids =', app_id).order('name')

    @classmethod
    def create_key(cls, email):
        return db.Key.from_path(cls.kind(), email)

    def has_access(self, team_id):
        if self.team_id == team_id:
            return self.ACCESS_FULL
        return self.ACCESS_READ_ONLY

    def grant(self, app_id, access):
        if access == self.ACCESS_READ_ONLY:
            if app_id not in self.app_ids:
                self.app_ids.append(app_id)
            if app_id not in self.read_only_app_ids:
                self.read_only_app_ids.append(app_id)
        elif access == self.ACCESS_FULL:
            if app_id not in self.app_ids:
                self.app_ids.append(app_id)
            if app_id in self.read_only_app_ids:
                self.read_only_app_ids.remove(app_id)

    def revoke(self, app_id):
        if app_id in self.read_only_app_ids:
            self.read_only_app_ids.remove(app_id)
        if app_id in self.app_ids:
            self.app_ids.remove(app_id)

    @property
    def team(self):
        if not hasattr(self, '_team'):
            self._team = RegioManagerTeam.get_by_id(self.team_id)
        return self._team


class Product(db.Model):
    PRODUCT_EXTRA_CITY = u'XCTY'
    PRODUCT_ACTION_3_EXTRA_CITIES = u'A3CT'
    PRODUCT_SUBSCRIPTION_ASSOCIATION = u'SJUP'
    PRODUCT_ROLLUP_BANNER = u'BNNR'
    PRODUCT_BEACON = u'BEAC'
    PRODUCT_FLYERS = u'POSM'
    PRODUCT_DEMO = u'DEMO'
    PRODUCT_FREE_PRESENCE = u'OCAP'
    PRODUCT_ONE_TIME_CREDIT_CARD_PAYMENT_DISCOUNT = u'CRED'
    PRODUCT_CARDS = u'KKRT'
    PRODUCT_NEWS_PROMOTION = u'NEWS'
    PRODUCT_FREE_SUBSCRIPTION = u'FREE'
    price = db.IntegerProperty()  # In euro cents
    default_count = db.IntegerProperty()
    default = db.BooleanProperty()
    possible_counts = db.ListProperty(int)
    is_subscription = db.BooleanProperty()
    is_subscription_discount = db.BooleanProperty()
    is_subscription_extension = db.BooleanProperty(default=False, indexed=False)
    module_set = db.StringProperty()
    organization_types = db.ListProperty(int)
    product_dependencies = db.StringListProperty()
    visible = db.BooleanProperty(default=False)
    extra_subscription_months = db.IntegerProperty(default=0)
    picture_url = db.StringProperty(default="", indexed=False)

    is_multilanguage = db.BooleanProperty(default=True, indexed=False)
    # when None: product_code.default_comment translation key is used. (see method default_comment)
    # Set to empty string to return an empty string as translation.
    default_comment_translation_key = db.StringProperty(indexed=False)
    # Same as above
    description_translation_key = db.StringProperty(indexed=False)
    legal_entity_id = db.IntegerProperty()

    @property
    def code(self):
        return self.key().name()

    def default_comment(self, language):
        if self.default_comment_translation_key is None:
            return shop_translate(language, u"%s.default_comment" % self.code)

        if self.is_multilanguage and self.default_comment_translation_key:
            return shop_translate(language, self.default_comment_translation_key)

        return self.default_comment_translation_key

    def description(self, language):
        if self.description_translation_key is None:
            return shop_translate(language, u"%s.description" % self.code)

        if self.is_multilanguage and self.description_translation_key:
            return shop_translate(language, self.description_translation_key)

        return self.description_translation_key

    @property
    def price_in_euro(self):
        return u'{:20,.2f}'.format(self.price / 100.0)

    def format_price(self, currency, locale=SHOP_DEFAULT_LANGUAGE, ratio=1.0, **kwargs):
        return format_currency(self.price * ratio / 100.0, currency, locale=locale, **kwargs)

    @staticmethod
    def get_by_code(code):
        return Product.get_by_key_name(code)

    @classmethod
    def create_key(cls, code):
        return db.Key.from_path(cls.kind(), code)

    @classmethod
    @db.non_transactional
    def get_products_dict(cls):
        return {p.code: p for p in cls.all()}

    @classmethod
    def list_by_legal_entity(cls, legal_entity_id):
        from shop.dal import get_mobicage_legal_entity
        legal_entity_id = legal_entity_id if legal_entity_id else get_mobicage_legal_entity().key().id()
        return cls.all().filter('legal_entity_id', legal_entity_id)

    @classmethod
    def list_visible_by_legal_entity(cls, legal_entity_id):
        return cls.all().filter("visible =", True).filter('legal_entity_id', legal_entity_id)


class Customer(db.Model):
    vat = db.StringProperty()
    name = db.StringProperty()
    normalized_name = db.StringProperty()
    creation_time = db.IntegerProperty(default=0)
    address1 = db.StringProperty()
    address2 = db.StringProperty()
    zip_code = db.StringProperty()
    city = db.StringProperty()
    country = db.StringProperty()
    language = db.StringProperty(indexed=False)
    user_email = db.StringProperty()
    service_email = db.StringProperty()
    manager = db.UserProperty(indexed=False)
    subscription_order_number = db.StringProperty()
    organization_type = db.IntegerProperty(default=ServiceProfile.ORGANIZATION_TYPE_PROFIT)
    managed_organization_types = db.ListProperty(int, indexed=False)
    migration_job = db.StringProperty(indexed=False)
    prospect_id = db.StringProperty()
    default_app_id = db.StringProperty()
    app_ids = db.StringListProperty()
    extra_apps_count = db.IntegerProperty(indexed=False)
    subscription_type = db.IntegerProperty(indexed=False, default=-1)
    has_loyalty = db.BooleanProperty(indexed=False, default=False)
    team_id = db.IntegerProperty(indexed=False)
    website = db.StringProperty()
    facebook_page = db.StringProperty()
    # when set to anything lower than the current date that isn't 0, the
    # service of the customer will be disabled over night.
    subscription_cancel_pending_date = db.IntegerProperty(default=0)
    service_disabled_at = db.IntegerProperty(default=0)  # 0 = not disabled
    disabled_reason = db.StringProperty(indexed=False)
    disabled_reason_int = db.IntegerProperty(default=0)

    stripe_id = db.StringProperty()
    stripe_id_created = db.IntegerProperty(default=0)
    stripe_credit_card_id = db.StringProperty()

    SUBSCRIPTION_TYPE_NONE = -1
    SUBSCRIPTION_TYPE_STATIC = 0
    SUBSCRIPTION_TYPE_DYNAMIC = 1
    SUBSCRIPTION_TYPES = {
        SUBSCRIPTION_TYPE_NONE: u'No subscription',
        SUBSCRIPTION_TYPE_STATIC: u'Static',
        SUBSCRIPTION_TYPE_DYNAMIC: u'Dynamic'
    }

    DISABLED_SUBSCRIPTION_EXPIRED = 1
    DISABLED_BAD_PAYER = 2
    DISABLED_OTHER = 3
    DISABLED_ASSOCIATION_BY_CITY = 4

    DISABLED_REASONS = {
        DISABLED_SUBSCRIPTION_EXPIRED: u'Subscription expired',
        DISABLED_BAD_PAYER: u'Did not pay on time',
        DISABLED_OTHER: u'Other',
        DISABLED_ASSOCIATION_BY_CITY: u'Disabled by city'
    }

    @property
    def service_user(self):
        return users.User(self.service_email)

    @property
    def country_str(self):
        return Locale(self.language).territories[self.country]

    @property
    def id(self):
        return self.key().id()

    @property
    def stripe_valid(self):
        if self.stripe_credit_card_id:
            cc = CreditCard.get_by_key_name(self.stripe_credit_card_id, parent=self)
            if cc:
                return cc.valid
        return False
    
    @property
    def payment_possible(self):
        if self.country in ('BE', 'NL',):
            return True
        return False

    @property
    def app_id(self):
        if self.default_app_id:
            return self.default_app_id
        if self.app_ids:
            return self.app_ids[0]
        return None

    @property
    def sorted_app_ids(self):
        if not self.app_ids:
            return self.app_ids

        default_app_id = self.app_id
        if self.app_ids[0] != default_app_id:
            self.app_ids.remove(default_app_id)
            self.app_ids.insert(0, default_app_id)
        return self.app_ids

    @classmethod
    def list_by_name(cls, name, limit=20):
        return cls.all().filter('name =', name).fetch(limit)

    @classmethod
    def create_key(cls, customer_id):
        azzert(isinstance(customer_id, (int, long)))
        return db.Key.from_path(cls.kind(), customer_id)

    @classmethod
    def starting_with(cls, name):
        name = cls.normalize_name(name)
        return cls.all().filter('normalized_name >=', name).filter('normalized_name <', name + u'\ufffd').order('normalized_name').fetch(20)

    @staticmethod
    def normalize_name(name):
        return "".join((c for c in name.strip().lower() if c in "abcdefghijklmnopqrstuvwxyz"))

    def list_contacts(self):
        return Contact.list(self.key())

    @property
    def auto_login_url(self):
        return u"/internal/shop/login_as?%s" % urllib.urlencode({"customer_id": self.id})

    @classmethod
    def get_by_service_email(cls, service_email):
        return cls.all().filter('service_email', service_email).get()

    @classmethod
    def list_by_user_email(cls, user_email):
        return cls.all().filter('user_email', user_email)

    @classmethod
    def list_by_manager(cls, manager, is_admin):
        if is_admin:
            # Get all customers from all regional managers
            order_keys = Order.all(keys_only=True)
            customers = db.get({order_key.parent() for order_key in order_keys})
            return customers
        else:
            order_keys = Order.all(keys_only=True).filter('manager', manager)
            return db.get({order_key.parent() for order_key in order_keys})

    @classmethod
    def list_enabled_by_app(cls, app_id):
        return cls.all().filter('default_app_id', app_id) \
            .filter('service_disabled_at', 0) \
            .filter('organization_type >', 0)

    @classmethod
    def list_enabled_by_organization_type_in_app(cls, app_id, organization_type):
        return cls.all().filter('default_app_id', app_id) \
            .filter('service_disabled_at', 0) \
            .filter('organization_type', organization_type).order('name')

    @property
    def disabled_reason_str(self):
        if self.disabled_reason_int == 0:
            return u'subscription not disabled'
        else:
            return self.DISABLED_REASONS[self.disabled_reason_int]

    @property
    def team(self):
        if not hasattr(self, '_team'):
            self._team = RegioManagerTeam.get_by_id(self.team_id)
        return self._team

    @property
    def legal_entity(self):
        if not hasattr(self, '_legal_entity'):
            self._legal_entity = self.team.legal_entity
        return self._legal_entity

    @classmethod
    def get_by_id(cls, ids, parent=None, **kwargs):
        """Get instance(s) of Customer by id.

        Args:
          ids: A single id or a list or tuple of ids.
          parent: Parent of instances to get.  Can be a model or key.
          config: datastore_rpc.Configuration to use for this request.

        Raises:
            CustomerNotFoundException: When the customer is not found (only when a single id was specified)

        Returns:
            Customer

        """
        customer = super(Customer, cls).get_by_id(ids, parent, **kwargs)
        if not customer and not isinstance(customer, list):
            raise CustomerNotFoundException(ids)
        return customer

    @property
    def should_pay_vat(self):
        return not self.vat or self.country == self.legal_entity.country_code

    @classmethod
    def list_by_app_id(cls, app_id):
        return Customer.all()\
            .filter('app_ids', app_id)

    @property
    def editable_organization_types(self):
        """
            The organization types of the services that this service can create/edit via the dashboard
        Returns:

        """
        if self.managed_organization_types:
            return self.managed_organization_types

        org_types = [ServiceProfile.ORGANIZATION_TYPE_NON_PROFIT]
        if self.country == 'BE':
            org_types.extend([ServiceProfile.ORGANIZATION_TYPE_PROFIT,
                              ServiceProfile.ORGANIZATION_TYPE_CITY,
                              ServiceProfile.ORGANIZATION_TYPE_EMERGENCY])
        return org_types

    def can_only_edit_organization_type(self, organization_type):
        return len(self.editable_organization_types) == 1 and self.editable_organization_types[0] == organization_type

    def can_edit_service(self, service_customer):
        """Check if a city service can edit another service on dashboard (merchants...etc).

        Args:
            service_customer (shop.models.Customer)

        Returns:
            bool
        """
        is_city = self.organization_type == OrganizationType.CITY
        if is_city and service_customer:
            return service_customer.organization_type in self.editable_organization_types
        return False


class CustomerSignup(db.Model):
    DEFAULT_MODULES = [SolutionModule.BROADCAST, SolutionModule.BULK_INVITE,
                       SolutionModule.QR_CODES, SolutionModule.STATIC_CONTENT,
                       SolutionModule.WHEN_WHERE, SolutionModule.ASK_QUESTION]

    company_name = db.StringProperty()
    company_organization_type = db.IntegerProperty()
    company_address1 = db.StringProperty()
    company_zip_code = db.StringProperty()
    company_city = db.StringProperty()
    company_vat = db.StringProperty()
    company_email = db.StringProperty()
    company_telephone = db.StringProperty()
    company_website = db.StringProperty()
    company_facebook_page = db.StringProperty()

    customer_name = db.StringProperty()
    customer_address1 = db.StringProperty()
    customer_zip_code = db.StringProperty()
    customer_city = db.StringProperty()
    customer_email = db.StringProperty()
    customer_telephone = db.StringProperty()
    customer_website = db.StringProperty()
    customer_facebook_page = db.StringProperty()

    modules = db.StringListProperty(default=DEFAULT_MODULES)
    timestamp = db.IntegerProperty()
    done = db.BooleanProperty(indexed=True, default=False)
    inbox_message_key = db.StringProperty(indexed=True)

    @classmethod
    def list_pending_by_customer_email(cls, email):
        return cls.all().filter('done', False).filter('customer_email', email)

    @staticmethod
    def normalize(value):
        if not isinstance(value, unicode):
            value = unicode(value)
        return ''.join(value.lower().split())

    def is_same_signup(self, signup):
        for prop_name, _ in self.properties().iteritems():
            if prop_name.startswith('company') or prop_name.startswith('customer'):
                value = self.normalize(getattr(self, prop_name))
                other_value = self.normalize(getattr(signup, prop_name))
                if value != other_value:
                    return False
        return True

    @property
    def id(self):
        return self.key().id()

    @property
    def city_customer(self):
        return self.parent()

    @property
    def city(self):
        return self.city_customer.city


class Contact(db.Model):
    first_name = db.StringProperty()
    last_name = db.StringProperty()
    email = db.StringProperty()
    phone_number = db.StringProperty()

    @property
    def id(self):
        return self.key().id()

    @property
    def customer_key(self):
        return self.parent_key()

    @property
    def customer(self):
        return Customer.get(self.customer_key)

    @staticmethod
    def list(customer_key):
        return list(Contact.all().ancestor(customer_key).order('first_name'))

    @staticmethod
    def get_one(customer_key):
        return Contact.all().ancestor(customer_key).get()

    @staticmethod
    def get_by_contact_id(customer, contact_id):
        return Contact.get_by_id(contact_id, customer)

    @classmethod
    def create_key(cls, contact_id, customer_id):
        return db.Key.from_path(cls.kind(), contact_id, parent=Customer.create_key(customer_id))


class OsaSequenceBaseModel(db.Model):
    last_number = db.IntegerProperty(default=0)

    @property
    def year(self):
        return int(self.key().name())

    @classmethod
    def _next_number(cls, legal_entity):
        azzert(db.is_in_transaction())
        azzert(legal_entity)
        year = str(datetime.datetime.now().year)
        number = cls.get_by_key_name(year, parent=legal_entity)
        if not number:
            number = cls(key_name=year, parent=legal_entity)
        number.last_number += 1
        number.put()
        return number

    @classmethod
    def next(cls, legal_entity):
        number = cls._next_number(legal_entity)
        return u"OSA.%s.%s" % (number.year, number.last_number)


class InvoiceNumber(OsaSequenceBaseModel):
    pass


class OrderNumber(OsaSequenceBaseModel):
    pass


class ChargeNumber(OsaSequenceBaseModel):

    @classmethod
    def next(cls, legal_entity):
        number = cls._next_number(legal_entity)
        return number.last_number


class Order(db.Model):
    STATUS_UNSIGNED = 0
    STATUS_SIGNED = 1
    STATUS_CANCELED = 2

    CUSTOMER_STORE_ORDER_NUMBER = '-1'

    date = db.IntegerProperty()
    amount = db.IntegerProperty()  # In euro cents
    vat_pct = db.IntegerProperty()
    vat = db.IntegerProperty()  # In euro cents
    total_amount = db.IntegerProperty()  # In euro cents
    contact_id = db.IntegerProperty()
    signature = db.BlobProperty()
    pdf = db.BlobProperty()
    status = db.IntegerProperty(default=STATUS_UNSIGNED)
    is_subscription_order = db.BooleanProperty()
    is_subscription_extension_order = db.BooleanProperty(default=False)
    date_signed = db.IntegerProperty()
    next_charge_date = db.IntegerProperty()
    date_canceled = db.IntegerProperty()
    manager = db.UserProperty()
    team_id = db.IntegerProperty(indexed=True)

    @property
    def amount_in_euro(self):
        return u'{:20,.2f}'.format(self.amount / 100.0)

    @property
    def vat_in_euro(self):
        return u'{:20,.2f}'.format(self.vat / 100.0)

    @property
    def total_amount_in_euro(self):
        return u'{:20,.2f}'.format(self.total_amount / 100.0)

    @property
    def order_number(self):
        return self.key().name()

    @property
    def full_date_str(self):
        return time.strftime(u'%d %b %Y %H:%M:%S', time.gmtime(self.date))

    @property
    def full_date_canceled_str(self):
        return time.strftime(u'%d %b %Y %H:%M:%S', time.gmtime(self.date_canceled))

    @property
    def date_str(self):
        return time.strftime(u'%d/%m/%Y', time.gmtime(self.date))

    @property
    def customer_key(self):
        return self.parent_key()

    @property
    def customer_id(self):
        return self.parent_key().id()

    @property
    def contact_key(self):
        return db.Key.from_path(Contact.kind(), self.contact_id, parent=self.customer_key)

    @property
    def contact(self):
        return Contact.get_by_id(self.contact_id, self.customer_key)

    @property
    def signature_as_data_url(self):
        if not self.signature:
            return None
        return u"data:image/jpg;base64,%s" % base64.b64encode(self.signature)

    @staticmethod
    def get_by_order_number(customer_id, order_number):
        return db.get(Order.create_key(customer_id, order_number))

    @classmethod
    def create_key(cls, customer_id, order_number):
        return db.Key.from_path(cls.kind(), order_number, parent=Customer.create_key(customer_id))

    @staticmethod
    def list(customer_key):
        return list(Order.all().ancestor(customer_key).order('date'))

    @staticmethod
    def list_unsigned(customer):
        return Order.all()\
            .ancestor(customer)\
            .filter('status', Order.STATUS_UNSIGNED)\
            .order('date')

    @staticmethod
    def list_signed(customer_key):
        return Order.all().ancestor(customer_key).filter('status', Order.STATUS_SIGNED).order('date')

    def list_items(self):
        order_item_qry = OrderItem.gql("WHERE ANCESTOR IS :ancestor ORDER BY number")
        order_item_qry.bind(ancestor=self)
        return list(order_item_qry)

    @classmethod
    def list_by_contact_id(cls, contact_id):
        return cls.all().filter('contact_id', contact_id)

    @staticmethod
    def default_next_charge_date():
        """Get the default next charge date (today + 1 month)."""
        next_month = datetime.datetime.utcfromtimestamp(now()) + relativedelta(months=1)
        return get_epoch_from_datetime(next_month)


class OrderItem(db.Expando):
    # Used for sorting
    number = db.IntegerProperty()
    product_code = db.StringProperty()
    count = db.IntegerProperty()
    comment = db.TextProperty()
    price = db.IntegerProperty()  # In euro cents
    # app_id : only for orderItems with product code XCTY and NEWS
    # news_item_id: for orderItems with product code NEWS

    @property
    def price_in_euro(self):
        return '{:20,.2f}'.format(self.price / 100.0)

    @property
    def total_price_in_euro(self):
        return '{:20,.2f}'.format((self.price * self.count) / 100.0)

    def format_total_price(self, currency, locale=SHOP_DEFAULT_LANGUAGE, ratio=1.0, **kwargs):
        return format_currency(self.price * self.count * ratio / 100.0, currency, locale=locale, **kwargs)

    def format_price(self, currency, locale=SHOP_DEFAULT_LANGUAGE, ratio=1.0, **kwargs):
        return format_currency(self.price * ratio / 100.0, currency, locale=locale, **kwargs)

    @property
    def order_key(self):
        return self.parent_key()

    @property
    def order_number(self):
        return self.parent_key().name()

    @property
    def order(self):
        return Order.get(self.order_key)

    @property
    def clean_product_code(self):
        if "." not in self.product_code:
            return self.product_code
        return self.product_code.split(".", 1)[1]

    @property
    @db.non_transactional
    def product(self):
        return Product.get_by_key_name(self.product_code)

    @staticmethod
    def list_by_order(order_key):
        return OrderItem.all().ancestor(order_key)

    @classmethod
    def create_key(cls, customer_id, order_number, order_item_id):
        return db.Key.from_path(cls.kind(), order_item_id, parent=Order.create_key(customer_id, order_number))


class CreditCard(db.Model):
    creation_time = db.IntegerProperty()
    deleted = db.BooleanProperty(default=False)
    valid = db.BooleanProperty(default=True)
    contact_id = db.IntegerProperty()

    @property
    def stripe_card_id(self):
        return self.key().name()

    @property
    def customer_key(self):
        return self.parent_key()

    @property
    def customer(self):
        return Customer.get(self.customer_key)

    @property
    def contact(self):
        return Contact.get_by_id(self.contact_id, self.customer_key)

    @classmethod
    def list_by_contact_id(cls, contact_id):
        return cls.all().filter('contact_id', contact_id)


class StructuredInfoSequence(db.Model):
    last_number = db.IntegerProperty(default=0)

    @property
    def year(self):
        return int(self.key().name())

    @staticmethod
    def next():
        azzert(db.is_in_transaction())
        year = datetime.datetime.now().year
        sis = StructuredInfoSequence.get_by_key_name(str(year))
        if not sis:
            sis = StructuredInfoSequence(key_name=str(year))
        sis.last_number += 1
        sis.put()
        modulo = sis.last_number % 97
        if modulo == 0:
            modulo = 97
        modulo = "%02d" % (modulo)
        number = "%010d" % sis.last_number
        azzert(len(number + modulo) == 12)
        return "+++%s/%s/%s%s+++" % (number[0:3], number[3:7], number[7:10], modulo)


class Charge(db.Model):
    STATUS_PENDING = 0
    STATUS_EXECUTED = 1
    STATUS_CANCELLED = 2
    TYPE_ORDER_DELIVERY = 1
    TYPE_RECURRING_SUBSCRIPTION = 2
    # For customers without credit card that still want to participate
    TYPE_SUBSCRIPTION_EXTENSION = 3

    date = db.IntegerProperty()
    date_executed = db.IntegerProperty()
    date_cancelled = db.IntegerProperty()
    type = db.IntegerProperty()
    charge_number = db.IntegerProperty(indexed=True)

    amount = db.IntegerProperty(indexed=False)  # In euro cents
    vat_pct = db.IntegerProperty(indexed=False)
    vat = db.IntegerProperty(indexed=False)  # In euro cents
    total_amount = db.IntegerProperty(indexed=False)  # In euro cents
    amount_paid_in_advance = db.IntegerProperty(indexed=False, default=0)  # In euro cents
    currency_code = db.StringProperty(indexed=False, default=u'EUR')
    paid = db.BooleanProperty(indexed=False, default=False)

    status = db.IntegerProperty(default=0)

    log = db.TextProperty()

    structured_info = db.StringProperty(indexed=True)
    last_notification = db.IntegerProperty(indexed=False)
    payment_reminders = db.IntegerProperty(default=0, indexed=False)
    manager = db.UserProperty()
    team_id = db.IntegerProperty(indexed=True)
    customer_po_number = db.StringProperty(indexed=False)
    invoice_number = db.StringProperty(default='', indexed=False)

    subscription_extension_order_item_keys = db.ListProperty(db.Key, indexed=False)
    subscription_extension_length = db.IntegerProperty(indexed=False, default=1)

    @property
    def id(self):
        return self.key().id()

    @property
    def payment_overdue(self):
        return now() - self.last_notification > 7 * 24 * 3600

    @property
    def order_number(self):
        return self.parent_key().name()

    @property
    def customer_key(self):
        return self.key().parent().parent()

    @property
    def customer_id(self):
        return self.customer_key.id()

    @classmethod
    def create_key(cls, charge_id, order_number, customer_id):
        azzert(isinstance(charge_id, (int, long)))
        return db.Key.from_path(cls.kind(), charge_id, parent=Order.create_key(customer_id, order_number))

    @property
    def full_date_str(self):
        return time.strftime('%d %b %Y %H:%M:%S', time.gmtime(self.date))

    @property
    def last_notification_date_str(self):
        if self.last_notification:
            return time.strftime('%d %b %Y %H:%M:%S', time.gmtime(self.last_notification))
        else:
            return ""

    @property
    def amount_paid_in_advance_formatted(self):
        return '{:20,.2f}'.format(self.amount_paid_in_advance / 100.0)

    @property
    def total_amount_formatted(self):
        return '{:20,.2f}'.format(self.total_amount / 100.0)

    @property
    def amount_in_euro(self):
        return '{:20,.2f}'.format(self.amount / 100.0)

    @property
    def vat_in_euro(self):
        return '{:20,.2f}'.format(self.vat / 100.0)

    @property
    def total_amount_in_euro(self):
        return '{:20,.2f}'.format(self.total_amount / 100.0)

    @property
    def reference(self):
        # place a " * " between after every 3rd digit
        return u" * ".join(chunks(str(self.charge_number), 3)) if self.charge_number else None

    @property
    def is_recurrent(self):
        return self.type in (self.TYPE_SUBSCRIPTION_EXTENSION, self.TYPE_RECURRING_SUBSCRIPTION)

    @classmethod
    def get_by_reference(cls, charge_reference, customer_or_key=None):
        charge_number = long(re.sub('\D', '', charge_reference))  # removing all non-digit characters
        qry = cls.all()
        if customer_or_key:
            qry.ancestor(customer_or_key)
        return qry.filter('charge_number', charge_number).get()

    @property
    def currency(self):
        return get_currency_symbol(self.currency_code, SHOP_DEFAULT_LANGUAGE)

    @property
    def is_reseller_charge(self):
        return self.customer_key.kind() == LegalEntity.kind()


class Invoice(db.Model):
    PAYMENT_STRIPE = 1
    PAYMENT_MANUAL = 2
    PAYMENT_MANUAL_AFTER = 3
    PAYMENT_ON_SITE = 4

    date = db.IntegerProperty()
    pdf = db.BlobProperty()
    amount = db.IntegerProperty()  # In euro cents
    vat_pct = db.IntegerProperty()
    vat = db.IntegerProperty()  # In euro cents
    total_amount = db.IntegerProperty()  # In euro cents
    currency_code = db.StringProperty(indexed=False, default=u'EUR')

    # Paid -> On bank account
    paid = db.BooleanProperty(default=False)
    paid_timestamp = db.IntegerProperty()
    payment_type = db.IntegerProperty(default=0)  # Does not mean it's already on our bank account
    payment_term = db.IntegerProperty()
    operator = db.UserProperty()  # RegioManager
    legal_entity_id = db.IntegerProperty()

    @property
    def payment_term_formatted(self):
        d = datetime.datetime.fromtimestamp(self.payment_term, tz=get_timezone('Europe/Brussels'))
        return format_date(d, format='full', locale='nl_BE')

    @property
    def invoice_number(self):
        return self.key().name()

    @property
    def charge_id(self):
        return self.parent_key().id()

    @property
    def charge(self):
        return self.parent()

    @property
    def charge_key(self):
        return self.parent_key()

    @property
    def order_number(self):
        return self.parent_key().parent().name()

    @property
    def order_key(self):
        return self.parent_key().parent()

    @property
    def customer_id(self):
        return self.parent_key().parent().parent().id()

    @property
    def full_date_str(self):
        return time.strftime('%d %b %Y %H:%M:%S', time.gmtime(self.date))

    @property
    def date_str(self):
        return time.strftime('%d/%m/%Y', time.gmtime(self.date))

    @staticmethod
    def get_by_invoice_number(customer_id, order_number, charge_id, invoice_number):
        return db.get(Invoice.create_key(customer_id, order_number, charge_id, invoice_number))

    @classmethod
    def create_key(cls, customer_id, order_number, charge_id, invoice_number):
        return db.Key.from_path(cls.kind(), invoice_number, parent=Charge.create_key(charge_id, order_number, customer_id))


class ExpiredSubscription(db.Model):
    STATUS_EXPIRED = 0
    STATUS_WILL_LINK_CREDIT_CARD = 1
    STATUS_EXTEND_SUBSCRIPTION = 2
    STATUSES = {
        STATUS_EXPIRED: 'Expired',
        STATUS_WILL_LINK_CREDIT_CARD: 'Will link credit card',
        STATUS_EXTEND_SUBSCRIPTION: 'Extend subscription'
    }
    expiration_timestamp = db.IntegerProperty()
    status = db.IntegerProperty(default=0)
    status_updated_timestamp = db.IntegerProperty()

    @classmethod
    def get_by_customer_id(cls, customer_id):
        return cls.get(cls.create_key(customer_id))

    @property
    def customer_id(self):
        return self.parent_key().id()

    @classmethod
    def create_key(cls, customer_id):
        return db.Key.from_path(cls.kind(), customer_id, parent=Customer.create_key(customer_id))

    @property
    def expiration_timestamp_str(self):
        if not self.expiration_timestamp:
            return u''
        return datetime.datetime.utcfromtimestamp(self.expiration_timestamp).strftime(u'%A %d %b %Y')

    @property
    def status_updated_timestamp_str(self):
        return datetime.datetime.utcfromtimestamp(self.status_updated_timestamp).strftime('%A %d %b %Y')

    @property
    def status_str(self):
        return self.STATUSES[self.status]

    @classmethod
    def list_all(cls):
        return cls.all().order('status_updated_timestamp')


class AuditLog(db.Model):
    date = db.IntegerProperty()
    customer_id = db.IntegerProperty()
    prospect_id = db.StringProperty()
    user = db.UserProperty()
    message = db.StringProperty(indexed=False)
    variables = db.TextProperty()


class ShopApp(CachedModelMixIn, db.Model):
    name = db.StringProperty(indexed=False)
    searched_south_west_bounds = db.ListProperty(db.GeoPt)  # [south_west1, south_west2, ...]
    searched_north_east_bounds = db.ListProperty(db.GeoPt)  # [north_east1, north_east2, ...]
    postal_codes = db.StringListProperty()
    signup_enabled = db.BooleanProperty(indexed=True, default=False)

    def south_west(self):
        if not self.searched_south_west_bounds:
            return None
        return db.GeoPt(min((sw.lat for sw in self.searched_south_west_bounds)),
                        min((sw.lon for sw in self.searched_south_west_bounds)))

    def north_east(self):
        if not self.searched_north_east_bounds:
            return None
        return db.GeoPt(max((ne.lat for ne in self.searched_north_east_bounds)),
                        max((ne.lon for ne in self.searched_north_east_bounds)))

    @property
    def app_id(self):
        return self.key().name()

    @classmethod
    def create_key(cls, app_id):
        return db.Key.from_path(cls.kind(), app_id)

    @classmethod
    def find_by_postal_code(cls, postal_code):
        return cls.all().filter('postal_codes =', postal_code).get()

    def invalidateCache(self):
        from shop.bizz import is_signup_enabled
        invalidate_cache(is_signup_enabled, self.app_id)


class ShopAppGridPoints(db.Model):
    points = db.ListProperty(db.GeoPt, indexed=False)

    @property
    def shop_app_key(self):
        return self.parent_key()

    @property
    def app_id(self):
        return self.shop_app_key.name()


class Prospect(db.Model):
    INVITE_CODE_IN_CALL = -1
    INVITE_CODE_NOT_ATTEMPTED = 0
    INVITE_CODE_HANG_UP = 1
    INVITE_CODE_NO_ANSWER = 2
    INVITE_CODE_ANSWERED = 3
    INVITE_CODE_CALL_FAILURE = 4
    INVITE_CODE_TO_BE_CALLED = 5

    INVITE_RESULT_YES = 1
    INVITE_RESULT_MAYBE = 2
    INVITE_RESULT_NO = 3

    INVITE_RESULT_STRING_YES = 'YES'
    INVITE_RESULT_STRING_NO = 'NO'
    INVITE_RESULT_STRING_MAYBE = 'MAYBE'
    INVITE_RESULT_STRING_NO_ANSWER = 'NO_ANSWER'
    INVITE_RESULT_STRING_CALL_FAILURE = 'CALL_FAILURE'

    INVITE_RESULT_STRINGS = (INVITE_RESULT_STRING_YES, INVITE_RESULT_STRING_NO,
                             INVITE_RESULT_STRING_MAYBE, INVITE_RESULT_STRING_NO_ANSWER, INVITE_RESULT_STRING_CALL_FAILURE)

    STATUS_TODO = 0
    STATUS_APPOINTMENT_MADE = 1
    STATUS_CALL_BACK = 2
    STATUS_NOT_INTERESTED = 3
    STATUS_IRRELEVANT = 4
    STATUS_CUSTOMER = 5
    STATUS_NOT_ANSWERED = 6
    STATUS_NOT_EXISTING = 7
    STATUS_CONTACT_LATER = 8
    STATUS_NOT_INTERESTED_AFTER_APPOINTMENT = 9
    STATUS_INVITED_TO_INTRODUCTION = 10
    STATUS_ADDED_BY_DISCOVERY = 11

    STATUS_TYPES = {
        STATUS_TODO: 'Not contacted',
        STATUS_APPOINTMENT_MADE: 'Appointment scheduled',
        STATUS_CALL_BACK: 'Need to call back',
        STATUS_NOT_INTERESTED: 'Not interested',
        STATUS_IRRELEVANT: 'Not relevant',
        STATUS_CUSTOMER: 'Customer',
        STATUS_NOT_ANSWERED: 'Not answered',
        STATUS_NOT_EXISTING: 'Not existing',
        STATUS_CONTACT_LATER: 'On hold',
        STATUS_NOT_INTERESTED_AFTER_APPOINTMENT: 'Not interested after appointment',
        STATUS_INVITED_TO_INTRODUCTION: 'Invited to introduction',
        STATUS_ADDED_BY_DISCOVERY: 'Added via prospect discovery app'
    }
    app_id = db.StringProperty()
    name = db.StringProperty()
    type = db.StringListProperty()  # google types like [cafe, food, establishment...]
    # Simplified/summarised version of google place types. See PROSPECT_CATEGORIES dict.
    categories = db.StringListProperty()
    address = db.StringProperty()
    geo_point = db.GeoPtProperty()
    phone = db.StringProperty()
    website = db.StringProperty()
    invite_code = db.IntegerProperty()
    invite_result = db.IntegerProperty()
    status = db.IntegerProperty(indexed=True, default=STATUS_TODO)
    reason = db.StringProperty(indexed=False, multiline=True)  # reason why prospect does not want to buy
    action_timestamp = db.IntegerProperty(indexed=False)  # time on which prospect needs to be called / visited / ...
    assignee = db.StringProperty()
    customer_id = db.IntegerProperty()
    email = db.StringProperty()
    comments = ProspectCommentsProperty()
    certainty = db.IntegerProperty(indexed=False)
    subscription = db.IntegerProperty(indexed=False)

    @property
    def id(self):
        return unicode(self.key().id_or_name())

    @property
    def type_html_str(self):
        if self.type:
            return "<br>".join(self.type)
        return ""

    def add_comment(self, comment_text, assignee_user):
        if self.comments is None:
            self.comments = ProspectComments()
        comment = ProspectComment()
        comment.index = max((c.index for c in self.comments)) + 1 if len(self.comments) else 0
        comment.text = comment_text
        comment.creator = assignee_user.email().decode('utf-8')
        comment.timestamp = now()
        self.comments.add(comment)

    @classmethod
    def create_key(cls, prospect_id):
        try:
            # prospect_id can be a numeric string (when added while using TROPO) that we need to cast to a long
            prospect_id = long(prospect_id)
        except ValueError:
            pass

        return db.Key.from_path(cls.kind(), prospect_id)

    @classmethod
    def find_by_assignee(cls, assignee):
        return cls.all().filter('assignee', assignee)

    @staticmethod
    def convert_place_types(prospect_google_place_types):
        """
        Converts list of Google place types to our own categories. See PROSPECT_CATEGORIES dict.
        Args:
            prospect_google_place_types: List of Google place types

        Returns:
            categories(list): List of place categories
        """
        categories = set()
        for prospect_google_place_type in prospect_google_place_types:
            for place_type, google_place_types in PROSPECT_CATEGORIES.iteritems():
                if prospect_google_place_type in google_place_types:
                    categories.add(place_type)
        if len(categories) == 0:
            categories.add('other')
        return list(categories)


class ProspectRejectionReason(db.Model):
    reason = db.StringProperty(indexed=True)


class ProspectInteractions(db.Model):
    TYPE_INVITE = 1
    type = db.IntegerProperty()
    timestamp = db.IntegerProperty()
    code = db.IntegerProperty()
    result = db.IntegerProperty()
    comment = db.StringProperty(indexed=False)

    @property
    def prospect(self):
        return db.get(self.parent_key())

    @property
    def str_key(self):
        return str(self.key())


class ShopTask(db.Model):
    VISIT_DURATION = 60  # minutes
    TYPE_VISIT = 1
    TYPE_CALL = 2
    TYPE_SUPPORT_NEEDED = 3
    TYPE_CHECK_CREDIT_CARD = 4

    TYPE_STRINGS = {
        TYPE_VISIT: u'Visit',
        TYPE_CALL: u'Call',
        TYPE_SUPPORT_NEEDED: u'Support',
        TYPE_CHECK_CREDIT_CARD: u'Check creditcard'
    }

    SUB_SILVER = 1
    SUB_GOLD = 2
    SUB_PLATINUM = 3

    SUB_STRINGS = {
        SUB_SILVER: u'Silver',
        SUB_GOLD: u'Gold',
        SUB_PLATINUM: u'Platinum'
    }

    STATUS_NEW = 1
    STATUS_PROCESSED = 2
    STATUS_CLOSED = 3

    STATUS_STRINGS = {STATUS_NEW: u'New',
                      STATUS_PROCESSED: u'Processed',
                      STATUS_CLOSED: u'Closed'}
    APPOINTMENT_TYPE_FIRST_APPOINTMENT = 1
    APPOINTMENT_TYPE_LOYALTY_EXPLANATION = 2
    APPOINTMENT_TYPE_SIGN = 3
    APPOINTMENT_TYPE_LOYALTY_INSTALATION = 4
    APPOINTMENT_TYPE_TECHNICAL_SUPPORT = 5
    APPOINTMENT_TYPES = {
        APPOINTMENT_TYPE_FIRST_APPOINTMENT: 'First appointment',
        APPOINTMENT_TYPE_LOYALTY_EXPLANATION: 'Loyalty system demo',
        APPOINTMENT_TYPE_SIGN: 'Sign order',
        APPOINTMENT_TYPE_LOYALTY_INSTALATION: 'Loyalty system installation',
        APPOINTMENT_TYPE_TECHNICAL_SUPPORT: 'Technical support'
    }

    assignee = db.StringProperty(indexed=True)  # e-mail address of regio_manager
    created_by = db.StringProperty(indexed=True)
    closed_by = db.StringProperty(indexed=True)

    creation_time = db.IntegerProperty(indexed=False)
    closed_time = db.IntegerProperty(indexed=True)
    execution_time = db.IntegerProperty(indexed=True)
    status = db.IntegerProperty(indexed=True)
    type = db.IntegerProperty(indexed=True)
    address = db.StringProperty(indexed=False)
    certainty = db.IntegerProperty(indexed=False)  # goes from 0 to 100
    subscription = db.IntegerProperty(indexed=False)
    comment = db.TextProperty()
    app_id = db.StringProperty()

    @property
    def id(self):
        return self.key().id()

    @property
    def type_str(self):
        return self.TYPE_STRINGS[self.type]

    @property
    def status_str(self):
        return self.STATUS_STRINGS[self.status]

    @classmethod
    def type_from_prospect_status(cls, prospect_status):
        if prospect_status == Prospect.STATUS_APPOINTMENT_MADE:
            return cls.TYPE_VISIT
        if prospect_status == Prospect.STATUS_CALL_BACK:
            return cls.TYPE_CALL

        raise ValueError('Unsupported prospect_status %s' % prospect_status)

    @classmethod
    def group_by_assignees(cls, filter_assignees=None, app_id=None, task_type=None):
        result = dict()
        qry = cls.all().filter('status', cls.STATUS_NEW).order('execution_time')
        if filter_assignees:
            result.update({assignee: list() for assignee in filter_assignees})
            if len(filter_assignees) == 1:
                qry.filter('assignee', filter_assignees[0])
            else:
                qry.filter('assignee IN', [assignee for assignee in filter_assignees])
        if app_id:
            qry.filter('app_id =', app_id)
        if task_type:
            qry.filter('type', task_type)
        for t in qry:
            result.setdefault(t.assignee, list()).append(t)
        return result

    @classmethod
    def list_by_prospect(cls, prospect_or_key, task_types=None, statuses=None):
        qry = cls.all().ancestor(prospect_or_key)
        if task_types is not None:
            qry.filter('type IN', task_types)
        if statuses is not None:
            qry.filter('status IN', statuses)
        return qry

    @classmethod
    def history(cls, dateFrom, dateTo):
        result = dict()
        qry = cls.all().filter('closed_time >', dateFrom).filter('closed_time <', dateTo).order('-closed_time')

        for t in qry:
            result.setdefault(t.assignee, list()).append(t)
        return result

    @classmethod
    def get_all_history(cls, prospect_id):
        return cls.all().ancestor(Prospect.create_key(prospect_id)).order('-closed_time')


class ProspectHistory(db.Model):
    TYPE_VISIT = 1
    TYPE_CALL = 2
    TYPE_SUPPORT_NEEDED = 3
    TYPE_CHECK_CREDIT_CARD = 4
    TYPE_ADDED_COMMENT = 10

    TYPE_STRINGS = {
        TYPE_VISIT: u'Visit',
        TYPE_CALL: u'Call',
        TYPE_SUPPORT_NEEDED: u'Support',
        TYPE_CHECK_CREDIT_CARD: u'Check creditcard',
        TYPE_ADDED_COMMENT: u'Added comment'
    }

    STATUS_TODO = 0
    STATUS_APPOINTMENT_MADE = 1
    STATUS_CALL_BACK = 2
    STATUS_NOT_INTERESTED = 3
    STATUS_IRRELEVANT = 4
    STATUS_CUSTOMER = 5
    STATUS_NOT_ANSWERED = 6
    STATUS_NOT_EXISTING = 7
    STATUS_CONTACT_LATER = 8
    STATUS_NOT_INTERESTED_AFTER_APPOINTMENT = 9
    STATUS_INVITED_TO_INTRODUCTION = 10
    STATUS_ADDED_BY_DISCOVERY = 11

    executed_by = db.StringProperty(indexed=False)  # e-mail address of regio_manager
    created_time = db.IntegerProperty(indexed=False)
    type = db.IntegerProperty(indexed=False)  # Same types as ShopTask, can be None (call back, visit, ...)
    comment = db.TextProperty(indexed=False)  # Comment added by regiomanager.
    # from Prospect-> status (contact later, not existing, irrelevant, customer, ...)
    status = db.IntegerProperty(indexed=False)
    # from Prospect -> reason (too expensive, asked to contact later, ...)
    reason = db.StringProperty(indexed=False, multiline=True)

    @property
    def id(self):
        return self.key().id()

    @property
    def type_str(self):
        return self.TYPE_STRINGS[self.type] if self.type else None


class ShopLoyaltySlide(db.Model):
    timestamp = db.IntegerProperty()
    name = db.StringProperty(indexed=False)
    time = db.IntegerProperty(indexed=False)
    item = blobstore.BlobReferenceProperty()  # deprecated
    gcs_filename = db.StringProperty(indexed=False)
    content_type = db.StringProperty(indexed=False)
    has_apps = db.BooleanProperty(default=True)
    apps = db.StringListProperty(indexed=True)
    function_dependencies = db.IntegerProperty(indexed=False)
    deleted = db.BooleanProperty(default=False)

    @property
    def id(self):
        return self.key().id()

    @property
    def str_apps(self):
        r = json.dumps(self.apps)
        return r

    def item_url(self):
        if self.gcs_filename:
            k = blobstore.create_gs_key('/gs' + self.gcs_filename)
        else:
            k = self.item
        return unicode(images.get_serving_url(k, secure_url=True))

    def slide_url(self):
        from rogerthat.settings import get_server_settings
        server_settings = get_server_settings()
        if self.gcs_filename:
            return get_serving_url(self.gcs_filename)
        return unicode("%s/unauthenticated/loyalty/slide?%s" % (server_settings.baseUrl, urllib.urlencode(dict(slide_key=self.item.key()))))


class ShopLoyaltySlideNewOrder(db.Model):
    timestamp = db.IntegerProperty(indexed=False)
    time = db.IntegerProperty(indexed=False)
    item = blobstore.BlobReferenceProperty()  # deprecated
    gcs_filename = db.StringProperty(indexed=False)
    content_type = db.StringProperty(indexed=False)

    @property
    def app_id(self):
        return self.key().name()

    def item_url(self):
        if self.gcs_filename:
            k = blobstore.create_gs_key('/gs' + self.gcs_filename)
        else:
            k = self.item
        return unicode(images.get_serving_url(k, secure_url=True))

    def slide_url(self):
        from rogerthat.settings import get_server_settings
        server_settings = get_server_settings()
        if self.gcs_filename:
            return get_serving_url(self.gcs_filename)
        return unicode("%s/unauthenticated/loyalty/slide?%s" % (server_settings.baseUrl, urllib.urlencode(dict(slide_key=self.item.key()))))

    @classmethod
    def create_key(cls, app):
        return db.Key.from_path(cls.kind(), app)


class RegioManagerStatistic(db.Model):
    month_revenue = db.ListProperty(int, indexed=False)  # [month, revenue] e.g.: [201509, 150000]
    day_revenue = db.ListProperty(int, indexed=False)  # [day, revenue] e.g.: [20150918, 9000, 20150919, 1000]

    @property
    def manager(self):
        return self.key().name()

    @classmethod
    def create_key(cls, manager_mail):
        return db.Key.from_path(cls.kind(), manager_mail)


class LegalEntity(CachedModelMixIn, db.Model):
    name = db.StringProperty(indexed=False)
    address = db.PostalAddressProperty(indexed=False)
    postal_code = db.StringProperty(indexed=False)
    city = db.StringProperty(indexed=False)
    country_code = db.StringProperty(indexed=False)
    phone = db.PhoneNumberProperty(indexed=False)
    email = db.EmailProperty(indexed=False)
    vat_percent = db.RatingProperty(indexed=False)  # min 0, max 100
    vat_number = db.StringProperty(indexed=False)
    iban = db.StringProperty(indexed=False)
    bic = db.StringProperty(indexed=False)
    terms_of_use = db.TextProperty()
    is_mobicage = db.BooleanProperty(required=True, indexed=True)
    currency_code = db.StringProperty(indexed=False, default=u'EUR')
    customer_id = db.IntegerProperty(indexed=False)
    contact_id = db.IntegerProperty(indexed=False)
    revenue_percentage = db.IntegerProperty(default=50)  # Their cut in %

    @property
    def is_reseller(self):
        return not self.is_mobicage

    @property
    def id(self):
        return self.key().id()

    @property
    def currency(self):
        return get_currency_symbol(self.currency_code, SHOP_DEFAULT_LANGUAGE)

    @property
    def revenue_percent(self):
        return self.revenue_percentage / 100.

    def country(self, language):
        return Locale(language).territories[self.country_code]

    def invalidateCache(self):
        if self.is_mobicage:
            from shop.dal import get_mobicage_legal_entity
            invalidate_cache(get_mobicage_legal_entity)

    @classmethod
    def create_key(cls, legal_entity_id):
        return db.Key.from_path(cls.kind(), legal_entity_id)

    @classmethod
    def list_all(cls):
        return cls.all()

    @classmethod
    def list_non_mobicage(cls, keys_only=False):
        return list(cls.all(keys_only=keys_only).filter('is_mobicage', False))

    @classmethod
    def get_mobicage(cls):
        from shop.dal import get_mobicage_legal_entity
        return get_mobicage_legal_entity()  # this method is cached

    def get_or_create_customer(self):
        if self.customer_id:
            return Customer.get_by_id(self.customer_id)
        else:
            from shop.bizz import create_contact
            customer = Customer(creation_time=now(),
                                team_id=RegioManagerTeam.get_mobicage().id,
                                manager=None,
                                vat=self.vat_number,
                                name=u'Reseller: %s' % self.name,
                                normalized_name=Customer.normalize_name(u'Reseller: %s' % self.name),
                                address1=self.address,
                                address2=u'',
                                zip_code=self.postal_code,
                                city=self.city,
                                country=self.country_code,
                                language='en',
                                organization_type=OrganizationType.PROFIT)
            customer.put()
            contact = create_contact(customer, u'Reseller', self.name, self.email, self.phone)
            self.customer_id = customer.id
            self.contact_id = contact.id
            self.put()
            return customer

    @classmethod
    def list_billable(cls):
        return cls.all().filter('revenue_percentage <', 100)


@deserializer
def ds_legal_entity(stream):
    return ds_model(stream, LegalEntity)


@serializer
def s_legal_entity(stream, model):
    s_model(stream, model, LegalEntity)


register(LegalEntity, s_legal_entity, ds_legal_entity)

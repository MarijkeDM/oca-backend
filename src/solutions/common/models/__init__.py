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

import json
import logging

from babel.dates import get_timezone
from google.appengine.ext import db
from mcfw.cache import invalidate_cache, CachedModelMixIn
from mcfw.properties import azzert
from mcfw.rpc import returns, arguments, parse_complex_value
from mcfw.serialization import deserializer, ds_model, serializer, s_model, register
from rogerthat.dal import parent_key, parent_key_unsafe
from rogerthat.rpc import users
from rogerthat.to.messaging import AttachmentTO
from rogerthat.utils import now
from rogerthat.utils.service import get_identity_from_service_identity_user, \
    get_service_user_from_service_identity_user
from solutions.common import SOLUTION_COMMON
from solutions.common.models.properties import SolutionUserProperty, MenuCategoriesProperty
from solutions.common.utils import create_service_identity_user_wo_default


class SolutionInboxMessage(db.Model):
    INBOX_NAME_UNREAD = u"unread"
    INBOX_NAME_STARRED = u"starred"
    INBOX_NAME_READ = u"read"
    INBOX_NAME_TRASH = u"trash"
    INBOX_NAME_DELETED = u"deleted"

    CATEGORY_APPOINTMENT = 'appointment'
    CATEGORY_ASK_QUESTION = 'ask_question'
    CATEGORY_BULK_INVITE = 'bulk_invite'
    CATEGORY_GROUP_PURCHASE = 'group_purchase'  # Not yet implemented
    CATEGORY_LOYALTY = 'loyalty'
    CATEGORY_ORDER = 'order'
    CATEGORY_PHARMACY_ORDER = 'pharmacy_order'
    CATEGORY_REPAIR = 'repair'
    CATEGORY_RESTAURANT_RESERVATION = 'restaurant_reservation'
    CATEGORY_SANDWICH_BAR = 'sandwich_bar'
    CATEGORY_AGENDA = 'agenda'
    CATEGORY_CUSTOMER_SIGNUP = 'customer_signup'

    ICON_NAMES = {CATEGORY_APPOINTMENT: u'fa-calendar-plus-o',
                  CATEGORY_ASK_QUESTION: u'fa-comments-o',
                  CATEGORY_BULK_INVITE: u'fa-user-plus',
                  CATEGORY_GROUP_PURCHASE: u'fa-shopping-cart',
                  CATEGORY_LOYALTY: u'fa-credit-card',
                  CATEGORY_ORDER: u'fa-shopping-basket',
                  CATEGORY_PHARMACY_ORDER: u'fa-medkit',
                  CATEGORY_REPAIR: u'fa-wrench',
                  CATEGORY_RESTAURANT_RESERVATION: u'fa-cutlery',
                  CATEGORY_SANDWICH_BAR: u'hamburger',
                  CATEGORY_AGENDA: u'fa-book',
                  CATEGORY_CUSTOMER_SIGNUP: u'fa-sign-in'}

    TOPICS = {CATEGORY_APPOINTMENT: u'appointment',
              CATEGORY_ASK_QUESTION: u'ask-question',
              CATEGORY_BULK_INVITE: u'settings-bulk-invite',
              CATEGORY_GROUP_PURCHASE: u'group-purchase',
              CATEGORY_LOYALTY: u'loyalty',
              CATEGORY_ORDER: u'order',
              CATEGORY_PHARMACY_ORDER: u'order',
              CATEGORY_REPAIR: u'repair',
              CATEGORY_RESTAURANT_RESERVATION: u'reserve',
              CATEGORY_SANDWICH_BAR: u'order-sandwich',
              CATEGORY_AGENDA: u'agenda',
              CATEGORY_CUSTOMER_SIGNUP: u'Customer'}

    category = db.StringProperty(indexed=False)  # only filled in on parent message
    category_key = db.StringProperty(indexed=False)  # only filled in on parent message

    sent_by_service = db.BooleanProperty(indexed=False)
    sender = SolutionUserProperty()
    message_key = db.StringProperty(indexed=False)  # Rogerthat mk (for migrated models this can be None)
    parent_message_key = db.StringProperty()  # Rogerthat pmk
    message_key_by_tag = db.TextProperty()  # only filled in on parent message

    timestamp = db.IntegerProperty(indexed=False)
    last_timestamp = db.IntegerProperty(indexed=True)  # only filled in on parent message
    message = db.TextProperty()
    last_message = db.TextProperty()  # only filled in on parent message
    awaiting_first_message = db.BooleanProperty(indexed=False)  # only filled in on parent message

    picture_urls = db.StringListProperty(indexed=False)
    video_urls = db.StringListProperty(indexed=False)

    reply_enabled = db.BooleanProperty(indexed=False)  # only filled in on parent message
    read = db.BooleanProperty(indexed=True)  # only filled in on parent message
    starred = db.BooleanProperty(indexed=True)  # only filled in on parent message
    trashed = db.BooleanProperty(indexed=True)  # only filled in on parent message
    deleted = db.BooleanProperty(indexed=True)  # only filled in on parent message

    child_messages = db.ListProperty(int, indexed=False)  # only filled in on parent message

    # timestamp, only filled in on parent message, only for non-profit associations
    question_asked_timestamp = db.IntegerProperty(default=0)

    @property
    def icon(self):
        if self.category and self.category in SolutionInboxMessage.ICON_NAMES:
            return SolutionInboxMessage.ICON_NAMES[self.category]
        elif self.category:
            logging.error("SolutionInboxMessage icon not found for category '%s' key '%s'", self.category, self.key())
        return None

    def icon_color(self, solution):
        if self.category:
            color = u"#FFFFFF" if solution == u"djmatic" else u"#000000"
            return color
        return None

    @property
    def chat_topic_key(self):
        if self.category and self.category in SolutionInboxMessage.TOPICS:
            return SolutionInboxMessage.TOPICS[self.category]
        elif self.category:
            logging.error("SolutionInboxMessage chat_topic_key not found for category '%s' key '%s'", self.category, self.key())
        return None

    @property
    def id(self):
        return self.key().id()

    @property
    def service_identity_user(self):
        pkey = self.parent_key()
        if pkey.kind() == self.kind():
            return users.User(pkey.parent().name())
        return users.User(pkey.name())

    @property
    def service_user(self):
        return get_service_user_from_service_identity_user(self.service_identity_user)

    @property
    def service_identity(self):
        return get_identity_from_service_identity_user(self.service_identity_user)

    @property
    def solution_inbox_message_key(self):
        return str(self.key())

    def get_child_messages(self):
        if self.child_messages:
            return SolutionInboxMessage.get_by_id(self.child_messages, self)
        return []

    @classmethod
    def get_all_unanswered_questions(cls, days):
        return cls.all().filter('question_asked_timestamp <', now() - days * 86400).filter('question_asked_timestamp >', 0)

    @classmethod
    def get_all_by_service(cls, service_user, service_identity, start_date):
        service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
        ancestor = parent_key_unsafe(service_identity_user, SOLUTION_COMMON)
        return cls.all().ancestor(ancestor) \
            .filter('parent_message_key', None) \
            .filter('deleted =', False) \
            .filter('last_timestamp >', start_date) \
            .order('-last_timestamp')

    @classmethod
    def create_key(cls, msg_id, parent):
        return db.Key.from_path(cls.kind(), msg_id, parent=parent)


class SolutionMessage(db.Model):
    message = db.TextProperty()
    parent_message_key = db.StringProperty(indexed=False)
    sender = SolutionUserProperty()
    timestamp = db.IntegerProperty(indexed=True)
    deleted = db.BooleanProperty(indexed=True, default=False)
    reply = db.TextProperty()
    reply_enabled = db.BooleanProperty(indexed=True, default=True)

    solution_inbox_message_key = db.StringProperty(indexed=False)

    @property
    def service_user(self):
        return users.User(self.parent_key().name())

    @property
    def solution_message_key(self):
        return str(self.key())


class SolutionIdentitySettings(db.Model):
    name = db.StringProperty(indexed=False)
    phone_number = db.StringProperty(indexed=False)
    qualified_identifier = db.StringProperty(indexed=False)
    description = db.TextProperty()
    opening_hours = db.TextProperty()
    address = db.TextProperty()
    location = db.GeoPtProperty(indexed=False)
    search_keywords = db.TextProperty()

    # Inbox
    inbox_forwarders = db.StringListProperty(indexed=False)
    inbox_connector_qrcode = db.StringProperty(indexed=False)
    inbox_mail_forwarders = db.StringListProperty(indexed=False)
    inbox_email_reminders_enabled = db.BooleanProperty(indexed=False)

    # Broadcast create news
    broadcast_create_news_qrcode = db.StringProperty(indexed=False)

    # List of epochs defining the start, end of holidays (start1, end1, start2, end2, ...)
    holidays = db.ListProperty(int)
    holiday_out_of_office_message = db.TextProperty()

    @staticmethod
    def create_key(service_user, service_identity):
        service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
        return db.Key.from_path(SolutionIdentitySettings.kind(), service_identity_user.email(),
                                parent=parent_key_unsafe(service_identity_user, SOLUTION_COMMON))

    @property
    def service_identity_user(self):
        return users.User(self.parent_key().name())

    @property
    def service_user(self):
        return get_service_user_from_service_identity_user(self.service_identity_user)

    @property
    def service_identity(self):
        return get_identity_from_service_identity_user(self.service_identity_user)

    def get_forwarders_by_type(self, forwarder_type):
        if forwarder_type == SolutionSettings.INBOX_FORWARDER_TYPE_MOBILE:
            return self.inbox_forwarders
        elif forwarder_type == SolutionSettings.INBOX_FORWARDER_TYPE_EMAIL:
            return self.inbox_mail_forwarders
        else:
            raise ValueError("Unexpected inbox forwarder type %s" % forwarder_type)

    @property
    def holiday_tuples(self):
        i = 0
        while i < len(self.holidays):
            yield (self.holidays[i], self.holidays[i + 1])
            i += 2

    def is_in_holiday_for_date(self, date):
        for holiday in self.holiday_tuples:
            logging.debug("checking if in holiday %s" % str(holiday))
            if holiday[0] <= date < holiday[1]:
                return True
        return False


class SolutionSettings(SolutionIdentitySettings):
    INBOX_FORWARDER_TYPE_EMAIL = u'email'
    INBOX_FORWARDER_TYPE_MOBILE = u'mobile'

    login = db.UserProperty(indexed=False)
    identities = db.StringListProperty(indexed=False)

    iban = db.StringProperty(indexed=False)
    bic = db.StringProperty(indexed=False)

    search_enabled = db.BooleanProperty(indexed=False, default=False)
    search_enabled_check = db.BooleanProperty(indexed=False, default=True)

    menu_item_color = db.StringProperty(indexed=False)

    currency = db.StringProperty(indexed=False)  # symbol, e.g. €
    solution = db.StringProperty(indexed=False)
    timezone = db.StringProperty(indexed=False, default=u"Europe/Brussels")
    main_language = db.StringProperty(indexed=False)

    updates_pending = db.BooleanProperty(indexed=False, default=False)
    publish_changes_users = db.StringListProperty(indexed=False)
    put_identity_pending = db.BooleanProperty(indexed=True, default=False)
    provisioned_modules = db.StringListProperty()
    modules = db.StringListProperty()
    modules_to_put = db.StringListProperty(default=[])
    modules_to_remove = db.StringListProperty(default=[])

    # Events
    events_visible = db.BooleanProperty(indexed=False, default=True)
    event_notifications_enabled = db.BooleanProperty(indexed=False, default=False)
    default_calendar = db.IntegerProperty(indexed=False)
    uitdatabank_actor_id = db.StringProperty(indexed=True)

    # Broadcast
    broadcast_types = db.StringListProperty(indexed=False)

    broadcast_on_facebook = db.BooleanProperty(indexed=False, default=False)
    broadcast_on_twitter = db.BooleanProperty(indexed=False, default=False)
    broadcast_to_all_locations = db.BooleanProperty(indexed=False, default=False)

    facebook_page = db.StringProperty(indexed=False)
    facebook_name = db.StringProperty(indexed=False)
    facebook_action = db.StringProperty(indexed=False)

    twitter_oauth_token = db.StringProperty(indexed=False)
    twitter_oauth_token_secret = db.StringProperty(indexed=False)
    twitter_username = db.StringProperty(indexed=False)

    # Branding
    events_branding_hash = db.StringProperty(indexed=False)
    loyalty_branding_hash = db.StringProperty(indexed=False)
    
    payment_enabled = db.BooleanProperty()
    payment_optional = db.BooleanProperty()

    service_disabled = db.BooleanProperty(default=False)

    @staticmethod
    def create_key(service_user):
        return db.Key.from_path(SolutionSettings.kind(), service_user.email(),
                                parent=parent_key(service_user, SOLUTION_COMMON))

    @property
    def service_identity_user(self):
        azzert(False, u"service_identity_user should not be called on SolutionSettings")

    @property
    def service_user(self):
        return users.User(self.parent_key().name())

    @property
    def service_identity(self):
        azzert(False, u"service_identity should not be called on SolutionSettings")

    def uses_inbox(self):
        from solutions.common.bizz import SolutionModule
        return any((m in self.modules for m in SolutionModule.INBOX_MODULES))

    def uses_facebook(self):
        from solutions.common.bizz import SolutionModule
        return any((m in self.modules for m in SolutionModule.FACEBOOK_MODULES))

    def uses_twitter(self):
        from solutions.common.bizz import SolutionModule
        return any((m in self.modules for m in SolutionModule.TWITTER_MODULES))

    def can_edit_services(self, customer):
        from solutions.common.bizz import SolutionModule, OrganizationType
        if SolutionModule.CITY_APP not in self.modules:
            return False
        if not customer or customer.country == u"FR" or customer.organization_type != OrganizationType.CITY:
            return False
        return True

    @staticmethod
    def label(module):
        return ' '.join([x.capitalize() for x in module.split('_')])

    @property
    def modules_labels(self):
        return sorted([(k, SolutionSettings.label(k)) for k in self.modules])

    @property
    def tz_info(self):
        return get_timezone(self.timezone)

class SolutionAutoBroadcastTypes(db.Model):
    broadcast_types = db.StringListProperty(indexed=False)

    @property
    def module(self):
        return self.key().name()

    @property
    def solution_settings_key(self):
        return self.parent_key()

    @staticmethod
    def list(sln_settings):
        return SolutionAutoBroadcastTypes.all().ancestor(sln_settings)

    @classmethod
    def create_key(cls, sln_settings_key, module_name):
        return db.Key().from_path(cls.kind(), module_name, parent=sln_settings_key)


class SolutionBrandingSettings(db.Model):
    DEFAULT_DARK_MENU_ITEM_COLOR = u'4D4D4D'
    DEFAULT_LIGHT_MENU_ITEM_COLOR = u'B2B2B2'
    DEFAULT_DARK_BACKGROUND_COLOR = u'141414'
    DEFAULT_LIGHT_BACKGROUND_COLOR = u'EBEBEB'
    DEFAULT_DARK_TEXT_COLOR = u'B2B2B2'
    DEFAULT_LIGHT_TEXT_COLOR = u'4D4D4D'
    color_scheme = db.StringProperty(indexed=False, default='light')
    background_color = db.StringProperty(indexed=False)
    text_color = db.StringProperty(indexed=False)
    menu_item_color = db.StringProperty(indexed=False)
    show_identity_name = db.BooleanProperty(indexed=False, default=True)
    show_avatar = db.BooleanProperty(indexed=False, default=True)
    modification_time = db.IntegerProperty(default=0)

    @classmethod
    def create_key(cls, service_user):
        return db.Key.from_path(cls.kind(), cls.kind(), parent=parent_key(service_user, SOLUTION_COMMON))

    @property
    def service_user(self):
        return users.User(self.parent_key().name())

    @classmethod
    def get_by_user(cls, service_user):
        # Note: DJ-Matic services do no have branding settings.
        return cls.get(cls.create_key(service_user))

    @classmethod
    def default_background_color(cls, color_scheme):
        return cls.DEFAULT_LIGHT_BACKGROUND_COLOR if color_scheme != 'dark' else cls.DEFAULT_DARK_BACKGROUND_COLOR

    @classmethod
    def default_text_color(cls, color_scheme):
        return cls.DEFAULT_LIGHT_TEXT_COLOR if color_scheme != 'dark' else cls.DEFAULT_DARK_TEXT_COLOR

    @classmethod
    def default_menu_item_color(cls, color_scheme):
        return cls.DEFAULT_LIGHT_MENU_ITEM_COLOR if color_scheme != 'dark' else cls.DEFAULT_DARK_MENU_ITEM_COLOR


class SolutionMainBranding(db.Model):
    # key_name = user email
    blob = db.BlobProperty(indexed=False)

    # Do not set branding_key to None to force a system.store_branding, but set branding_creation_time to 0
    branding_key = db.StringProperty(indexed=False)  # Rogerthat branding key
    branding_creation_time = db.IntegerProperty(default=0)

    @property
    def service_user(self):
        return users.User(self.key().name())

    @staticmethod
    def create_key(service_user):
        return db.Key.from_path(SolutionMainBranding.kind(), service_user.email())


class BaseSolutionImage(db.Model):
    picture = db.BlobProperty()
    is_default = db.BooleanProperty(indexed=False, default=False)

    @property
    def service_user(self):
        return users.User(self.key().name())

    @classmethod
    def create_key(cls, service_user):
        return db.Key.from_path(cls.kind(), service_user.email())


class SolutionLogo(BaseSolutionImage):
    pass


class SolutionAvatar(BaseSolutionImage):
    published = db.BooleanProperty(indexed=False)



class RestaurantMenu(db.Model):
    categories = MenuCategoriesProperty()
    predescription = db.TextProperty()
    postdescription = db.TextProperty()
    name = db.StringProperty(indexed=False)
    is_default = db.BooleanProperty(indexed=False, default=False)

    @property
    def service_user(self):
        return users.User(self.parent_key().name())

    @staticmethod
    def create_key(service_user, solution):
        return db.Key.from_path(RestaurantMenu.kind(), 'menu', parent=parent_key(service_user, solution))


class RestaurantInvite(db.Model):
    STATUS_INVITED = 1
    STATUS_ACCEPTED = 2
    STATUS_REJECTED = 3

    epoch = db.FloatProperty(indexed=True)
    status = db.IntegerProperty(required=True, default=STATUS_INVITED)

    @property
    def service_user(self):
        return users.User(self.parent_key().name())

    @property
    def invitee(self):
        return self.key().name()

    @staticmethod
    @returns(db.Key)
    @arguments(service_user=users.User, service_identity=unicode, invitee=unicode, solution=unicode)
    def create_key(service_user, service_identity, invitee, solution):
        service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
        return db.Key.from_path(RestaurantInvite.kind(), invitee, parent=parent_key_unsafe(service_identity_user, solution))


class SolutionQR(db.Model):
    description = db.StringProperty(indexed=False)
    image_url = db.StringProperty(indexed=False)

    @property
    def name(self):
        return self.key().name()

    @property
    def service_identity_user(self):
        return users.User(self.parent_key().name())

    @property
    def service_user(self):
        return get_service_user_from_service_identity_user(self.service_identity_user)

    @property
    def service_identity(self):
        return get_identity_from_service_identity_user(self.service_identity_user)

    @classmethod
    def create_key(cls, name, service_user, service_identity, solution):
        service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
        return db.Key.from_path(cls.kind(), name, parent=parent_key_unsafe(service_identity_user, solution))

    @classmethod
    def get_by_name(cls, name, service_user, service_identity, solution):
        return cls.get(cls.create_key(name, service_user, service_identity, solution))

    @classmethod
    def list_by_user(cls, service_user, service_identity, solution):
        service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
        return cls.all().ancestor(parent_key_unsafe(service_identity_user, solution))


class SolutionScheduledBroadcast(db.Model):
    timestamp = db.IntegerProperty()
    broadcast_epoch = db.IntegerProperty()

    broadcast_type = db.StringProperty(indexed=False)
    message = db.TextProperty()
    target_audience_enabled = db.BooleanProperty(indexed=False)
    target_audience_min_age = db.IntegerProperty(indexed=False)
    target_audience_max_age = db.IntegerProperty(indexed=False)
    target_audience_gender = db.StringProperty(indexed=False)
    json_attachments = db.TextProperty()
    json_urls = db.TextProperty()

    broadcast_on_twitter = db.BooleanProperty(indexed=False, default=False)
    broadcast_on_facebook = db.BooleanProperty(indexed=False, default=False)
    facebook_access_token = db.StringProperty(indexed=False)
    service_identity = db.StringProperty(indexed=False)  # Service who created the broadcast
    broadcast_to_all_locations = db.BooleanProperty(indexed=False, default=False)
    statistics_keys = db.StringListProperty(indexed=False)  # Link to BroadcastStatistic
    identities = db.StringListProperty(indexed=False)

    deleted = db.BooleanProperty(default=False)

    news_id = db.IntegerProperty(indexed=False)
    scheduled_task_name = db.StringProperty(indexed=False)

    @property
    def key_str(self):
        return str(self.key())

    @property
    def service_user(self):
        return users.User(self.parent_key().name())

    @property
    def attachments(self):
        return parse_complex_value(AttachmentTO, json.loads(self.json_attachments), True)

    @property
    def urls(self):
        from solutions.common.to import UrlTO
        return parse_complex_value(UrlTO, json.loads(self.json_urls), True)

    @classmethod
    def get_keys_last_month(cls):
        return db.Query(cls, keys_only=True) \
            .filter('broadcast_epoch <', now()) \
            .filter('broadcast_epoch >', now() - 2592000)

    @classmethod
    def create_key(cls, news_id, service_user, solution):
        parent = parent_key(service_user, solution)
        return db.Key.from_path(cls.kind(), news_id, parent=parent)


class SolutionNewsPublisher(db.Model):

    timestamp = db.IntegerProperty(indexed=False)
    app_user = db.UserProperty(indexed=True)

    @staticmethod
    def createKey(app_user, service_user, solution):
        return db.Key.from_path(SolutionNewsPublisher.kind(),
                                app_user.email(),
                                parent=parent_key(service_user, solution))


class SolutionEmailSettings(CachedModelMixIn, db.Model):
    visible_in_inbox = db.ListProperty(users.User, indexed=False)

    def invalidateCache(self):
        from solutions.common.dal import get_solution_email_settings
        logging.info("SolutionEmailSettings removed from cache.")
        invalidate_cache(get_solution_email_settings)


@deserializer
def ds_solution_email_settings(stream):
    return ds_model(stream, SolutionEmailSettings)


@serializer
def s_solution_email_settings(stream, app):
    s_model(stream, app, SolutionEmailSettings)


register(SolutionEmailSettings, s_solution_email_settings, ds_solution_email_settings)


class FileBlob(db.Model):
    content = db.BlobProperty()
    service_user_email = db.StringProperty()


class SolutionNewsScraperSettings(db.Model):

    urls = db.StringListProperty(indexed=False)

    @staticmethod
    def create_key(service_user):
        return db.Key.from_path(SolutionNewsScraperSettings.kind(), service_user.email(),
                                parent=parent_key(service_user, SOLUTION_COMMON))

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
from collections import defaultdict
import datetime
import logging
import os
from types import NoneType

from google.appengine.ext import db, deferred

from babel.dates import format_date
from babel.numbers import format_currency
from mcfw.consts import MISSING
from mcfw.properties import azzert, get_members
from mcfw.restapi import rest, GenericRESTRequestHandler
from mcfw.rpc import returns, arguments, serialize_complex_value
from rogerthat.bizz.rtemail import EMAIL_REGEX
from rogerthat.bizz.service import AvatarImageNotSquareException, InvalidValueException
from rogerthat.dal import parent_key, put_and_invalidate_cache, parent_key_unsafe, put_in_chunks
from rogerthat.dal.profile import get_user_profile, get_service_or_user_profile, get_profile_key
from rogerthat.models import ServiceIdentity
from rogerthat.rpc import users
from rogerthat.rpc.service import BusinessException
from rogerthat.service.api import system
from rogerthat.service.api.friends import get_broadcast_reach
from rogerthat.service.api.system import get_flow_statistics, list_roles
from rogerthat.to import ReturnStatusTO, RETURNSTATUS_TO_SUCCESS
from rogerthat.to.friends import FriendListResultTO, SubscribedBroadcastReachTO, ServiceMenuDetailTO
from rogerthat.to.messaging import AttachmentTO, BaseMemberTO, BroadcastTargetAudienceTO
from rogerthat.to.service import UserDetailsTO
from rogerthat.to.statistics import FlowStatisticsTO
from rogerthat.translations import DEFAULT_LANGUAGE
from rogerthat.utils.app import get_human_user_from_app_user, sanitize_app_user, \
    get_app_id_from_app_user
from rogerthat.utils.channel import send_message
from rogerthat.utils.service import create_service_identity_user, remove_slash_default
from shop.business.order import get_subscription_order_remaining_length
from shop.dal import get_customer, get_customer_signups
from shop.exceptions import InvalidEmailFormatException
from shop.models import Product, Order
from shop.to import ProductTO
from shop.view import get_current_http_host
from solution_server_settings import get_solution_server_settings
from solutions import translate as common_translate
from solutions.common import SOLUTION_COMMON
from solutions.common.bizz import get_next_free_spots_in_service_menu, common_provision, timezone_offset, \
    broadcast_updates_pending, SolutionModule, save_broadcast_types_order, delete_file_blob, create_file_blob, \
    OrganizationType, create_news_publisher, delete_news_publisher, enable_or_disable_solution_module, \
    twitter as bizz_twitter, get_user_defined_roles, get_translated_broadcast_types
from solutions.common.bizz.branding_settings import save_branding_settings
from solutions.common.bizz.events import update_events_from_google, get_google_authenticate_url, get_google_calendars, \
    create_calendar_admin, delete_calendar_admin
from solutions.common.bizz.facebook import get_facebook_app_info
from solutions.common.bizz.group_purchase import save_group_purchase, delete_group_purchase, broadcast_group_purchase, \
    new_group_purchase_subscription
from solutions.common.bizz.inbox import send_statistics_export_email
from solutions.common.bizz.loyalty import update_user_data_admins
from solutions.common.bizz.menu import _put_default_menu, get_menu_item_qr_url, menu_is_visible
from solutions.common.bizz.messaging import validate_broadcast_url, send_reply, delete_all_trash
from solutions.common.bizz.provisioning import create_calendar_admin_qr_code
from solutions.common.bizz.repair import send_message_for_repair_order, delete_repair_order
from solutions.common.bizz.sandwich import ready_sandwich_order, delete_sandwich_order, reply_sandwich_order
from solutions.common.bizz.service import set_customer_signup_status
from solutions.common.bizz.settings import save_settings, set_logo, set_avatar
from solutions.common.bizz.static_content import put_static_content as bizz_put_static_content, delete_static_content
from solutions.common.dal import get_solution_settings, get_static_content_list, get_solution_group_purchase_settings, \
    get_solution_main_branding, get_event_by_id, get_solution_calendars, get_solution_scheduled_broadcasts, \
    get_solution_inbox_messages, get_solution_identity_settings, get_solution_settings_or_identity_settings, \
    get_admins_of_solution_calendars, get_solution_news_publishers, get_user_from_key
from solutions.common.dal.appointment import get_solution_appointment_settings
from solutions.common.dal.repair import get_solution_repair_orders, get_solution_repair_settings
from solutions.common.models import SolutionBrandingSettings, SolutionAutoBroadcastTypes, \
    SolutionSettings, SolutionInboxMessage, SolutionLogo, SolutionAvatar, RestaurantMenu
from solutions.common.models.agenda import SolutionCalendar
from solutions.common.models.appointment import SolutionAppointmentWeekdayTimeframe, SolutionAppointmentSettings
from solutions.common.models.group_purchase import SolutionGroupPurchase
from solutions.common.models.repair import SolutionRepairSettings
from solutions.common.models.sandwich import SandwichType, SandwichTopping, SandwichOption, SandwichSettings, \
    SandwichOrder
from solutions.common.models.static_content import SolutionStaticContent
from solutions.common.to import ServiceMenuFreeSpotsTO, SolutionStaticContentTO, SolutionSettingsTO, \
    MenuTO, EventItemTO, PublicEventItemTO, SolutionAppointmentWeekdayTimeframeTO, BrandingSettingsTO, \
    SolutionRepairOrderTO, SandwichSettingsTO, SandwichOrderTO, SolutionGroupPurchaseTO, \
    SolutionGroupPurchaseSettingsTO, SolutionCalendarTO, EventGuestTO, SolutionInboxForwarder, UrlTO, \
    TimestampTO, SolutionScheduledBroadcastTO, SolutionInboxesTO, SolutionInboxMessageTO, SolutionAppointmentSettingsTO, \
    SolutionRepairSettingsTO, UrlReturnStatusTO, ImageReturnStatusTO, SolutionUserKeyLabelTO, \
    SolutionCalendarWebTO, BrandingSettingsAndMenuItemsTO, ServiceMenuItemWithCoordinatesTO, \
    ServiceMenuItemWithCoordinatesListTO, SolutionGoogleCalendarStatusTO, PictureReturnStatusTO, SaveSettingsResultTO, \
    SaveSettingsReturnStatusTO, AppUserRolesTO, CustomerSignupTO
from solutions.common.to.broadcast import BroadcastOptionsTO, SubscriptionInfoTO
from solutions.common.to.statistics import StatisticsResultTO
from solutions.common.utils import is_default_service_identity, create_service_identity_user_wo_default
from solutions.flex import SOLUTION_FLEX


@rest("/solutions/common/public/menu/load", "get", authenticated=False)
@returns(dict)
@arguments(service_user_email=unicode)
def public_load_menu(service_user_email):
    from solutions.common.dal import get_restaurant_menu

    if service_user_email in (None, MISSING):
        logging.debug("Could not load public menu (service_user_email None|MISSING)")
        return None

    service_user = users.User(service_user_email)
    sln_settings = get_solution_settings(service_user)
    if not sln_settings:
        logging.debug("Could not load public menu for: %s (SolutionSettings==None)", service_user_email)
        return None

    menu = get_restaurant_menu(service_user, sln_settings.solution)
    if not menu:
        logging.debug("Could not load public menu for: %s (Menu==None)", service_user_email)
        return None

    menu = serialize_complex_value(MenuTO.fromMenuObject(menu), MenuTO, False)
    # convert prices from long to unicode
    for category in menu['categories']:
        for item in category['items']:
            item['price'] = format_currency((item['price'] or 0) / 100.0, sln_settings.currency, '#,##0.00',
                                            locale=sln_settings.main_language)
    return menu


@rest("/solutions/common/public/events/load", "get", authenticated=False)
@returns([PublicEventItemTO])
@arguments(service_user_email=unicode)
def public_load_events(service_user_email):
    from solutions.common.dal import get_public_event_list
    from rogerthat.models import ServiceProfile

    if service_user_email and service_user_email != MISSING:
        service_user = users.User(service_user_email)
        sp_up = get_service_or_user_profile(service_user)
        if sp_up and isinstance(sp_up, ServiceProfile):
            if sp_up.solution:
                return map(PublicEventItemTO.fromPublicEventItemObject,
                           get_public_event_list(service_user, sp_up.solution))
            else:
                logging.debug("Could not load public events for: %s (ServiceProfile.solution None)", service_user_email)
        else:
            logging.debug("Could not load public events for: %s (ServiceProfile None)", service_user_email)
    else:
        logging.debug("Could not load public events (service_user_email None|MISSING)")
    return None


@rest("/solutions/common/public/events/picture", "get", authenticated=False, silent_result=True)
@returns(PictureReturnStatusTO)
@arguments(service_user_email=unicode, event_id=long, picture_version=long)
def public_event_picture(service_user_email, event_id, picture_version=0):
    service_user = users.User(service_user_email)
    sln_settings = get_solution_settings(service_user)
    event = get_event_by_id(service_user, sln_settings.solution, event_id)
    if not event or not event.picture:
        return PictureReturnStatusTO.create(False, None)

    response = GenericRESTRequestHandler.getCurrentResponse()
    response.headers['Cache-Control'] = "public, max-age=31536000"  # Cache forever (1 year)
    response.headers['Access-Control-Allow-Origin'] = '*'
    return PictureReturnStatusTO.create(picture=unicode(event.picture))


@rest("/solutions/common/public/group_purchase/picture", "get", authenticated=False, silent_result=True)
@returns(PictureReturnStatusTO)
@arguments(service_user_email=unicode, group_purchase_id=long, picture_version=long, service_identity=unicode)
def public_group_purchase_picture(service_user_email, group_purchase_id, picture_version=0, service_identity=None):
    service_user = users.User(service_user_email)
    settings = get_solution_settings(service_user)
    service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
    sgp = SolutionGroupPurchase.get_by_id(group_purchase_id,
                                          parent_key_unsafe(service_identity_user, settings.solution))
    if not sgp or not sgp.picture:
        return PictureReturnStatusTO.create(False, None)

    response = GenericRESTRequestHandler.getCurrentResponse()
    response.headers['Cache-Control'] = "public, max-age=31536000"  # Cache forever (1 year)
    response.headers['Access-Control-Allow-Origin'] = '*'
    return PictureReturnStatusTO.create(picture=unicode(sgp.picture))


@rest("/common/service_menu/get_free_spots", "get", read_only_access=True)
@returns(ServiceMenuFreeSpotsTO)
@arguments(count=int)
def get_free_spots(count=10):
    service_user = users.get_current_user()
    sm = system.get_menu()
    all_taken_coords = [item.coords for item in sm.items]
    static_content_items = SolutionStaticContent.list_changed(service_user)
    for sc in static_content_items:
        if sc.deleted or not sc.visible:
            try:
                all_taken_coords.remove(sc.coords)
            except ValueError:
                pass
        else:  # not deleted and visible
            all_taken_coords.append(sc.coords)
    spots = get_next_free_spots_in_service_menu(all_taken_coords, count)
    return ServiceMenuFreeSpotsTO.fromList(spots)


@rest("/common/static_content/load", "get", read_only_access=True, silent_result=True)
@returns([SolutionStaticContentTO])
@arguments()
def get_static_content():
    service_user = users.get_current_user()
    return [SolutionStaticContentTO.fromModel(sc) for sc in get_static_content_list(service_user)]


@rest("/common/static_content/put", "post")
@returns(ReturnStatusTO)
@arguments(static_content=SolutionStaticContentTO)
def put_static_content(static_content):
    service_user = users.get_current_user()
    try:
        bizz_put_static_content(service_user, static_content)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/static_content/delete", "post")
@returns(ReturnStatusTO)
@arguments(static_content_id=(int, long, NoneType))
def rest_delete_static_content(static_content_id=None):
    service_user = users.get_current_user()
    try:
        delete_static_content(service_user, static_content_id)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/inbox/load/all", "get", read_only_access=True)
@returns([SolutionInboxesTO])
@arguments()
def inbox_load_all():
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    sln_settings = get_solution_settings(service_user)
    sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)

    unread_cursor, unread_messages, unread_has_more = get_solution_inbox_messages(service_user,
                                                                                  service_identity,
                                                                                  10,
                                                                                  SolutionInboxMessage.INBOX_NAME_UNREAD)
    starred_cursor, starred_messages, starred_has_more = get_solution_inbox_messages(service_user,
                                                                                     service_identity,
                                                                                     10,
                                                                                     SolutionInboxMessage.INBOX_NAME_STARRED)
    read_cursor, read_messages, read_has_more = get_solution_inbox_messages(service_user,
                                                                            service_identity,
                                                                            10,
                                                                            SolutionInboxMessage.INBOX_NAME_READ)
    trash_cursor, trash_messages, trash_has_more = get_solution_inbox_messages(service_user,
                                                                               service_identity,
                                                                               10,
                                                                               SolutionInboxMessage.INBOX_NAME_TRASH)

    inboxes = [(SolutionInboxMessage.INBOX_NAME_UNREAD, unread_cursor, unread_messages, unread_has_more),
               (SolutionInboxMessage.INBOX_NAME_STARRED, starred_cursor, starred_messages, starred_has_more),
               (SolutionInboxMessage.INBOX_NAME_READ, read_cursor, read_messages, read_has_more),
               (SolutionInboxMessage.INBOX_NAME_TRASH, trash_cursor, trash_messages, trash_has_more)]

    return [SolutionInboxesTO.fromModel(name, cursor, messages, has_more, sln_settings, sln_i_settings, True) for
            name, cursor, messages, has_more in inboxes]


@rest("/common/inbox/load/more", "get", read_only_access=True)
@returns(SolutionInboxesTO)
@arguments(name=unicode, count=(int, long), cursor=unicode)
def inbox_load_more(name, count, cursor):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    sln_settings = get_solution_settings(service_user)
    sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
    cursor_, messages, has_more = get_solution_inbox_messages(service_user, service_identity, count, name, cursor)
    return SolutionInboxesTO.fromModel(name, cursor_, messages, has_more, sln_settings, sln_i_settings, True)


@rest("/common/inbox/load/detail", "get", read_only_access=True)
@returns([SolutionInboxMessageTO])
@arguments(key=unicode)
def inbox_load_detail(key):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    sln_settings = get_solution_settings(service_user)
    sim = SolutionInboxMessage.get(key)
    messages = [sim]
    messages.extend(sim.get_child_messages())
    sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
    return [SolutionInboxMessageTO.fromModel(message, sln_settings, sln_i_settings, False) for message in messages]


@rest("/common/inbox/message/update/reply", "post")
@returns(ReturnStatusTO)
@arguments(key=unicode, message=unicode)
def inbox_message_update_reply(key, message):
    service_user = users.get_current_user()
    try:
        send_reply(service_user, key, message)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/inbox/message/update/starred", "post")
@returns(ReturnStatusTO)
@arguments(key=unicode, starred=bool)
def inbox_message_update_starred(key, starred):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    sln_settings = get_solution_settings(service_user)
    sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
    try:
        sim = SolutionInboxMessage.get(key)
        sim.starred = starred
        sim.put()
        send_message(service_user, u"solutions.common.messaging.update",
                     service_identity=service_identity,
                     message=serialize_complex_value(
                         SolutionInboxMessageTO.fromModel(sim, sln_settings, sln_i_settings, True),
                         SolutionInboxMessageTO, False))
        deferred.defer(update_user_data_admins, service_user, service_identity)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/inbox/message/update/read", "post")
@returns(ReturnStatusTO)
@arguments(key=unicode, read=bool)
def inbox_message_update_read(key, read):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    sln_settings = get_solution_settings(service_user)
    sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
    try:
        sim = SolutionInboxMessage.get(key)
        sim.read = read
        sim.put()
        send_message(service_user, u"solutions.common.messaging.update",
                     service_identity=service_identity,
                     message=serialize_complex_value(
                         SolutionInboxMessageTO.fromModel(sim, sln_settings, sln_i_settings, True),
                         SolutionInboxMessageTO, False))
        deferred.defer(update_user_data_admins, service_user, service_identity)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/inbox/message/update/trashed", "post")
@returns(ReturnStatusTO)
@arguments(key=unicode, trashed=bool)
def inbox_message_update_trashed(key, trashed):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    sln_settings = get_solution_settings(service_user)
    sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
    try:
        sim = SolutionInboxMessage.get(key)
        if trashed and sim.trashed:
            sim.deleted = True
        sim.trashed = trashed
        sim.put()
        send_message(service_user, u"solutions.common.messaging.update",
                     service_identity=service_identity,
                     message=serialize_complex_value(
                         SolutionInboxMessageTO.fromModel(sim, sln_settings, sln_i_settings, True),
                         SolutionInboxMessageTO, False))
        if not sim.deleted:
            deferred.defer(update_user_data_admins, service_user, service_identity)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/inbox/message/update/deleted", "post")
@returns(ReturnStatusTO)
@arguments()
def inbox_message_update_deleted():
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    try:
        delete_all_trash(service_user, service_identity)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/inbox/messages/export", "get")
@returns(ReturnStatusTO)
@arguments(email=unicode)
def export_inbox_messages(email=''):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    sln_settings = get_solution_settings(service_user)
    try:
        send_statistics_export_email(service_user, service_identity, email, sln_settings)
        return RETURNSTATUS_TO_SUCCESS
    except InvalidEmailFormatException, ex:
        error_msg = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'invalid_email_format',
                                     email=ex.email)
        return ReturnStatusTO.create(False, error_msg)


@rest("/common/broadcast/options", "get", read_only_access=True)
@returns(BroadcastOptionsTO)
@arguments()
def rest_get_broadcast_options():
    service_user = users.get_current_user()
    sln_settings_key = SolutionSettings.create_key(service_user)
    news_promotion_product_key = Product.create_key(Product.PRODUCT_NEWS_PROMOTION)
    extra_city_product_key = Product.create_key(Product.PRODUCT_EXTRA_CITY)
    to_get = (sln_settings_key, news_promotion_product_key, extra_city_product_key)
    sln_settings, news_promotion_product, extra_city_product = db.get(to_get)

    def transl(key):
        try:
            return common_translate(sln_settings.main_language, SOLUTION_COMMON, key, suppress_warning=True)
        except:
            return key

    editable_broadcast_types = map(transl, sln_settings.broadcast_types)

    abt_agenda = SolutionAutoBroadcastTypes.get_by_key_name(SolutionModule.AGENDA, parent=sln_settings)
    broadcast_types = list(editable_broadcast_types)
    if abt_agenda:
        broadcast_types.extend(abt_agenda.broadcast_types)
    news_promotion_product_to = ProductTO.create(news_promotion_product, sln_settings.main_language)
    extra_city_product_to = ProductTO.create(extra_city_product, sln_settings.main_language)
    news_enabled = sln_settings.solution == SOLUTION_FLEX
    customer = get_customer(service_user)
    remaining_length = 0
    sub_order = None
    can_order_extra_apps = True
    has_signed_order = False
    if customer and customer.organization_type != OrganizationType.CITY:
        if customer.subscription_cancel_pending_date != 0 and customer.subscription_order_number:
            can_order_extra_apps = False
            has_signed_order = False
        else:
            remaining_length, sub_order = get_subscription_order_remaining_length(customer.id,
                                                                                  customer.subscription_order_number)
            has_signed_order = sub_order.status == Order.STATUS_SIGNED if sub_order else False
            if has_signed_order:
                can_order_extra_apps = False
    else:
        can_order_extra_apps = False

    subscription_order_charge_date = None
    if has_signed_order:
        subscription_order_charge_date = format_date(datetime.datetime.utcfromtimestamp(sub_order.next_charge_date),
                                                     locale=sln_settings.main_language)
    subscription_info = SubscriptionInfoTO(subscription_order_charge_date, remaining_length, has_signed_order)
    roles = get_user_defined_roles()
    return BroadcastOptionsTO(broadcast_types, editable_broadcast_types, news_promotion_product_to,
                              extra_city_product_to, news_enabled, subscription_info, can_order_extra_apps,
                              roles)


@rest("/common/broadcast/scheduled/load", "get", read_only_access=True)
@returns([SolutionScheduledBroadcastTO])
@arguments()
def load_scheduled_broadcasts():
    service_user = users.get_current_user()
    return [SolutionScheduledBroadcastTO.fromModel(ssb) for ssb in get_solution_scheduled_broadcasts(service_user)]


@rest("/common/broadcast/scheduled/delete", "post")
@returns(ReturnStatusTO)
@arguments(key=unicode)
def delete_scheduled_broadcast(key):
    service_user = users.get_current_user()
    from solutions.common.bizz.messaging import delete_scheduled_broadcast as delete_scheduled_broadcast_bizz
    try:
        delete_scheduled_broadcast_bizz(service_user, key)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/broadcast", "post")
@returns(ReturnStatusTO)
@arguments(broadcast_type=unicode, message=unicode, broadcast_on_facebook=bool, target_audience_enabled=bool,
           target_audience_min_age=int, target_audience_max_age=int, target_audience_gender=unicode,
           msg_attachments=[AttachmentTO], msg_urls=[UrlTO], broadcast_date=TimestampTO, broadcast_on_twitter=bool,
           broadcast_to_all_locations=bool)
def broadcast_send(broadcast_type, message, broadcast_on_facebook, target_audience_enabled=False,
                   target_audience_min_age=0, target_audience_max_age=0, target_audience_gender="MALE_OR_FEMALE",
                   msg_attachments=None, msg_urls=None, broadcast_date=None, broadcast_on_twitter=False,
                   broadcast_to_all_locations=False):
    from solutions.common.bizz.messaging import broadcast_send as broadcast_send_bizz
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    return broadcast_send_bizz(service_user, service_identity, broadcast_type, message, broadcast_on_facebook,
                               broadcast_on_twitter, target_audience_enabled, target_audience_min_age,
                               target_audience_max_age, target_audience_gender, msg_attachments, msg_urls,
                               broadcast_date, broadcast_to_all_locations)


@rest("/common/broadcast/validate/url", "post")
@returns(UrlReturnStatusTO)
@arguments(url=unicode, allow_empty=bool)
def broadcast_validate_url(url, allow_empty=False):
    try:
        service_user = users.get_current_user()
        sln_settings = get_solution_settings(service_user)
        url = url.strip()
        if url or not allow_empty:
            if not (url.startswith("http://") or url.startswith("https://")):
                url = "http://%s" % url
            validate_broadcast_url(url, sln_settings.main_language)
        return UrlReturnStatusTO.create(True, None, url)
    except BusinessException, e:
        return UrlReturnStatusTO.create(False, e.message, url)


@rest("/common/settings/save", "post")
@returns(SaveSettingsReturnStatusTO)
@arguments(name=unicode, description=unicode, opening_hours=unicode, address=unicode, phone_number=unicode,
           facebook_page=unicode, facebook_name=unicode, facebook_action=unicode, currency=unicode, search_enabled=bool,
           search_keywords=unicode, timezone=unicode, events_visible=bool, email_address=unicode,
           inbox_email_reminders=bool, iban=unicode, bic=unicode, search_enabled_check=bool)
def settings_save(name, description=None, opening_hours=None, address=None, phone_number=None, facebook_page=None,
                  facebook_name=None, facebook_action=None, currency=None, search_enabled=True, search_keywords=None,
                  timezone=None, events_visible=None, email_address=None, inbox_email_reminders=None, iban=None,
                  bic=None, search_enabled_check=False):
    try:
        service_user = users.get_current_user()
        session_ = users.get_current_session()
        service_identity = session_.service_identity
        address_geocoded = save_settings(service_user, service_identity, name, description, opening_hours, address,
                                         phone_number, facebook_page, facebook_name, facebook_action, currency,
                                         search_enabled, search_keywords, timezone, events_visible, email_address,
                                         inbox_email_reminders, iban, bic, search_enabled_check)

        r = SaveSettingsResultTO()
        r.address_geocoded = address_geocoded
        return SaveSettingsReturnStatusTO.create(True, None, r)
    except BusinessException, e:
        return SaveSettingsReturnStatusTO.create(False, e.message, None)


@rest("/common/settings/load", "get", read_only_access=True)
@returns(SolutionSettingsTO)
@arguments()
def settings_load():
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    sln_settings = get_solution_settings(service_user)
    sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
    to = SolutionSettingsTO.fromModel(sln_settings, sln_i_settings)
    return to


@rest("/common/settings/defaults/all", "get")
@returns([unicode])
@arguments()
def get_all_defaults():
    """Get all settings that are set to the default. (e.g. menu, logo...etc)"""
    service_user = users.get_current_user()
    sln_settings, logo, avatar = db.get([SolutionSettings.create_key(service_user),
                                         SolutionLogo.create_key(service_user),
                                         SolutionAvatar.create_key(service_user)])
    defaults = []

    if not sln_settings.broadcast_types:
        defaults.append(u'broadcast_types')

    if not logo or logo.is_default:
        defaults.append(u'Logo')

    if not avatar or avatar.is_default:
        defaults.append(u'Avatar')

    if menu_is_visible(sln_settings):
        menu = db.get(RestaurantMenu.create_key(service_user, sln_settings.solution))
        if not menu or menu.is_default:
            defaults.append(u'menu')

    return defaults


@rest("/common/settings/publish_changes", "post")
@returns(ReturnStatusTO)
@arguments(friends=[BaseMemberTO])
def settings_publish_changes(friends=None):
    service_user = users.get_current_user()
    try:
        common_provision(service_user, friends=friends)
        return RETURNSTATUS_TO_SUCCESS
    except InvalidValueException as e:
        reason = e.fields.get('reason')
        property_ = e.fields.get('property')
        logging.warning("Invalid value for property %s: %s", property_, reason, exc_info=1)
        return ReturnStatusTO.create(False, reason or e.message)
    except AvatarImageNotSquareException:
        sln_settings = get_solution_settings(service_user)
        message = common_translate(sln_settings.main_language, SOLUTION_COMMON,
                                   'please_select_valid_avatar_image')
        return ReturnStatusTO.create(False, message)
    except BusinessException as e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/settings/publish_changes/users", "post")
@returns()
@arguments(user_keys=[unicode])
def settings_save_publish_changes_users(user_keys):
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    sln_settings.publish_changes_users = user_keys
    sln_settings.put()


@rest('/common/settings/logo', 'post')
@returns(unicode)
@arguments(image=unicode)
def rest_update_logo(image):
    return set_logo(users.get_current_user(), image)


@rest('/common/settings/avatar', 'post')
@returns(unicode)
@arguments(image=unicode)
def rest_update_avatar(image):
    return set_avatar(users.get_current_user(), image)


@rest("/common/settings/events/notifications/save", "post")
@returns(ReturnStatusTO)
@arguments(notifications_enabled=bool)
def agenda_set_event_notifications(notifications_enabled):
    try:
        sln_settings = get_solution_settings(users.get_current_user())
        logging.debug(notifications_enabled)
        sln_settings.event_notifications_enabled = notifications_enabled
        sln_settings.put()
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException as e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/menu/save", "post")
@returns(ReturnStatusTO)
@arguments(menu=MenuTO)
def menu_save(menu):
    from solutions.common.bizz.menu import save_menu
    try:
        service_user = users.get_current_user()
        save_menu(service_user, menu)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/menu/import", "post", silent=True)
@returns(ReturnStatusTO)
@arguments(file_contents=str)
def menu_import(file_contents):
    """" import menu from excel files """
    from solutions.common.bizz.menu import import_menu_from_excel
    try:
        service_user = users.get_current_user()
        import_menu_from_excel(service_user, file_contents)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/menu/save_name", "post")
@returns(ReturnStatusTO)
@arguments(name=unicode)
def menu_save_name(name):
    from solutions.common.bizz.menu import save_menu_name
    try:
        service_user = users.get_current_user()
        save_menu_name(service_user, name)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/menu/load", "get", read_only_access=True)
@returns(MenuTO)
@arguments()
def load_menu():
    from solutions.common.dal import get_restaurant_menu
    service_user = users.get_current_user()
    menu = get_restaurant_menu(service_user)
    if not menu:
        logging.info('Setting menu')
        menu = _put_default_menu(service_user)
    return MenuTO.fromMenuObject(menu)


@rest("/common/bulkinvite", "post")
@returns(ReturnStatusTO)
@arguments(emails=[unicode], invitation_message=unicode)
def bulk_invite(emails, invitation_message):
    from solutions.common.bizz.bulk_invite import bulk_invite
    try:
        service_user = users.get_current_user()
        session_ = users.get_current_session()
        service_identity = session_.service_identity
        bulk_invite(service_user, service_identity, emails, invitation_message)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/calendar/delete", "post")
@returns(ReturnStatusTO)
@arguments(calendar_id=(int, long))
def delete_calendar(calendar_id):
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    try:
        sc = SolutionCalendar.get_by_id(calendar_id, parent_key(service_user, sln_settings.solution))
        if sc.events.count() > 0:
            raise BusinessException(common_translate(sln_settings.main_language, SOLUTION_COMMON,
                                                     'calendar-remove-failed-has-events'))

        sc.deleted = True
        sln_settings.updates_pending = True
        put_and_invalidate_cache(sc, sln_settings)
        broadcast_updates_pending(sln_settings)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/calendar/save", "post")
@returns(ReturnStatusTO)
@arguments(calendar=SolutionCalendarTO)
def save_calendar(calendar):
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    try:
        if calendar.id:
            sc = SolutionCalendar.get_by_id(calendar.id, parent_key(service_user, sln_settings.solution))
        else:
            sc = SolutionCalendar(parent=parent_key(service_user, sln_settings.solution), deleted=False)

        for c in get_solution_calendars(service_user, sln_settings.solution):

            if c.name.lower() == calendar.name.lower():
                if calendar.id != c.calendar_id:
                    raise BusinessException(common_translate(sln_settings.main_language, SOLUTION_COMMON,
                                                             'calendar-name-already-exists', name=calendar.name))

        sc.name = calendar.name
        sc.broadcast_enabled = calendar.broadcast_enabled

        sln_settings.updates_pending = True
        put_and_invalidate_cache(sc, sln_settings)
        if not sc.connector_qrcode:
            main_branding = get_solution_main_branding(service_user)
            qr_code = create_calendar_admin_qr_code(sc, main_branding.branding_key, sln_settings.main_language)
            sc.connector_qrcode = qr_code.image_uri
            sc.put()
        broadcast_updates_pending(sln_settings)

        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/calendar/load", "get", silent_result=True, read_only_access=True)
@returns([SolutionCalendarWebTO])
@arguments()
def load_calendar():
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    return [SolutionCalendarWebTO.fromSolutionCalendar(sln_settings, c, True, True, False)
            for c in get_solution_calendars(service_user, sln_settings.solution)]


@rest("/common/calendar/load/more", "get", silent_result=True, read_only_access=True)
@returns(SolutionCalendarWebTO)
@arguments(calendar_id=(int, long), cursor=unicode)
def load_calendar_more(calendar_id, cursor=None):
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    c = SolutionCalendar.get_by_id(calendar_id, parent=parent_key(service_user, sln_settings.solution))
    return SolutionCalendarWebTO.fromSolutionCalendar(sln_settings, c, True, True, False, cursor)


@rest("/common/calendar/admin/add", "post")
@returns(ReturnStatusTO)
@arguments(calendar_id=(int, long), key=unicode)
def calendar_add_admin(calendar_id, key):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    sln_settings = get_solution_settings(service_user)
    try:
        sc = SolutionCalendar.get_by_id(calendar_id, parent_key(service_user, sln_settings.solution))
        if not sc:
            raise BusinessException(common_translate(sln_settings.main_language, SOLUTION_COMMON, 'Calendar not found'))

        app_user, _ = get_user_from_key(key, service_identity)
        create_calendar_admin(calendar_id, app_user, service_user, sln_settings.solution)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/calendar/admin/delete", "post")
@returns(ReturnStatusTO)
@arguments(calendar_id=(int, long), key=unicode)
def calendar_remove_admin(calendar_id, key):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    sln_settings = get_solution_settings(service_user)
    try:
        sc = SolutionCalendar.get_by_id(calendar_id, parent_key(service_user, sln_settings.solution))
        if not sc:
            raise BusinessException(common_translate(sln_settings.main_language, SOLUTION_COMMON, 'Calendar not found'))

        app_user, _ = get_user_from_key(key, service_identity)
        delete_calendar_admin(calendar_id, app_user, service_user, sln_settings.solution)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/calendar/google/authenticate/url", "get", read_only_access=True)
@returns(unicode)
@arguments(calendar_id=(int, long))
def calendar_google_authenticate_url(calendar_id):
    return get_google_authenticate_url(calendar_id)


@rest("/common/calendar/google/load", "get", read_only_access=True)
@returns(SolutionGoogleCalendarStatusTO)
@arguments(calendar_id=(int, long))
def calendar_google_load(calendar_id):
    service_user = users.get_current_user()
    return get_google_calendars(service_user, calendar_id)


@rest("/common/calendar/import/google/put", "post")
@returns(ReturnStatusTO)
@arguments(calendar_id=(int, long), google_calendars=[SolutionUserKeyLabelTO])
def calendar_put_google_import(calendar_id, google_calendars):
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    try:
        def trans():
            sc = SolutionCalendar.get_by_id(calendar_id, parent_key(service_user, sln_settings.solution))
            if not sc:
                raise BusinessException(
                    common_translate(sln_settings.main_language, SOLUTION_COMMON, 'Calendar not found'))

            deferred.defer(update_events_from_google, service_user, calendar_id, _transactional=True)

            sc.google_calendar_ids = list()
            sc.google_calendar_names = list()
            for google_calendar in google_calendars:
                sc.google_calendar_ids.append(google_calendar.key)
                sc.google_calendar_names.append(google_calendar.label)
            sc.google_sync_events = bool(sc.google_calendar_ids)
            sc.put()

        db.run_in_transaction(trans)

        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/events/put", "post")
@returns(ReturnStatusTO)
@arguments(event=EventItemTO)
def put_event(event):
    from solutions.common.bizz.events import put_event as put_event_bizz
    try:
        service_user = users.get_current_user()
        put_event_bizz(service_user, event)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/events/delete", "post")
@returns(ReturnStatusTO)
@arguments(event_id=(int, long))
def delete_event(event_id):
    from solutions.common.bizz.events import delete_event as delete_event_bizz
    try:
        service_user = users.get_current_user()
        delete_event_bizz(service_user, event_id)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/events/guests", "post", read_only_access=True)
@returns([EventGuestTO])
@arguments(event_id=(int, long))
def guests_event(event_id):
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    event = get_event_by_id(service_user, sln_settings.solution, event_id)
    guests = []
    if event:
        for guest in event.guests:
            guests.append(EventGuestTO.fromEventGuest(guest))
    return guests


@rest("/common/events/uit/actor/load", "get", read_only_access=True)
@returns(unicode)
@arguments()
def load_uit_actor_id():
    service_user = users.get_current_user()
    settings = get_solution_settings(service_user)
    return settings.uitdatabank_actor_id


@rest("/common/events/uit/actor/put", "post")
@returns(ReturnStatusTO)
@arguments(uit_id=unicode)
def put_uit_actor_id(uit_id):
    service_user = users.get_current_user()
    settings = get_solution_settings(service_user)
    settings.uitdatabank_actor_id = uit_id
    settings.put()
    return RETURNSTATUS_TO_SUCCESS


@rest("/common/settings/getTimezoneOffset", "get", read_only_access=True)
@returns(long)
@arguments()
def get_timezone_offset():
    service_user = users.get_current_user()
    settings = get_solution_settings(service_user)
    return timezone_offset(settings.timezone)


@rest("/common/friends/load", "get", read_only_access=True)
@returns(FriendListResultTO)
@arguments(batch_count=int, cursor=unicode)
def load_friends_list(batch_count, cursor):
    from rogerthat.service.api.friends import list_friends
    from rogerthat.utils.crypto import encrypt
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    frto = list_friends(service_identity, cursor, batch_count=batch_count)
    for f in frto.friends:
        f.email = unicode(encrypt(service_user, f.email))
    return frto


@rest("/common/statistics/load", "get", silent_result=True, read_only_access=True)
@returns(StatisticsResultTO)
@arguments()
def load_service_statistics():
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    si_stats = system.get_statistics(service_identity)

    result = StatisticsResultTO()
    result.service_identity_statistics = si_stats
    return result


@rest("/common/broadcast/subscribed", "get")
@returns(SubscribedBroadcastReachTO)
@arguments(broadcast_type=unicode, min_age=(int, long, NoneType), max_age=(int, long, NoneType), gender=unicode,
           broadcast_to_all_locations=bool)
def broadcast_subscribed(broadcast_type, min_age, max_age, gender, broadcast_to_all_locations):
    flrto = SubscribedBroadcastReachTO()
    flrto.total_users = 0
    flrto.subscribed_users = 0
    if broadcast_type and broadcast_type is not MISSING:
        service_user = users.get_current_user()
        session_ = users.get_current_session()
        service_identity = session_.service_identity
        if broadcast_to_all_locations:
            sln_settings = get_solution_settings(service_user)
            identities = [None]
            if sln_settings.identities:
                identities.extend(sln_settings.identities)
        else:
            identities = [service_identity if service_identity else ServiceIdentity.DEFAULT]

        for si in identities:
            target_audience = BroadcastTargetAudienceTO()
            target_audience.app_id = None
            target_audience.min_age = min_age
            target_audience.max_age = max_age
            target_audience.gender = gender
            flrto_si = get_broadcast_reach(broadcast_type, target_audience, si)
            flrto.total_users += flrto_si.total_users
            flrto.subscribed_users += flrto_si.subscribed_users
    return flrto


@rest("/common/users/search", "post", read_only_access=True)
@returns([UserDetailsTO])
@arguments(name_or_email_term=unicode, app_id=unicode)
def search_connected_users(name_or_email_term, app_id=None):
    from rogerthat.bizz.profile import search_users_via_friend_connection_and_name_or_email
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    if service_identity is None:
        service_identity = ServiceIdentity.DEFAULT
    connection = remove_slash_default(create_service_identity_user(service_user, service_identity)).email()
    return search_users_via_friend_connection_and_name_or_email(connection, name_or_email_term, app_id, True)


@rest("/common/users/roles/load", "get")
@returns([AppUserRolesTO])
@arguments()
def users_load_roles():
    """
        Gather inbox forwarders, calendar admins and news publishers
        from different places/models
    """
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)

    # get inbox forwarders, calendar admins and news publishers
    inbox_forwarders = inbox_load_forwarders()
    calendar_admins = get_admins_of_solution_calendars(service_user, sln_settings.solution)
    news_publishers = get_solution_news_publishers(service_user, sln_settings.solution)

    def get_calendar_of_admin(admin):
        """returns: SolutionCalendarTO."""
        calendar_key = admin.calendar_key
        calendar = db.get(calendar_key)
        if calendar:
            calendar_to = SolutionCalendarTO.fromSolutionCalendar(sln_settings,
                                                                  calendar)
            return calendar_to

    # create AppUserRolesTO for every role type
    # with different additional information for every type
    all_user_roles = defaultdict(AppUserRolesTO)

    TYPE_MOBILE = SolutionSettings.INBOX_FORWARDER_TYPE_MOBILE
    TYPE_EMAIL = SolutionSettings.INBOX_FORWARDER_TYPE_EMAIL
    mobile_inbox_forwarders = filter(lambda f: f.type == TYPE_MOBILE,
                                     inbox_forwarders)
    email_inbox_forwarders = filter(lambda f: f.type == TYPE_EMAIL,
                                    inbox_forwarders)

    # mobile forwarders may have an app id
    for forwarder in mobile_inbox_forwarders:
        email = forwarder.key
        try:
            app_id = email.split(':')[1]
        except IndexError:
            app_id = None
        user_roles = all_user_roles[email]
        user_roles.app_user_email = email
        user_roles.app_id = app_id
        # additional info: forwarder type
        user_roles.add_forwarder_type(TYPE_MOBILE)

    for admin in calendar_admins:
        email = admin.app_user.email()
        user_roles = all_user_roles[email]
        user_roles.app_user_email = email
        user_roles.app_id = get_app_id_from_app_user(admin.app_user)
        # additional info: calendars
        calendar = get_calendar_of_admin(admin)
        if calendar:
            user_roles.add_calendar(calendar)

    for publisher in news_publishers:
        email = publisher.app_user.email()
        user_roles = all_user_roles[email]
        user_roles.app_user_email = email
        user_roles.app_id = get_app_id_from_app_user(publisher.app_user)
        user_roles.news_publisher = True

    # because email forwarders are stored only by email, without an app id
    # after gathering all roles, check if a user with this email
    # is a mobile forwarder, then just append the type
    for forwarder in email_inbox_forwarders:
        email = forwarder.key  # email only
        has_roles = False  # check if any roles have this email
        for user_email, user_roles in all_user_roles.iteritems():
            # user_email may contain an app id, so check if it contains
            # email, then append the email forwarder type
            if email in user_email:
                user_roles.add_forwarder_type(TYPE_EMAIL)
                has_roles = True

        # no user roles for this email, then create it
        if not has_roles:
            user_roles = all_user_roles[email]
            user_roles.app_user_email = email
            user_roles.add_forwarder_type(TYPE_EMAIL)

    return all_user_roles.values()


@rest("/common/users/roles/add", "post")
@returns(ReturnStatusTO)
@arguments(key=unicode, user_roles=AppUserRolesTO)
def users_add_user_roles(key, user_roles):
    """ set different app roles for a user """
    try:
        service_user = users.get_current_user()
        session_ = users.get_current_session()
        service_identity = session_.service_identity
        sln_settings = get_solution_settings(service_user)
        sln_i_settings = get_solution_settings_or_identity_settings(sln_settings,
                                                                    service_identity)

        # try first to get the user from user key
        app_user, is_existing_user = get_user_from_key(key, service_identity)

        # add inbox forwarder
        if user_roles.inbox_forwarder:
            forwarder_types = user_roles.forwarder_types
            for forwarder_type in forwarder_types:
                if forwarder_type:
                    if forwarder_type == SolutionSettings.INBOX_FORWARDER_TYPE_EMAIL:
                        # only email without an app id
                        key = get_human_user_from_app_user(app_user).email()
                    else:
                        key = app_user.email()

                    if not EMAIL_REGEX.match(key):
                        return ReturnStatusTO.create(False,
                                                     common_translate(sln_settings.main_language, SOLUTION_COMMON,
                                                                      'Please provide a valid e-mail address'))
                    forwarders = sln_i_settings.get_forwarders_by_type(forwarder_type)
                    if key not in forwarders:
                        forwarders.append(key)
            sln_i_settings.put()

        if is_existing_user:
            # add as a calendar admin
            if user_roles.calendar_admin:
                calendars = user_roles.calendars
                for calendar in calendars:
                    calendar_id = calendar.id
                    create_calendar_admin(calendar_id, app_user, service_user,
                                          sln_settings.solution)

            # add as news publisher
            if user_roles.news_publisher:
                create_news_publisher(app_user, service_user, sln_settings.solution)

        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/users/roles/delete", "post")
@returns(ReturnStatusTO)
@arguments(key=unicode, forwarder_types=[unicode], calendar_ids=[(int, long)])
def users_delete_user_roles(key, forwarder_types, calendar_ids):
    """ remove all the user app roles """
    try:
        service_user = users.get_current_user()
        session_ = users.get_current_session()
        service_identity = session_.service_identity
        sln_settings = get_solution_settings(service_user)
        sln_i_settings = get_solution_settings_or_identity_settings(sln_settings,
                                                                    service_identity)

        # try first to get the user profile from user key
        app_user, _ = get_user_from_key(key, service_identity)

        # inbox
        if forwarder_types:
            key = app_user.email()
            for forwarder_type in forwarder_types:
                if forwarder_type == SolutionSettings.INBOX_FORWARDER_TYPE_EMAIL:
                    key = get_human_user_from_app_user(app_user).email()

                forwarders = sln_i_settings.get_forwarders_by_type(forwarder_type)
                if key in forwarders:
                    forwarders.remove(key)
            sln_i_settings.put()

        # calendars
        if calendar_ids:
            for calendar_id in calendar_ids:
                delete_calendar_admin(calendar_id, app_user, service_user,
                                      sln_settings.solution)

        # news
        delete_news_publisher(app_user, service_user, sln_settings.solution)

        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/inbox/forwarders/load", "get", read_only_access=True)
@returns([SolutionInboxForwarder])
@arguments()
def inbox_load_forwarders():
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    if is_default_service_identity(service_identity):
        sln_i_settings = get_solution_settings(service_user)
    else:
        sln_i_settings = get_solution_identity_settings(service_user, service_identity)
    forwarder_profiles = dict(zip(sln_i_settings.inbox_forwarders,
                                  db.get(
                                      [get_profile_key(u) for u in map(users.User, sln_i_settings.inbox_forwarders)])))

    forwarders_to_be_removed = list()
    sifs = []
    for fw_type, forwarders in [(SolutionSettings.INBOX_FORWARDER_TYPE_MOBILE, sln_i_settings.inbox_forwarders),
                                (SolutionSettings.INBOX_FORWARDER_TYPE_EMAIL, sln_i_settings.inbox_mail_forwarders), ]:
        for forwarder in forwarders:
            sif = SolutionInboxForwarder()
            sif.type = fw_type
            sif.key = forwarder
            if fw_type == SolutionSettings.INBOX_FORWARDER_TYPE_MOBILE:
                up = forwarder_profiles[forwarder]
                if up:
                    sif.label = u"%s (%s)" % (up.name, get_human_user_from_app_user(up.user).email())
                else:
                    forwarders_to_be_removed.append(forwarder)
                    continue
            else:
                sif.label = forwarder
            sifs.append(sif)

    if forwarders_to_be_removed:
        logging.info('Inbox forwarders %s do not exist anymore', forwarders_to_be_removed)

        def trans():
            if is_default_service_identity(service_identity):
                sln_i_settings = get_solution_settings(service_user)
            else:
                sln_i_settings = get_solution_identity_settings(service_user, service_identity)
            for fwd in forwarders_to_be_removed:
                sln_i_settings.inbox_forwarders.remove(fwd)
            sln_i_settings.put()

        db.run_in_transaction(trans)
    return sifs


@rest("/common/inbox/forwarders/add", "post")
@returns(ReturnStatusTO)
@arguments(key=unicode, forwarder_type=unicode)
def inbox_add_forwarder(key, forwarder_type=SolutionSettings.INBOX_FORWARDER_TYPE_MOBILE):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    sln_settings = get_solution_settings(service_user)
    sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)

    if forwarder_type == SolutionSettings.INBOX_FORWARDER_TYPE_EMAIL:
        if not EMAIL_REGEX.match(key):
            return ReturnStatusTO.create(False, common_translate(sln_settings.main_language, SOLUTION_COMMON,
                                                                 'Please provide a valid e-mail address'))
    elif forwarder_type == SolutionSettings.INBOX_FORWARDER_TYPE_MOBILE:
        app_user = sanitize_app_user(users.User(key))
        get_user_profile(app_user)
        key = app_user.email()

    forwarders = sln_i_settings.get_forwarders_by_type(forwarder_type)
    if key not in forwarders:
        forwarders.append(key)
        sln_i_settings.put()
    return RETURNSTATUS_TO_SUCCESS


@rest("/common/inbox/forwarders/delete", "post")
@returns(ReturnStatusTO)
@arguments(key=unicode, forwarder_type=unicode)
def inbox_delete_forwarder(key, forwarder_type=SolutionSettings.INBOX_FORWARDER_TYPE_MOBILE):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    if is_default_service_identity(service_identity):
        sln_i_settings = get_solution_settings(service_user)
    else:
        sln_i_settings = get_solution_identity_settings(service_user, service_identity)
    forwarders = sln_i_settings.get_forwarders_by_type(forwarder_type)
    if key in forwarders:
        forwarders.remove(key)
        sln_i_settings.put()
    else:
        logging.warn('%s inbox forwarder "%s" not found', forwarder_type, key)
    return RETURNSTATUS_TO_SUCCESS


@rest("/common/appointment/settings/load", "get", read_only_access=True)
@returns(SolutionAppointmentSettingsTO)
@arguments()
def load_appointment_settings():
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    sln_appointment_settings = get_solution_appointment_settings(service_user)
    return SolutionAppointmentSettingsTO.fromModel(sln_appointment_settings, sln_settings.main_language)


@rest("/common/appointment/settings/put", "post")
@returns(ReturnStatusTO)
@arguments(text_1=unicode)
def put_appointment_settings(text_1):
    service_user = users.get_current_user()
    try:
        sln_appointment_settings_key = SolutionAppointmentSettings.create_key(service_user)
        sln_appointment_settings = SolutionAppointmentSettings.get(sln_appointment_settings_key)
        if not sln_appointment_settings:
            sln_appointment_settings = SolutionAppointmentSettings(key=sln_appointment_settings_key)
        sln_appointment_settings.text_1 = text_1
        sln_appointment_settings.put()

        sln_settings = get_solution_settings(service_user)
        sln_settings.updates_pending = True
        put_and_invalidate_cache(sln_appointment_settings, sln_settings)
        broadcast_updates_pending(sln_settings)
        send_message(service_user, u"solutions.common.appointment.settings.update")
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/appointment/settings/timeframe/put", "post")
@returns(ReturnStatusTO)
@arguments(appointment_id=(int, long, NoneType), day=int, time_from=int, time_until=int)
def put_appointment_weekday_timeframe(appointment_id, day, time_from, time_until):
    from solutions.common.bizz.appointment import \
        put_appointment_weekday_timeframe as put_appointment_weekday_timeframe_bizz
    service_user = users.get_current_user()
    try:
        put_appointment_weekday_timeframe_bizz(service_user, appointment_id, day, time_from, time_until)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/appointment/settings/timeframe/load", "get", read_only_access=True)
@returns([SolutionAppointmentWeekdayTimeframeTO])
@arguments()
def load_appointment_weekday_timeframes():
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    return [SolutionAppointmentWeekdayTimeframeTO.fromModel(f, sln_settings.main_language or DEFAULT_LANGUAGE) for f in
            SolutionAppointmentWeekdayTimeframe.list(service_user, sln_settings.solution)]


@rest("/common/appointment/settings/timeframe/delete", "post")
@returns(ReturnStatusTO)
@arguments(appointment_id=(int, long))
def delete_appointment_weekday_timeframe(appointment_id):
    from solutions.common.bizz.appointment import \
        delete_appointment_weekday_timeframe as delete_appointment_weekday_timeframe_bizz
    service_user = users.get_current_user()
    try:
        delete_appointment_weekday_timeframe_bizz(service_user, appointment_id)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/settings/branding", "get", read_only_access=True)
@returns(BrandingSettingsTO)
@arguments()
def get_branding_settings():
    branding_settings = SolutionBrandingSettings.get_by_user(users.get_current_user())
    return BrandingSettingsTO.from_model(branding_settings)


@rest("/common/settings/branding_and_menu", "get", read_only_access=True)
@returns(BrandingSettingsAndMenuItemsTO)
@arguments()
def rest_get_branding_settings_and_menu():
    branding_settings = SolutionBrandingSettings.get_by_user(users.get_current_user())
    branding_settings_to = BrandingSettingsTO.from_model(branding_settings)
    service_menu = system.get_menu_item()
    smi_dict = {'x'.join(map(str, smi.coords)): smi for smi in service_menu.items}
    service_menu_items = list()
    z = 0
    for y in xrange(3):
        row = list()
        for x in xrange(4):
            coords = 'x'.join(map(str, [x, y, z]))
            label = None
            iconName = None
            if y == 0:
                if x == 0:
                    label = service_menu.aboutLabel or u'About'
                    iconName = u'fa-info'
                elif x == 1:
                    label = service_menu.messagesLabel or u'History'
                    iconName = u'fa-envelope'
                elif x == 2:
                    if service_menu.phoneNumber:
                        label = service_menu.callLabel or u'Call'
                    iconName = u'fa-phone'
                elif x == 3:
                    if service_menu.shareQRId:
                        label = service_menu.shareLabel or u'Recommend'
                        iconName = u'fa-thumbs-o-up'
                iconUrl = None
            else:
                smi = smi_dict.get(coords)
                label = smi.label if smi else None
                iconUrl = smi.iconUrl if smi else None
                iconName = smi.iconName if smi else None

            row.append(ServiceMenuItemWithCoordinatesTO.create(label, iconName, iconUrl, coords))
        service_menu_items.append(ServiceMenuItemWithCoordinatesListTO.create(row))
    return BrandingSettingsAndMenuItemsTO.create(branding_settings_to, service_menu_items)


@rest("/common/settings/branding", "post")
@returns(ReturnStatusTO)
@arguments(branding_settings=BrandingSettingsTO)
def rest_save_branding_settings(branding_settings):
    """
    Args:
        branding_settings (BrandingSettingsTO)
    """
    try:
        branding_settings.background_color = MISSING
        branding_settings.text_color = MISSING
        save_branding_settings(users.get_current_user(), branding_settings)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException as e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/repair/settings/load", "get", read_only_access=True)
@returns(SolutionRepairSettingsTO)
@arguments()
def repair_settings_load():
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    sln_repair_settings = get_solution_repair_settings(service_user)
    return SolutionRepairSettingsTO.fromModel(sln_repair_settings, sln_settings.main_language)


@rest("/common/repair/settings/put", "post")
@returns(ReturnStatusTO)
@arguments(text_1=unicode)
def put_repair_settings(text_1):
    service_user = users.get_current_user()
    try:
        sln_repair_settings_key = SolutionRepairSettings.create_key(service_user)
        sln_repair_settings = SolutionRepairSettings.get(sln_repair_settings_key)
        if not sln_repair_settings:
            sln_repair_settings = SolutionRepairSettings(key=sln_repair_settings_key)
        sln_repair_settings.text_1 = text_1
        sln_repair_settings.put()

        sln_settings = get_solution_settings(service_user)
        sln_settings.updates_pending = True
        put_and_invalidate_cache(sln_repair_settings, sln_settings)
        broadcast_updates_pending(sln_settings)
        send_message(service_user, u"solutions.common.repair.settings.update")
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/repair_order/delete", "post")
@returns(ReturnStatusTO)
@arguments(order_key=unicode, message=unicode)
def repair_order_delete(order_key, message):
    service_user = users.get_current_user()
    try:
        delete_repair_order(service_user, order_key, message)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/repair_order/load", "get", read_only_access=True)
@returns([SolutionRepairOrderTO])
@arguments()
def repair_orders_load():
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    sln_settings = get_solution_settings(service_user)
    return map(SolutionRepairOrderTO.fromModel,
               get_solution_repair_orders(service_user, service_identity, sln_settings.solution))


@rest("/common/repair_order/sendmessage", "post")
@returns(ReturnStatusTO)
@arguments(order_key=unicode, order_status=int, message=unicode)
def repair_order_send_message(order_key, order_status, message):
    service_user = users.get_current_user()
    try:
        send_message_for_repair_order(service_user, order_key, order_status, message)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/sandwich/settings/load", "get", read_only_access=True)
@returns(SandwichSettingsTO)
@arguments()
def rest_load_sandwich_settings():
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)

    types = SandwichType.list(service_user, sln_settings.solution).run()
    toppings = SandwichTopping.list(service_user, sln_settings.solution).run()
    options = SandwichOption.list(service_user, sln_settings.solution).run()
    sandwich_settings = SandwichSettings.get_settings(service_user, sln_settings.solution)

    return SandwichSettingsTO.from_model(sandwich_settings, types, toppings, options, sln_settings.currency)


@rest("/common/sandwich/settings/save", "post")
@returns(SandwichSettingsTO)
@arguments(sandwich_settings=SandwichSettingsTO)
def save_sandwich_settings(sandwich_settings):
    """
    Args:
        sandwich_settings (SandwichSettingsTO)
    Returns:
        sandwich_settings (SandwichSettingsTO)
    """
    service_user = users.get_current_user()

    sln_settings = get_solution_settings(service_user)
    simple_members = get_members(SandwichSettingsTO)[1]
    to_put = []

    if any(getattr(sandwich_settings, name) is not MISSING for name, _ in simple_members):
        sandwich_settings_model = SandwichSettings.get_settings(service_user, sln_settings.solution)
        if sandwich_settings.show_prices != MISSING:
            sandwich_settings_model.show_prices = sandwich_settings.show_prices
        if sandwich_settings.days != MISSING:
            sandwich_settings_model.status_days = sandwich_settings.days
        if sandwich_settings.from_ != MISSING:
            sandwich_settings_model.time_from = sandwich_settings.from_
        if sandwich_settings.till != MISSING:
            sandwich_settings_model.time_until = sandwich_settings.till
        if sandwich_settings.reminder_days != MISSING:
            sandwich_settings_model.broadcast_days = sandwich_settings.reminder_days
        if sandwich_settings.reminder_message != MISSING:
            sandwich_settings_model.reminder_broadcast_message = sandwich_settings.reminder_message
        if sandwich_settings.reminder_at != MISSING:
            sandwich_settings_model.remind_at = sandwich_settings.reminder_at
        if sandwich_settings.leap_time is not MISSING:
            sandwich_settings_model.leap_time = sandwich_settings.leap_time
        if sandwich_settings.leap_time_enabled is not MISSING:
            sandwich_settings_model.leap_time_enabled = sandwich_settings.leap_time_enabled
        if sandwich_settings.leap_time_type is not MISSING:
            sandwich_settings_model.leap_time_type = sandwich_settings.leap_time_type

        to_put.append(sandwich_settings_model)

    has_new = False

    def update(items, clazz):
        has_new_items = False
        # XXX: multiget
        for item in items:
            if item.id is MISSING:
                item_model = clazz(parent=parent_key(service_user, sln_settings.solution))
                has_new_items = True
            else:
                item_model = clazz.get_by_id(item.id, parent_key(service_user, sln_settings.solution))
                if item.deleted:
                    item_model.deleted = True
            item_model.description = item.description
            item_model.price = item.price
            item_model.order = item.order
            to_put.append(item_model)
            return has_new_items

    if sandwich_settings.types != MISSING:
        has_new = has_new or update(sandwich_settings.types, SandwichType)
    if sandwich_settings.toppings != MISSING:
        has_new = has_new or update(sandwich_settings.toppings, SandwichTopping)
    if sandwich_settings.options != MISSING:
        has_new = has_new or update(sandwich_settings.options, SandwichOption)
    sln_settings.updates_pending = True
    to_put.append(sln_settings)
    put_in_chunks(to_put)

    broadcast_updates_pending(sln_settings)
    if has_new:
        return rest_load_sandwich_settings()


@rest("/common/sandwich/orders/load", "get", read_only_access=True)
@returns([SandwichOrderTO])
@arguments()
def load_sandwich_orders():
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    sln_settings = get_solution_settings(service_user)
    return [SandwichOrderTO.fromModel(m) for m in
            SandwichOrder.list(service_user, service_identity, sln_settings.solution)]


@rest("/common/sandwich/orders/reply", "post")
@returns(ReturnStatusTO)
@arguments(sandwich_id=unicode, message=unicode)
def sandwich_order_reply(sandwich_id, message):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    try:
        reply_sandwich_order(service_user, service_identity, sandwich_id, message)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/sandwich/orders/ready", "post")
@returns(ReturnStatusTO)
@arguments(sandwich_id=unicode, message=unicode)
def sandwich_order_ready(sandwich_id, message):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    try:
        ready_sandwich_order(service_user, service_identity, sandwich_id, message)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/sandwich/orders/delete", "post")
@returns(ReturnStatusTO)
@arguments(sandwich_id=unicode, message=unicode)
def sandwich_order_delete(sandwich_id, message):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    try:
        delete_sandwich_order(service_user, service_identity, sandwich_id, message)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/group_purchase/broadcast", "post")
@returns(ReturnStatusTO)
@arguments(group_purchase_id=(int, long), message=unicode)
def group_purchase_broadcast(group_purchase_id, message=unicode):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    try:
        broadcast_group_purchase(service_user, service_identity, group_purchase_id, message)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/group_purchase/load", "get", silent_result=True, read_only_access=True)
@returns([SolutionGroupPurchaseTO])
@arguments()
def group_purchase_load():
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    sln_settings = get_solution_settings(service_user)
    return [SolutionGroupPurchaseTO.fromModel(m, include_picture=True, incude_subscriptions=True) for m in
            SolutionGroupPurchase.list(service_user, service_identity, sln_settings.solution)]


@rest("/common/group_purchase/save", "post")
@returns(ReturnStatusTO)
@arguments(group_purchase=SolutionGroupPurchaseTO)
def group_purchase_save(group_purchase):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    try:
        save_group_purchase(service_user, service_identity, group_purchase)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/group_purchase/delete", "post")
@returns(ReturnStatusTO)
@arguments(group_purchase_id=(int, long))
def group_purchase_delete(group_purchase_id):
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    try:
        delete_group_purchase(service_user, service_identity, group_purchase_id)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/group_purchase/subscriptions/add", "post")
@returns(ReturnStatusTO)
@arguments(group_purchase_id=(int, long), name=unicode, units=int)
def group_purchase_subscription_add(group_purchase_id, name, units):
    service_user = users.get_current_user()
    try:
        new_group_purchase_subscription(service_user, None, group_purchase_id, name, None, units)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/group_purchase/settings/load", "get", read_only_access=True)
@returns(SolutionGroupPurchaseSettingsTO)
@arguments()
def group_purchase_settings_load():
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    return SolutionGroupPurchaseSettingsTO.fromModel(
        get_solution_group_purchase_settings(service_user, sln_settings.solution))


@rest("/common/group_purchase/settings/save", "post")
@returns(ReturnStatusTO)
@arguments(group_purchase_settings=SolutionGroupPurchaseSettingsTO)
def group_purchase_settings_save(group_purchase_settings):
    service_user = users.get_current_user()
    try:
        def trans():
            sln_settings = get_solution_settings(service_user)
            sgps = get_solution_group_purchase_settings(service_user, sln_settings.solution)
            sgps.visible = group_purchase_settings.visible

            sln_settings.updates_pending = True
            put_and_invalidate_cache(sgps, sln_settings)
            return sln_settings

        xg_on = db.create_transaction_options(xg=True)
        sln_settings = db.run_in_transaction_options(xg_on, trans)

        broadcast_updates_pending(sln_settings)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/twitter/auth_url", "get", read_only_access=True)
@returns(unicode)
@arguments()
def get_twitter_auth_url():
    service_user = users.get_current_user()
    return bizz_twitter.get_twitter_auth_url(service_user)


@rest("/common/twitter/logout", "get", read_only_access=True)
@returns(unicode)
@arguments()
def twitter_logout():
    service_user = users.get_current_user()
    return bizz_twitter.twitter_logout(service_user)


@rest('/common/menu/item/image/upload', 'post', read_only_access=False, silent_result=True)
@returns(ImageReturnStatusTO)
@arguments(image=unicode, image_id_to_delete=(int, long, NoneType))
def upload_menu_item_image(image=None, image_id_to_delete=None):
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    logging.info('%s uploaded a small file', sln_settings.name)
    azzert(image)
    if image_id_to_delete:
        delete_file_blob(service_user, image_id_to_delete)
    try:
        image = create_file_blob(service_user, base64.b64decode(image.split(',', 1)[1]))
        return ImageReturnStatusTO.create(True, None, image.key().id())

    except BusinessException, ex:
        return ImageReturnStatusTO.create(False, ex.message, None)


@rest('/common/menu/item/image/qr_url', 'get')
@returns(unicode)
@arguments(category_index=(int, long), item_index=(int, long))
def menu_item_qr_url(category_index, item_index):
    service_user = users.get_current_user()
    return get_menu_item_qr_url(service_user, category_index, item_index)


@rest('/common/menu/item/image/remove', 'post', read_only_access=False)
@returns(ReturnStatusTO)
@arguments(image_id=(int, long))
def remove_file_blob(image_id):
    delete_file_blob(users.get_current_user(), image_id)


@rest('/common/settings/broadcast/change_order', 'post')
@returns(ReturnStatusTO)
@arguments(broadcast_types=[unicode])
def change_broadcast_types_order(broadcast_types):
    save_broadcast_types_order(users.get_current_user(), broadcast_types)
    return RETURNSTATUS_TO_SUCCESS


@rest('/common/settings/broadcast/add_or_remove_type', 'post')
@returns(ReturnStatusTO)
@arguments(broadcast_type=unicode, delete=bool)
def add_or_remove_broadcast_type(broadcast_type, delete):
    try:
        updated = False
        sln_settings = get_solution_settings(users.get_current_user())
        translated_broadcast_types = get_translated_broadcast_types(sln_settings)
        if delete:
            if translated_broadcast_types[broadcast_type] in sln_settings.broadcast_types:
                sln_settings.broadcast_types.remove(translated_broadcast_types[broadcast_type])
                updated = True
        else:
            if broadcast_type not in translated_broadcast_types and broadcast_type not in sln_settings.broadcast_types:
                sln_settings.broadcast_types.append(broadcast_type)
                updated = True

        if updated:
            sln_settings.updates_pending = True
            put_and_invalidate_cache(sln_settings)
            broadcast_updates_pending(sln_settings)

        return RETURNSTATUS_TO_SUCCESS
    except BusinessException as e:
        return ReturnStatusTO.create(False, e.message)


@rest('/common/get_menu', 'get', read_only_access=True)
@returns(ServiceMenuDetailTO)
@arguments()
def rest_get_menu():
    service_menu = system.get_menu()
    user_role_ids = [role.id for role in get_user_defined_roles()]

    def has_user_defined_roles_only(item):
        return all([role_id in user_role_ids for role_id in item.roles])

    def include_item(item):
        return '__rt__.' not in item.tag and has_user_defined_roles_only(item)

    service_menu.items = filter(include_item, service_menu.items)
    return service_menu


@rest('/common/settings/facebook/app/id', 'get')
@returns(str)
@arguments()
def get_facebook_app_id():
    host = get_current_http_host()
    app_info = get_facebook_app_info(host)
    if app_info:
        logging.debug('%s --> FB app id %s', host, app_info[0])
        return app_info[0]

    logging.warn('cannot get facebook app id for host: %s', host)
    return ''


@rest('/common/customer/signup/all', 'get')
@returns([CustomerSignupTO])
@arguments()
def rest_get_customer_signups():
    service_user = users.get_current_user()
    city_customer = get_customer(service_user)
    return [CustomerSignupTO.from_model(s) for s in get_customer_signups(city_customer)]


@rest('/common/customer/singup/reply', 'post')
@returns(ReturnStatusTO)
@arguments(signup_key=unicode, message=unicode)
def rest_customer_signup_reply(signup_key, message):
    service_user = users.get_current_user()
    city_customer = get_customer(service_user)

    signup = db.get(signup_key)
    if signup:
        set_customer_signup_status(city_customer, signup, approved=False, reason=message)

    return RETURNSTATUS_TO_SUCCESS


@rest('/common/functionalities/modules/activated', 'get')
@returns([unicode])
@arguments()
def rest_get_activated_modules():
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    modules = sln_settings.modules

    for module in sln_settings.modules_to_put:
        if module not in modules:
            modules.append(module)
    for module in sln_settings.modules_to_remove:
        if module in modules:
            modules.remove(module)

    return modules


@rest('/common/functionalities/modules/enable', 'post')
@returns(ReturnStatusTO)
@arguments(name=unicode, enabled=bool)
def rest_enable_or_disable_module(name, enabled):
    try:
        service_user = users.get_current_user()
        enable_or_disable_solution_module(service_user, name, enabled)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException as e:
        return ReturnStatusTO.create(False, e.message)

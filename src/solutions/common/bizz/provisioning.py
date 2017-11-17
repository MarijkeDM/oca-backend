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
from contextlib import closing
from datetime import timedelta, datetime
import json
import logging
import os
import time
from types import NoneType
import urllib
from zipfile import ZipFile, ZIP_DEFLATED

from babel import dates
from babel.dates import format_date, format_timedelta, get_next_timezone_transition, format_time, get_timezone

from google.appengine.ext import db
import jinja2
from mcfw.properties import azzert
from mcfw.rpc import arguments, returns, serialize_complex_value
from rogerthat.bizz.app import add_auto_connected_services, delete_auto_connected_service
from rogerthat.bizz.features import Features
from rogerthat.consts import DAY
from rogerthat.dal import parent_key, put_and_invalidate_cache
from rogerthat.models import Branding, ServiceMenuDef, ServiceRole, App, ServiceProfile
from rogerthat.models.properties.app import AutoConnectedService
from rogerthat.rpc import users
from rogerthat.service.api import system, qr
from rogerthat.settings import get_server_settings
from rogerthat.to.friends import ServiceMenuDetailTO, ServiceMenuItemLinkTO
from rogerthat.to.profile import ProfileLocationTO
from rogerthat.to.qr import QRDetailsTO
from rogerthat.utils import now, is_flag_set, xml_escape
from rogerthat.utils.service import create_service_identity_user
from rogerthat.utils.transactions import on_trans_committed
from solutions import translate as common_translate
import solutions
from solutions.common import SOLUTION_COMMON
from solutions.common.bizz import timezone_offset, render_common_content, SolutionModule, \
    get_coords_of_service_menu_item, get_next_free_spot_in_service_menu, SolutionServiceMenuItem, put_branding,\
    OrganizationType
from solutions.common.bizz.events import provision_events_branding
from solutions.common.bizz.group_purchase import provision_group_purchase_branding
from solutions.common.bizz.loyalty import provision_loyalty_branding, get_loyalty_slide_footer
from solutions.common.bizz.menu import _put_default_menu, get_item_image_url
from solutions.common.bizz.messaging import POKE_TAG_ASK_QUESTION, POKE_TAG_APPOINTMENT, POKE_TAG_REPAIR, \
    POKE_TAG_SANDWICH_BAR, POKE_TAG_EVENTS, POKE_TAG_MENU, POKE_TAG_WHEN_WHERE, \
    POKE_TAG_CONNECT_INBOX_FORWARDER_VIA_SCAN, POKE_TAG_GROUP_PURCHASE, POKE_TAG_NEW_EVENT, \
    POKE_TAG_EVENTS_CONNECT_VIA_SCAN, POKE_TAG_RESERVE_PART1, POKE_TAG_MY_RESERVATIONS, POKE_TAG_ORDER, \
    POKE_TAG_LOYALTY_ADMIN, POKE_TAG_PHARMACY_ORDER, POKE_TAG_LOYALTY, POKE_TAG_DISCUSSION_GROUPS, \
    POKE_TAG_BROADCAST_CREATE_NEWS, POKE_TAG_BROADCAST_CREATE_NEWS_CONNECT
from solutions.common.bizz.reservation import put_default_restaurant_settings
from solutions.common.bizz.sandwich import get_sandwich_reminder_broadcast_type, validate_sandwiches
from solutions.common.bizz.system import generate_branding
from solutions.common.consts import ORDER_TYPE_SIMPLE, ORDER_TYPE_ADVANCED, UNIT_GRAM, UNIT_KG, SECONDS_IN_HOUR, \
    SECONDS_IN_DAY, SECONDS_IN_MINUTE, SECONDS_IN_WEEK
from solutions.common.dal import get_solution_settings, get_event_list, get_restaurant_menu, \
    get_solution_logo, get_solution_group_purchase_settings, get_solution_calendars, get_static_content_keys, \
    get_solution_avatar, get_solution_identity_settings, get_solution_settings_or_identity_settings, \
    get_solution_news_publishers
from solutions.common.dal.appointment import get_solution_appointment_settings
from solutions.common.dal.cityapp import invalidate_service_user_for_city
from solutions.common.dal.order import get_solution_order_settings
from solutions.common.dal.repair import get_solution_repair_settings
from solutions.common.dal.reservations import get_restaurant_profile, get_restaurant_settings
from solutions.common.handlers import JINJA_ENVIRONMENT
from solutions.common.models import SolutionMainBranding, SolutionSettings, SolutionBrandingSettings, \
    SolutionAutoBroadcastTypes, SolutionQR, RestaurantMenu
from solutions.common.models.agenda import SolutionCalendar, SolutionCalendarAdmin
from solutions.common.models.appointment import SolutionAppointmentWeekdayTimeframe
from solutions.common.models.cityapp import CityAppProfile
from solutions.common.models.discussion_groups import SolutionDiscussionGroup
from solutions.common.models.group_purchase import SolutionGroupPurchase
from solutions.common.models.loyalty import SolutionLoyaltySettings, SolutionLoyaltyLottery, \
    SolutionLoyaltyIdentitySettings
from solutions.common.models.order import SolutionOrderWeekdayTimeframe
from solutions.common.models.properties import MenuItem
from solutions.common.models.reservation import RestaurantProfile
from solutions.common.models.sandwich import SandwichType, SandwichTopping, SandwichSettings, SandwichOption
from solutions.common.models.static_content import SolutionStaticContent
from solutions.common.to import EventItemTO, MenuTO, SolutionGroupPurchaseTO, SolutionCalendarTO, TimestampTO
from solutions.common.to.loyalty import LoyaltyRevenueDiscountSettingsTO, LoyaltyStampsSettingsTO
from solutions.common.utils import is_default_service_identity
from solutions.djmatic import SOLUTION_DJMATIC
from solutions.jinja_extensions import TranslateExtension


try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


POKE_TAGS = { SolutionModule.AGENDA:        POKE_TAG_EVENTS,
              SolutionModule.APPOINTMENT:   POKE_TAG_APPOINTMENT,
              SolutionModule.ASK_QUESTION:  POKE_TAG_ASK_QUESTION,
              SolutionModule.BROADCAST:     ServiceMenuDef.TAG_MC_BROADCAST_SETTINGS,
              SolutionModule.BILLING:       None,
              SolutionModule.BULK_INVITE:   None,
              SolutionModule.CITY_APP:      None,
              SolutionModule.CITY_VOUCHERS: None,
              SolutionModule.DISCUSSION_GROUPS: POKE_TAG_DISCUSSION_GROUPS,
              SolutionModule.GROUP_PURCHASE:POKE_TAG_GROUP_PURCHASE,
              SolutionModule.LOYALTY:       POKE_TAG_LOYALTY,
              SolutionModule.MENU:          POKE_TAG_MENU,
              SolutionModule.ORDER:         POKE_TAG_ORDER,
              SolutionModule.PHARMACY_ORDER:POKE_TAG_PHARMACY_ORDER,
              SolutionModule.QR_CODES:      None,
              SolutionModule.REPAIR:        POKE_TAG_REPAIR,
              SolutionModule.RESTAURANT_RESERVATION: None,
              SolutionModule.SANDWICH_BAR:  POKE_TAG_SANDWICH_BAR,
              SolutionModule.STATIC_CONTENT:None,
              SolutionModule.WHEN_WHERE:    POKE_TAG_WHEN_WHERE,
              SolutionModule.HIDDEN_CITY_WIDE_LOTTERY: None,
              }

STATIC_CONTENT_TAG_PREFIX = 'Static content: '

COLOR_WHITE = '#FFFFFF'
COLOR_BLACK = '#000000'

@returns(unicode)
@arguments()
def get_default_language():
    return system.get_languages().default_language


@arguments(translation_map=dict)
def get_default_translations(translation_map):
    default_lang = get_default_language()
    default_translation = {name: common_translate(default_lang, sln, name)
                           for names_dict in translation_map.itervalues()
                           for (name, sln) in names_dict.iteritems()}
    return default_lang, default_translation


@returns(SolutionSettings)
@arguments(service_user=users.User, solution=unicode)
def get_and_complete_solution_settings(service_user, solution):
    settings = get_solution_settings(service_user)

    updated = False
    if not settings.solution:
        settings.solution = solution
        updated = True

    if settings.search_enabled is None:
        settings.search_enabled = False
        updated = True

    if updated:
        settings.put()

    return settings


@returns(SolutionMainBranding)
@arguments(service_user=users.User)
def get_and_store_main_branding(service_user):
    sln_settings, main_branding, branding_settings = db.get([SolutionSettings.create_key(service_user),
                                                             SolutionMainBranding.create_key(service_user),
                                                             SolutionBrandingSettings.create_key(service_user)])

    main_branding.old_branding_key = main_branding.branding_key
    must_store_branding = not main_branding.branding_key or not main_branding.branding_creation_time

    if sln_settings.solution == SOLUTION_DJMATIC:
        if branding_settings:
            logging.warn('DJ-Matic services should not have SolutionBrandingSettings')
    else:
        if branding_settings and branding_settings.modification_time >= main_branding.branding_creation_time:
            logging.info('Using SolutionBrandingSettings: %s', db.to_dict(branding_settings))
            with closing(StringIO()) as stream:
                with closing(ZipFile(stream, 'w', compression=ZIP_DEFLATED)) as zip_:
                    main_branding_dir = os.path.join(os.path.dirname(__file__), '..', 'templates', 'main_branding')
                    for f_name in os.listdir(main_branding_dir):
                        content = None
                        if f_name == 'branding.html':
                            content = _render_branding_html(main_branding_dir,
                                                            'branding.html',
                                                            branding_settings.color_scheme,
                                                            branding_settings.background_color,
                                                            branding_settings.text_color,
                                                            branding_settings.menu_item_color,
                                                            branding_settings.show_avatar,
                                                            {'show_identity_name': branding_settings.show_identity_name})
                            content = content.encode('utf8')
                            logging.debug('Generated %s: %s', f_name, content)
                        elif f_name == 'logo.jpg':
                            solution_logo = get_solution_logo(service_user)
                            if solution_logo:
                                content = str(solution_logo.picture)

                        elif f_name == 'avatar.jpg':
                            if not branding_settings.show_avatar:
                                continue
                            solution_avatar = get_solution_avatar(service_user)
                            if solution_avatar:
                                content = str(solution_avatar.picture)

                        if not content:
                            # just take the file from disk
                            with open(os.path.join(main_branding_dir, f_name)) as f:
                                content = f.read()

                        zip_.writestr(f_name, content)
                main_branding.blob = db.Blob(stream.getvalue())
            must_store_branding = True

    if must_store_branding:
        logging.info('Storing MAIN branding')
        main_branding.branding_key = put_branding(u'Main', base64.b64encode(str(main_branding.blob))).id
        main_branding.branding_creation_time = now()
        main_branding.put()
    return main_branding


@returns(SolutionLoyaltySettings)
@arguments(service_user=users.User, language=unicode)
def get_and_store_content_branding(service_user, language):
    from rogerthat.bizz.rtemail import generate_auto_login_url

    branding_settings, loyalty_settings = db.get([SolutionBrandingSettings.create_key(service_user),
                                                  SolutionLoyaltySettings.create_key(service_user)])
    azzert(branding_settings)
    if not loyalty_settings:
        loyalty_settings = SolutionLoyaltySettings(key=SolutionLoyaltySettings.create_key(service_user))

    if not loyalty_settings.branding_key or loyalty_settings.modification_time >= loyalty_settings.branding_creation_time:
        logging.info('Using SolutionBrandingSettings: %s', db.to_dict(branding_settings))
        with closing(StringIO()) as stream:
            with closing(ZipFile(stream, 'w', compression=ZIP_DEFLATED)) as zip_:
                content_branding_dir = os.path.join(os.path.dirname(__file__), '..', 'templates', 'content_branding')
                for f_name in os.listdir(content_branding_dir):
                    content = None
                    if f_name == 'app.html':
                        content = _render_branding_html(content_branding_dir,
                                                        f_name,
                                                        branding_settings.color_scheme,
                                                        branding_settings.background_color,
                                                        branding_settings.text_color,
                                                        branding_settings.menu_item_color,
                                                        branding_settings.show_avatar,
                                                        {'language': language,
                                                         'loyalty_type': loyalty_settings.loyalty_type,
                                                         'auto_login_link': "%s&loyalty=1" % generate_auto_login_url(service_user),
                                                         'website': loyalty_settings.website})

                        content = content.encode('utf8')
                        logging.debug('Generated %s: %s', f_name, content)
                    elif f_name == 'logo.jpg':
                        solution_logo = get_solution_logo(service_user)
                        if solution_logo:
                            content = str(solution_logo.picture)

                    if not content:
                        if os.path.isdir(os.path.join(content_branding_dir, f_name)):
                            for f_name_in_map in os.listdir(os.path.join(content_branding_dir, f_name)):
                                with open(os.path.join(content_branding_dir, f_name, f_name_in_map)) as f:
                                    content = f.read()
                                if f_name == "js":
                                    if f_name_in_map == "app_translations.js":
                                        content = JINJA_ENVIRONMENT.get_template("content_branding/%s/%s" % (f_name, f_name_in_map)).render({'language': language}).encode("utf-8")
                                zip_.writestr("%s/%s" % (f_name, f_name_in_map), content)
                            content = None
                        else:
                            with open(os.path.join(content_branding_dir, f_name)) as f:
                                content = f.read()
                    if content:
                        zip_.writestr(f_name, content)

                zip_.writestr('img/osa_slide_overlay.png', get_loyalty_slide_footer())

            logging.info('Storing CONTENT branding')
            loyalty_settings.branding_key = put_branding(u'Content', base64.b64encode(stream.getvalue())).id
            loyalty_settings.branding_creation_time = now()
            loyalty_settings.put()

    return loyalty_settings


@returns(unicode)
def _render_branding_html(main_branding_dir, file_name, color_scheme, background_color, text_color, menu_item_color,
                          show_avatar, extra_params=None):
    if background_color is None:
        background_color = COLOR_BLACK if color_scheme == Branding.COLOR_SCHEME_DARK else COLOR_WHITE
    if text_color is None:
        text_color = Branding.DEFAULT_MENU_ITEM_COLORS[color_scheme]
    if menu_item_color is None:
        menu_item_color = Branding.DEFAULT_MENU_ITEM_COLORS[color_scheme]

    params = {
        'color_scheme': color_scheme,
        'background_color': '#%s' % background_color,
        'text_color': '#%s' % text_color,
        'menu_item_color': '#%s' % menu_item_color,
        'show_avatar': show_avatar
    }

    if extra_params:
        params.update(extra_params)

    jinja_environment = jinja2.Environment(loader=jinja2.FileSystemLoader([main_branding_dir]),
                                           extensions=[TranslateExtension])

    return jinja_environment.get_template(file_name).render(params)

def create_inbox_forwarding_flow(main_branding_key, main_language):
    flow_params = dict(branding_key=main_branding_key, language=main_language)
    flow = JINJA_ENVIRONMENT.get_template('flows/connect-inbox-via-scan.xml').render(flow_params)
    connect_inbox_via_scan_flow = system.put_flow(flow.encode('utf-8'), multilanguage=False)
    return connect_inbox_via_scan_flow.identifier

def create_inbox_forwarding_qr_code(service_identity, identifier):
    return qr.create("Receive inbox messages", POKE_TAG_CONNECT_INBOX_FORWARDER_VIA_SCAN, None, service_identity, identifier)


@returns()
@arguments(sln_calendar=SolutionCalendar, main_branding_key=unicode, main_language=unicode)
def _configure_calendar_admin_qr_code(sln_calendar, main_branding_key, main_language):
    qr_code = create_calendar_admin_qr_code(sln_calendar, main_branding_key, main_language)

    def trans():
        sc = db.get(sln_calendar.key())
        sc.connector_qrcode = qr_code.image_uri
        sc.put()
    db.run_in_transaction(trans)


@returns(QRDetailsTO)
@arguments(sc=SolutionCalendar, main_branding_key=unicode, main_language=unicode)
def create_calendar_admin_qr_code(sc, main_branding_key, main_language):
    flow_params = dict(branding_key=main_branding_key, language=main_language, calendar=sc)
    flow = JINJA_ENVIRONMENT.get_template('flows/events_connect_via_scan.xml').render(flow_params)
    connect_via_scan_flow = system.put_flow(flow.encode('utf-8'), multilanguage=False)
    info = json.dumps(dict(calendar_id=sc.calendar_id)).decode('utf8')
    tag = POKE_TAG_EVENTS_CONNECT_VIA_SCAN + info
    return qr.create("Calendar admin connect %s" % sc.name, tag, None, None, connect_via_scan_flow.identifier)


@returns(QRDetailsTO)
@arguments(service_identity=unicode)
def create_loyalty_admin_qr_code(service_identity):
    return qr.create("loyalty admin", POKE_TAG_LOYALTY_ADMIN, None, service_identity)


@returns()
@arguments(service_user=users.User)
def put_avatar_if_needed(service_user):
    sln_avatar = get_solution_avatar(service_user)
    if sln_avatar and not sln_avatar.published:
        system.put_avatar(base64.b64encode(sln_avatar.picture))
        sln_avatar.published = True
        sln_avatar.put()


@returns()
@arguments(sln_settings=SolutionSettings, main_branding_key=unicode, previous_main_branding_key=unicode)
def populate_identity(sln_settings, main_branding_key, previous_main_branding_key):
    """
    Args:
        sln_settings (SolutionSettings)
        main_branding_key (unicode)
        previous_main_branding_key (unicode)
    """
    search_config_locations = list()
    if sln_settings.location:
        location_to = ProfileLocationTO()
        location_to.address = sln_settings.address
        location_to.lat = long(sln_settings.location.lat * 1000000)
        location_to.lon = long(sln_settings.location.lon * 1000000)
        search_config_locations.append(location_to)

    content_branding_hash = None
    if SolutionModule.LOYALTY in sln_settings.modules or SolutionModule.HIDDEN_CITY_WIDE_LOTTERY in sln_settings.modules:
        solution_loyalty_settings = get_and_store_content_branding(sln_settings.service_user, sln_settings.main_language)
        content_branding_hash = solution_loyalty_settings.branding_key

    logging.info('Updating identities')  # idempotent
    identities = [None]
    if sln_settings.identities:
        identities.extend(sln_settings.identities)
    for service_identity in identities:
        sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
        search_config_locations = list()
        if sln_i_settings.location:
            location_to = ProfileLocationTO()
            location_to.address = sln_i_settings.address
            location_to.lat = long(sln_i_settings.location.lat * 1000000)
            location_to.lon = long(sln_i_settings.location.lon * 1000000)
            search_config_locations.append(location_to)

        logging.info('Updating identity %s', service_identity)  # idempotent
        identity = system.get_identity(service_identity)
        if not service_identity:
            default_app_name = identity.app_names[0]
            if SolutionModule.CITY_APP in sln_settings.modules:
                invalidate_service_user_for_city(identity.app_ids[0])
        identity.name = sln_i_settings.name
        identity.description = sln_i_settings.description
        identity.description_use_default = False
        # making sure we don't overwrite a custom description_branding
        logging.debug('identity.description_branding=%s <> previous_main_branding_key=%s',
                      identity.description_branding, previous_main_branding_key)
        if not identity.description_branding or identity.description_branding == previous_main_branding_key:
            identity.description_branding = main_branding_key
        identity.menu_branding = main_branding_key
        identity.phone_number = sln_i_settings.phone_number
        identity.phone_number_use_default = False
        identity.recommend_enabled = True
        identity.search_config.enabled = sln_settings.search_enabled
        identity.search_config.keywords = sln_i_settings.search_keywords
        identity.search_config.locations = search_config_locations
        identity.qualified_identifier = sln_i_settings.qualified_identifier
        identity.content_branding_hash = content_branding_hash
        default_app_id = identity.app_ids[0]

        app_data = create_app_data(sln_settings, service_identity, sln_i_settings, default_app_name, default_app_id)
        identity.app_data = json.dumps(app_data).decode('utf8')
        system.put_identity(identity)

        handle_auto_connected_service(sln_settings.service_user, sln_settings.search_enabled)


def handle_auto_connected_service(service_user, visible):
    from shop.models import Customer

    customer = Customer.get_by_service_email(service_user.email())
    if not customer:
        return
    if customer.organization_type != OrganizationType.CITY:
        return

    service_user = users.User(customer.service_email)
    service_identity_email = create_service_identity_user(service_user).email()
    app = App.get_by_key_name(customer.app_id)
    if app.type != App.APP_TYPE_CITY_APP:
        logging.debug('Not auto-connecting %s because "%s" is not a city app', customer.service_email, customer.app_id)
        return
    if app.demo:
        logging.debug('Not auto-connecting %s because "%s" is a demo app', customer.service_email, customer.app_id)
        return

    if visible:
        connected_services = app.auto_connected_services
        if not connected_services.get(service_identity_email):
            auto_connected_service = AutoConnectedService.create(service_identity_email, False, None, None)
            add_auto_connected_services(customer.app_id, [auto_connected_service])
    else:
        delete_auto_connected_service(service_user, customer.app_id, service_identity_email)


def create_app_data(sln_settings, service_identity, sln_i_settings, default_app_name, default_app_id):
    start = datetime.now()
    timezone_offsets = list()
    for _ in xrange(20):
        try:
            t = get_next_timezone_transition(sln_settings.timezone, start)
        except TypeError:
            timezone_offsets.append([0, now() + (DAY * 7 * 52 * 20), timezone_offset(sln_settings.timezone)])
            break
        if t is None:
            break
        timezone_offsets.append([int(time.mktime(start.timetuple())),
                                 int(time.mktime(t.activates.timetuple())),
                                 int(t.from_offset)])
        start = t.activates

    app_data = dict()
    holiday_dates = list()
    holiday_dates_str = list()
    cur_date = now()
    for d1, d2 in sln_i_settings.holiday_tuples:
    # don't include holidays in the past
        if cur_date < d2:
            holiday_dates.append({'from':d1, 'to':d2})
            holiday_dates_str.append(common_translate(sln_settings.main_language,
                                                      SOLUTION_COMMON,
                                                      'date_until_date',
                                                      from_date=format_date(datetime.fromtimestamp(d1, tz=get_timezone(sln_settings.timezone)),
                                                                            format='medium',
                                                                            locale=sln_settings.main_language),
                                                      until_date=format_date(datetime.fromtimestamp(d2, tz=get_timezone(sln_settings.timezone)),
                                                                             format='medium',
                                                                             locale=sln_settings.main_language)))

    address_url = None
    if sln_i_settings.address and sln_i_settings.location:
        address = sln_i_settings.address.replace("\r", " ").replace("\n", " ").replace("\t", " ")
        if isinstance(address, unicode):
            address = address.encode('utf-8')
        params = urllib.urlencode(dict(q=address,
                t=u"d"))
        address_url = u"https://maps.google.com/maps?%s" % params
    app_data['settings'] = {}
    app_data['settings']['app_name'] = default_app_name
    app_data['settings']['service_identity'] = service_identity or u"+default+"
    app_data['settings']['name'] = sln_i_settings.name
    app_data['settings']['address'] = sln_i_settings.address or None
    app_data['settings']['address_url'] = address_url
    app_data['settings']['opening_hours'] = sln_i_settings.opening_hours or None
    app_data['settings']['timezone'] = sln_settings.timezone
    app_data['settings']['timezoneOffset'] = timezone_offset(sln_settings.timezone)
    app_data['settings']['timezoneOffsets'] = timezone_offsets
    app_data['settings']['holidays'] = dict()
    app_data['settings']['holidays']['dates'] = holiday_dates
    app_data['settings']['holidays']['dates_str'] = holiday_dates_str
    if not sln_i_settings.holiday_out_of_office_message:
        sln_i_settings.holiday_out_of_office_message = common_translate(sln_settings.main_language, SOLUTION_COMMON,
            'holiday-out-of-office')
    app_data['settings']['holidays']['out_of_office_message'] = xml_escape(sln_i_settings.holiday_out_of_office_message)
    app_data['settings']['modules'] = sln_settings.modules
    for module, get_app_data_func in MODULES_GET_APP_DATA_FUNCS.iteritems():
        if module in sln_settings.modules:
            get_app_data_func = MODULES_GET_APP_DATA_FUNCS[module]
            app_data.update(get_app_data_func(sln_settings, service_identity, default_app_id))

    return app_data


@returns()
@arguments(sln_settings=SolutionSettings, main_branding_key=unicode)
def populate_identity_and_publish(sln_settings, main_branding_key):
    users.set_user(sln_settings.service_user)
    try:
        populate_identity(sln_settings, main_branding_key, main_branding_key)
        system.publish_changes()
    finally:
        users.clear_user()


@returns(dict)
@arguments(sln_settings=SolutionSettings, service_identity=unicode, default_app_id=unicode)
def get_app_data_agenda(sln_settings, service_identity, default_app_id):
    events = sorted(get_event_list(sln_settings.service_user, sln_settings.solution), key=lambda e: e.get_first_event_date())
    event_items = []
    size = 0
    for i in xrange(len(events)):
        event_items.append(EventItemTO.fromEventItemObject(events[i]))
        size += len(json.dumps(serialize_complex_value(event_items[-1], EventItemTO, False)))
        if size > 600 * 1024:
            del event_items[len(event_items) - 1]
            break
    logging.debug("reducing events from agenda %s/%s = %s" % (len(event_items), len(events), size))
    calendar_items = [SolutionCalendarTO.fromSolutionCalendar(sln_settings, c)
                      for c in get_solution_calendars(sln_settings.service_user, sln_settings.solution)]

    solution_events = serialize_complex_value(event_items, EventItemTO, True)
    solution_calendars = serialize_complex_value(calendar_items, SolutionCalendarTO, True)

    if SolutionModule.CITY_APP in sln_settings.modules:
        city_app_profile_key = CityAppProfile.create_key(sln_settings.service_user)

        def trans():
            city_app_profile = CityAppProfile.get(city_app_profile_key)
            events_per_type = {}
            if city_app_profile and city_app_profile.gather_events_enabled and city_app_profile.gather_events:
                for organization_type in CityAppProfile.EVENTS_ORGANIZATION_TYPES:
                    events_stream = city_app_profile.gather_events.get(unicode(organization_type))
                    if events_stream is not None:
                        events_per_type[organization_type] = json.load(events_stream)
            return events_per_type

        events_per_organization_type = db.run_in_transaction(trans)
        lang = sln_settings.main_language
        for organization_type in events_per_organization_type:
            events = events_per_organization_type[organization_type]
            if events:
                solution_events.extend(events)
                name = ServiceProfile.localized_plural_organization_type(organization_type, lang, default_app_id)
                calendar = SolutionCalendarTO(organization_type, name)
                solution_calendars.append(serialize_complex_value(calendar, SolutionCalendarTO, False))

    return {
        'timezoneOffset': timezone_offset(sln_settings.timezone),
        'solutionEvents': solution_events,
        'solutionCalendars': solution_calendars
    }


@returns(dict)
@arguments(sln_settings=SolutionSettings, service_identity=unicode, default_app_id=unicode)
def get_app_data_broadcast(sln_settings, service_identity, default_app_id):
    with users.set_user(sln_settings.service_user):
        si = system.get_info(service_identity)

    def transl(key):
        try:
            return common_translate(sln_settings.main_language, SOLUTION_COMMON, key, suppress_warning=True)
        except:
            return key

    broadcast_types = map(transl, sln_settings.broadcast_types)
    broadcast_target_audience = {}
    # get current apps of customer and set it as target audience
    for app_id, app_name in zip(si.app_ids, si.app_names):
        if app_id == App.APP_ID_ROGERTHAT and len(broadcast_target_audience) > 0:
            continue  # Rogerthat is not the default app. Don't show it.
        elif app_id == App.APP_ID_OSA_LOYALTY:
            continue  # Don't show the OSA Terminal app
        broadcast_target_audience[app_id] = app_name

    return dict(broadcast_types=broadcast_types,
                broadcast_target_audience=broadcast_target_audience)


@returns(dict)
@arguments(sln_settings=SolutionSettings, service_identity=unicode, default_app_id=unicode)
def get_app_data_group_purchase(sln_settings, service_identity, default_app_id):
    group_purchases = [SolutionGroupPurchaseTO.fromModel(m) for m in SolutionGroupPurchase.list(sln_settings.service_user, service_identity, sln_settings.solution)]
    return dict(currency=sln_settings.currency,
                solutionGroupPurchases=serialize_complex_value(group_purchases, SolutionGroupPurchaseTO, True))

@returns(dict)
@arguments(sln_settings=SolutionSettings, service_identity=unicode, default_app_id=unicode)
def get_app_data_loyalty(sln_settings, service_identity, default_app_id):
    app_data = dict(currency=sln_settings.currency)
    loyalty_settings = SolutionLoyaltySettings.get_by_user(sln_settings.service_user)
    if loyalty_settings.loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_REVENUE_DISCOUNT:
        app_data["loyalty"] = {"settings": serialize_complex_value(loyalty_settings, LoyaltyRevenueDiscountSettingsTO, False)}
    elif loyalty_settings.loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_LOTTERY:
        app_data["loyalty_2"] = {"dates": list()}
        ll_info = SolutionLoyaltyLottery.load_pending(sln_settings.service_user, service_identity)
        if ll_info:
            app_data["loyalty_2"]["dates"].append({"date": serialize_complex_value(TimestampTO.fromEpoch(ll_info.end_timestamp), TimestampTO, False),
                                                   "winnings": ll_info.winnings})
    elif loyalty_settings.loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_STAMPS:
        app_data["loyalty_3"] = {"settings": serialize_complex_value(loyalty_settings, LoyaltyStampsSettingsTO, False)}

    return app_data


@returns(dict)
@arguments(sln_settings=SolutionSettings, service_identity=unicode, default_app_id=unicode)
def get_app_data_sandwich_bar(sln_settings, service_identity, default_app_id):
    service_user = sln_settings.service_user
    sandwich_settings = SandwichSettings.get_settings(service_user, sln_settings.solution)
    return {
        'sandwich_settings': {
            'status_days': sandwich_settings.status_days,
            'time_from': sandwich_settings.time_from,
            'time_until': sandwich_settings.time_until,
            'days': SandwichSettings.DAYS_JS,
            'leap_time': sandwich_settings.leap_time * sandwich_settings.leap_time_type,
            'leap_time_enabled': sandwich_settings.leap_time_enabled
        }
    }


@returns(dict)
@arguments(sln_settings=SolutionSettings, service_identity=unicode, default_app_id=unicode)
def get_app_data_city_vouchers(sln_settings, service_identity, default_app_id):
    return dict(currency=sln_settings.currency)


def _configure_inbox_qr_code_if_needed(sln_settings, main_branding):
    # type: (SolutionSettings, SolutionMainBranding) -> None
    if not sln_settings.uses_inbox():
        return
    identities = [None]
    if sln_settings.identities:
        identities.extend(sln_settings.identities)
    flow_identifier = create_inbox_forwarding_flow(main_branding.branding_key, sln_settings.main_language)
    for service_identity in identities:
        sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
        if not sln_i_settings.inbox_connector_qrcode:
            if db.is_in_transaction():
                on_trans_committed(_configure_inbox_forwarding_qr_code, sln_settings.service_user, service_identity,
                                   flow_identifier)
            else:
                _configure_inbox_forwarding_qr_code(sln_settings.service_user, service_identity, flow_identifier)


@returns()
@arguments(sln_settings=SolutionSettings, coords_dict=dict, main_branding=SolutionMainBranding, default_lang=unicode)
def provision_all_modules(sln_settings, coords_dict, main_branding, default_lang):
    for module in sln_settings.modules:
        # Check if coords are supplied for each module in settings.modules
        azzert(module in coords_dict)
        # Check if put/delete funcs are created for each module in settings.modules
        azzert(module in MODULES_PUT_FUNCS)
        azzert(module in MODULES_DELETE_FUNCS)

    if not sln_settings.provisioned_modules:
        sln_settings.provisioned_modules = []

    service_menu = system.get_menu()
    for provisioned_module in sln_settings.provisioned_modules:
        if provisioned_module not in sln_settings.modules:
            logging.info("should remove module: %s", provisioned_module)
            current_coords = get_coords_of_service_menu_item(service_menu, POKE_TAGS[provisioned_module])
            delete_func = MODULES_DELETE_FUNCS[provisioned_module]
            delete_func(sln_settings, current_coords, service_menu)

        if coords_dict[provisioned_module]:
            for tag in coords_dict[provisioned_module]:
                if coords_dict[provisioned_module][tag]["preferred_page"] == -1:
                    current_coords = get_coords_of_service_menu_item(service_menu, tag)
                    _default_delete(sln_settings, current_coords, service_menu)
    sln_settings.provisioned_modules = []

    _configure_inbox_qr_code_if_needed(sln_settings, main_branding)
    ssmi_modules = {}
    for module in sorted(sln_settings.modules, key=lambda m: SolutionModule.PROVISION_ORDER[m]):
        current_coords = get_coords_of_service_menu_item(service_menu, POKE_TAGS[module])
        put_func = MODULES_PUT_FUNCS[module]
        if module == SolutionModule.BROADCAST:
            auto_broadcast_types = list()
            for ssmi_list in ssmi_modules.itervalues():
                for ssmi in ssmi_list:
                    auto_broadcast_types.extend(ssmi.broadcast_types)
            ssmi_modules[module] = put_func(sln_settings, current_coords, main_branding, default_lang,
                                            POKE_TAGS[module], auto_broadcast_types)
        else:
            ssmi_modules[module] = put_func(sln_settings, current_coords, main_branding, default_lang,
                                            POKE_TAGS[module])
        sln_settings.provisioned_modules.append(module)

    ssmi_to_put = []
    for module in ssmi_modules:
        for ssmi in ssmi_modules[module]:
            if ssmi.coords:
                if service_menu:
                    for item in reversed(service_menu.items):
                        if item.coords == ssmi.coords:
                            service_menu.items.remove(item)
                coords = ssmi.coords
                priority = 99
                preferred_page = ssmi.coords[2]
            else:
                coords = get_coords_of_service_menu_item(service_menu, ssmi.tag)
                priority = 0
                preferred_page = 0
            if not coords:
                try:
                    coords = coords_dict[module][ssmi.tag]["coords"]
                    priority = coords_dict[module][ssmi.tag]["priority"]
                    preferred_page = coords_dict[module][ssmi.tag]["preferred_page"]
                except KeyError:
                    logging.error("KeyError for module '%s' and tag '%s'", module, ssmi.tag)
                    raise
            ssmi_to_put.append({"tag": ssmi.tag,
                                "ssmi": ssmi,
                                "preferred_page": preferred_page,
                                "coords": coords,
                                "priority": priority})

    def menu_sorting_key(ssmi):
        """ sort the menu items according to:
            1- preferred_page: is -1 or not (>= 0 is better)
            2- priority: higher is better
            3- label
         """
        if ssmi["preferred_page"] == -1:
            page_key = 1
        else:
            page_key = 0
        return page_key, -ssmi["priority"], ssmi["ssmi"].label

    all_taken_coords = [item.coords for item in service_menu.items]
    sorted_ssmis = sorted(ssmi_to_put, key=menu_sorting_key)
    last_prefered_page = max([m['preferred_page'] for m in sorted_ssmis]) + 1 if sorted_ssmis else 0
    for ssmi_dict in sorted_ssmis:
        coords = ssmi_dict["coords"]
        preferred_page = ssmi_dict["preferred_page"]
        ssmi = ssmi_dict["ssmi"]
        if preferred_page == -1:
            preferred_page = last_prefered_page

        if coords == [-1, -1, -1] or (ssmi_dict["priority"] != 0 and (coords in all_taken_coords)):
            new_coords = get_next_free_spot_in_service_menu(all_taken_coords, preferred_page)
            logging.debug("Got next free spot %s instead of preferred spot %s for %s", new_coords, coords, ssmi.label)
            coords = new_coords
        # after getting the new coords, check again if the original
        # preferred page is not -1, then set it + 1 as the last preferred page
        if coords[2] >= last_prefered_page and ssmi_dict["preferred_page"] != -1:
            last_prefered_page = coords[2] + 1

        logging.debug("Putting menu item at %s: %s",
                      coords, serialize_complex_value(ssmi, SolutionServiceMenuItem, False))

        args = [ssmi.icon_name, ssmi.label, ssmi.tag, coords, ssmi.icon_color, ssmi.screen_branding, ssmi.static_flow,
                ssmi.requires_wifi, ssmi.run_in_background, ssmi.is_broadcast_settings, ssmi.broadcast_branding,
                ssmi.roles, ssmi.action, ssmi.link]
        if db.is_in_transaction():
            on_trans_committed(system.put_menu_item, *args)
        else:
            system.put_menu_item(*args)

        if coords not in all_taken_coords:
            all_taken_coords.append(coords)

    put_and_invalidate_cache(sln_settings)


@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_agenda(sln_settings, current_coords, main_branding, default_lang, tag):

    ssmis = []
    role_id = None
    roles = system.list_roles()
    for role in roles:
        if role.name == POKE_TAG_NEW_EVENT:
            role_id = role.id
            break
    if not role_id:
        role_id = system.put_role(POKE_TAG_NEW_EVENT, ServiceRole.TYPE_MANAGED)

    ssmi = SolutionServiceMenuItem(u"fa-plus-square-o",
                                   sln_settings.menu_item_color,
                                   common_translate(default_lang, SOLUTION_COMMON, 'create-event'),
                                   POKE_TAG_NEW_EVENT,
                                   roles=[role_id],
                                   action=SolutionModule.action_order(SolutionModule.AGENDA))
    ssmis.append(ssmi)

    if not sln_settings.default_calendar:
        def trans():
            sc = SolutionCalendar(parent=parent_key(sln_settings.service_user, sln_settings.solution),
                                  name="Default",
                                  deleted=False)
            sc.put()
            sln_settings.default_calendar = sc.calendar_id
            put_and_invalidate_cache(sln_settings)
            return sc

        xg_on = db.create_transaction_options(xg=True)
        sc = db.run_in_transaction_options(xg_on, trans)

        if db.is_in_transaction():
            on_trans_committed(_configure_calendar_admin_qr_code, sc, main_branding.branding_key, sln_settings.main_language)
        else:
            _configure_calendar_admin_qr_code(sc, main_branding.branding_key, sln_settings.main_language)

    if sln_settings.events_visible:
        provision_events_branding(sln_settings, main_branding, default_lang)

        # Configure automatic broadcast types
        broadcast_types = list()
        for c in get_solution_calendars(sln_settings.service_user, sln_settings.solution, True):
            broadcast_types.append(common_translate(default_lang, SOLUTION_COMMON, u'calendar-broadcast-type') % dict(name=c.name))
        SolutionAutoBroadcastTypes(key_name=SolutionModule.AGENDA, parent=sln_settings, broadcast_types=broadcast_types).put()

        if default_lang == "nl" and SolutionModule.CITY_APP in sln_settings.modules:
            icon = u"uit"
            label = u"in %s" % sln_settings.name
        else:
            icon = u"fa-book"
            label = common_translate(default_lang, SOLUTION_COMMON, 'agenda')

        ssmi = SolutionServiceMenuItem(icon,
                                       sln_settings.menu_item_color,
                                       label,
                                       tag,
                                       screen_branding=sln_settings.events_branding_hash,
                                       broadcast_types=broadcast_types,
                                       action=SolutionModule.action_order(SolutionModule.AGENDA))
        ssmis.append(ssmi)
    else:
        delete_agenda_item(sln_settings, current_coords, None)

    return ssmis


@returns(NoneType)
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], service_menu=ServiceMenuDetailTO)
def delete_agenda_item(sln_settings, current_coords, service_menu):
    _default_delete(sln_settings, current_coords, service_menu)
    SolutionAutoBroadcastTypes(key_name=SolutionModule.AGENDA, parent=sln_settings, broadcast_types=list()).put()

@returns(NoneType)
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], service_menu=ServiceMenuDetailTO)
def delete_qr_codes(sln_settings, current_coords, service_menu):
    identities = [None]
    if sln_settings.identities:
        identities.extend(sln_settings.identities)
    for service_identity in identities:
        db.delete(SolutionQR.list_by_user(sln_settings.service_user, service_identity, sln_settings.solution))

@returns(NoneType)
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], service_menu=ServiceMenuDetailTO)
def delete_agenda(sln_settings, current_coords, service_menu):
    delete_agenda_item(sln_settings, current_coords, service_menu)
    current_coords = get_coords_of_service_menu_item(service_menu, POKE_TAG_NEW_EVENT)
    _default_delete(sln_settings, current_coords, service_menu)

    admins_to_delete = []
    for admin_key in SolutionCalendarAdmin.all(keys_only=True).ancestor(parent_key(sln_settings.service_user, sln_settings.solution)):
        admins_to_delete.append(admin_key)

    db.delete(admins_to_delete)
    role_id = None
    roles = system.list_roles()
    for role in roles:
        if role.name == POKE_TAG_NEW_EVENT:
            role_id = role.id
            break
    if role_id:
        on_trans_committed(system.delete_role, role_id, True)


@returns(NoneType)
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], service_menu=ServiceMenuDetailTO)
def delete_broadcast(sln_settings, current_coords, service_menu):
    """like delete_agenda but for broadcast"""
    _default_delete(sln_settings, current_coords, service_menu)
    # create news menu
    create_news_coords = get_coords_of_service_menu_item(service_menu,
                                                         POKE_TAG_BROADCAST_CREATE_NEWS)
    _default_delete(sln_settings, create_news_coords, service_menu)

    news_publishers = get_solution_news_publishers(sln_settings.service_user,
                                                   sln_settings.solution)

    role_id = None
    roles = filter(lambda r: r.name == POKE_TAG_BROADCAST_CREATE_NEWS,
                   system.list_roles())

    if roles:
        role_id = roles[0].id

    def trans():
        db.delete(news_publishers)
        if role_id:
            system.delete_role(role_id, cleanup_members=True)

    if db.is_in_transaction():
        on_trans_committed(trans)
    else:
        db.run_in_transaction(trans)


@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_static_content(sln_settings, current_coords, main_branding, default_lang, tag):
    menu_items = list()
    to_put = list()
    to_delete = list()
    for sc in SolutionStaticContent.list_changed(sln_settings.service_user):  # type: SolutionStaticContent
        system.delete_menu_item(sc.old_coords)
        if sc.deleted:
            to_delete.append(sc)
        else:
            if sc.visible:
                logging.debug('Creating static content menu item \"%s\"' % sc.icon_label)
                link = None
                if sc.sc_type == SolutionStaticContent.TYPE_WEBSITE:
                    link = ServiceMenuItemLinkTO()
                    link.url = sc.website
                    link.external = False
                menu_items.append(SolutionServiceMenuItem(sc.icon_name, sln_settings.menu_item_color, sc.icon_label,
                                                          u'%s%s' % (STATIC_CONTENT_TAG_PREFIX, sc.icon_label),
                                                          sc.branding_hash, coords=map(int, sc.coords), link=link))
            sc.provisioned = True
            sc.old_coords = map(int, sc.coords)
            to_put.append(sc)
    if to_put:
        db.put(to_put)
    if to_delete:
        db.delete(to_delete)
    return menu_items


@returns(NoneType)
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], service_menu=ServiceMenuDetailTO)
def delete_static_content(sln_settings, current_coords, service_menu):
    db.delete(get_static_content_keys(sln_settings.service_user, sln_settings.solution))


@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_appointment(sln_settings, current_coords, main_branding, default_lang, tag):
    logging.info('Creating APPOINTMENT message flow')

    def timeframe_sort(tf1, tf2):
        if tf1.day < tf2.day:
            return -1
        if tf1.day > tf2.day:
            return 1

        if tf1.time_from < tf2.time_from:
            return -1
        if tf1.time_from > tf2.time_from:
            return 1

        if tf1.time_until < tf2.time_until:
            return -1
        if tf1.time_until > tf2.time_until:
            return 1
        return 0

    timeframes = list(SolutionAppointmentWeekdayTimeframe.list(sln_settings.service_user, sln_settings.solution))
    if not timeframes:
        _default_delete(sln_settings, current_coords)
        return []

    timeframes.sort(timeframe_sort)

    for tf in timeframes:
        tf.label_str = tf.label(default_lang)

    text_1 = None
    sln_appointment_settings = get_solution_appointment_settings(sln_settings.service_user)
    if sln_appointment_settings:
        text_1 = sln_appointment_settings.text_1

    if not text_1:
        text_1 = common_translate(default_lang, SOLUTION_COMMON, 'appointment-1')

    flow_params = dict(branding_key=main_branding.branding_key, language=default_lang, timeframes=timeframes,
                       text_1=text_1, settings=sln_settings)
    flow = JINJA_ENVIRONMENT.get_template('flows/appointment.xml').render(flow_params)
    appointment_flow = system.put_flow(flow.encode('utf-8'), multilanguage=False)
    logging.info('Creating APPOINTMENT menu item')
    ssmi = SolutionServiceMenuItem(u'fa-calendar-plus-o',
                                   sln_settings.menu_item_color,
                                   common_translate(default_lang, SOLUTION_COMMON, 'appointment'),
                                   tag,
                                   static_flow=appointment_flow.identifier,
                                   action=SolutionModule.action_order(SolutionModule.APPOINTMENT))

    return [ssmi]


@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_ask_question(sln_settings, current_coords, main_branding, default_lang, tag):
    logging.info('Creating ASK QUESTION message flow')

    flow_params = dict(branding_key=main_branding.branding_key,
                       language=default_lang,
                       settings=sln_settings,
                       SolutionModule=SolutionModule)
    flow = JINJA_ENVIRONMENT.get_template('flows/ask_question.xml').render(flow_params)
    ask_question_flow = system.put_flow(flow.encode('utf-8'), multilanguage=False)

    ssmi = SolutionServiceMenuItem(u'fa-comments-o',
                                   sln_settings.menu_item_color,
                                   common_translate(default_lang, SOLUTION_COMMON, 'ask-question'),
                                   tag,
                                   static_flow=ask_question_flow.identifier,
                                   action=SolutionModule.action_order(SolutionModule.ASK_QUESTION))
    return [ssmi]


@returns()
@arguments(service_user=users.User, service_identity=unicode, flow_identifier=unicode)
def _configure_inbox_forwarding_qr_code(service_user, service_identity, flow_identifier):
    qrcode = create_inbox_forwarding_qr_code(service_identity, flow_identifier)
    def trans():
        if is_default_service_identity(service_identity):
            sln_i_settings = get_solution_settings(service_user)
        else:
            sln_i_settings = get_solution_identity_settings(service_user, service_identity)
        sln_i_settings.inbox_connector_qrcode = qrcode.image_uri
        sln_i_settings.put()
    db.run_in_transaction(trans)


@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode, auto_broadcast_types=[unicode])
def put_broadcast(sln_settings, current_coords, main_branding, default_lang, tag, auto_broadcast_types):
    logging.info('Saving broadcast types')

    def transl(key):
        try:
            return common_translate(default_lang, SOLUTION_COMMON, key, suppress_warning=True)
        except:
            return key

    broadcast_types = map(transl, sln_settings.broadcast_types)
    broadcast_types.extend(auto_broadcast_types)

    system.put_broadcast_types(broadcast_types)

    ssmi = SolutionServiceMenuItem(u'fa-bell',
                                   sln_settings.menu_item_color,
                                   common_translate(default_lang, SOLUTION_COMMON, 'broadcast-settings'),
                                   tag,
                                   is_broadcast_settings=True,
                                   broadcast_branding=main_branding.branding_key,
                                   action=SolutionModule.action_order(SolutionModule.BROADCAST))

    create_news_ssmi = _configure_broadcast_create_news(sln_settings, main_branding,
                                                        default_lang, POKE_TAG_BROADCAST_CREATE_NEWS)

    return [ssmi, create_news_ssmi]


@returns()
@arguments(sln_settings=SolutionSettings, flow_identifier=unicode)
def _configure_create_news_qr_code(sln_settings, flow_identifier):
    """ the same as _configure_connect_qr_code """
    identities = [None]
    if sln_settings.identities:
        identities.extend(sln_settings.identities)
    for service_identity in identities:
        sln_i_settings = get_solution_settings_or_identity_settings(sln_settings,
                                                                    service_identity)
        if sln_i_settings:
            create_news_qr_uri = sln_i_settings.broadcast_create_news_qrcode

            if not create_news_qr_uri:
                description = common_translate(sln_settings.main_language,
                                               SOLUTION_COMMON,
                                               'create-news-from-mobile')
                qr_code = qr.create(description, POKE_TAG_BROADCAST_CREATE_NEWS_CONNECT,
                                    None, service_identity, flow_identifier)
                sln_i_settings.broadcast_create_news_qrcode = qr_code.image_uri
                sln_i_settings.put()


@returns(SolutionServiceMenuItem)
@arguments(sln_settings=SolutionSettings, main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def _configure_broadcast_create_news(sln_settings, main_branding, default_lang, tag):
    logging.info('Creating broadcast publish/create news flow')
    loyalty_enabled = SolutionModule.LOYALTY in sln_settings.modules
    flow_params = dict(branding_key=main_branding.branding_key,
                       language=default_lang,
                       loyalty_enabled=loyalty_enabled)
    create_news_flow_template = JINJA_ENVIRONMENT.get_template('flows/publish_news.xml').render(flow_params)
    create_news_flow = system.put_flow(create_news_flow_template.encode('utf-8'))

    qr_connect_template = JINJA_ENVIRONMENT.get_template('flows/news_publisher_connect_via_scan.xml').render(flow_params)
    qr_connect_flow = system.put_flow(qr_connect_template.encode('utf-8'))
    roles = filter(lambda r: r.name == POKE_TAG_BROADCAST_CREATE_NEWS,
                  system.list_roles())
    if roles:
        role_id = roles[0].id
    else:
        role_id = system.put_role(POKE_TAG_BROADCAST_CREATE_NEWS,
                                  ServiceRole.TYPE_MANAGED)

    ssmi = SolutionServiceMenuItem(u'fa-newspaper-o',
                                   sln_settings.menu_item_color,
                                   common_translate(default_lang, SOLUTION_COMMON, 'create_news'),
                                   tag=tag,
                                   roles=[role_id],
                                   static_flow=create_news_flow.identifier,
                                   action=SolutionModule.action_order(SolutionModule.BROADCAST))

    # add qr code to identities
    # wait until transactions are done first
    if db.is_in_transaction():
        on_trans_committed(_configure_create_news_qr_code, sln_settings, qr_connect_flow.identifier)
    else:
        _configure_create_news_qr_code(sln_settings, qr_connect_flow.identifier)

    return ssmi

@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_group_purchase(sln_settings, current_coords, main_branding, default_lang, tag):
    service_user = sln_settings.service_user
    sgps = get_solution_group_purchase_settings(service_user, sln_settings.solution)
    if sgps.visible:
        provision_group_purchase_branding(sgps, main_branding, default_lang)

        ssmi = SolutionServiceMenuItem(u'fa-shopping-cart',
                                       sln_settings.menu_item_color,
                                       common_translate(default_lang, SOLUTION_COMMON, 'group-purchase'),
                                       tag,
                                       screen_branding=sgps.branding_hash,
                                       action=SolutionModule.action_order(SolutionModule.GROUP_PURCHASE))

        return [ssmi]
    else:
        _default_delete(sln_settings, current_coords)
        return []

@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_loyalty(sln_settings, current_coords, main_branding, default_lang, tag):
    service_user = sln_settings.service_user

    identities = [None]
    if sln_settings.identities:
        identities.extend(sln_settings.identities)
    for service_identity in identities:
        if is_default_service_identity(service_identity):
            loyalty_settings = SolutionLoyaltySettings.get_by_user(service_user)
            should_put = False
            if not loyalty_settings:
                logging.debug('Creating new SolutionLoyaltySettings')
                should_put = True
                loyalty_settings = SolutionLoyaltySettings(key=SolutionLoyaltySettings.create_key(service_user))
                system.put_callback("friend.register", True)
                system.put_callback("friend.register_result", True)
            if not loyalty_settings.image_uri:
                qr_code = create_loyalty_admin_qr_code(service_identity)
                should_put = True
                loyalty_settings.image_uri = qr_code.image_uri
                loyalty_settings.content_uri = qr_code.content_uri
            if should_put:
                loyalty_settings.put()
        else:
            sln_li_settings = SolutionLoyaltyIdentitySettings.get_by_user(service_user, service_identity)
            if not sln_li_settings:
                logging.debug('Creating new SolutionLoyaltyIdentitySettings')
                should_put = True
                sln_li_settings = SolutionLoyaltyIdentitySettings(key=SolutionLoyaltyIdentitySettings.create_key(service_user, service_identity))
            if not sln_li_settings.image_uri:
                qr_code = create_loyalty_admin_qr_code(service_identity)
                should_put = True
                sln_li_settings.image_uri = qr_code.image_uri
                sln_li_settings.content_uri = qr_code.content_uri
                sln_li_settings.put()
            if should_put:
                sln_li_settings.put()


    if loyalty_settings.loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_CITY_WIDE_LOTTERY:
        logging.info("Clearing LOYALTY icon")
        _default_delete(sln_settings, current_coords)
        return []

    logging.info('Creating LOYALTY screen branding')
    provision_loyalty_branding(sln_settings, main_branding, default_lang, loyalty_settings.loyalty_type)

    ssmi = SolutionServiceMenuItem(u"fa-credit-card",
                                   sln_settings.menu_item_color,
                                   common_translate(default_lang, SOLUTION_COMMON, 'loyalty'),
                                   tag,
                                   screen_branding=sln_settings.loyalty_branding_hash,
                                   action=SolutionModule.action_order(SolutionModule.LOYALTY))

    return [ssmi]

@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_menu(sln_settings, current_coords, main_branding, default_lang, tag):
    service_user = sln_settings.service_user
    menu = get_restaurant_menu(service_user)
    if not menu:
        logging.info('Creating default menu')
        menu = _put_default_menu(sln_settings.service_user,
                                 lambda name: common_translate(default_lang, SOLUTION_COMMON, name),
                                 sln_settings.solution)

    logging.info('Creating MENU screen branding')
    menu = MenuTO.fromMenuObject(menu)
    for cat in menu.categories:
        cat.has_visible = False
        for item in cat.items:
            if is_flag_set(MenuItem.VISIBLE_IN_MENU, item.visible_in):
                item.visible = True
                cat.has_visible = True
            else:
                item.visible = False

    template_dict = {'menu': menu, 'currency': sln_settings.currency}
    content = render_common_content(default_lang, 'brandings/menu.tmpl', template_dict)
    menu_branding = generate_branding(main_branding, u'menu', content)

    ssmi = SolutionServiceMenuItem(u'fa-list',
                                   sln_settings.menu_item_color,
                                   menu.name or common_translate(default_lang, SOLUTION_COMMON, 'menu'),
                                   tag,
                                   screen_branding=menu_branding.id,
                                   action=SolutionModule.action_order(SolutionModule.MENU))

    return [ssmi]


def put_menu_item_image_upload_flow(main_branding_key, language):
    flow_params = dict(branding_key=main_branding_key, language=language)
    menu_item_image_flow = JINJA_ENVIRONMENT.get_template('flows/upload_menu_item_image.xml').render(flow_params)
    system.put_flow(menu_item_image_flow.encode('utf-8'), multilanguage=False)


def _put_advanced_order_flow(sln_settings, sln_order_settings, main_branding, lang):
    menu = MenuTO.fromMenuObject(RestaurantMenu.get(RestaurantMenu.create_key(sln_settings.service_user,
                                                                              sln_settings.solution)))
    holiday_dates_str = list()
    holiday_dates = list()
    orderable_times = list()
    orderable_times_str = StringIO()
    leap_time = sln_order_settings.leap_time * sln_order_settings.leap_time_type

    if sln_order_settings.leap_time_type == SECONDS_IN_MINUTE:
        if sln_order_settings.leap_time > 1:
            leap_time_message = common_translate(lang, SOLUTION_COMMON, 'advanced_order_leaptime_minutes_x', minutes=sln_order_settings.leap_time)
        else:
            leap_time_message = common_translate(lang, SOLUTION_COMMON, 'advanced_order_leaptime_minutes_1')
    elif sln_order_settings.leap_time_type == SECONDS_IN_HOUR:
        if sln_order_settings.leap_time > 1:
            leap_time_message = common_translate(lang, SOLUTION_COMMON, 'advanced_order_leaptime_hours_x', hours=sln_order_settings.leap_time)
        else:
            leap_time_message = common_translate(lang, SOLUTION_COMMON, 'advanced_order_leaptime_hours_1')
    elif sln_order_settings.leap_time_type == SECONDS_IN_DAY:
        if sln_order_settings.leap_time > 1:
            leap_time_message = common_translate(lang, SOLUTION_COMMON, 'advanced_order_leaptime_days_x', days=sln_order_settings.leap_time)
        else:
            leap_time_message = common_translate(lang, SOLUTION_COMMON, 'advanced_order_leaptime_days_1')
    else:
        if sln_order_settings.leap_time > 1:
            leap_time_message = common_translate(lang, SOLUTION_COMMON, 'advanced_order_leaptime_weeks_x', weeks=sln_order_settings.leap_time)
        else:
            leap_time_message = common_translate(lang, SOLUTION_COMMON, 'advanced_order_leaptime_weeks_1')

    multiple_locations = True
    if not sln_settings.identities:
        multiple_locations = False
        cur_date = now()
        for d1, d2 in sln_settings.holiday_tuples:
            if d2 > cur_date:
                holiday_dates.append({
                    'from': d1,
                    'to': d2
                })
                holiday_dates_str.append(
                    common_translate(lang, SOLUTION_COMMON, 'date_until_date') % {
                        'from_date': format_date(datetime.fromtimestamp(d1, tz=get_timezone(sln_settings.timezone)),
                                                 format='medium',
                                                 locale=lang),
                        'until_date': format_date(datetime.fromtimestamp(d2, tz=get_timezone(sln_settings.timezone)),
                                                  format='medium',
                                                  locale=lang)
                    }
                )

    leap_time_str = format_timedelta(timedelta(seconds=leap_time), locale=lang)
    for t in SolutionOrderWeekdayTimeframe.list(sln_settings.service_user, sln_settings.solution):
        orderable_times_str.write('\\n')  # needs to be double-escaped because it's used in a JS string
        orderable_times_str.write(t.label(lang).encode('utf-8'))
        orderable_times.append(t)

    server_settings = get_server_settings()
    category_count = 0
    for cat in menu.categories:
        cat.has_visible = False
        for item in cat.items:
            if is_flag_set(MenuItem.VISIBLE_IN_ORDER, item.visible_in):
                item.visible = True
                if not cat.has_visible:
                    cat.has_visible = True
                    category_count += 1
            else:
                item.visible = False
            item.unit_str = solutions.translate_unit_symbol(lang, item.unit)
            item.step_unit = None
            item.step_unit_conversion = 0
            if item.unit == UNIT_GRAM:
                item.step_unit = solutions.translate_unit_symbol(lang, UNIT_KG)
                item.step_unit_conversion = 1000

            if item.image_id:
                item.image_url = get_item_image_url(item.image_id, server_settings)
            else:
                item.image_url = None

    if category_count == 0:
        return None

    start = datetime.now()
    timezone_offsets = list()
    for _ in xrange(20):
        try:
            t = get_next_timezone_transition(sln_settings.timezone, start)
        except TypeError:
            timezone_offsets.append([0, now() + (DAY * 7 * 52 * 20), timezone_offset(sln_settings.timezone)])
            break
        if t is None:
            break
        timezone_offsets.append([int(time.mktime(start.timetuple())),
                                 int(time.mktime(t.activates.timetuple())),
                                 int(t.from_offset)])
        start = t.activates

    flow_params = dict(
        branding_key=main_branding.branding_key,
        language=lang,
        settings=sln_settings,
        menu=menu,
        multiple_locations=multiple_locations,
        holiday_dates_str=xml_escape(json.dumps(holiday_dates_str)),
        holiday_dates=xml_escape(json.dumps(holiday_dates)),
        orderable_times=xml_escape(json.dumps(
            [{'time_from': o.time_from, 'time_until': o.time_until, 'day': (o.day + 8) % 7 } for o in orderable_times])),
        orderable_times_str=orderable_times_str.getvalue().decode('utf-8'),
        leap_time=leap_time,
        leap_time_message=leap_time_message,
        leap_time_str=leap_time_str,
        timezone_offsets=json.dumps(timezone_offsets),
        Features=Features,
        manual_confirmation=sln_order_settings.manual_confirmation
    )
    flow = JINJA_ENVIRONMENT.get_template('flows/advanced_order.xml').render(flow_params)
    return system.put_flow(flow.encode('utf-8'), multilanguage=False).identifier


@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_order(sln_settings, current_coords, main_branding, default_lang, tag):
    logging.info('Creating ORDER message flow')
    sln_order_settings = get_solution_order_settings(sln_settings)
    order_type = sln_order_settings.order_type

    if order_type == ORDER_TYPE_SIMPLE:
        flow_params = dict(branding_key=main_branding.branding_key, language=default_lang, text_1=sln_order_settings.text_1,
                           manual_confirmation=sln_order_settings.manual_confirmation, name=sln_settings.name)
        order_flow = JINJA_ENVIRONMENT.get_template('flows/order.xml').render(flow_params)
        static_flow_hash = system.put_flow(order_flow.encode('utf-8'), multilanguage=False).identifier
    elif order_type == ORDER_TYPE_ADVANCED:
        static_flow_hash = _put_advanced_order_flow(sln_settings, sln_order_settings, main_branding, default_lang)
        put_menu_item_image_upload_flow(main_branding.branding_key, default_lang)

    if not static_flow_hash:
        _default_delete(sln_settings, current_coords)
        return []
    logging.info('Creating ORDER menu item')
    ssmi = SolutionServiceMenuItem(u'fa-shopping-basket',
                                   sln_settings.menu_item_color,
                                   common_translate(default_lang, SOLUTION_COMMON, 'order'),
                                   tag,
                                   static_flow=static_flow_hash,
                                   action=SolutionModule.action_order(SolutionModule.ORDER))

    return [ssmi]

@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_pharmacy_order(sln_settings, current_coords, main_branding, default_lang, tag):
    logging.info('Creating PHARMACY ORDER message flow')
    flow_params = dict(branding_key=main_branding.branding_key, language=default_lang, name=sln_settings.name,
                       settings=sln_settings)
    flow = JINJA_ENVIRONMENT.get_template('flows/pharmacy_order.xml').render(flow_params)
    pharmacy_order_flow = system.put_flow(flow.encode('utf-8'), multilanguage=False)

    logging.info('Creating PHARMACY ORDER menu item')
    ssmi = SolutionServiceMenuItem(u'fa-medkit',
                                   sln_settings.menu_item_color,
                                   common_translate(default_lang, SOLUTION_COMMON, 'order'),
                                   tag,
                                   static_flow=pharmacy_order_flow.identifier,
                                   action=SolutionModule.action_order(SolutionModule.PHARMACY_ORDER))

    return [ssmi]


@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_qr_codes(sln_settings, current_coords, main_branding, default_lang, tag):
    logging.info('Creating WELCOME message flow')
    flow_params = dict(branding_key=main_branding.branding_key, language=default_lang)
    flow = JINJA_ENVIRONMENT.get_template('flows/welcome.xml').render(flow_params)
    welcome_flow = system.put_flow(flow.encode('utf-8'), multilanguage=False)

    if db.is_in_transaction():
        on_trans_committed(_configure_connect_qr_code, sln_settings, welcome_flow.identifier)
    else:
        _configure_connect_qr_code(sln_settings, welcome_flow.identifier)
    return list()


@returns()
@arguments(sln_settings=SolutionSettings, welcome_flow_identifier=unicode)
def _configure_connect_qr_code(sln_settings, welcome_flow_identifier):
    identities = [None]
    if sln_settings.identities:
        identities.extend(sln_settings.identities)
    for service_identity in identities:
        connect_qr = SolutionQR.get_by_name('Connect', sln_settings.service_user, service_identity, sln_settings.solution)
        if not connect_qr:
            connect_qr = SolutionQR(key=SolutionQR.create_key('Connect', sln_settings.service_user, service_identity, sln_settings.solution),
                                    description=common_translate(sln_settings.main_language, SOLUTION_COMMON,
                                                                 'get-connected'))

        if not connect_qr.image_url:
            qr_templates = qr.list_templates().templates
            qr_template_id = qr_templates[0].id if qr_templates else None
            qr_code = qr.create(connect_qr.description, 'connect', qr_template_id, service_identity, welcome_flow_identifier)
            connect_qr.image_url = qr_code.image_uri
            connect_qr.put()


@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_repair(sln_settings, current_coords, main_branding, default_lang, tag):
    logging.info('Creating REPAIR message flow')
    text_1 = None
    sln_repair_settings = get_solution_repair_settings(sln_settings.service_user)
    if sln_repair_settings:
        text_1 = sln_repair_settings.text_1

    if not text_1:
        text_1 = common_translate(default_lang, SOLUTION_COMMON, 'repair-1')

    flow_params = dict(branding_key=main_branding.branding_key, language=default_lang, text_1=text_1,
                       settings=sln_settings)
    flow = JINJA_ENVIRONMENT.get_template('flows/repair.xml').render(flow_params)
    repair_flow = system.put_flow(flow.encode('utf-8'), multilanguage=False)

    logging.info('Creating REPAIR menu item')
    ssmi = SolutionServiceMenuItem(u'fa-wrench',
                                   sln_settings.menu_item_color,
                                   common_translate(default_lang, SOLUTION_COMMON, 'repair'),
                                   tag,
                                   static_flow=repair_flow.identifier,
                                   action=SolutionModule.action_order(SolutionModule.REPAIR))
    return [ssmi]


@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_restaurant_reservation(sln_settings, current_coords, main_branding, default_lang, tag):
    logging.info('Creating RESERVE message flow')
    flow_params = dict(branding_key=main_branding.branding_key, language=default_lang, name=sln_settings.name)
    flow = JINJA_ENVIRONMENT.get_template('flows/reservation_part1.xml').render(flow_params)
    reserve_flow_part1 = system.put_flow(flow, multilanguage=False)
    flow = JINJA_ENVIRONMENT.get_template('flows/reservation_part2.xml').render(flow_params)
    reserve_flow_part2 = system.put_flow(flow, multilanguage=False)

    service_user = sln_settings.service_user

    identities = [None]
    if sln_settings.identities:
        identities.extend(sln_settings.identities)
    for service_identity in identities:
        if not get_restaurant_settings(service_user, service_identity):
            put_default_restaurant_settings(service_user,
                                            service_identity,
                                            lambda k: common_translate(default_lang, SOLUTION_COMMON, k),
                                            default_lang)

    restaurant_profile = get_restaurant_profile(service_user)
    if restaurant_profile:
        restaurant_profile.reserve_flow_part2 = reserve_flow_part2.identifier
    else:
        restaurant_profile = RestaurantProfile(key=RestaurantProfile.create_key(service_user),
                                               reserve_flow_part2=reserve_flow_part2.identifier)
    restaurant_profile.put()

    return [SolutionServiceMenuItem(u'fa-cutlery',
                                    sln_settings.menu_item_color,
                                    common_translate(default_lang, SOLUTION_COMMON, 'reserve'),
                                    POKE_TAG_RESERVE_PART1,
                                    static_flow=reserve_flow_part1.identifier,
                                    action=SolutionModule.action_order(SolutionModule.RESTAURANT_RESERVATION)),
             SolutionServiceMenuItem(u'fa-calendar',
                                     sln_settings.menu_item_color,
                                     common_translate(default_lang, SOLUTION_COMMON, 'My reservations'),
                                     POKE_TAG_MY_RESERVATIONS,
                                     action=0)]


@returns(NoneType)
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], service_menu=ServiceMenuDetailTO)
def delete_restaurant_reservation(sln_settings, current_coords, service_menu):
    _default_delete(sln_settings, get_coords_of_service_menu_item(service_menu, POKE_TAG_RESERVE_PART1))
    _default_delete(sln_settings, get_coords_of_service_menu_item(service_menu, POKE_TAG_MY_RESERVATIONS))


@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_sandwich_bar(sln_settings, current_coords, main_branding, default_lang, tag):
    """
    Args:
        sln_settings (SolutionSettings)
        current_coords (list of int)
        main_branding (SolutionMainBranding)
        default_lang (unicode)
        tag (unicode)
    """
    logging.info('Creating ORDER SANDWICH message flow')
    lang = sln_settings.main_language
    service_user = sln_settings.service_user
    default_data = []
    types = list(SandwichType.list(service_user, sln_settings.solution))
    to_put = []
    if not types:
        # Add some default data
        types.append(SandwichType(parent=parent_key(service_user, sln_settings.solution),
                                  description=common_translate(lang, SOLUTION_COMMON,
                                                               'order-sandwich-default-data-type-white'),
                                  price=0,
                                  order=1))
        types.append(SandwichType(parent=parent_key(service_user, sln_settings.solution),
                                  description=common_translate(lang, SOLUTION_COMMON,
                                                               'order-sandwich-default-data-type-dark'),
                                  price=0,
                                  order=2))
        default_data.extend(types)
    toppings = list(SandwichTopping.list(service_user, sln_settings.solution))
    if not toppings:
        toppings.append(SandwichTopping(parent=parent_key(service_user, sln_settings.solution),
                                        description=common_translate(lang, SOLUTION_COMMON,
                                                                     'order-sandwich-default-data-topping-ham'),
                                        price=200,
                                        order=1))
        toppings.append(SandwichTopping(parent=parent_key(service_user, sln_settings.solution),
                                        description=common_translate(lang, SOLUTION_COMMON,
                                                                     'order-sandwich-default-data-topping-cheese'),
                                        price=200,
                                        order=2))
        toppings.append(SandwichTopping(parent=parent_key(service_user, sln_settings.solution),
                                        description=common_translate(lang, SOLUTION_COMMON,
                                                                     'order-sandwich-default-data-topping-ham-cheese'),
                                        price=300,
                                        order=3))
        default_data.extend(toppings)
    options = list(SandwichOption.list(service_user, sln_settings.solution, True))
    if not options:
        options.append(SandwichOption(parent=parent_key(service_user, sln_settings.solution),
                                      description=common_translate(lang, SOLUTION_COMMON,
                                                                   'order-sandwich-default-data-option-mayo'),
                                      price=0,
                                      order=1))
        options.append(SandwichOption(parent=parent_key(service_user, sln_settings.solution),
                                      description=common_translate(lang, SOLUTION_COMMON,
                                                                   'order-sandwich-default-data-option-cocktail'),
                                      price=0,
                                      order=2))
        options.append(SandwichOption(parent=parent_key(service_user, sln_settings.solution),
                                      description=common_translate(lang, SOLUTION_COMMON,
                                                                   'order-sandwich-default-data-option-greens'),
                                      price=100,
                                      order=3))
        default_data.extend(options)
    else:
        options = list(SandwichOption.list(service_user, sln_settings.solution))

    validate_sandwiches(sln_settings.main_language, types, toppings, options)

    sandwich_settings = SandwichSettings.get_settings(service_user, sln_settings.solution)

    if default_data:
        db.put(default_data)

    days = list()
    day_names = dates.get_day_names('wide', locale=lang)
    for day in SandwichSettings.DAYS:
        if sandwich_settings.status_days & day == day:
            days.append(day_names[SandwichSettings.DAYS.index(day)])

    days = ', '.join(days)
    leap_time = sandwich_settings.leap_time * sandwich_settings.leap_time_type
    from_ = format_time(datetime.utcfromtimestamp(sandwich_settings.time_from + leap_time), format='short', locale=lang)
    till = format_time(datetime.utcfromtimestamp(sandwich_settings.time_until - leap_time), format='short', locale=lang)
    orderable_sandwich_days_message = common_translate(lang, SOLUTION_COMMON, u'order-sandwich-cannot-order-now',
                                                       days=days, from_=from_, till=till)
    possible_times_message = common_translate(lang, SOLUTION_COMMON, u'order-sandwich-cannot-order-at-time', days=days,
                                              from_=from_, till=till)
    holiday_dates_str = []
    holiday_dates = []

    leap_time_str = format_timedelta(timedelta(seconds=leap_time), locale=lang)

    leaptime_msg_replacement = 'minutes'
    if sandwich_settings.leap_time_type == SECONDS_IN_MINUTE:
        leaptime_msg_replacement = 'minutes'
    elif sandwich_settings.leap_time_type == SECONDS_IN_HOUR:
        leaptime_msg_replacement = 'hours'
    elif sandwich_settings.leap_time_type == SECONDS_IN_DAY:
        leaptime_msg_replacement = 'days'
    elif sandwich_settings.leap_time_type == SECONDS_IN_WEEK:
        leaptime_msg_replacement = 'weeks'
    leap_time_message = common_translate(lang, SOLUTION_COMMON, 'advanced_order_leaptime_%s_%s' % (
        leaptime_msg_replacement, '1' if sandwich_settings.leap_time == 1 else 'x'))
    multiple_locations = True
    if not sln_settings.identities:
        multiple_locations = False
        cur_date = now()
        for d1, d2 in sln_settings.holiday_tuples:
            if d2 > cur_date:
                holiday_dates.append({
                    'from': d1,
                    'to': d2
                })
                holiday_dates_str.append(
                    common_translate(lang, SOLUTION_COMMON, 'date_until_date') % {
                        'from_date': format_date(datetime.fromtimestamp(d1), format='medium', locale=lang),
                        'until_date': format_date(datetime.fromtimestamp(d2), format='medium', locale=lang)
                    }
                )
    start = datetime.now()
    timezone_offsets = []
    for _ in xrange(20):
        try:
            t = get_next_timezone_transition(sln_settings.timezone, start)
        except TypeError:
            timezone_offsets.append([0, now() + (DAY * 7 * 52 * 20), timezone_offset(sln_settings.timezone)])
            break
        if t is None:
            break
        timezone_offsets.append([int(time.mktime(start.timetuple())),
                                 int(time.mktime(t.activates.timetuple())),
                                 int(t.from_offset)])
    flow_params = {
        'branding_key': main_branding.branding_key,
        'language': default_lang,
        'types': types,
        'toppings': toppings,
        'options': options,
        'sandwich_settings': sandwich_settings,
        'settings': sln_settings,
        'orderable_sandwich_days_message': orderable_sandwich_days_message,
        'multiple_locations': multiple_locations,
        'holiday_dates_str': xml_escape(json.dumps(holiday_dates_str)),
        'holiday_dates': xml_escape(json.dumps(holiday_dates)),
        'possible_times_message': possible_times_message,
        'leap_time_message': leap_time_message,
        'leap_time_str': leap_time_str,
        'timezone_offsets': json.dumps(timezone_offsets)
    }
    flow = JINJA_ENVIRONMENT.get_template('flows/order_sandwich.xml').render(flow_params)
    order_sandwich_flow = system.put_flow(flow.encode('utf-8'), multilanguage=False)
    sandwich_settings.order_flow = order_sandwich_flow.identifier
    to_put.append(sandwich_settings)

    # Configure automatic broadcast types
    broadcast_types = list()
    for day in SandwichSettings.DAYS:
        if day & sandwich_settings.broadcast_days == day:
            broadcast_types.append(get_sandwich_reminder_broadcast_type(default_lang, day))
    auto_broadcast_types = SolutionAutoBroadcastTypes(key_name=SolutionModule.SANDWICH_BAR, parent=sln_settings,
                                                      broadcast_types=broadcast_types)
    to_put.append(auto_broadcast_types)
    db.put(to_put)

    logging.info('Creating ORDER SANDWICH menu item')
    ssmi = SolutionServiceMenuItem(u'hamburger',
                                   sln_settings.menu_item_color,
                                   common_translate(default_lang, SOLUTION_COMMON, 'order-sandwich'),
                                   tag, static_flow=order_sandwich_flow.identifier, broadcast_types=broadcast_types,
                                   action=SolutionModule.action_order(SolutionModule.SANDWICH_BAR))

    return [ssmi]


@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_when_where(sln_settings, current_coords, main_branding, default_lang, tag):
    logging.info('Creating WHEN_WHERE screen branding')
    content = render_common_content(default_lang, 'when_where.tmpl', {})
    map_png = os.path.join(os.path.dirname(solutions.__file__), 'common', 'templates', 'map.png')

    when_where_branding = generate_branding(main_branding, u'when_where', content, [map_png])

    logging.info('Creating WHEN_WHERE menu item')
    ssmi = SolutionServiceMenuItem(u'fa-map-marker',
                                   sln_settings.menu_item_color,
                                   common_translate(default_lang, SOLUTION_COMMON, 'when-where'),
                                   tag,
                                   screen_branding=when_where_branding.id,
                                   action=SolutionModule.action_order(SolutionModule.WHEN_WHERE))

    return [ssmi]


@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_discussion_groups(sln_settings, current_coords, main_branding, default_lang, tag):
    ssmi = SolutionServiceMenuItem(u'fa-comments',
                                   sln_settings.menu_item_color,
                                   common_translate(default_lang, SOLUTION_COMMON, SolutionModule.DISCUSSION_GROUPS),
                                   tag,
                                   action=SolutionModule.action_order(SolutionModule.DISCUSSION_GROUPS))
    return [ssmi]


@returns(NoneType)
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], service_menu=ServiceMenuDetailTO)
def delete_discussion_groups(sln_settings, current_coords, service_menu):
    from solutions.common.bizz.discussion_groups import delete_discussion_group
    service_user = sln_settings.service_user

    # delete the menu first
    _default_delete(sln_settings, current_coords, service_menu)

    def trans():
        for k in SolutionDiscussionGroup.list(service_user, keys_only=True):
            delete_discussion_group(service_user, k.id())

    if db.is_in_transaction():
        on_trans_committed(trans)
    else:
        db.run_in_transaction(trans)


@returns([SolutionServiceMenuItem])
@arguments(sln_settings=SolutionSettings, current_coords=[(int, long)], main_branding=SolutionMainBranding,
           default_lang=unicode, tag=unicode)
def put_hidden_city_wide_lottery(sln_settings, current_coords, main_branding, default_lang, tag):
    if SolutionModule.LOYALTY in sln_settings.modules:
        raise Exception(u"hidden_city_wide_lottery and loyalty should not be used together")

    service_user = sln_settings.service_user
    service_identity = None
    loyalty_settings = SolutionLoyaltySettings.get_by_user(service_user)
    if not loyalty_settings:
        loyalty_settings = SolutionLoyaltySettings(key=SolutionLoyaltySettings.create_key(service_user))
    loyalty_settings.loyalty_type = SolutionLoyaltySettings.LOYALTY_TYPE_CITY_WIDE_LOTTERY
    should_put = False
    if not loyalty_settings:
        logging.debug('Creating new SolutionLoyaltySettings for city_wide_lottery')
        should_put = True
        loyalty_settings = SolutionLoyaltySettings(key=SolutionLoyaltySettings.create_key(service_user))
        system.put_callback("friend.register", True)
        system.put_callback("friend.register_result", True)
    if not loyalty_settings.image_uri:
        qr_code = create_loyalty_admin_qr_code(service_identity)
        should_put = True
        loyalty_settings.image_uri = qr_code.image_uri
        loyalty_settings.content_uri = qr_code.content_uri
    if should_put:
        loyalty_settings.put()
    return []


@returns([SolutionServiceMenuItem])
def _dummy_put(*args, **kwargs):
    return []  # we don't need to do anything


@returns(NoneType)
@arguments(sln_settings=SolutionSettings, current_coords=[(int , long)], service_menu=ServiceMenuDetailTO)
def _default_delete(sln_settings, current_coords, service_menu=None):
    if current_coords:
        system.delete_menu_item(current_coords)
    if service_menu:
        for item in reversed(service_menu.items):
            if item.coords == current_coords:
                service_menu.items.remove(item)


MODULES_GET_APP_DATA_FUNCS = {SolutionModule.AGENDA: get_app_data_agenda,
                              SolutionModule.BROADCAST: get_app_data_broadcast,
                              SolutionModule.CITY_VOUCHERS: get_app_data_city_vouchers,
                              SolutionModule.GROUP_PURCHASE: get_app_data_group_purchase,
                              SolutionModule.LOYALTY: get_app_data_loyalty,
                              SolutionModule.SANDWICH_BAR: get_app_data_sandwich_bar
                              }

MODULES_PUT_FUNCS = {SolutionModule.AGENDA: put_agenda,
                     SolutionModule.APPOINTMENT: put_appointment,
                     SolutionModule.ASK_QUESTION: put_ask_question,
                     SolutionModule.BILLING: _dummy_put,
                     SolutionModule.BROADCAST: put_broadcast,
                     SolutionModule.BULK_INVITE: _dummy_put,
                     SolutionModule.DISCUSSION_GROUPS: put_discussion_groups,
                     SolutionModule.CITY_APP: _dummy_put,
                     SolutionModule.CITY_VOUCHERS: _dummy_put,
                     SolutionModule.GROUP_PURCHASE: put_group_purchase,
                     SolutionModule.LOYALTY: put_loyalty,
                     SolutionModule.MENU: put_menu,
                     SolutionModule.ORDER: put_order,
                     SolutionModule.PHARMACY_ORDER: put_pharmacy_order,
                     SolutionModule.QR_CODES: put_qr_codes,
                     SolutionModule.REPAIR: put_repair,
                     SolutionModule.RESTAURANT_RESERVATION: put_restaurant_reservation,
                     SolutionModule.SANDWICH_BAR: put_sandwich_bar,
                     SolutionModule.STATIC_CONTENT: put_static_content,
                     SolutionModule.WHEN_WHERE: put_when_where,
                     SolutionModule.HIDDEN_CITY_WIDE_LOTTERY: put_hidden_city_wide_lottery,
                     }

MODULES_DELETE_FUNCS = {SolutionModule.AGENDA: delete_agenda,
                        SolutionModule.APPOINTMENT: _default_delete,
                        SolutionModule.ASK_QUESTION: _default_delete,
                        SolutionModule.BILLING: _default_delete,
                        SolutionModule.BROADCAST: delete_broadcast,
                        SolutionModule.BULK_INVITE: _default_delete,
                        SolutionModule.CITY_APP: _default_delete,
                        SolutionModule.CITY_VOUCHERS: _default_delete,
                        SolutionModule.DISCUSSION_GROUPS: delete_discussion_groups,
                        SolutionModule.GROUP_PURCHASE: _default_delete,
                        SolutionModule.LOYALTY: _default_delete,
                        SolutionModule.MENU: _default_delete,
                        SolutionModule.ORDER: _default_delete,
                        SolutionModule.PHARMACY_ORDER: _default_delete,
                        SolutionModule.QR_CODES: delete_qr_codes,
                        SolutionModule.REPAIR: _default_delete,
                        SolutionModule.RESTAURANT_RESERVATION: delete_restaurant_reservation,
                        SolutionModule.SANDWICH_BAR: _default_delete,
                        SolutionModule.STATIC_CONTENT: delete_static_content,
                        SolutionModule.WHEN_WHERE: _default_delete,
                        SolutionModule.HIDDEN_CITY_WIDE_LOTTERY: _default_delete,
                        }

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
import os

import jinja2
import webapp2

from babel import dates
from mcfw.rpc import serialize_complex_value
from rogerthat.bizz import channel
from rogerthat.bizz.app import get_app
from rogerthat.bizz.session import set_service_identity
from rogerthat.consts import DEBUG, APPSCALE
from rogerthat.dal.service import get_service_identity
from rogerthat.models import ServiceIdentity, App
from rogerthat.pages.login import SessionHandler
from rogerthat.rpc import users
from rogerthat.service.api import system
from rogerthat.translations import DEFAULT_LANGUAGE
from rogerthat.utils.channel import send_message_to_session
from rogerthat.utils.service import create_service_identity_user
from shop.bizz import get_organization_types, is_signup_enabled
from shop.business.legal_entities import get_vat_pct
from shop.constants import LOGO_LANGUAGES
from shop.dal import get_customer, get_mobicage_legal_entity, get_available_apps_for_customer
from solution_server_settings import get_solution_server_settings
from solutions import translate, translations, COMMON_JS_KEYS
from solutions.common import SOLUTION_COMMON
from solutions.common.bizz import SolutionModule
from solutions.common.bizz.functionalities import get_functionalities
from solutions.common.bizz.settings import SLN_LOGO_WIDTH, SLN_LOGO_HEIGHT
from solutions.common.consts import UNITS, UNIT_SYMBOLS, UNIT_PIECE, UNIT_LITER, UNIT_KG, UNIT_GRAM, UNIT_HOUR, \
    UNIT_MINUTE, ORDER_TYPE_SIMPLE, ORDER_TYPE_ADVANCED, UNIT_PLATTER, UNIT_SESSION, UNIT_PERSON, UNIT_DAY
from solutions.common.dal import get_solution_settings, get_restaurant_menu, get_solution_email_settings, \
    get_solution_settings_or_identity_settings
from solutions.common.dal.city_vouchers import get_city_vouchers_settings
from solutions.common.dal.order import get_solution_order_settings
from solutions.common.models import SolutionQR
from solutions.common.models.properties import MenuItem
from solutions.common.to import SolutionEmailSettingsTO
from solutions.common.to.order import SolutionOrderSettingsTO
from solutions.flex import SOLUTION_FLEX
from solutions.jinja_extensions import TranslateExtension

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader([os.path.join(os.path.dirname(__file__), 'templates'),
                                    os.path.join(os.path.dirname(__file__), '..', 'common', 'templates')]),
    extensions=[TranslateExtension])

DEFAULT_JS_TEMPLATES = ['inbox_messages',
                        'inbox_detail_messages',
                        'holiday_addholiday',
                        'holiday_holiday',
                        'qanda_question_table',
                        'qanda_question_modules',
                        'qanda_question_detail',
                        'hints_modal',
                        'shop/apps',
                        'shop/shopping_cart',
                        'shop/product',
                        'settings/settings_branding',
                        'settings/settings_branding_preview',
                        'settings/app_user_roles',
                        'settings/app_user_add_roles',
                        'settings/try_publish_changes',
                        'settings/upload_image',
                        'functionalities/functionality'
                        ]

MODULES_JS_TEMPLATE_MAPPING = {SolutionModule.AGENDA:           ['events_add',
                                                                 'events_add_dates',
                                                                 'events',
                                                                 'events_events',
                                                                 'events_settings',
                                                                 'events_calendar_settings',
                                                                 'events_guests_modal',
                                                                 'events_guests_table',
                                                                 'events_uitcalendar_settings'],
                               SolutionModule.APPOINTMENT: ['timeframe_template'],
                               SolutionModule.ASK_QUESTION:     [],
                               SolutionModule.BILLING:          ['billing_manage_credit_card',
                                                                 'billing_view_invoice',
                                                                 'billing_settings_unsigned_orders_table',
                                                                 'billing_settings_orders_table',
                                                                 'billing_settings_invoices_table'],
                               SolutionModule.BROADCAST:        ['addattachment',
                                                                 'broadcast_types',
                                                                 'broadcast_schedule',
                                                                 'broadcast_schedule_items',
                                                                 'broadcast_settings_list',
                                                                 'broadcast/broadcast_news',
                                                                 'broadcast/broadcast_news_overview',
                                                                 'broadcast/broadcast_news_preview',
                                                                 'broadcast/news_stats_row'],
                               SolutionModule.CITY_APP: ['services/service',
                                                         'services/service_form',
                                                         'services/modules_list',
                                                         'services/service_search',
                                                         'settings/app_settings'],
                               SolutionModule.CITY_VOUCHERS: ['city_vouchers/city_vouchers_list',
                                                              'city_vouchers/city_vouchers_transactions',
                                                              'city_vouchers/city_vouchers_qrcode_export_list',
                                                              'city_vouchers/city_vouchers_export_list'],
                               SolutionModule.DISCUSSION_GROUPS: ['discussion_groups/discussion_groups_list',
                                                                  'discussion_groups/discussion_groups_put'],
                               SolutionModule.GROUP_PURCHASE:   ['group_purchase',
                                                                 'group_purchase_subscriptions'],
                               SolutionModule.LOYALTY:          ['loyalty_slides',
                                                                 'loyalty_slide_add',
                                                                 'loyalty_tablets',
                                                                 'loyalty_tablet_modal',
                                                                 'loyalty_scans',
                                                                 'loyalty_scans_redeem_stamps_modal',
                                                                 'loyalty_lottery_add_modal',
                                                                 'loyalty_customer_visits_detail_modal',
                                                                 'loyalty_customer_visits_detail',
                                                                 'loyalty_customer_visit',
                                                                 'loyalty_lottery_history',
                                                                 'loyalty_export',
                                                                 'voucher_export'],
                               SolutionModule.MENU:             ['menu',
                                                                 'menu_additem',
                                                                 'menu_editdescription',
                                                                 'menu_edit_image',
                                                                 'menu_import'],
                               SolutionModule.ORDER: ['order',
                                                      'order_list',
                                                      'timeframe_template',
                                                      'menu',
                                                      'menu_import',
                                                      'menu_additem',
                                                      'menu_editdescription',
                                                      'menu_edit_image'],
                               SolutionModule.PHARMACY_ORDER: ['pharmacy_order',
                                                               'pharmacy_order_list'],
                               SolutionModule.RESTAURANT_RESERVATION: ['reservation_addshift',
                                                                       'reservation_addtable',
                                                                       'reservation_broken_reservations',
                                                                       'reservation_delete_table_confirmation',
                                                                       'reservation_editreservation',
                                                                       'reservation_edittables',
                                                                       'reservation_no_shift_found',
                                                                       'reservation_shiftcontents',
                                                                       'reservation_tablecontents',
                                                                       'reservation_update_reservation_tables',
                                                                       'reservations'],
                               SolutionModule.REPAIR:           ['repair_order'],
                               SolutionModule.SANDWICH_BAR: ['sandwiches_order_inbox_detail',
                                                             'sandwiches_list_item'],
                               SolutionModule.STATIC_CONTENT:   ['static_content/static_content_select_icon',
                                                                 'static_content/static_content'],
                               SolutionModule.HIDDEN_CITY_WIDE_LOTTERY: ['loyalty_lottery_add_modal',
                                                                         'loyalty_customer_visits_detail_modal',
                                                                         'loyalty_customer_visits_detail',
                                                                         'loyalty_customer_visit',
                                                                         'loyalty_lottery_history',
                                                                         'loyalty_slides',
                                                                         'loyalty_slide_add'],
                               }


class FlexHomeHandler(webapp2.RequestHandler):

    def _get_location_templates(self, sln_settings):
        tmpl_params = {'language': sln_settings.main_language or DEFAULT_LANGUAGE,
                       'debug': DEBUG,
                       'appscale': APPSCALE,
                       'currency': sln_settings.currency,
                       'service_user_email': sln_settings.service_user}
        templates = dict()
        templates_to_get = set()
        templates_to_get.add("location")
        for tmpl in templates_to_get:
            templates[tmpl] = JINJA_ENVIRONMENT.get_template(tmpl + '.html').render(tmpl_params)
        templates = json.dumps(templates)
        return templates

    def _get_templates(self, sln_settings):
        tmpl_params = {'language': sln_settings.main_language or DEFAULT_LANGUAGE,
                       'debug': DEBUG,
                       'currency': sln_settings.currency,
                       'appscale': APPSCALE,
                       'service_user_email': sln_settings.service_user}
        templates = dict()
        templates_to_get = set()
        for tmpl in DEFAULT_JS_TEMPLATES:
            templates_to_get.add(tmpl)
        for module in sln_settings.modules:
            for tmpl in MODULES_JS_TEMPLATE_MAPPING.get(module, tuple()):
                templates_to_get.add(tmpl)
        for tmpl in templates_to_get:
            templates[tmpl] = JINJA_ENVIRONMENT.get_template(tmpl + '.html').render(tmpl_params)
        templates = json.dumps(templates)
        return templates

    def _get_qr_codes(self, sln_settings, service_identity):
        return SolutionQR.list_by_user(sln_settings.service_user, service_identity, sln_settings.solution)

    def _get_days(self, sln_settings):
        return [(k, v.capitalize()) for k, v in dates.get_day_names('wide', locale=sln_settings.main_language or DEFAULT_LANGUAGE).items()]

    def _get_months(self, sln_settings, width):
        return [v.capitalize() for _, v in dates.get_month_names(width, locale=sln_settings.main_language or DEFAULT_LANGUAGE).items()]

    def _get_day_str(self, sln_settings, day):
        return dates.get_day_names('wide', locale=sln_settings.main_language or DEFAULT_LANGUAGE)[day].capitalize()

    def _get_week_days(self, sln_settings):
        return [self._get_day_str(sln_settings, day) for day in [6, 0, 1, 2, 3, 4, 5]]

    def get(self):
        service_user = users.get_current_user()
        if not service_user:
            self.redirect("/ourcityapp")
            return
        sln_settings = get_solution_settings(service_user)
        if not sln_settings or sln_settings.solution != SOLUTION_FLEX:
            self.redirect("/ourcityapp")
            return

        session_ = users.get_current_session()
        all_translations = {key: translate(sln_settings.main_language, SOLUTION_COMMON, key) for key in
                            translations[SOLUTION_COMMON]['en']}
        for key in COMMON_JS_KEYS:
            all_translations[key] = translate(sln_settings.main_language, SOLUTION_COMMON, COMMON_JS_KEYS[key])
        if sln_settings.identities:
            if not session_.service_identity:
                jinja_template = JINJA_ENVIRONMENT.get_template('locations.html')
                params = {'language': sln_settings.main_language or DEFAULT_LANGUAGE,
                          'debug': DEBUG,
                          'appscale': APPSCALE,
                          'templates': self._get_location_templates(sln_settings),
                          'service_name': sln_settings.name,
                          'service_display_email': sln_settings.qualified_identifier or service_user.email().encode("utf-8"),
                          'service_user_email': service_user.email().encode("utf-8"),
                          'currency': sln_settings.currency,
                          'translations': json.dumps(all_translations)
                          }
                channel.append_firebase_params(params)
                self.response.out.write(jinja_template.render(params))
                return
        elif session_.service_identity:
            session_ = set_service_identity(session_, None)

        service_identity = session_.service_identity if session_.service_identity else ServiceIdentity.DEFAULT
        sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
        customer = get_customer(service_user)
        solution_server_settings = get_solution_server_settings()
        jinja_template = JINJA_ENVIRONMENT.get_template('index.html')

        days = self._get_days(sln_settings)
        day_flags = [(pow(2, day_num), day_name) for day_num, day_name in days]
        months = self._get_months(sln_settings, 'wide')
        months_short = self._get_months(sln_settings, 'abbreviated')
        week_days = self._get_week_days(sln_settings)

        loyalty_version = self.request.get("loyalty")
        if customer:
            city_app_id = customer.app_id
            default_app = get_app(customer.app_id)
            is_demo_app = default_app.demo
            available_apps = get_available_apps_for_customer(customer)
            active_app_ids = customer.sorted_app_ids
        else:
            city_app_id = None
            is_demo_app = False
            logging.info('Getting app ids from service identity since no customer exists for user %s', service_user)
            service_identity_user = create_service_identity_user(service_user, service_identity)
            app_ids = get_service_identity(service_identity_user).appIds
            available_apps = App.get([App.create_key(app_id) for app_id in app_ids])
            active_app_ids = app_ids

        if SolutionModule.ORDER or SolutionModule.MENU in sln_settings.modules:
            order_settings = get_solution_order_settings(sln_settings)
        else:
            order_settings = None  # Client code should not need this variable

        consts = {
            'UNIT_PIECE': UNIT_PIECE,
            'UNIT_LITER': UNIT_LITER,
            'UNIT_KG': UNIT_KG,
            'UNIT_GRAM': UNIT_GRAM,
            'UNIT_HOUR': UNIT_HOUR,
            'UNIT_MINUTE': UNIT_MINUTE,
            'UNIT_DAY': UNIT_DAY,
            'UNIT_PERSON': UNIT_PERSON,
            'UNIT_SESSION': UNIT_SESSION,
            'UNIT_PLATTER': UNIT_PLATTER,
            'ORDER_TYPE_SIMPLE': ORDER_TYPE_SIMPLE,
            'ORDER_TYPE_ADVANCED': ORDER_TYPE_ADVANCED,
            'ORDER_ITEM_VISIBLE_IN_MENU': MenuItem.VISIBLE_IN_MENU,
            'ORDER_ITEM_VISIBLE_IN_ORDER': MenuItem.VISIBLE_IN_ORDER
        }
        if not customer:
            mobicage_legal_entity = get_mobicage_legal_entity()
            vat_pct = mobicage_legal_entity.vat_percent
            legal_entity_currency = mobicage_legal_entity.currency
            is_mobicage = True
        else:
            vat_pct = get_vat_pct(customer)
            is_mobicage = customer.team.legal_entity.is_mobicage
            legal_entity_currency = customer.team.legal_entity.currency

        functionality_modules = functionality_info = None
        if city_app_id and is_signup_enabled(city_app_id):
            functionality_modules, functionality_info = map(json.dumps, get_functionalities(sln_settings))

        vouchers_settings = None
        if city_app_id and SolutionModule.CITY_VOUCHERS in sln_settings.modules:
            vouchers_settings = get_city_vouchers_settings(city_app_id)

        params = {'stripePublicKey': solution_server_settings.stripe_public_key,
                  'language': sln_settings.main_language or DEFAULT_LANGUAGE,
                  'logo_languages': LOGO_LANGUAGES,
                  'sln_settings': sln_settings,
                  'sln_i_settings': sln_i_settings,
                  'debug': DEBUG,
                  'appscale': APPSCALE,
                  'templates': self._get_templates(sln_settings),
                  'service_name': sln_i_settings.name,
                  'service_display_email': sln_i_settings.qualified_identifier or service_user.email().encode("utf-8"),
                  'service_user_email': service_user.email().encode("utf-8"),
                  'service_identity': service_identity,
                  'has_multiple_locations': True if sln_settings.identities else False,
                  'qr_codes': self._get_qr_codes(sln_settings, service_identity),
                  'SolutionModule': SolutionModule,
                  'news_enabled': True,
                  'days': days,
                  'day_flags': day_flags,
                  'months': months,
                  'months_short': months_short,
                  'week_days': week_days,
                  'customer': customer,
                  'loyalty': True if loyalty_version else False,
                  'city_app_id': city_app_id,
                  'is_demo_app': is_demo_app,
                  'functionality_modules': functionality_modules,
                  'functionality_info': functionality_info,
                  'email_settings': json.dumps(serialize_complex_value(SolutionEmailSettingsTO.fromModel(get_solution_email_settings(), service_user), SolutionEmailSettingsTO, False)),
                  'currency': sln_settings.currency,
                  'is_layout_user': session_.layout_only if session_ else False,
                  'SLN_LOGO_WIDTH': SLN_LOGO_WIDTH,
                  'SLN_LOGO_HEIGHT': SLN_LOGO_HEIGHT,
                  'active_apps': json.dumps(active_app_ids),
                  'all_apps': json.dumps([dict(id=a.app_id, name=a.name) for a in available_apps]),
                  'UNITS': json.dumps(UNITS),
                  'UNIT_SYMBOLS': json.dumps(UNIT_SYMBOLS),
                  'CONSTS': consts,
                  'CONSTS_JSON': json.dumps(consts),
                  'order_settings': order_settings,
                  'order_settings_json': json.dumps(
                      serialize_complex_value(
                          SolutionOrderSettingsTO.fromModel(order_settings, sln_settings.main_language),
                          SolutionOrderSettingsTO, False)),
                  'modules': json.dumps(sln_settings.modules),
                  'provisioned_modules': json.dumps(sln_settings.provisioned_modules),
                  'hide_menu_tab': SolutionModule.MENU not in sln_settings.modules
                  and SolutionModule.ORDER in sln_settings.modules
                  and (
                      not order_settings or order_settings.order_type != order_settings.TYPE_ADVANCED),
                  'VAT_PCT': vat_pct,
                  'IS_MOBICAGE_LEGAL_ENTITY': is_mobicage,
                  'LEGAL_ENTITY_CURRENCY': legal_entity_currency,
                  'translations': json.dumps(all_translations),
                  'organization_types': get_organization_types(customer, sln_settings.main_language),
                  'vouchers_settings': vouchers_settings
                  }

        if SolutionModule.BULK_INVITE in sln_settings.modules:
            params['bulk_invite_message'] = translate(sln_settings.main_language, SOLUTION_COMMON,
                                                      "settings-bulk-invite-message",
                                                      app_name=system.get_identity().app_names[0])

        if SolutionModule.MENU in sln_settings.modules:
            params['menu'] = get_restaurant_menu(service_user)

        channel.append_firebase_params(params)
        self.response.out.write(jinja_template.render(params))


class FlexLogoutHandler(SessionHandler):

    def get(self):
        service_user = users.get_current_user()
        sln_settings = get_solution_settings(service_user)

        if not sln_settings or sln_settings.solution != SOLUTION_FLEX or not sln_settings.identities:
            self.stop_session()
            return self.redirect('/ourcityapp')

        session_ = users.get_current_session()
        if session_.service_identity:
            session_ = set_service_identity(session_, None)

        send_message_to_session(service_user, session_, u"solutions.common.locations.update", si=None)
        self.redirect('/ourcityapp')

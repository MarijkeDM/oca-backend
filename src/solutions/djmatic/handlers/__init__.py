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

from babel import dates
from google.appengine.api import users as gae_users
import jinja2
from mcfw.rpc import serialize_complex_value
from rogerthat.bizz import channel
from rogerthat.consts import DEBUG
from rogerthat.rpc import users
from rogerthat.service.api import system
from rogerthat.translations import DEFAULT_LANGUAGE
from shop.constants import LOGO_LANGUAGES
from solution_server_settings import get_solution_server_settings
from solutions import translate, translations, COMMON_JS_KEYS
from solutions.common import SOLUTION_COMMON
from solutions.common.bizz import SolutionModule
from solutions.common.bizz.settings import SLN_LOGO_WIDTH, SLN_LOGO_HEIGHT
from solutions.common.consts import UNIT_PIECE, UNIT_LITER, UNIT_KG, UNIT_GRAM, UNIT_HOUR, UNIT_MINUTE, \
    ORDER_TYPE_SIMPLE, ORDER_TYPE_ADVANCED, UNITS, UNIT_SYMBOLS, UNIT_DAY, UNIT_PERSON, UNIT_PLATTER, UNIT_SESSION
from solutions.common.dal import get_solution_settings, get_solution_email_settings
from solutions.common.models.properties import MenuItem
from solutions.common.to import SolutionEmailSettingsTO
from solutions.djmatic import JUKEBOX_SERVER_API_URL, SOLUTION_DJMATIC
from solutions.djmatic.dal import get_djmatic_profile
from solutions.jinja_extensions import TranslateExtension
import webapp2


JINJA_ENVIRONMENT = jinja2.Environment(loader=jinja2.FileSystemLoader([os.path.join(os.path.dirname(__file__), '..', 'templates'),
                                                                       os.path.join(os.path.dirname(__file__), '..', '..', 'common', 'templates')]),
                                       extensions=[TranslateExtension])

class DJMaticHomeHandler(webapp2.RequestHandler):

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
            self.redirect("/")
            return
        sln_settings = get_solution_settings(service_user)
        if not sln_settings or sln_settings.solution != SOLUTION_DJMATIC:
            self.redirect("/")
            return

        tmpl_params = {'language': DEFAULT_LANGUAGE,
                       'debug': DEBUG,
                       'currency': sln_settings.currency,
                       'service_user_email': service_user.email()}
        templates = dict()
        for tmpl in ('menu_additem', 'menu', 'menu_editdescription', 'menu_edit_image', 'holiday_holiday',
                     'inbox_messages', 'inbox_detail_messages',
                     'events_add', 'events_add_dates', 'events', 'events_events', 'events_settings', 'events_calendar_settings', 'events_guests_modal',
                     'events_guests_table', 'events_uitcalendar_settings',
                     'broadcast_types', 'broadcast_schedule', 'broadcast_schedule_items', 'addattachment',
                     'settings/try_publish_changes', 'settings/settings_branding', 'settings/settings_branding_preview', 'settings/upload_image'):
            templates[tmpl] = JINJA_ENVIRONMENT.get_template(tmpl + '.html').render(tmpl_params)
        templates = json.dumps(templates)

        bulk_invite_message = translate(sln_settings.main_language, SOLUTION_COMMON, "settings-bulk-invite-message",
                                        app_name=system.get_identity().app_names[0])

        jinja_template = JINJA_ENVIRONMENT.get_template('index.html')

        days = self._get_days(sln_settings)
        day_flags = [(pow(2, day_num), day_name) for day_num, day_name in days ]
        months = self._get_months(sln_settings, 'wide')
        months_short = self._get_months(sln_settings, 'abbreviated')
        week_days = self._get_week_days(sln_settings)
        all_translations = {key: translate(sln_settings.main_language, SOLUTION_COMMON, key) for key in
                            translations[SOLUTION_COMMON]['en']}
        for key in COMMON_JS_KEYS:
            all_translations[key] = translate(sln_settings.main_language, SOLUTION_COMMON, COMMON_JS_KEYS[key])

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
        params = {
            'language': DEFAULT_LANGUAGE,
            'solution': sln_settings.solution,
            'logo_languages': LOGO_LANGUAGES,
            'debug': DEBUG,
            'templates': templates,
            'service_user_email': service_user.email().encode("utf-8"),
            'service_name': sln_settings.name,
            'has_multiple_locations': False,
            'sln_settings': sln_settings,
            'days': days,
            'day_flags': day_flags,
            'months': months,
            'months_short': months_short,
            'week_days': week_days,
            'djmatic_profile': get_djmatic_profile(service_user),
            'jukebox_server_api': JUKEBOX_SERVER_API_URL,
            'bulk_invite_message': bulk_invite_message,
            'SolutionModule': SolutionModule,
            'email_settings': json.dumps(
                serialize_complex_value(
                    SolutionEmailSettingsTO.fromModel(get_solution_email_settings(), service_user),
                    SolutionEmailSettingsTO, False)),
            'SLN_LOGO_WIDTH': SLN_LOGO_WIDTH,
            'SLN_LOGO_HEIGHT': SLN_LOGO_HEIGHT,
            'UNITS': json.dumps(UNITS),
            'UNIT_SYMBOLS': json.dumps(UNIT_SYMBOLS),
            'CONSTS': consts,
            'CONSTS_JSON': json.dumps(consts),
            'modules': json.dumps(sln_settings.modules),
            'translations': json.dumps(all_translations)
        }

        channel.append_firebase_params(params)
        self.response.out.write(jinja_template.render(params))


class DJMaticOverviewHandler(webapp2.RequestHandler):

    def get(self):
        solution_server_settings = get_solution_server_settings()
        VALID_USERS = [gae_users.User(email) for email in solution_server_settings.djmatic_overview_emails]
        user = gae_users.get_current_user()
        if user and user in VALID_USERS:

            templates = dict()
            for tmpl in ['djmatic_overview_items']:
                templates[tmpl] = JINJA_ENVIRONMENT.get_template(tmpl + '.html').render({})
            templates = json.dumps(templates)

            jinja_template = JINJA_ENVIRONMENT.get_template('djmatic_overview.html')
            self.response.out.write(jinja_template.render({"templates": templates}))
        else:
            if user:
                logging.warn("Untrusted google user in DJMaticOverviewHandler: %s" % user)
            self.abort(404)

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
import os
import pprint
import sys
import traceback
import unittest

from google.appengine.ext import db
from mcfw.cache import _tlocal
from rogerthat.bizz.qrtemplate import store_template
from rogerthat.bizz.service import create_qr_template_key_name
from rogerthat.bizz.system import DEFAULT_QR_CODE_OVERLAY, DEFAULT_QR_CODE_COLOR, HAND_ONLY_QR_CODE_OVERLAY
from rogerthat.dal import put_and_invalidate_cache, app
from rogerthat.models import App
from rogerthat.utils import now, guid
from shop.bizz import put_app_signup_enabled
from shop.models import RegioManagerTeam, RegioManager, LegalEntity
from shop.products import add_all_products
from solution_server_settings import get_solution_server_settings


class TestCase(unittest.TestCase):

    def log(self, *logs):
        sys.stdout.write("\n" + traceback.format_stack()[-2].splitlines()[0] + "\n")
        for logitem in logs:
            if isinstance(logitem, db.Model):
                sys.stdout.write("  db.model: %s.%s key_name %s key_id %s parent_key name %s" % (logitem.__class__.__module__, logitem.__class__.__name__, logitem.key().name(),
                                                                                                 logitem.key().id(), logitem.parent_key().name()))
                logitem = db.to_dict(logitem)
            sys.stdout.write('\n  ' + '\n  '.join(pprint.pformat(logitem, 2, 120, None).splitlines()))
        sys.stdout.write("\n\n")

    def set_datastore_hr_probability(self, datastore_hr_probability):
        self.tearDown()
        self.setUp(datastore_hr_probability)

    def clear_request_cache(self):
        _tlocal.request_cache = dict()

    def setUp(self, datastore_hr_probability=0):
        from rogerthat.bizz.profile import create_user_profile
        from rogerthat.settings import get_server_settings
        from rogerthat.rpc import users
        from google.appengine.datastore import datastore_stub_util
        from google.appengine.ext import testbed
        from rogerthat_tests import register_tst_mobile

        os.environ['HTTP_HOST'] = 'rt.dev:8080'

        self.testbed = testbed.Testbed()
        self.testbed.activate()
        self.datastore_hr_policy = datastore_stub_util.PseudoRandomHRConsistencyPolicy(
            probability=datastore_hr_probability)
        self.testbed.init_datastore_v3_stub(consistency_policy=self.datastore_hr_policy)
        self.testbed.init_taskqueue_stub(root_path=os.path.join(os.path.dirname(__file__), '..', 'build'))
        self.task_queue_stub = self.testbed.get_stub(testbed.TASKQUEUE_SERVICE_NAME)
        self.testbed.init_channel_stub()
        self.testbed.init_search_stub()
        self.testbed.init_blobstore_stub()

        ss = get_server_settings()
        ss.baseUrl = "http://localhost:8080"  # not used
        ss.mobidickAddress = "http://1.2.3.4:8090"  # not used
        ss.jabberEndPoints = ["jabber.mobicage.com:8084"]  # Development jabber server
        ss.jabberSecret = "leeg"
        ss.userCodeCipher = u"dGVzdCAlcyB0ZXN0"
        ss.dashboardEmail = u"dashboard@example.com"
        ss.supportEmail = u"support@example.com"
        ss.supportWorkers = ["test@example.com"]
        ss.serviceCreators = ["djmatic", "djmatic@example.com", "", "test@example.com"]
        ss.staticPinCodes = ["0666", "test@example.com"]
        ss.userEncryptCipherPart1 = base64.b64encode(u'userEncryptCipherPart1')
        ss.userEncryptCipherPart2 = base64.b64encode(u'userEncryptCipherPart2')

        sss = get_solution_server_settings()
        sss.shop_bizz_admin_emails = [u"test@example.com"]
        sss.shop_no_reply_email = u"norepy@example.com"

        apps_to_be_created = {App.APP_TYPE_ROGERTHAT: {App.APP_ID_ROGERTHAT: u'Rogerthat'},
                              App.APP_TYPE_CONTENT_BRANDING: {App.APP_ID_OSA_LOYALTY: u'OSA Terminal'},
                              App.APP_TYPE_CITY_APP: {u'be-loc': u'Lochristi',
                                                      u'be-berlare': u'Berlare',
                                                      u'be-beveren': u'Beveren',
                                                      u'be-neerpelt': u'Neerpelt',
                                                      u'be-sint-truiden': u'Sint-Truiden',
                                                      u'es-madrid': u'Madrid'}}

        apps = {}
        for app_type, apps_dict in apps_to_be_created.iteritems():
            for app_id, app_name in apps_dict.iteritems():
                new_app = App(key=App.create_key(app_id))
                new_app.name = app_name
                new_app.type = app_type
                new_app.core_branding_hash = None
                new_app.facebook_app_id = None
                new_app.ios_app_id = u'com.mobicage.%s' % app_id
                new_app.android_app_id = new_app.ios_app_id
                new_app.is_default = False
                new_app.visible = True
                new_app.creation_time = now()
                new_app.mdp_client_id = guid()
                new_app.mdp_client_secret = guid()
                apps[app_id] = new_app

        rogerthat_app = apps[App.APP_ID_ROGERTHAT]
        rogerthat_app.admin_services = [u'app_admin@rogerth.at']
        rogerthat_app.is_default = True
        rogerthat_app.facebook_app_id = 188033791211994

        app.get_default_app = lambda: rogerthat_app
        app.get_default_app_key = lambda: rogerthat_app.key()

        mobicage_entity = LegalEntity(is_mobicage=True,
                                      name='Mobicage NV',
                                      address='Antwerpsesteenweg 19',
                                      postal_code='9080',
                                      city='Lochristi',
                                      country_code='BE',
                                      phone='+32 9 324 25 64',
                                      email='info@example.com',
                                      iban='BE85 3630 8576 4006',
                                      bic='BBRUBEBB',
                                      terms_of_use=None,
                                      vat_number='BE 0835 560 572',
                                      vat_percent=21)
        mobicage_entity.put()

        regio_manager_team = RegioManagerTeam()
        regio_manager_team.deleted = False
        regio_manager_team.name = u'(test) Mobicage headquarters'
        regio_manager_team.app_ids = [u'rogerthat', u'be-loc']
        regio_manager_team.legal_entity_id = mobicage_entity.key().id()
        regio_manager_team.put()  # need to put here because we need its id later on

        regio_manager = RegioManager(key=RegioManager.create_key(u'support@example.com'))
        regio_manager.name = u'Support'
        regio_manager.app_ids = [u'rogerthat', u'be-loc']
        regio_manager.read_only_app_ids = []
        regio_manager.show_in_stats = True
        regio_manager.internal_support = True
        regio_manager.phone = u'0032654984984'
        regio_manager.credentials = None
        regio_manager.team_id = regio_manager_team.id
        regio_manager_team.support_manager = regio_manager.email

        to_put = apps.values() + [ss, sss, regio_manager, regio_manager_team]
        put_and_invalidate_cache(*to_put)

        for app_id in apps:
            self.setup_qr_templates(app_id)

        users.get_current_user = lambda: users.User(u'g.audenaert@gmail.com')
        user = users.get_current_user()
        create_user_profile(user, u"Geert Audenaert", language='nl')
        m = register_tst_mobile(user.email())
        users.get_current_mobile = lambda: m

        add_all_products(mobicage_entity)

        for app_id, new_app in apps.iteritems():
            if new_app.type == App.APP_TYPE_CITY_APP and app_id.startswith('be-'):
                put_app_signup_enabled(app_id=new_app.app_id, enabled=True)

    def setup_qr_templates(self, app_id):
        app = App.get(App.create_key(app_id))
        app.qrtemplate_keys = list()

        description = u"DEFAULT"
        key_name = create_qr_template_key_name(app_id, description)
        store_template(None, DEFAULT_QR_CODE_OVERLAY, description, u"".join(("%X" % c).rjust(2, '0')
                                                                            for c in DEFAULT_QR_CODE_COLOR), key_name)
        app.qrtemplate_keys.append(key_name)

        description = u"HAND"
        key_name = create_qr_template_key_name(app_id, description)
        store_template(None, HAND_ONLY_QR_CODE_OVERLAY, description, u"".join(("%X" % c).rjust(2, '0')
                                                                              for c in DEFAULT_QR_CODE_COLOR), key_name)
        app.qrtemplate_keys.append(key_name)

        put_and_invalidate_cache(app)

    def tearDown(self):
        self.testbed.deactivate()

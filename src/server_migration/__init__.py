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

from google.appengine.ext import db
import webapp2

from mcfw.rpc import serialize_complex_value
from rogerthat.consts import DEBUG
from rogerthat.dal.profile import get_service_profile
from rogerthat.models import ServiceProfile, UserProfile
from rogerthat.rpc import users


class ServicerMigrationHandler(webapp2.RequestHandler):

    def get(self, path):
        if not DEBUG:
            raise Exception("ServicerMigrationHandler is DEBUG only for now")

        if path == u'users':
            export_users(self)

        elif path == u'services':
            export_services(self)

        elif path == u'service/create_api_key':
            service_create_api_key(self)

        elif path == u'service/config':
            export_service_config(self)

        else:
            self.abort(404)


# # USER ####
def export_users(self):
    cursor = self.request.get("cursor", None)

    qry = UserProfile.all()
    qry.with_cursor(cursor)
    ups = qry.fetch(200)
    if not ups:
        self.response.write(json.dumps({"cursor": None, "l": []}))
        return

    l = []
    for up in ups:
        if not up.owningServiceEmails:
            continue
        l.append({"email": up.user.email(),
                  "password_hash": up.passwordHash,
                  "services": up.owningServiceEmails})

    new_cursor = unicode(qry.cursor())
    self.response.write(json.dumps({"cursor": new_cursor, "l": l}))


# # SERVICE ####
def export_services(self):
    cursor = self.request.get("cursor", None)

    qry = ServiceProfile.all()
    qry.with_cursor(cursor)
    sps = qry.fetch(200)
    if not sps:
        self.response.write(json.dumps({"cursor": None, "l": []}))
        return

    l = []
    for sp in sps:
        if not sp.solution:
            continue
        l.append({"email": sp.user.email(),
                  "password_hash": sp.passwordHash,
                  "solution": sp.solution})

    new_cursor = unicode(qry.cursor())
    self.response.write(json.dumps({"cursor": new_cursor, "l": l}))


def service_create_api_key(self):
    from rogerthat.bizz.service import get_configuration, _generate_api_key
    from rogerthat.to.service import ServiceConfigurationTO

    id_ = self.request.get("id", None)
    service_user = users.User(id_)
    config = get_configuration(service_user)
    should_generate_api_key = True
    for api_key in config.apiKeys:
        if api_key.name == u"oca_dashboard":
            should_generate_api_key = False
            break

    if should_generate_api_key:
        _generate_api_key(service_user, u'oca_dashboard').put()


def export_service_config(self):
    from rogerthat.bizz.service import get_configuration
    from rogerthat.to.service import ServiceConfigurationTO

    id_ = self.request.get("id", None)

    service_user = users.User(id_)
    config = get_configuration(service_user)

    self.response.write(json.dumps({"config": serialize_complex_value(config, ServiceConfigurationTO, False)}))

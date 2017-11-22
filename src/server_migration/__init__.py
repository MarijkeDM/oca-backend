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

import webapp2

from rogerthat.consts import DEBUG
from rogerthat.models import ServiceProfile, UserProfile


class ServicerMigrationHandler(webapp2.RequestHandler):

    def get(self, path):
        if not DEBUG:
            raise Exception("ServicerMigrationHandler is DEBUG only for now")

        if path == u'users':
            export_users(self)
            return
        if path == u'services':
            export_services(self)
            return

        self.abort(404)


def export_users(self):
    cursor = self.request.get("cursor", None)
    logging.debug("export_users with cursor: '%s'", cursor)

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
        l.append({"email": up.user.email(), "services": up.owningServiceEmails})

    new_cursor = unicode(qry.cursor())
    self.response.write(json.dumps({"cursor": new_cursor, "l": l}))


def export_services(self):
    cursor = self.request.get("cursor", None)
    logging.debug("export_services with cursor: '%s'", cursor)

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
        l.append({"email": sp.user.email(), "solution": sp.solution})

    new_cursor = unicode(qry.cursor())
    self.response.write(json.dumps({"cursor": new_cursor, "l": l}))

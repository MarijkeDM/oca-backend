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

import datetime
import hashlib

from google.appengine.ext import db
from rogerthat.dal import parent_key_unsafe
from rogerthat.rpc import users
from rogerthat.utils import base38, today
from rogerthat.utils.service import get_service_user_from_service_identity_user, get_identity_from_service_identity_user
from solutions.common import SOLUTION_COMMON
from solutions.common.utils import create_service_identity_user_wo_default


class SolutionCityVoucherSettings(db.Model):

    usernames = db.StringListProperty(indexed=False)
    pincodes = db.StringListProperty(indexed=False)

    validity = db.IntegerProperty(indexed=False)  # in months

    @property
    def app_id(self):
        return self.key().name()

    @classmethod
    def create_key(cls, app_id):
        return db.Key.from_path(cls.kind(), app_id)


class SolutionCityVoucherTransaction(db.Model):

    ACTION_CREATED = 1
    ACTION_ACTIVATED = 2
    ACTION_REDEEMED = 3

    created = db.IntegerProperty(indexed=True)
    action = db.IntegerProperty(indexed=True)
    value = db.IntegerProperty(indexed=False)
    service_user = db.UserProperty(indexed=False)
    service_identity = db.StringProperty(indexed=False)

    @property
    def action_str(self):
        if self.action == SolutionCityVoucherTransaction.ACTION_CREATED:
            return u'Created'
        elif self.action == SolutionCityVoucherTransaction.ACTION_ACTIVATED:
            return u'Activated'
        elif self.action == SolutionCityVoucherTransaction.ACTION_REDEEMED:
            return u'Redeemed'
        return u'Unknown'


class SolutionCityVoucherRedeemTransaction(db.Model):
    created = db.IntegerProperty(indexed=True)
    confirmed = db.BooleanProperty(indexed=True)
    value = db.IntegerProperty(indexed=False)
    voucher_key = db.StringProperty(indexed=False)
    signature = db.StringProperty(indexed=False)

    @property
    def service_identity_user(self):
        return users.User(self.parent_key().name())


class SolutionCityVoucher(db.Model):
    TYPE = u'city_voucher'

    image_uri = db.StringProperty(indexed=False)
    content_uri = db.StringProperty(indexed=False)

    created = db.IntegerProperty(indexed=True)
    activated = db.BooleanProperty(indexed=True, default=False)
    activation_date = db.IntegerProperty(indexed=False)
    redeemed = db.BooleanProperty(indexed=True, default=False)
    expiration_date = db.IntegerProperty(indexed=True)
    expiration_reminders_sent = db.ListProperty(int, default=[])

    username = db.StringProperty(indexed=False)
    internal_account = db.StringProperty(indexed=False)
    cost_center = db.StringProperty(indexed=False)

    search_fields = db.StringListProperty(indexed=True)

    value = db.IntegerProperty(indexed=False)
    redeemed_value = db.IntegerProperty(indexed=False)
    owner = db.UserProperty(indexed=False)
    owner_name = db.StringProperty(indexed=False)

    @property
    def key_str(self):
        return str(self.key())

    @property
    def uid(self):
        dt = datetime.datetime.utcfromtimestamp(self.created)
        return u"%s-%s-%s %s" % (dt.year, dt.month, dt.day, base38.encode_int(self.key().id()))

    @property
    def app_id(self):
        return self.parent_key().name()

    @property
    def expired(self):
        return self.expiration_date and self.expiration_date <= today()

    @classmethod
    def create_parent_key(cls, app_id):
        return db.Key.from_path(u"city_wide_voucher", app_id)

    def load_transactions(self):
        qry = SolutionCityVoucherTransaction.all().ancestor(self)
        qry.order('-created')
        return qry

    def signature(self):
        digester = hashlib.sha256()
        digester.update(str(self.created))
        digester.update(str(self.activated))
        digester.update(str(self.redeemed))
        if self.username:
            digester.update(self.username.encode("utf8"))
            digester.update(self.internal_account.encode("utf8"))
            digester.update(self.cost_center.encode("utf8"))
        digester.update(str(self.value))
        digester.update(str(self.redeemed_value))

        for t in self.load_transactions():
            digester.update(str(t.created))
            digester.update(str(t.action))
            digester.update(str(t.value))
            if t.service_user:
                digester.update(t.service_user.email().encode("utf8"))
                digester.update(t.service_identity)

        return digester.hexdigest()


class SolutionCityVoucherQRCodeExport(db.Model):

    created = db.IntegerProperty(indexed=True)
    ready = db.BooleanProperty(indexed=False, default=False)

    voucher_ids = db.ListProperty(long, indexed=False)

    @property
    def key_str(self):
        return str(self.key())

    @classmethod
    def create_parent_key(cls, app_id):
        return db.Key.from_path(u"city_wide_voucher", app_id)


class SolutionCityVoucherExport(db.Model):
    xls = db.BlobProperty()
    year_month = db.IntegerProperty()  # 201606

    @classmethod
    def create_parent_key(cls, app_id):
        return db.Key.from_path(u"city_wide_voucher", app_id)

    @classmethod
    def create_key(cls, app_id, year, month):
        ancestor_key = cls.create_parent_key(app_id)
        return db.Key.from_path(cls.kind(), '%s_%s' % (year, month), parent=ancestor_key)


class SolutionCityVoucherExportMerchant(db.Model):
    xls = db.BlobProperty()
    year_month = db.IntegerProperty()  # 201606

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
    def create_key(cls, service_user, service_identity, year, month):
        service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
        return db.Key.from_path(cls.kind(), '%s_%s' % (year, month), parent=parent_key_unsafe(service_identity_user, SOLUTION_COMMON))

    @classmethod
    def list_by_service_user(cls, service_user, service_identity):
        service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
        return cls.all().ancestor(parent_key_unsafe(service_identity_user, SOLUTION_COMMON)).order('-year_month')

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

from mcfw.properties import unicode_property, long_property, bool_property, typed_property
from rogerthat.utils import today
from solutions.common.to.loyalty import SolutionLoyaltyExportTO


class SolutionCityVoucherTO(object):
    id = long_property('1')
    created = long_property('2')
    uid = unicode_property('3')
    value = long_property('4')
    redeemed_value = long_property('5')
    activated = bool_property('6')
    redeemed = bool_property('7')
    expiration_date = long_property('8')
    expired = bool_property('9')
    owner = unicode_property('10')
    owner_name = unicode_property('11')

    @classmethod
    def fromModel(cls, obj):
        to = cls()
        to.id = obj.key().id()
        to.created = obj.created
        to.uid = obj.uid
        to.value = obj.value
        to.redeemed_value = obj.redeemed_value
        to.activated = obj.activated
        to.redeemed = obj.redeemed
        to.expiration_date = obj.expiration_date
        to.expired = obj.expired
        to.owner = obj.owner and obj.owner.email()
        to.owner_name = obj.owner_name
        return to


class SolutionCityVouchersTO(object):
    cursor = unicode_property('1')
    has_more = bool_property('2')
    vouchers = typed_property('3', SolutionCityVoucherTO, True)

    @staticmethod
    def fromModel(cursor, vouchers, has_more):
        to = SolutionCityVouchersTO()
        to.cursor = cursor
        to.has_more = has_more
        to.vouchers = [SolutionCityVoucherTO.fromModel(v) for v in vouchers]
        return to


class SolutionCityVoucherTransactionLogTO(object):
    created = long_property('1')
    action = long_property('2')
    value = long_property('3')

    @staticmethod
    def fromModel(obj):
        to = SolutionCityVoucherTransactionLogTO()
        to.created = obj.created
        to.action = obj.action
        to.value = obj.value
        return to


class SolutionCityVoucherTransactionsTO(SolutionCityVoucherTO):
    transactions = typed_property('transactions', SolutionCityVoucherTransactionLogTO, True)

    @classmethod
    def fromModel(cls, obj):
        to = super(SolutionCityVoucherTransactionsTO, cls).fromModel(obj)
        to.transactions = [SolutionCityVoucherTransactionLogTO.fromModel(v) for v in obj.load_transactions()]
        return to


class SolutionCityVoucherQRCodeExportTO(object):
    id = long_property('1')
    created = long_property('2')
    ready = bool_property('3')

    @staticmethod
    def fromModel(obj):
        to = SolutionCityVoucherQRCodeExportTO()
        to.id = obj.key().id()
        to.created = obj.created
        to.ready = obj.ready
        return to

class SolutionCityVoucherQRCodeExportsTO(object):
    cursor = unicode_property('1')
    has_more = bool_property('2')
    data = typed_property('3', SolutionCityVoucherQRCodeExportTO, True)

    @staticmethod
    def fromModel(cursor, data, has_more):
        to = SolutionCityVoucherQRCodeExportsTO()
        to.cursor = cursor
        to.has_more = has_more
        to.data = [SolutionCityVoucherQRCodeExportTO.fromModel(d) for d in data]
        return to


class SolutionCityVoucherExportListTO(object):
    cursor = unicode_property('1')
    has_more = bool_property('2')
    data = typed_property('3', SolutionLoyaltyExportTO, True)

    @classmethod
    def fromModel(cls, cursor, data, has_more):
        to = cls()
        to.cursor = cursor
        to.has_more = has_more
        to.data = data
        return to

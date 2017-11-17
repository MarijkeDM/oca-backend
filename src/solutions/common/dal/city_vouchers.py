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

from mcfw.rpc import returns, arguments
from rogerthat.utils import today
from solutions.common.models.city_vouchers import SolutionCityVoucherQRCodeExport, SolutionCityVoucher, \
    SolutionCityVoucherExport, SolutionCityVoucherSettings


@returns(SolutionCityVoucherSettings)
@arguments(app_id=unicode)
def get_city_vouchers_settings(app_id):
    key = SolutionCityVoucherSettings.create_key(app_id)
    return SolutionCityVoucherSettings.get(key)


@returns(tuple)
@arguments(app_id=unicode, cursor=unicode, limit=int)
def get_expired_vouchers(app_id, cursor=None, limit=50):
    parnet_key = SolutionCityVoucher.create_parent_key(app_id)
    qry = SolutionCityVoucher.all().with_cursor(cursor).ancestor(parnet_key)
    qry.filter('expiration_date <=', today()).order('-expiration_date')
    data = qry.fetch(limit)
    new_cursor = unicode(qry.cursor())
    has_more = new_cursor != cursor
    return new_cursor, data, has_more


@returns(tuple)
@arguments(app_id=unicode, search_string=unicode, count=(int, long), cursor=unicode)
def get_solution_city_vouchers(app_id, search_string, count, cursor=None):
    ancestor_key = SolutionCityVoucher.create_parent_key(app_id)
    qry = SolutionCityVoucher.all().with_cursor(cursor).ancestor(ancestor_key)
    search_array = search_string.split(" ")
    for term in search_array:
        if not term:
            continue

        qry.filter("search_fields =", term.lower())
    data = qry.fetch(count)
    cursor_ = qry.cursor()
    has_more = False
    if len(data) != 0:
        qry.with_cursor(cursor_)
        if len(qry.fetch(1)) > 0:
            has_more = True

    return unicode(cursor_), data, has_more


@returns(tuple)
@arguments(app_id=unicode, count=(int, long), cursor=unicode)
def get_solution_city_voucher_qr_codes(app_id, count, cursor=None):
    ancestor_key = SolutionCityVoucherQRCodeExport.create_parent_key(app_id)
    qry = SolutionCityVoucherQRCodeExport.all().with_cursor(cursor).ancestor(ancestor_key)
    qry.order('-created')
    data = qry.fetch(count)
    cursor_ = qry.cursor()
    has_more = False
    if len(data) != 0:
        qry.with_cursor(cursor_)
        if len(qry.fetch(1)) > 0:
            has_more = True

    return unicode(cursor_), data, has_more


@returns(tuple)
@arguments(app_id=unicode, count=(int, long), cursor=unicode)
def get_solution_city_voucher_exports(app_id, count, cursor=None):
    ancestor_key = SolutionCityVoucherExport.create_parent_key(app_id)
    qry = SolutionCityVoucherExport.all().with_cursor(cursor).ancestor(ancestor_key)
    qry.order('-year_month')
    data = qry.fetch(count)
    cursor_ = qry.cursor()
    has_more = False
    if len(data) != 0:
        qry.with_cursor(cursor_)
        if len(qry.fetch(1)) > 0:
            has_more = True

    return unicode(cursor_), data, has_more

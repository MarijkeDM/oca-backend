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

from mcfw.restapi import rest
from mcfw.rpc import returns, arguments, NoneType
from rogerthat.rpc import users
from rogerthat.to import ReturnStatusTO, RETURNSTATUS_TO_SUCCESS
from rogerthat.utils import now
from solutions.common.bizz import SolutionModule
from solutions.common.bizz.city_vouchers import create_city_voucher_qr_codes
from solutions.common.dal import get_solution_settings
from solutions.common.dal.city_vouchers import get_solution_city_voucher_qr_codes, get_solution_city_vouchers, \
    get_solution_city_voucher_exports, get_city_vouchers_settings, get_expired_vouchers
from solutions.common.models.city_vouchers import SolutionCityVoucher, SolutionCityVoucherExportMerchant, \
    SolutionCityVoucherSettings
from solutions.common.to.city_vouchers import SolutionCityVouchersTO, SolutionCityVoucherQRCodeExportsTO, \
    SolutionCityVoucherTransactionsTO, SolutionCityVoucherExportListTO
from solutions.common.to.loyalty import SolutionLoyaltyExportTO, SolutionLoyaltyExportListTO


@rest("/common/city/vouchers/search", "get", read_only_access=True)
@returns(SolutionCityVouchersTO)
@arguments(app_id=unicode, search_string=unicode, cursor=unicode)
def search_city_vouchers(app_id, search_string, cursor=None):
    cursor_, vouchers, has_more = get_solution_city_vouchers(app_id, search_string, 10, cursor)
    return SolutionCityVouchersTO.fromModel(cursor_, vouchers, has_more)


@rest("/common/city/vouchers/expired", "get", read_only_access=True)
@returns(SolutionCityVouchersTO)
@arguments(app_id=unicode, cursor=unicode)
def load_expired_vouchers(app_id, cursor=None):
    return SolutionCityVouchersTO.fromModel(*get_expired_vouchers(app_id, cursor))


@rest("/common/city/vouchers/transactions/load", "get", read_only_access=True)
@returns(SolutionCityVoucherTransactionsTO)
@arguments(app_id=unicode, voucher_id=(int, long))
def load_city_voucher_history(app_id, voucher_id):
    ancestor_key = SolutionCityVoucher.create_parent_key(app_id)
    sln_city_voucher = SolutionCityVoucher.get_by_id(voucher_id, ancestor_key)
    return SolutionCityVoucherTransactionsTO.fromModel(sln_city_voucher)


@rest("/common/city/vouchers/qrcode_export/load", "get", read_only_access=True)
@returns(SolutionCityVoucherQRCodeExportsTO)
@arguments(app_id=unicode, cursor=unicode)
def load_city_voucher_qr_codes_export(app_id, cursor=None):
    cursor_, data, has_more = get_solution_city_voucher_qr_codes(app_id, 10, cursor)
    return SolutionCityVoucherQRCodeExportsTO.fromModel(cursor_, data, has_more)


@rest("/common/city/vouchers/qrcode_export/put", "post")
@returns(ReturnStatusTO)
@arguments(app_id=unicode)
def put_city_voucher_qr_codes_export(app_id):
    service_user = users.get_current_user()
    create_city_voucher_qr_codes(service_user, app_id)
    return RETURNSTATUS_TO_SUCCESS


@rest("/common/city/vouchers/export/load", "get", read_only_access=True)
@returns(SolutionCityVoucherExportListTO)
@arguments(app_id=unicode, cursor=unicode)
def load_city_voucher_export(app_id, cursor=None):
    service_user = users.get_current_user()
    cursor_, data, has_more = get_solution_city_voucher_exports(app_id, 10, cursor)
    sln_settings = get_solution_settings(service_user)
    d = [SolutionLoyaltyExportTO.from_model(e, sln_settings.main_language) for e in data]
    return SolutionCityVoucherExportListTO.fromModel(cursor_, d, has_more)


@rest("/common/vouchers/export/list", "get", read_only_access=True)
@returns(SolutionLoyaltyExportListTO)
@arguments(cursor=unicode)
def load_loyalty_export_list(cursor=None):
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    exports_q = SolutionCityVoucherExportMerchant.list_by_service_user(service_user, None)
    exports_q.with_cursor(cursor)
    exports_list = exports_q.fetch(10)
    cursor = unicode(exports_q.cursor())
    to = SolutionLoyaltyExportListTO.create(cursor,
                                            [SolutionLoyaltyExportTO.from_model(e, sln_settings.main_language)
                                             for e in exports_list])
    return to


@rest("/common/vouchers/validity/put", "post")
@returns(ReturnStatusTO)
@arguments(app_id=unicode, validity=(int, long, NoneType))
def update_vouchers_validity(app_id, validity):
    """Sets the vouchers validity in months"""
    sln_settings = get_solution_settings(users.get_current_user())
    if SolutionModule.CITY_VOUCHERS not in sln_settings.modules:
        return ReturnStatusTO.create(False, 'no_permission')

    if isinstance(validity, (int, long)) and validity < 1:
        return ReturnStatusTO.create(False, 'invalid_validity_period')

    voucher_settings = get_city_vouchers_settings(app_id)
    if not voucher_settings:
        voucher_settings = SolutionCityVoucherSettings(key=SolutionCityVoucherSettings.create_key(app_id))
    voucher_settings.validity = validity
    voucher_settings.put()
    return RETURNSTATUS_TO_SUCCESS

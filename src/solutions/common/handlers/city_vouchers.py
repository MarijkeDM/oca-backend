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

from collections import namedtuple
import csv

from rogerthat.rpc import users
from rogerthat.service.api import system
from shop.dal import get_customer
from solutions import translate, SOLUTION_COMMON
from solutions.common.bizz import SolutionModule
from solutions.common.dal import get_solution_settings
from solutions.common.models.city_vouchers import SolutionCityVoucherQRCodeExport, SolutionCityVoucherExport, \
    SolutionCityVoucherExportMerchant, SolutionCityVoucher
import webapp2


def get_exported_filename(language, year, month):
    name = translate(language, SOLUTION_COMMON, 'Vouchers')
    return '%s %s-%s.xls' % (name, year, month)


class CityVouchersDownloadHandler(webapp2.RequestHandler):
    def get(self, city_voucher_id):
        city_voucher_id = long(city_voucher_id)
        service_user = users.get_current_user()

        users.set_user(service_user)
        try:
            identity = system.get_identity()
        except:
            self.abort(500)
            return
        finally:
            users.clear_user()

        app_id = identity.app_ids[0]
        ancestor_key = SolutionCityVoucherQRCodeExport.create_parent_key(app_id)
        sln_qr_export = SolutionCityVoucherQRCodeExport.get_by_id(city_voucher_id, parent=ancestor_key)
        if not sln_qr_export:
            self.abort(500)
            return

        Export = namedtuple('Export', 'url uid')

        result = dict()
        voucher_ancestor_key = SolutionCityVoucher.create_parent_key(app_id)
        vouchers = SolutionCityVoucher.get_by_id(sln_qr_export.voucher_ids, parent=voucher_ancestor_key)
        for voucher in vouchers:
            result[voucher.uid] = Export(voucher.content_uri, voucher.uid)

        self.response.headers['Content-Type'] = 'application/vnd.ms-excel'
        self.response.headers['Content-Disposition'] = str('attachment; filename=city_vouchers_%s.csv' % sln_qr_export.created)
        writer = csv.writer(self.response.out, dialect='excel')
        for export in result.values():
            writer.writerow((export.url.encode("utf-8"),
                             export.uid.encode("utf-8")))


class CityVoucherExportHandler(webapp2.RequestHandler):
    def get(self):
        service_user = users.get_current_user()
        sln_settings = get_solution_settings(service_user)
        if SolutionModule.CITY_VOUCHERS not in sln_settings.modules:
            self.response.set_status(404)
            return

        app_id = self.request.get('a')
        customer = get_customer(service_user)
        if app_id != customer.app_id:
            self.response.set_status(404)
            return

        year = self.request.get('y')
        month = self.request.get('m')

        sln_city_voucher_export_key = SolutionCityVoucherExport.create_key(app_id, year, month)
        export = SolutionCityVoucherExport.get(sln_city_voucher_export_key)
        if export:
            self.response.headers['Content-Type'] = 'application/vnd.ms-excel'
            filename = get_exported_filename(sln_settings.main_language, year, month)
            self.response.headers['Content-Disposition'] = str('attachment; filename=%s' % filename)
            self.response.write(export.xls)
        else:
            self.response.set_status(404)


class ExportVoucherHandler(webapp2.RequestHandler):
    def get(self):
        service_user = users.get_current_user()
        sln_settings = get_solution_settings(service_user)

        year = self.request.get('y')
        month = self.request.get('m')

        sln_city_voucher_export_key = SolutionCityVoucherExportMerchant.create_key(service_user, None, year, month)
        export = SolutionCityVoucherExportMerchant.get(sln_city_voucher_export_key)
        if export:
            self.response.headers['Content-Type'] = 'application/vnd.ms-excel'
            filename = get_exported_filename(sln_settings.main_language, year, month)
            self.response.headers['Content-Disposition'] = str('attachment; filename=%s' % filename)
            self.response.write(export.xls)
        else:
            self.response.set_status(404)

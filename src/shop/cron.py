# -*- coding: utf-8 -*-
# Copyright 2016 Mobicage NV
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
# @@license_version:1.1@@

import webapp2

from shop.jobs import notify_extention_needed
from shop.jobs.export_reseller_invoices import export_reseller_invoices_this_week
from shop.jobs.recurrentbilling import schedule_recurrent_billing
from shop.jobs.report_on_site_payments import schedule_report_on_site_payments


class RecurrentBilling(webapp2.RequestHandler):

    def get(self):
        schedule_recurrent_billing()


class ReportOnSitePaymentsHandler(webapp2.RequestHandler):

    def get(self):
        schedule_report_on_site_payments()


class NotifyExtentionNeededHandler(webapp2.RequestHandler):

    def get(self):
        notify_extention_needed.job()


class ExportResellerInvoicesHandler(webapp2.RequestHandler):
    def get(self):
        export_reseller_invoices_this_week()
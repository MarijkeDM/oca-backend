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
import logging
import time

from dateutil.relativedelta import relativedelta

from rogerthat.settings import get_server_settings
from rogerthat.utils import send_mail
from google.appengine.ext import db, deferred
from shop.models import Invoice, Charge, Customer
from solution_server_settings import get_solution_server_settings


def schedule_report_on_site_payments():
    deferred.defer(report_on_site_payments, _transactional=db.is_in_transaction())


def report_on_site_payments():
    one_month_ago = datetime.datetime.today() - relativedelta(months=1)
    min_date = int(time.mktime(one_month_ago.timetuple()))

    invoices = Invoice.all().filter('payment_type', Invoice.PAYMENT_ON_SITE).filter('date >=', min_date)
    charges = Charge.get((i.charge_key for i in invoices))
    customers = Customer.get((i.order_key.parent() for i in invoices))

    l = ['[%(date_str)s][%(customer)s][%(manager)s][%(amount).02f][%(charge_number)s]'
         % dict(customer=c.name, manager=i.operator, amount=i.amount / 100.0, date=i.date, date_str=time.ctime(i.date), charge_number=charge.charge_number)
         for (i, charge, c) in sorted(zip(invoices, charges, customers),
                                      key=lambda t: t[0].date)]
    body = "\n".join(l) or u"There were no on site payments for the last month"
    logging.info(body)
    
    server_settings = get_server_settings()
    solution_server_settings = get_solution_server_settings()
    subject = u'On site payments for the last month'
    send_mail(server_settings.dashboardEmail,
              solution_server_settings.shop_payment_admin_emails,
              subject,
              body)

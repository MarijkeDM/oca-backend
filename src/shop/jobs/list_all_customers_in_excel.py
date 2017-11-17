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
from collections import defaultdict
import datetime

from babel.dates import format_datetime

from rogerthat.settings import get_server_settings
from rogerthat.translations import DEFAULT_LANGUAGE
from rogerthat.utils import send_mail
from shop.models import Customer
import xlwt


try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


def job():
    settings = get_server_settings()
    customers = list(Customer.all().fetch(10))
    customers_per_app = defaultdict(list)
    for customer in customers:
        customers_per_app[customer.default_app_id].append(customer)
    book = xlwt.Workbook(encoding='utf-8')
    for app_id in customers_per_app:
        if not app_id:
            continue
        sheet = book.add_sheet(app_id)
        row = 0
        sheet.write(row, 0, 'Customer name')
        for customer in customers_per_app[app_id]:
            row += 1
            url = '%s/internal/shop/login_as?customer_id=%d' % (settings.baseUrl, customer.id)
            sheet.write(row, 0, xlwt.Formula('HYPERLINK("%s";"%s")' % (url, customer.name.replace('"', ''))))

    excel = StringIO()
    book.save(excel)
    excel_string = excel.getvalue()

    current_date = format_datetime(datetime.datetime.now(), locale=DEFAULT_LANGUAGE)
    to_emails = [u'lucas@mobicage.com', u'tom@mobicage.com', u'gert@mobicage.com']
    
    attachments = []
    attachments.append(('Customers %s.xls' % current_date,
                        base64.b64encode(excel_string)))

    subject = 'List of all customers'
    message = 'See attachment.'
    send_mail('export@mobicage.com', to_emails, subject, message, attachments=attachments)

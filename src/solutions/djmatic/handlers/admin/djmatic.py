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
import calendar
import csv
import datetime
import os
import time
from types import NoneType

from babel.dates import get_timezone, format_datetime
from dateutil.relativedelta import relativedelta

from google.appengine.ext import webapp, deferred, db
from google.appengine.ext.webapp import template
from mcfw.restapi import rest
from mcfw.rpc import returns, arguments
from rogerthat.models import ServiceIdentityStatistic, ServiceIdentity
from rogerthat.to import ReturnStatusTO, RETURNSTATUS_TO_SUCCESS
from rogerthat.utils import get_epoch_from_datetime, now, send_mail
from rogerthat.utils.service import create_service_identity_user
from solution_server_settings import get_solution_server_settings
from solutions.djmatic.dal import get_djmatic_overview_log
from solutions.djmatic.models import DjMaticProfile


try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

class DjmaticOverviewLogsHandler(webapp.RequestHandler):

    def _epoch_to_str(self, epoch):
        split = time.ctime(epoch).split(" ")
        while "" in split:
            split.remove("")
        split.remove(split[0])  # Day of week
        split.remove(split[1])  # day
        split.remove(split[1])  # timestamp
        return " ".join(split)

    def get(self):
        offset = int(self.request.GET.get("offset", 0))  # go back <offset> days in the past

        today = datetime.date.today()
        viewed_day = today - relativedelta(months=offset)
        first_day_of_viewed_month = datetime.date(viewed_day.year, viewed_day.month, 1)
        last_day_of_viewed_month = datetime.date(viewed_day.year, viewed_day.month, calendar.monthrange(viewed_day.year, viewed_day.month)[1])

        min_timestamp = get_epoch_from_datetime(first_day_of_viewed_month)
        max_timestamp = get_epoch_from_datetime(last_day_of_viewed_month)

        args = {"changes": get_djmatic_overview_log(min_timestamp, max_timestamp),
                "current_day":self._epoch_to_str(min_timestamp),
                "next_url":"/admin/djmatic_overview_logs?offset=%s" % (offset - 1) if offset else "",
                "back_url":"/admin/djmatic_overview_logs?offset=%s" % (offset + 1)}
        path = os.path.join(os.path.dirname(__file__), 'djmatic_overview_logs.html')
        self.response.out.write(template.render(path, args))

class DjmaticExportHandler(webapp.RequestHandler):

    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'djmatic_export.html')
        self.response.out.write(template.render(path, {}))


@rest("/admin/rest/djmatic/export", "post")
@returns(ReturnStatusTO)
@arguments(email=unicode)
def start_export(email):
    if email:
        deferred.defer(_djmatic_export, email)
        return RETURNSTATUS_TO_SUCCESS
    else:
        return ReturnStatusTO.create(False, u"Please provide an email address")

@returns(NoneType)
@arguments(email=unicode)
def _djmatic_export(email):
    data = []
    cursor = None
    while True:
        new_data, cursor, has_more = _djmatic_export_step1_gather_data(cursor)
        if new_data:
            data.extend(new_data)
        if not has_more:
            break

    fieldnames = ['PLAYER_ID', 'NAME', 'EMAIL', 'STATUS', 'TYPE', 'USERS', 'DATE', 'DAYS', 'USAGE']
    csv_string = StringIO()
    writer = csv.DictWriter(csv_string, dialect='excel', fieldnames=fieldnames)
    writer.writeheader()
    for row in data:
        writer.writerow(row)

    current_date = datetime.datetime.fromtimestamp(now(), tz=get_timezone('Europe/Brussels'))
    current_date_str = format_datetime(current_date, locale='nl_BE',
                                        format='d/M/yyyy H:mm')

    solution_server_settings = get_solution_server_settings()
    subject = u'DJMatic export %s' % current_date_str
    body_text = u'The exported DJMatic list from %s can be found in the attachment of this email.' % current_date_str

    attachments = []
    attachments.append((u'djmatic_export %s.csv' % current_date_str,
                        base64.b64encode(csv_string.getvalue())))

    send_mail(solution_server_settings.shop_export_email, [email], subject, body_text, attachments=attachments)

def _djmatic_export_step1_gather_data(cursor):
    qry = DjMaticProfile.all()
    qry.with_cursor(cursor)
    djmatic_profiles = qry.fetch(100)
    if not djmatic_profiles:
        return [], None, False
    cursor_ = qry.cursor()
    sis_keys = []
    for djmatic_profile in djmatic_profiles:
        sis_key = ServiceIdentityStatistic.create_key(create_service_identity_user(djmatic_profile.service_user,
                                                                                   identity=ServiceIdentity.DEFAULT))
        sis_keys.append(sis_key)

    siss = db.get(sis_keys)

    data = []
    for djmatic_profile, sis in zip(djmatic_profiles, siss):
        if not sis:
            continue
        if sis.number_of_users < 10:
            continue

        sum_count = 0
        for i, _ in enumerate(sis.mip_labels):
            l = getattr(sis, 'mip_%s' % i)
            sum_count += sum(l)

        data.append({"PLAYER_ID": djmatic_profile.player_id,
                     "NAME": djmatic_profile.name.encode('ascii', 'ignore'),
                     "EMAIL": djmatic_profile.service_user.email(),
                     "STATUS": DjMaticProfile.status_string(djmatic_profile.status),
                     "TYPE": djmatic_profile.type,
                     "USERS": sis.number_of_users,
                     'DATE': unicode(djmatic_profile.days_date),
                     "DAYS": djmatic_profile.days,
                     "USAGE": sum_count})

    return data, cursor_, True

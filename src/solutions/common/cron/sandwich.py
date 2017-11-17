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

from datetime import datetime
import logging

import pytz

from google.appengine.ext import webapp, deferred, db
from rogerthat.bizz.job import run_job
from rogerthat.consts import SCHEDULED_QUEUE
from rogerthat.dal import parent_key
from rogerthat.rpc import users
from rogerthat.service.api import messaging
from rogerthat.to.messaging import AnswerTO
from rogerthat.translations import DEFAULT_LANGUAGE
from rogerthat.utils import now
from solutions import translate
from solutions.common import SOLUTION_COMMON
from solutions.common.bizz import SolutionModule
from solutions.common.bizz.messaging import MESSAGE_TAG_SANDWICH_ORDER_NOW
from solutions.common.bizz.sandwich import get_sandwich_reminder_broadcast_type
from solutions.common.dal import get_solution_settings_or_identity_settings
from solutions.common.models import SolutionSettings, SolutionMainBranding
from solutions.common.models.sandwich import SandwichSettings, \
    SandwichLastBroadcastDay


class SandwichAutoBroadcastCronHandler(webapp.RequestHandler):

    def get(self):
        deferred.defer(_schedule_auto_broadcasts)

def _schedule_auto_broadcasts():
    run_job(_qry, [], _worker, [])

def _qry():
    return SolutionSettings.all(keys_only=True).filter("modules =", SolutionModule.SANDWICH_BAR)

def _worker(sln_settings_key):
    sln_settings = db.get(sln_settings_key)
    def trans():
        sandwich_settings = SandwichSettings.get_settings(sln_settings.service_user, sln_settings.solution)
        solution_datetime = datetime.now(pytz.timezone(sln_settings.timezone))
        if not sandwich_settings.can_broadcast_for_sandwiches_on(solution_datetime):
            logging.info("No email_reminders today for %s", sln_settings.service_user.email())
            return

        last_broad_cast_day = SandwichLastBroadcastDay.get_last_broadcast_day(sln_settings.service_user,
                                                                              sln_settings.solution)
        if last_broad_cast_day and last_broad_cast_day.year == solution_datetime.year and \
            last_broad_cast_day.month == solution_datetime.month and last_broad_cast_day.day == solution_datetime.day:
            logging.info("Sandwich broadcast already sent today for %s", sln_settings.service_user.email())
            return
        seconds_before_broadcast = sandwich_settings.remind_at - ((solution_datetime.hour * 3600) +
                                                                  (solution_datetime.minute * 60) +
                                                                  (solution_datetime.second))
        if seconds_before_broadcast < 0:
            seconds_before_broadcast = 0
        if not last_broad_cast_day:
            last_broad_cast_day = SandwichLastBroadcastDay(key_name=sln_settings.service_user.email(),
                                                           parent=parent_key(sln_settings.service_user,
                                                                             sln_settings.solution))
        last_broad_cast_day.year = solution_datetime.year
        last_broad_cast_day.month = solution_datetime.month
        last_broad_cast_day.day = solution_datetime.day
        last_broad_cast_day.put()
        deferred.defer(_broadcast, sln_settings_key, sandwich_settings.key(),
                       _transactional=True, _countdown=seconds_before_broadcast, _queue=SCHEDULED_QUEUE)
    db.run_in_transaction(trans)

def _broadcast(sln_settings_key, sandwich_settings_key):
    sln_settings, sandwich_settings = db.get([sln_settings_key, sandwich_settings_key])
    if not sln_settings:
        logging.info("Service has been deleted in the meantime")
        return
    solution_datetime = datetime.now(pytz.timezone(sln_settings.timezone))
    if not sandwich_settings.can_order_sandwiches_on(solution_datetime):
        logging.info("No email_reminders anymore today for %s", sln_settings.service_user.email())
        return
    broadcast_type = get_sandwich_reminder_broadcast_type(sln_settings.main_language or DEFAULT_LANGUAGE,
                                                          SandwichSettings.DAYS[solution_datetime.weekday()])
    message = sandwich_settings.reminder_broadcast_message
    order_sandwich_answer = AnswerTO()
    order_sandwich_answer.action = None
    order_sandwich_answer.caption = translate(sln_settings.main_language, SOLUTION_COMMON, u'order')
    order_sandwich_answer.type = u'button'
    order_sandwich_answer.id = u'order'
    order_sandwich_answer.ui_flags = 1
    no_sandwich_today_answer = AnswerTO()
    no_sandwich_today_answer.action = None
    no_sandwich_today_answer.caption = translate(sln_settings.main_language, SOLUTION_COMMON,
                                                 u'order-sandwiches-not-today')
    no_sandwich_today_answer.type = u'button'
    no_sandwich_today_answer.id = u'Not now'
    no_sandwich_today_answer.ui_flags = 0
    answers = list()
    answers.append(order_sandwich_answer)
    answers.append(no_sandwich_today_answer)
    flags = 0
    branding = db.get(SolutionMainBranding.create_key(sln_settings.service_user)).branding_key
    tag = MESSAGE_TAG_SANDWICH_ORDER_NOW
    alert_flags = 0
    timeout = sandwich_settings.get_reminder_broadcast_timeout(solution_datetime)

    users.set_user(sln_settings.service_user)
    try:
        identities = [None]
        if sln_settings.identities:
            identities.extend(sln_settings.identities)
        for service_identity in identities:
            sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
            if sln_i_settings.is_in_holiday_for_date(now()):
                logging.info("Not sending out sandwich broadcast '%s'. %s is in holiday.",
                             broadcast_type, sln_i_settings.service_user)
            else:
                logging.info("Sending broadcast to users of %s with broadcast type %s",
                             sln_i_settings.service_user, broadcast_type)
                messaging.broadcast(broadcast_type, message, answers, flags, branding, tag, service_identity,
                                    alert_flags, timeout=timeout)
    finally:
        users.clear_user()

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

from datetime import date, datetime
from dateutil.relativedelta import relativedelta
import json
import logging
import pytz
import random
import time

from babel.dates import format_datetime

from google.appengine.ext import webapp, deferred, db
from mcfw.properties import azzert
from mcfw.rpc import serialize_complex_value, returns, arguments
from rogerthat.bizz.job import run_job
from rogerthat.consts import SCHEDULED_QUEUE
from rogerthat.dal import parent_key_unsafe, put_and_invalidate_cache
from rogerthat.dal.profile import get_profile_infos
from rogerthat.models import Message
from rogerthat.rpc import users
from rogerthat.service.api import messaging, system
from rogerthat.to.messaging import AnswerTO
from rogerthat.to.service import UserDetailsTO
from rogerthat.translations import DEFAULT_LANGUAGE
from rogerthat.utils import now, send_mail
from rogerthat.utils.channel import send_message
from solution_server_settings import get_solution_server_settings
from solutions import translate
from solutions.common import SOLUTION_COMMON
from solutions.common.bizz import SolutionModule, get_app_info_cached
from solutions.common.bizz.inbox import create_solution_inbox_message, add_solution_inbox_message
from solutions.common.bizz.loyalty import update_user_data_admins, create_loyalty_statistics_for_service, \
    send_email_to_user_for_loyalty_update
from solutions.common.bizz.messaging import send_inbox_forwarders_message
from solutions.common.dal import get_solution_settings_or_identity_settings, get_solution_settings
from solutions.common.dal.cityapp import get_service_user_for_city
from solutions.common.models import SolutionInboxMessage, SolutionSettings
from solutions.common.models.loyalty import SolutionLoyaltyLottery, SolutionLoyaltySettings, SolutionLoyaltyVisitLottery, \
    SolutionLoyaltyLotteryStatistics, SolutionCityWideLottery, SolutionCityWideLotteryStatistics, \
    SolutionCityWideLotteryVisit
from solutions.common.models.properties import SolutionUser
from solutions.common.to import SolutionInboxMessageTO
from solutions.common.to.loyalty import ExtendedUserDetailsTO
from solutions.common.utils import create_service_identity_user_wo_default
from rogerthat.rpc.users import set_user


class LootLotteryCronHandler(webapp.RequestHandler):

    def get(self):
        _schedule_loot_lottery()
        _schedule_loot_city_wide_lottery()


class SolutionLoyaltyExportHandler(webapp.RequestHandler):
    def get(self):
        create_loyalty_export_pdfs()


def _schedule_loot_lottery():
    run_job(_qry, [], _worker, [])

def _qry():
    return SolutionLoyaltyLottery.all(keys_only=True).filter("schedule_loot_time <", now()).filter("schedule_loot_time >", 0)

def _worker(sln_loyalty_lottery_key):
    def trans():
        sln_loyalty_lottery = db.get(sln_loyalty_lottery_key)
        service_user = sln_loyalty_lottery.service_user
        logging.info("loyalty lottery loot: %s", service_user)

        sls_key = SolutionLoyaltySettings.create_key(service_user)
        sln_settings_key = SolutionSettings.create_key(service_user)
        sln_loyalty_settings, sln_settings = db.get([sls_key, sln_settings_key])

        if SolutionModule.LOYALTY in sln_settings.modules:
            if sln_loyalty_settings.loyalty_type != SolutionLoyaltySettings.LOYALTY_TYPE_LOTTERY:
                sln_loyalty_lottery.deleted = True
            else:
                now_tz = int(time.mktime(datetime.fromtimestamp(now(), pytz.timezone(sln_settings.timezone)).timetuple()))
                logging.debug("sln_loyalty_lottery.end_timestamp: %s", sln_loyalty_lottery.end_timestamp)
                logging.debug("end: %s" , now_tz)
                seconds_before = sln_loyalty_lottery.end_timestamp - now_tz
                if seconds_before < 0:
                    seconds_before = 0
                logging.debug("_schedule_loot_lottery seconds_before: %s", seconds_before)
                deferred.defer(_pick_winner, service_user, sln_loyalty_lottery_key,
                               _countdown=seconds_before, _queue=SCHEDULED_QUEUE, _transactional=True)

        else:
            sln_loyalty_lottery.deleted = True
        sln_loyalty_lottery.schedule_loot_time = sln_loyalty_lottery.schedule_loot_time * -1
        sln_loyalty_lottery.put()

    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans)

@returns()
@arguments(service_user=users.User, message_key=unicode, message_parent_key=unicode, parent_message_key=unicode, dirty_behavior=int)
def _messaging_seal(service_user, message_key, message_parent_key, parent_message_key, dirty_behavior):
    users.set_user(service_user)
    try:
        messaging.seal(message_key, message_parent_key, parent_message_key, 1)
    finally:
        users.clear_user()

def _pick_winner(service_user, sln_loyalty_lottery_key):
    now_ = now()
    sln_loyalty_lottery = db.get(sln_loyalty_lottery_key)
    if sln_loyalty_lottery.claimed or sln_loyalty_lottery.redeemed or sln_loyalty_lottery.deleted:
        return
    if sln_loyalty_lottery.schedule_loot_time > 0:
        return
    service_identity = sln_loyalty_lottery.service_identity
    service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
    sls_key = SolutionLoyaltySettings.create_key(service_user)
    slls_key = SolutionLoyaltyLotteryStatistics.create_key(service_user, service_identity)
    sln_settings_key = SolutionSettings.create_key(service_user)
    sln_loyalty_settings, slls, sln_settings = db.get([sls_key, slls_key, sln_settings_key])

    if sln_loyalty_settings.loyalty_type != SolutionLoyaltySettings.LOYALTY_TYPE_LOTTERY:
        sln_loyalty_lottery.deleted = True
        sln_loyalty_lottery.put()
        return

    logging.info("loyalty lottery loot: %s", service_user)
    possible_winners = []

    if slls:
        for i, app_user in enumerate(slls.app_users):
            if app_user not in sln_loyalty_lottery.skip_winners and app_user != sln_loyalty_lottery.winner:
                for i in xrange(slls.count[i]):
                    possible_winners.append(app_user)

    logging.debug("possible winners count: %s", len(possible_winners))

    if len(possible_winners) == 0:
        if sln_loyalty_lottery.winner:
            logging.debug("can not assign winner, keep old")
        else:
            logging.debug("can not assign winner, delete lottery")
            sln_loyalty_lottery.deleted = True
            sln_loyalty_lottery.put()
        return

    else:
        winner = random.choice(possible_winners)
        logging.debug("new winner: %s", winner)

    slvl = SolutionLoyaltyVisitLottery.all() \
        .ancestor(parent_key_unsafe(service_identity_user, SOLUTION_COMMON)) \
        .filter('redeemed =', False) \
        .filter('app_user =', winner).get()

    azzert(slvl, "SolutionLoyaltyVisitLottery for app_user %s not found!" % winner)

    if slvl.app_user_info:
        user_detail = UserDetailsTO()
        user_detail.email = slvl.app_user_info.email
        user_detail.name = slvl.app_user_info.name
        user_detail.language = slvl.app_user_info.language
        user_detail.avatar_url = slvl.app_user_info.avatar_url
        user_detail.app_id = slvl.app_user_info.app_id
    else:
        # XXX: don't use get_profile_infos
        profile_info = get_profile_infos([slvl.app_user], allow_none_in_results=True)[0]
        if not profile_info or profile_info.isServiceIdentity:
            azzert(False, "profile_info for app_user %s not found!" % winner)
        else:
            user_detail = UserDetailsTO.fromUserProfile(profile_info)

    loot_datetime_tz = datetime.fromtimestamp(sln_loyalty_lottery.end_timestamp, pytz.timezone(sln_settings.timezone))
    loot_date_str = format_datetime(loot_datetime_tz, format='medium', locale=sln_settings.main_language or DEFAULT_LANGUAGE)

    next_datetime_tz = datetime.fromtimestamp(now() + 24 * 3600, pytz.timezone(sln_settings.timezone))
    next_date_str = format_datetime(next_datetime_tz, format='medium', locale=sln_settings.main_language or DEFAULT_LANGUAGE)

    msg_ok = translate(sln_settings.main_language, SOLUTION_COMMON, 'loyalty-lottery-loot-ok',
                       name=user_detail.name,
                       date_loot=loot_date_str,
                       price=sln_loyalty_lottery.winnings,
                       date=next_date_str)
    msg_sorry = translate(sln_settings.main_language, SOLUTION_COMMON, 'loyalty-lottery-loot-nok')

    btn = AnswerTO()
    btn.id = u'%s' % json.dumps({"key": unicode(sln_loyalty_lottery_key)})
    btn.type = u'button'
    btn.caption = translate(sln_settings.main_language, SOLUTION_COMMON, 'Confirm')
    btn.action = None
    btn.ui_flags = 0

    message_flags = Message.FLAG_ALLOW_DISMISS

    sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
    def trans():
        sm_data = []

        if sln_loyalty_lottery.winner_timestamp != 0:
            logging.debug("loyalty lottery loot: update winner %s", sln_loyalty_lottery.winner)
            sim_parent, _ = add_solution_inbox_message(service_user, sln_loyalty_lottery.solution_inbox_message_key, True, None, now_, msg_sorry, mark_as_read=True)
            if sim_parent.message_key_by_tag:
                message_key_by_tag = json.loads(sim_parent.message_key_by_tag)
                if message_key_by_tag.get(u"loyalty_lottery_loot", None):
                    deferred.defer(_messaging_seal, service_user, message_key_by_tag[u"loyalty_lottery_loot"], sim_parent.message_key, sim_parent.message_key, 1, _transactional=True)

            send_inbox_forwarders_message(service_user, service_identity, None, msg_sorry, {
                    'if_name': user_detail.name,
                    'if_email':user_detail.email
            }, message_key=sim_parent.solution_inbox_message_key, reply_enabled=sim_parent.reply_enabled, send_reminder=False)

            deferred.defer(send_email_to_user_for_loyalty_update, service_user, service_identity, sln_loyalty_lottery.winner, msg_sorry, False)
            sm_data.append({u"type": u"solutions.common.messaging.update",
                         u"message": serialize_complex_value(SolutionInboxMessageTO.fromModel(sim_parent, sln_settings, sln_i_settings, True), SolutionInboxMessageTO, False)})

        logging.debug("loyalty lottery loot: new winner %s", winner)

        sim_parent = create_solution_inbox_message(service_user, service_identity, SolutionInboxMessage.CATEGORY_LOYALTY, unicode(sln_loyalty_lottery_key), True, [user_detail], now_, msg_ok, True, mark_as_read=True)

        sln_loyalty_lottery.solution_inbox_message_key = sim_parent.solution_inbox_message_key

        if sln_loyalty_lottery.winner:
            if not sln_loyalty_lottery.skip_winners:
                sln_loyalty_lottery.skip_winners = []
            sln_loyalty_lottery.skip_winners.append(sln_loyalty_lottery.winner)
        sln_loyalty_lottery.pending = False
        sln_loyalty_lottery.winner = winner
        sln_loyalty_lottery.winner_info = SolutionUser.fromTO(user_detail) if user_detail else None
        sln_loyalty_lottery.winner_timestamp = now_
        sln_loyalty_lottery.put()

        send_inbox_forwarders_message(service_user, service_identity, None, msg_ok, {
            'if_name': user_detail.name,
            'if_email':user_detail.email
        }, message_key=sim_parent.solution_inbox_message_key, reply_enabled=sim_parent.reply_enabled, send_reminder=False, answers=[btn], store_tag=u"loyalty_lottery_loot", flags=message_flags)

        deferred.defer(send_email_to_user_for_loyalty_update, service_user, service_identity, sln_loyalty_lottery.winner, msg_ok, False, sim_parent.solution_inbox_message_key)
        sm_data.append({u"type": u"solutions.common.messaging.update",
                     u"message": serialize_complex_value(SolutionInboxMessageTO.fromModel(sim_parent, sln_settings, sln_i_settings, True), SolutionInboxMessageTO, False)})
        sm_data.append({u"type": u"solutions.common.loyalty.lottery.update"})
        send_message(service_user, sm_data, service_identity=service_identity)

        deferred.defer(_continue, service_user, service_identity, sln_loyalty_lottery_key, _transactional=True)

    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans)


def _continue(service_user, service_identity, sln_loyalty_lottery_key):
    def trans():
        deferred.defer(update_user_data_admins, service_user, service_identity, _transactional=True)
        deferred.defer(_pick_winner, service_user, sln_loyalty_lottery_key, _countdown=24 * 3600, _queue=SCHEDULED_QUEUE, _transactional=True)
    db.run_in_transaction(trans)


def create_loyalty_export_pdfs():

    def get_last_month():
        today = date.today()
        d = today - relativedelta(months=1)
        return date(d.year, d.month, 1)

    first_day_of_last_month = int(time.mktime(get_last_month().timetuple()))
    first_day_of_current_month = int(time.mktime(date.today().replace(day=1).timetuple()))
    countdown = 0
    for sln_settings in SolutionSettings.all().filter('modules =', 'loyalty'):
        identities = [None]
        if sln_settings.identities:
            identities.extend(sln_settings.identities)
        for service_identity in identities:
            deferred.defer(create_loyalty_statistics_for_service, sln_settings.service_user, service_identity,
                           first_day_of_last_month, first_day_of_current_month, _countdown=countdown)
        countdown += 2



def _schedule_loot_city_wide_lottery():
    run_job(_qry_city_wide_lottery, [], _worker_city_wide_lottery, [])

def _qry_city_wide_lottery():
    return SolutionCityWideLottery.all(keys_only=True).filter("schedule_loot_time <", now()).filter("schedule_loot_time >", 0)

def _get_service_user_for_app_id(sln_settings, app_id):
    users.set_user(sln_settings.service_user)
    try:
        identity = system.get_identity()
        if app_id == identity.app_ids[0]:
            return sln_settings.service_user
        return None
    finally:
        users.clear_user()

def _worker_city_wide_lottery(sln_cwl_lottery_key):
    tmp_sln_cwl = db.get(sln_cwl_lottery_key)
    service_user = get_service_user_for_city(tmp_sln_cwl.app_id)

    if not service_user:
        raise Exception("Failed to do city wide lottery service_user not found for app: %s", tmp_sln_cwl.app_id)

    def trans():
        sln_cwl = db.get(sln_cwl_lottery_key)
        logging.info("city wide lottery loot: %s", sln_cwl.app_id)
        sln_settings = db.get(SolutionSettings.create_key(service_user))

        if SolutionModule.HIDDEN_CITY_WIDE_LOTTERY in sln_settings.modules:
            now_tz = int(time.mktime(datetime.fromtimestamp(now(), pytz.timezone(sln_settings.timezone)).timetuple()))
            logging.debug("sln_cwl.end_timestamp: %s", sln_cwl.end_timestamp)
            logging.debug("end: %s" , now_tz)
            seconds_before = sln_cwl.end_timestamp - now_tz
            if seconds_before < 0:
                seconds_before = 0
            logging.debug("_schedule_loot_city_wide_lottery seconds_before: %s", seconds_before)
            deferred.defer(_pick_city_wide_lottery_winner, service_user, sln_cwl_lottery_key,
                           _countdown=seconds_before, _queue=SCHEDULED_QUEUE, _transactional=True)

        else:
            sln_cwl.deleted = True
        sln_cwl.schedule_loot_time = sln_cwl.schedule_loot_time * -1
        sln_cwl.put()

    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans)


def _pick_city_wide_lottery_winner(service_user, sln_cwl_lottery_key):
    sln_cwl = db.get(sln_cwl_lottery_key)
    if sln_cwl.winners:
        return
    slls = db.get(SolutionCityWideLotteryStatistics.create_key(sln_cwl.app_id))
    logging.info("city wide lottery loot: %s", sln_cwl.app_id)
    possible_winners = []

    if slls:
        for i, app_user in enumerate(slls.app_users):
            if app_user not in sln_cwl.skip_winners and app_user not in sln_cwl.winners:
                for i in xrange(slls.count[i]):
                    possible_winners.append(app_user)

    logging.debug("possible winners count: %s", len(possible_winners))

    if len(possible_winners) == 0:
        if sln_cwl.winners:
            logging.debug("can not assign winners, keep old")
        else:
            logging.debug("can not assign winners, delete city wide lottery")
            sln_cwl.deleted = True
            sln_cwl.put()
        return
    else:
        winners_needed = sln_cwl.x_winners
        logging.debug("winners_needed: %s", winners_needed)
        if len(possible_winners) < winners_needed:
            winners_needed = len(possible_winners)

        winners = []
        while True:
            if not possible_winners:
                break
            if len(winners) >= winners_needed:
                break
            winner = random.choice(possible_winners)
            possible_winners = filter(lambda a: a != winner, possible_winners)
            winners.append(winner)

    sln_settings = get_solution_settings(service_user)
    winners_info = []
    slvl_parent_key = SolutionCityWideLotteryVisit.create_city_parent_key(sln_cwl.app_id)
    winner_text = ""
    for winner in winners:
        slvl = SolutionCityWideLotteryVisit.all() \
            .ancestor(slvl_parent_key) \
            .filter('redeemed =', False) \
            .filter('app_user =', winner).get()

        azzert(slvl, "SolutionLoyaltyVisitLottery for app_user %s not found!" % winner)

        if slvl.app_user_info:
            eud = ExtendedUserDetailsTO()
            eud.email = slvl.app_user_info.email
            eud.name = slvl.app_user_info.name
            eud.language = slvl.app_user_info.language
            eud.avatar_url = slvl.app_user_info.avatar_url
            eud.app_id = slvl.app_user_info.app_id
        else:
            # XXX: don't use get_profile_infos
            profile_info = get_profile_infos([slvl.app_user], allow_none_in_results=True)[0]
            if not profile_info or profile_info.isServiceIdentity:
                continue
            else:
                eud = ExtendedUserDetailsTO.fromUserProfile(profile_info, None)

        with set_user(service_user):
            app_info = get_app_info_cached(eud.app_id)
        eud.app_name = app_info.name
        eud.public_key = None
        eud.public_keys = []
        winners_info.append(eud)

        winner_text = winner_text + "\n - %s (%s)" % (eud.name, eud.email)

    def trans():
        sln_cwl.pending = False
        sln_cwl.winners = winners
        sln_cwl.winners_info = json.dumps(serialize_complex_value(winners_info, ExtendedUserDetailsTO, True))
        sln_cwl.put()
        deferred.defer(_redeem_city_wide_lottery_visits, service_user, sln_cwl_lottery_key, now(), _transactional=True)

        to_emails = sln_settings.inbox_mail_forwarders
        if to_emails:
            solution_server_settings = get_solution_server_settings()
            subject = 'Winnaars gemeentelijke tombola'
            body = """Beste,
Volgende mensen hebben gewonnen met de tombola: %s


Met vriendelijke groeten,

Het Onze Stad App Team
""" % winner_text

            send_mail(solution_server_settings.shop_export_email, to_emails, subject, body)

    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans)


def _redeem_city_wide_lottery_visits(service_user, sln_cwl_key, now_):

    def trans():
        models_to_put = []
        sln_cwl = db.get(sln_cwl_key)
        slls = db.get(SolutionCityWideLotteryStatistics.create_key(sln_cwl.app_id))
        if slls:
            sln_cwl.count = slls.count
            sln_cwl.app_users = slls.app_users
            models_to_put.append(sln_cwl)

            slls.count = []
            slls.app_users = []
            models_to_put.append(slls)

        for s in SolutionCityWideLotteryVisit.load(sln_cwl.app_id):
            s.redeemed = True
            s.redeemed_timestamp = now_
            models_to_put.append(s)

        if models_to_put:
            put_and_invalidate_cache(*models_to_put)

        send_message(service_user, u"solutions.common.loyalty.points.update")

    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans)

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

import logging
import time
from types import NoneType

from google.appengine.ext import deferred, db
from mcfw.rpc import returns, arguments, serialize_complex_value
from rogerthat.bizz.job.app_broadcast import APP_BROADCAST_TAG
from rogerthat.rpc import users
from rogerthat.service.api import system
from rogerthat.to.service import UserDetailsTO
from rogerthat.translations import DEFAULT_LANGUAGE
from rogerthat.utils import now
from rogerthat.utils.app import create_app_user_by_email
from rogerthat.utils.channel import send_message
from rogerthat.utils.models import reconstruct_key
from rogerthat.utils.transactions import run_in_xg_transaction
from solutions import translate as common_translate
from solutions.common import SOLUTION_COMMON
from solutions.common.bizz import SERVICE_AUTOCONNECT_INVITE_TAG
from solutions.common.bizz.inbox import create_solution_inbox_message
from solutions.common.bizz.messaging import send_inbox_forwarders_message
from solutions.common.dal import get_solution_settings, get_solution_settings_or_identity_settings
from solutions.common.models import RestaurantInvite, SolutionSettings, SolutionInboxMessage
from solutions.common.to import SolutionInboxMessageTO


@returns(NoneType)
@arguments(service_user=users.User, service_identity=unicode, emails=[unicode], message=unicode, app_id=unicode)
def bulk_invite(service_user, service_identity, emails, message, app_id=None):
    def trans(app_id):
        emailz = list(emails)
        counter = 0
        while emailz:
            counter += 1
            if counter < 4:
                email = emailz.pop()
                deferred.defer(_create_restaurant_invite, service_user, service_identity,
                               email, message, app_id, _transactional=True)
            else:
                deferred.defer(bulk_invite, service_user, service_identity,
                               emailz, message, app_id, _transactional=True)
                break

    if not app_id:
        app_id = system.get_info().app_ids[0]
    db.run_in_transaction(trans, app_id)


@returns(NoneType)
@arguments(service_user=users.User, service_identity=unicode, invitee=unicode, message=unicode, app_id=unicode)
def _create_restaurant_invite(service_user, service_identity, invitee, message, app_id):
    def trans():
        # 1: Check if invitee has been send from service in the last month
        sln_settings = get_solution_settings(service_user)
        db_key = RestaurantInvite.create_key(service_user, service_identity, invitee, sln_settings.solution)
        old_invite = db.get(db_key)
        t = time.time()
        # 2: Store in datastore
        if old_invite:
            if old_invite.status == RestaurantInvite.STATUS_ACCEPTED:
                return
            if not old_invite.epoch < t - 30 * 24 * 60 * 60:
                return
            else:
                old_invite.epoch = t
                old_invite.put()
        else:
            invite = RestaurantInvite(key=db_key)
            invite.epoch = t
            invite.put()
        # 3: Do invite
        deferred.defer(_restaurant_invite, service_user, service_identity, invitee, message, unicode(db_key), sln_settings, app_id,
                       _transactional=True)
    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans)


@returns(NoneType)
@arguments(service_user=users.User, service_identity=unicode, invitee=unicode, message=unicode, tag=unicode, sln_settings=SolutionSettings, app_id=unicode)
def _restaurant_invite(service_user, service_identity, invitee, message, tag, sln_settings, app_id):
    from rogerthat.service.api.friends import invite as invite_api_call
    from rogerthat.bizz.friends import CanNotInviteFriendException
    language = sln_settings.main_language or DEFAULT_LANGUAGE

    users.set_user(service_user)
    try:
        invite_api_call(invitee, None, message, language, tag, service_identity, app_id)
    except CanNotInviteFriendException:
        logging.debug('%s is already connected with %s', invitee, service_user)
        pass
    finally:
        users.clear_user()


@returns(NoneType)
@arguments(service_user=users.User, service_identity=unicode, tag=unicode, email=unicode, result=unicode, user_details=[UserDetailsTO])
def bulk_invite_result(service_user, service_identity, tag, email, result, user_details):
    if not tag:
        logging.exception("Expected tag in bulk_invite_result")
        return

    if tag in (SERVICE_AUTOCONNECT_INVITE_TAG, APP_BROADCAST_TAG):
        return

    try:
        key = db.Key(tag)
    except db.BadKeyError:
        logging.info('Tag is no db.Key: %s. Ignoring...', tag)
        return

    def trans():
        invite = db.get(reconstruct_key(key))
        if not invite:
            logging.error("Invite object not found in datastore")
            return
        save_message = False
        if "accepted" == result:
            invite.status = RestaurantInvite.STATUS_ACCEPTED
            save_message = True
        else:
            invite.status = RestaurantInvite.STATUS_REJECTED
        invite.put()
        return save_message

    save_message = run_in_xg_transaction(trans)
    if save_message:
        now_ = now()
        sln_settings = get_solution_settings(service_user)
        msg = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'if-accepted-invitation',
                               if_name=user_details[0].name,
                               if_email=user_details[0].email)

        message = create_solution_inbox_message(
            service_user, service_identity, SolutionInboxMessage.CATEGORY_BULK_INVITE, None, False, user_details, now_, msg, False)
        app_user = create_app_user_by_email(user_details[0].email, user_details[0].app_id)
        send_inbox_forwarders_message(service_user, service_identity, app_user, msg, {
            'if_name': user_details[0].name,
            'if_email': user_details[0].email
        }, message_key=message.solution_inbox_message_key, reply_enabled=message.reply_enabled, send_reminder=False)

        sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
        send_message(service_user, u"solutions.common.messaging.update",
                     service_identity=service_identity,
                     message=serialize_complex_value(SolutionInboxMessageTO.fromModel(message, sln_settings, sln_i_settings, True), SolutionInboxMessageTO, False))

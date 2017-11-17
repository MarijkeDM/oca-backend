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

import json
import logging
from types import NoneType

from rogerthat.models import ServiceProfile, Message
from rogerthat.models.properties.forms import FormResult
from rogerthat.rpc import users
from rogerthat.rpc.solutions import service_api_callback_handler
from rogerthat.service.api import messaging
from rogerthat.service.api.system import put_user_data
from rogerthat.to.messaging.flow import FLOW_STEP_MAPPING
from rogerthat.to.messaging.service_callback_results import FlowMemberResultCallbackResultTO, \
    MessageAcknowledgedCallbackResultTO, FormAcknowledgedCallbackResultTO
from rogerthat.to.service import UserDetailsTO, SendApiCallCallbackResultTO
from rogerthat.utils import try_or_defer
from mcfw.properties import object_factory
from mcfw.rpc import returns, arguments
from solutions.common.api_callback_handlers import common_new_chat_message
from solutions.common.bizz.bulk_invite import bulk_invite_result
from solutions.common.bizz.messaging import API_METHOD_MAPPING, MESSAGE_TAG_MAPPING, \
    POKE_TAG_INBOX_FORWARDING_REPLY_TEXT_BOX, reply_on_inbox_forwarding
from solutions.common.dal import get_solution_main_branding
from solutions.djmatic import SOLUTION_DJMATIC
from solutions.djmatic.bizz import register_jukebox


@service_api_callback_handler(solution=SOLUTION_DJMATIC, code=ServiceProfile.CALLBACK_FRIEND_INVITED)
@returns(unicode)
@arguments(email=unicode, name=unicode, message=unicode, language=unicode, tag=unicode, origin=unicode,
           service_identity=unicode, user_details=[UserDetailsTO])
def invited(email, name, message, language, tag, origin, service_identity, user_details):
    return register_jukebox(users.get_current_user(), user_details[0])


@service_api_callback_handler(solution=SOLUTION_DJMATIC, code=ServiceProfile.CALLBACK_FRIEND_INVITE_RESULT)
@returns(NoneType)
@arguments(email=unicode, result=unicode, tag=unicode, origin=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def invite_result(email, result, tag, origin, service_identity, user_details):
    service_user = users.get_current_user()
    try_or_defer(_process_invite_result, service_user, email, result, tag, origin, service_identity, user_details)


def _process_invite_result(service_user, email, result, tag, origin, service_identity, user_details):
    if result == "accepted":
        user_data = register_jukebox(service_user, user_details[0])
        try_or_defer(_put_user_data, service_user, email, user_data, service_identity, user_details[0].app_id)
    if origin == "service_invite":
        bulk_invite_result(service_user, service_identity, tag, email, result, user_details)


def _put_user_data(service_user, email, user_data, service_identity, app_id):
    with users.set_user(service_user):
        return put_user_data(email, user_data, service_identity, app_id)


@service_api_callback_handler(solution=SOLUTION_DJMATIC, code=ServiceProfile.CALLBACK_MESSAGING_FLOW_MEMBER_RESULT)
@returns(FlowMemberResultCallbackResultTO)
@arguments(message_flow_run_id=unicode, member=unicode, steps=[object_factory("step_type", FLOW_STEP_MAPPING)],
           end_id=unicode, end_message_flow_id=unicode, parent_message_key=unicode, tag=unicode, result_key=unicode,
           flush_id=unicode, flush_message_flow_id=unicode, service_identity=unicode, user_details=[UserDetailsTO])
def flow_member_result(message_flow_run_id, member, steps, end_id, end_message_flow_id, parent_message_key, tag,
                       result_key, flush_id, flush_message_flow_id, service_identity, user_details):
    from solutions.common.bizz.messaging import FMR_POKE_TAG_MAPPING
    if tag in FMR_POKE_TAG_MAPPING:
        handler = FMR_POKE_TAG_MAPPING[tag]
    else:
        logging.info("Unconfigured messaging.flow_member_result tag: %s" % tag)
        return None

    return handler(users.get_current_user(), message_flow_run_id, member, steps, end_id,
                   end_message_flow_id, parent_message_key, tag, result_key, flush_id,
                   flush_message_flow_id, service_identity, user_details)


@service_api_callback_handler(solution=SOLUTION_DJMATIC, code=ServiceProfile.CALLBACK_SYSTEM_API_CALL)
@returns(SendApiCallCallbackResultTO)
@arguments(email=unicode, method=unicode, params=unicode, tag=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def api_call(email, method, params, tag, service_identity, user_details):
    if method in API_METHOD_MAPPING:
        return API_METHOD_MAPPING[method](users.get_current_user(), email, method, params, tag, service_identity,
                                          user_details)
    else:
        if method == "jukebox.remindme":
            jsondata = json.loads(params)
            reminderMessage = "Reminder:\n\nArtist: %s \nTitle: %s" % (jsondata['a'], jsondata['t'])
            service_user = users.get_current_user()
            main_branding = get_solution_main_branding(service_user)

            members = list()
            members.append(email)

            messaging.send(parent_key=None,
                           parent_message_key=None,
                           message=reminderMessage,
                           answers=[],
                           flags=Message.FLAG_ALLOW_DISMISS,
                           members=members,
                           branding=main_branding.branding_key,
                           tag=None)

            r = SendApiCallCallbackResultTO()
            r.result = u"successfully reminded"
            r.error = None
            return r
        else:
            r = SendApiCallCallbackResultTO()
            r.error = u"method (%s) is not defined" % method
            r.result = None
            return r


@service_api_callback_handler(solution=SOLUTION_DJMATIC, code=ServiceProfile.CALLBACK_MESSAGING_ACKNOWLEDGED)
@returns(MessageAcknowledgedCallbackResultTO)
@arguments(status=int, answer_id=unicode, received_timestamp=int, member=unicode, message_key=unicode, tag=unicode,
           acked_timestamp=int, parent_message_key=unicode, result_key=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def messaging_update(status, answer_id, received_timestamp, member, message_key, tag, acked_timestamp,
                     parent_message_key, result_key, service_identity, user_details):
    if tag in MESSAGE_TAG_MAPPING:
        handler = MESSAGE_TAG_MAPPING[tag]
    else:
        logging.info("Unconfigured messaging.update tag: %s" % tag)
        return None
    return handler(users.get_current_user(), status, answer_id, received_timestamp, member, message_key, tag,
                   acked_timestamp, parent_message_key, result_key, service_identity, user_details)


@service_api_callback_handler(solution=SOLUTION_DJMATIC, code=ServiceProfile.CALLBACK_MESSAGING_FORM_ACKNOWLEDGED)
@returns(FormAcknowledgedCallbackResultTO)
@arguments(status=int, form_result=FormResult, answer_id=unicode, member=unicode, message_key=unicode, tag=unicode,
           received_timestamp=int, acked_timestamp=int, parent_message_key=unicode, result_key=unicode,
           service_identity=unicode, user_details=[UserDetailsTO])
def messaging_form_update(status, form_result, answer_id, member, message_key, tag, received_timestamp, acked_timestamp,
                          parent_message_key, result_key, service_identity, user_details):
    if tag and tag.startswith(POKE_TAG_INBOX_FORWARDING_REPLY_TEXT_BOX):
        handler = reply_on_inbox_forwarding
    elif tag in MESSAGE_TAG_MAPPING:
        handler = MESSAGE_TAG_MAPPING[tag]
    else:
        logging.info("Unconfigured messaging.form_update tag: %s" % tag)
        return None
    return handler(users.get_current_user(), status, form_result, answer_id, member, message_key, tag,
                   received_timestamp, acked_timestamp, parent_message_key, result_key, service_identity, user_details)


def wrap_common_callback_handler(f, code):
    return service_api_callback_handler(solution=SOLUTION_DJMATIC, code=code)(f)

new_chat_message = wrap_common_callback_handler(common_new_chat_message,
                                                ServiceProfile.CALLBACK_MESSAGING_NEW_CHAT_MESSAGE)

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

from google.appengine.ext import db
from mcfw.properties import object_factory
from mcfw.rpc import returns, arguments, serialize_complex_value
from rogerthat.bizz.friends import ACCEPT_ID
from rogerthat.models.properties.forms import FormResult
from rogerthat.rpc import users
from rogerthat.service.api import messaging
from rogerthat.to.messaging import AnswerTO, AttachmentTO, MemberTO
from rogerthat.to.messaging.flow import FLOW_STEP_MAPPING
from rogerthat.to.messaging.service_callback_results import FlowMemberResultCallbackResultTO, \
    FormAcknowledgedCallbackResultTO, MessageAcknowledgedCallbackResultTO, PokeCallbackResultTO
from rogerthat.to.service import UserDetailsTO, SendApiCallCallbackResultTO
from rogerthat.utils.app import create_app_user_by_email
from rogerthat.utils.channel import send_message
from rogerthat.utils.models import reconstruct_key
from solutions.common.bizz.bulk_invite import bulk_invite_result
from solutions.common.bizz.discussion_groups import discussion_group_deleted
from solutions.common.bizz.events import solution_add_admin_to_calendar
from solutions.common.bizz.inbox import add_solution_inbox_message
from solutions.common.bizz.loyalty import loyalty_qr_register, loyalty_qr_register_result, \
    messaging_update_inbox_forwaring_reply
from solutions.common.bizz.messaging import API_METHOD_MAPPING, POKE_TAG_INBOX_FORWARDING_REPLY_TEXT_BOX, \
    reply_on_inbox_forwarding, MESSAGE_TAG_MAPPING, POKE_TAG_MAPPING, POKE_TAG_EVENTS_CONNECT_VIA_SCAN, \
    MESSAGE_TAG_MY_RESERVATIONS_EDIT_COMMENT, MESSAGE_TAG_MY_RESERVATIONS_EDIT_PEOPLE, POKE_TAG_RESERVE_PART2, \
    POKE_TAG_INBOX_FORWARDING_REPLY, POKE_TAG_DISCUSSION_GROUPS
from solutions.common.bizz.reservation import my_reservations_edit_comment_updated, my_reservations_edit_people_updated, \
    reservation_part2
from solutions.common.dal import get_solution_settings, get_solution_settings_or_identity_settings
from solutions.common.models import SolutionInboxMessage
from solutions.common.to import SolutionInboxMessageTO
from solutions.common.bizz.provisioning import STATIC_CONTENT_TAG_PREFIX


# XXX TODO
# CALLBACK_FRIEND_INVITE_RESULT
@returns(unicode)
@arguments(email=unicode, name=unicode, message=unicode, language=unicode, tag=unicode, origin=unicode,
           service_identity=unicode, user_details=[UserDetailsTO])
def common_friend_invited(email, name, message, language, tag, origin, service_identity, user_details):
    return ACCEPT_ID


def _get_human_readable_tag(tag):
    if tag and tag.startswith('{'):
        try:
            tag_dict = json.loads(tag)
            return tag_dict.get('__rt__.tag', tag)
        except:
            logging.info("tag isn't json")
    return tag


@returns(PokeCallbackResultTO)
@arguments(email=unicode, tag=unicode, result_key=unicode, context=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def common_messaging_poke(email, tag, result_key, context, service_identity, user_details):
    if tag in POKE_TAG_MAPPING:
        handler = POKE_TAG_MAPPING[tag]
    elif tag and tag.startswith(STATIC_CONTENT_TAG_PREFIX):
        return None
    elif tag and tag.startswith(POKE_TAG_EVENTS_CONNECT_VIA_SCAN):
        handler = solution_add_admin_to_calendar
    else:
        logging.info("Unconfigured messaging.poke tag: %s" % tag)
        raise NotImplementedError()
    return handler(users.get_current_user(), email, tag, result_key, context, service_identity, user_details)


@returns(FlowMemberResultCallbackResultTO)
@arguments(message_flow_run_id=unicode, member=unicode, steps=[object_factory("step_type", FLOW_STEP_MAPPING)],
           end_id=unicode, end_message_flow_id=unicode, parent_message_key=unicode, tag=unicode, result_key=unicode,
           flush_id=unicode, flush_message_flow_id=unicode, service_identity=unicode, user_details=[UserDetailsTO])
def common_messaging_flow_member_result(message_flow_run_id, member, steps, end_id, end_message_flow_id,
                                        parent_message_key, tag, result_key, flush_id, flush_message_flow_id,
                                        service_identity, user_details):
    from solutions.common.bizz.messaging import FMR_POKE_TAG_MAPPING
    human_readable_tag = tag
    if tag and tag.startswith('{') and tag.endswith('}'):
        try:
            tag_dict = json.loads(tag)
        except:
            logging.info("tag isn't json")
        else:
            human_readable_tag = tag_dict.get('__rt__.tag', tag)

    if human_readable_tag and human_readable_tag.startswith(POKE_TAG_RESERVE_PART2):
        handler = reservation_part2
    elif human_readable_tag in FMR_POKE_TAG_MAPPING:
        handler = FMR_POKE_TAG_MAPPING[human_readable_tag]
    else:
        logging.info("Unconfigured messaging.flow_member_result tag: %s" % tag)
        raise NotImplementedError()

    return handler(users.get_current_user(), message_flow_run_id, member, steps, end_id,
                   end_message_flow_id, parent_message_key, tag, result_key, flush_id,
                   flush_message_flow_id, service_identity, user_details)


@returns(SendApiCallCallbackResultTO)
@arguments(email=unicode, method=unicode, params=unicode, tag=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def common_system_api_call(email, method, params, tag, service_identity, user_details):
    f = API_METHOD_MAPPING.get(method)
    if f:
        return f(users.get_current_user(), email, method, params, tag, service_identity, user_details)
    else:
        raise NotImplementedError()


@returns(MessageAcknowledgedCallbackResultTO)
@arguments(status=int, answer_id=unicode, received_timestamp=int, member=unicode, message_key=unicode, tag=unicode,
           acked_timestamp=int, parent_message_key=unicode, result_key=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def common_messaging_update(status, answer_id, received_timestamp, member, message_key, tag, acked_timestamp,
                     parent_message_key, result_key, service_identity, user_details):
    service_user = users.get_current_user()
    if tag and tag.startswith(POKE_TAG_INBOX_FORWARDING_REPLY):
        messaging_update_inbox_forwaring_reply(service_user, service_identity, tag, user_details, status)
        return None
    elif tag in MESSAGE_TAG_MAPPING:
        handler = MESSAGE_TAG_MAPPING[tag]
    else:
        logging.info("Unconfigured messaging.update tag: %s" % tag)
        raise NotImplementedError()
    return handler(service_user, status, answer_id, received_timestamp, member, message_key, tag,
                   acked_timestamp, parent_message_key, result_key, service_identity, user_details)


@returns(FormAcknowledgedCallbackResultTO)
@arguments(status=int, form_result=FormResult, answer_id=unicode, member=unicode, message_key=unicode, tag=unicode,
           received_timestamp=int, acked_timestamp=int, parent_message_key=unicode, result_key=unicode,
           service_identity=unicode, user_details=[UserDetailsTO])
def common_messaging_form_update(status, form_result, answer_id, member, message_key, tag, received_timestamp,
                                 acked_timestamp, parent_message_key, result_key, service_identity, user_details):
    if tag and tag.startswith(POKE_TAG_INBOX_FORWARDING_REPLY_TEXT_BOX):
        handler = reply_on_inbox_forwarding
    elif tag and tag.startswith(MESSAGE_TAG_MY_RESERVATIONS_EDIT_COMMENT):
        handler = my_reservations_edit_comment_updated
    elif tag and tag.startswith(MESSAGE_TAG_MY_RESERVATIONS_EDIT_PEOPLE):
        handler = my_reservations_edit_people_updated
    elif tag in MESSAGE_TAG_MAPPING:
        handler = MESSAGE_TAG_MAPPING[tag]
    else:
        logging.info("Unconfigured messaging.form_update tag: %s" % tag)
        raise NotImplementedError()
    return handler(users.get_current_user(), status, form_result, answer_id, member, message_key, tag,
                   received_timestamp, acked_timestamp, parent_message_key, result_key, service_identity, user_details)


@returns()
@arguments(email=unicode, result=unicode, tag=unicode, origin=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def common_friend_invite_result(email, result, tag, origin, service_identity, user_details):
    if origin == "service_invite":
        bulk_invite_result(users.get_current_user(), service_identity, tag, email, result, user_details)
    else:
        raise NotImplementedError()

@returns(unicode)
@arguments(service_identity=unicode, user_details=[UserDetailsTO], origin=unicode, data=unicode)
def common_friend_register(service_identity, user_details, origin, data):
    return loyalty_qr_register(users.get_current_user(), user_details, origin, data)

@returns(NoneType)
@arguments(service_identity=unicode, user_details=[UserDetailsTO], origin=unicode)
def common_friend_register_result(service_identity, user_details, origin):
    loyalty_qr_register_result(users.get_current_user(), service_identity, user_details, origin)


@returns()
@arguments(parent_message_key=unicode, member=UserDetailsTO, timestamp=int, service_identity=unicode, tag=unicode)
def common_chat_deleted(parent_message_key, member, timestamp, service_identity, tag):
    human_readable_tag = _get_human_readable_tag(tag)
    if human_readable_tag == POKE_TAG_DISCUSSION_GROUPS:
        discussion_group_deleted(users.get_current_user(), parent_message_key, member, timestamp, service_identity, tag)
    else:
        raise NotImplementedError()


@returns()
@arguments(parent_message_key=unicode, message_key=unicode, sender=UserDetailsTO, message=unicode, answers=[AnswerTO],
           timestamp=int, tag=unicode, service_identity=unicode, attachments=[AttachmentTO])
def common_new_chat_message(parent_message_key, message_key, sender, message, answers, timestamp, tag, service_identity,
                            attachments):
    if tag and tag.startswith(POKE_TAG_INBOX_FORWARDING_REPLY):
        info = json.loads(tag[len(POKE_TAG_INBOX_FORWARDING_REPLY):])
        message_key = info['message_key']
        sim_parent = SolutionInboxMessage.get(reconstruct_key(db.Key(message_key)))

        if sim_parent.awaiting_first_message:
            sim_parent.awaiting_first_message = False
            sim_parent.put()
        else:
            service_user = sim_parent.service_user
            sln_settings = get_solution_settings(service_user)
            sent_by_service = True
            if sim_parent.sender.email == sender.email and sim_parent.sender.app_id == sender.app_id:
                sent_by_service = False

            picture_attachments = []
            video_attachments = []
            for a in attachments:
                if a.content_type.startswith("image"):
                    picture_attachments.append(a.download_url)
                if a.content_type.startswith("video"):
                    video_attachments.append(a.download_url)

            if sent_by_service:
                sim_parent, _ = add_solution_inbox_message(service_user, message_key, sent_by_service, [sender], timestamp, message, picture_attachments, video_attachments, mark_as_unread=False, mark_as_read=True)
            else:
                sim_parent, _ = add_solution_inbox_message(service_user, message_key, sent_by_service, [sender], timestamp, message, picture_attachments, video_attachments)

            sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
            send_message(service_user, u"solutions.common.messaging.update",
                         service_identity=service_identity,
                         message=serialize_complex_value(SolutionInboxMessageTO.fromModel(sim_parent, sln_settings, sln_i_settings, True), SolutionInboxMessageTO, False))

            member_sender_user = create_app_user_by_email(sim_parent.sender.email, sim_parent.sender.app_id)
            sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
            members = [MemberTO.from_user(users.User(f)) for f in sln_i_settings.inbox_forwarders]
            if member_sender_user.email() not in sln_i_settings.inbox_forwarders:
                members.append(MemberTO.from_user(member_sender_user))

            users.set_user(service_user)
            try:
                messaging.add_chat_members(sim_parent.message_key, members)
            finally:
                users.clear_user()
    else:
        raise NotImplementedError()

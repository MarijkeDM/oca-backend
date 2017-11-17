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

from contextlib import closing
import datetime
import json
from types import NoneType

from babel.dates import format_datetime, get_timezone
import pytz

from google.appengine.ext import db, deferred
from mcfw.properties import azzert, object_factory
from mcfw.rpc import returns, arguments, serialize_complex_value
from rogerthat.dal import parent_key, put_and_invalidate_cache, parent_key_unsafe
from rogerthat.models import Message
from rogerthat.rpc import users
from rogerthat.rpc.service import BusinessException
from rogerthat.service.api import messaging
from rogerthat.to.messaging import AttachmentTO, MemberTO
from rogerthat.to.messaging.flow import FLOW_STEP_MAPPING
from rogerthat.to.service import UserDetailsTO
from rogerthat.utils import now, try_or_defer
from rogerthat.utils.channel import send_message
from rogerthat.utils.transactions import run_in_transaction
from solutions import translate
from solutions import translate as common_translate
from solutions.common import SOLUTION_COMMON
from solutions.common.bizz import _get_value, broadcast_updates_pending
from solutions.common.bizz.inbox import create_solution_inbox_message, add_solution_inbox_message
from solutions.common.bizz.loyalty import update_user_data_admins
from solutions.common.consts import ORDER_TYPE_SIMPLE, ORDER_TYPE_ADVANCED
from solutions.common.dal import get_solution_main_branding, get_solution_settings, \
    get_solution_settings_or_identity_settings
from solutions.common.dal.order import get_solution_order_settings
from solutions.common.models import SolutionInboxMessage
from solutions.common.models.order import SolutionOrder, SolutionOrderWeekdayTimeframe
from solutions.common.models.properties import SolutionUser
from solutions.common.to import SolutionInboxMessageTO
from solutions.common.utils import create_service_identity_user_wo_default


try:
    from cStringIO import StringIO
except ImportError:
    from cStringIO import StringIO


@returns()
@arguments(service_user=users.User, message_flow_run_id=unicode, member=unicode,
           steps=[object_factory("step_type", FLOW_STEP_MAPPING)], end_id=unicode, end_message_flow_id=unicode,
           parent_message_key=unicode, tag=unicode, result_key=unicode, flush_id=unicode, flush_message_flow_id=unicode,
           service_identity=unicode, user_details=[UserDetailsTO])
def _order_received(service_user, message_flow_run_id, member, steps, end_id, end_message_flow_id, parent_message_key,
                    tag, result_key, flush_id, flush_message_flow_id, service_identity, user_details):


    from solutions.common.bizz.messaging import send_inbox_forwarders_message
    for step in steps:
        if step.step_id == u'message_advanced_order':
            order_type = ORDER_TYPE_ADVANCED
            break
    else:
        order_type = ORDER_TYPE_SIMPLE


    def get_extended_details_from_tag(details):
        if tag and tag.startswith('{') and tag.endswith('}'):
            try:
                new_details = u""
                tag_dict = json.loads(tag)
                for k, v in tag_dict.iteritems():
                    if not k.startswith("_"):
                        if new_details:
                            new_details = u"%s\n%s: %s" % (new_details, k, v)
                        else:
                            new_details = u"%s: %s" % (k, v)

                if new_details:
                    return u"%s\n%s" % (new_details, details)
            except:
                pass

        return details


    def trans():
        sln_settings = get_solution_settings(service_user)
        order_settings = get_solution_order_settings(sln_settings)
        lang = sln_settings.main_language
        comment = None
        phone = None
        takeaway_time = None
        if order_type == ORDER_TYPE_SIMPLE:
            details = get_extended_details_from_tag(_get_value(steps[0], u'message_details'))
            if steps[1].answer_id == u"positive":
                picture_url = _get_value(steps[1], u'message_picture')
                att = AttachmentTO()
                att.content_type = AttachmentTO.CONTENT_TYPE_IMG_JPG
                att.download_url = picture_url
                att.name = translate(lang, SOLUTION_COMMON, u'picture')
                att.size = 0
                attachments = [att]
            else:
                picture_url = None
                attachments = []
            phone = _get_value(steps[2], u'message_phone')
            msg = common_translate(lang, SOLUTION_COMMON, 'if-order-received') % {
                'remarks': details,
                'phone_number': phone
            }

        elif order_type == ORDER_TYPE_ADVANCED:
            with closing(StringIO()) as order:
                timezone_offset = datetime.datetime.now(pytz.timezone(sln_settings.timezone)).utcoffset().total_seconds()
                has_order_items = False
                for step in steps:
                    if step.step_id == u'message_phone':
                        phone = step.get_value()
                    elif step.step_id == u'message_comment':
                        comment = step.get_value()
                    elif step.step_id == u'message_advanced_order':
                        step_value = step.display_value.encode('utf-8')
                        if step_value:
                            has_order_items = True
                        order.write(step_value)
                    elif step.step_id == u'message_takeaway_time':
                        takeaway_time = int(step.get_value() - timezone_offset)
                picture_url = None
                attachments = []
                if comment:
                    if has_order_items:
                        order.write('\n\n')
                    c = '%s: %s' % (common_translate(lang, SOLUTION_COMMON, 'reservation-comment'), comment)
                    order.write(c.encode('utf-8') if isinstance(c, unicode) else c)
                details = get_extended_details_from_tag(order.getvalue().decode('utf-8'))
                takeaway_datetime = datetime.datetime.fromtimestamp(takeaway_time, tz=get_timezone(sln_settings.timezone))
                takeaway_time_str = format_datetime(takeaway_datetime, locale=lang, format='d/M/yyyy H:mm')

                msg = '%s:\n%s\n%s: %s\n%s: %s' % (common_translate(lang, SOLUTION_COMMON, 'order_received'), details,
                                                   common_translate(lang, SOLUTION_COMMON, 'phone_number'), phone,
                                                   common_translate(lang, SOLUTION_COMMON, 'takeaway_time'), takeaway_time_str)
        else:
            raise BusinessException('Unsupported order type %s', order_type)

        if not order_settings.manual_confirmation:
            # Waiting for follow-up message
            deferred.defer(_send_order_confirmation, service_user, lang, message_flow_run_id, member, steps, end_id,
                            end_message_flow_id, parent_message_key, tag, result_key, flush_id, flush_message_flow_id,
                            service_identity, user_details, details, _transactional=db.is_in_transaction())

        service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
        o = SolutionOrder(parent=parent_key_unsafe(service_identity_user, SOLUTION_COMMON))
        o.description = details
        o.phone_number = phone
        o.sender = SolutionUser.fromTO(user_details[0])
        o.timestamp = now()
        o.status = SolutionOrder.STATUS_RECEIVED
        o.picture_url = picture_url
        o.takeaway_time = takeaway_time
        o.user = user_details[0].toAppUser() if user_details else None

        message = create_solution_inbox_message(service_user, service_identity, SolutionInboxMessage.CATEGORY_ORDER,
                                                None, False, user_details, steps[2].received_timestamp, msg, True,
                                                [picture_url] if picture_url else [])
        o.solution_inbox_message_key = message.solution_inbox_message_key
        o.put()
        message.category_key = unicode(o.key())
        message.put()

        sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
        sm_data = [{u"type": u"solutions.common.orders.update"},
                   {u"type": u"solutions.common.messaging.update",
                    u"message": serialize_complex_value(SolutionInboxMessageTO.fromModel(message, sln_settings,
                                                                                         sln_i_settings, True),
                                                        SolutionInboxMessageTO, False)}]
        send_message(service_user, sm_data, service_identity=service_identity)

        app_user = user_details[0].toAppUser()

        send_inbox_forwarders_message(service_user, service_identity, app_user, msg,
                                      dict(if_name=user_details[0].name, if_email=user_details[0].email),
                                      message_key=message.solution_inbox_message_key, attachments=attachments,
                                      reply_enabled=message.reply_enabled)

    run_in_transaction(trans, xg=True)


def _send_order_confirmation(service_user, lang, message_flow_run_id, member, steps, end_id, end_message_flow_id,
                             parent_message_key, tag, result_key, flush_id, flush_message_flow_id, service_identity,
                             user_details, order_details):
    if now() - steps[-1].acknowledged_timestamp < 10:
        alert_flags = Message.ALERT_FLAG_SILENT
    else:
        alert_flags = Message.ALERT_FLAG_VIBRATE

    users.set_user(service_user)
    try:
        messaging.send(parent_key=parent_message_key,
                       parent_message_key=parent_message_key,
                       message=u'%s\n\n%s:\n%s' % (translate(lang, SOLUTION_COMMON, u'order_complete_will_notify'),
                                                   translate(lang, SOLUTION_COMMON, u'usage-detail'),
                                                   order_details),
                       answers=list(),
                       flags=Message.FLAG_ALLOW_DISMISS | Message.FLAG_AUTO_LOCK,
                       members=[MemberTO.from_user(user_details[0].toAppUser(), alert_flags)],
                       branding=get_solution_main_branding(service_user).branding_key,
                       tag=None,
                       service_identity=service_identity,
                       alert_flags=alert_flags,
                       step_id=u'order_complete')
    finally:
        users.clear_user()


@returns()
@arguments(service_user=users.User, message_flow_run_id=unicode, member=unicode,
           steps=[object_factory("step_type", FLOW_STEP_MAPPING)], end_id=unicode, end_message_flow_id=unicode,
           parent_message_key=unicode, tag=unicode, result_key=unicode, flush_id=unicode, flush_message_flow_id=unicode,
           service_identity=unicode, user_details=[UserDetailsTO])
def order_received(service_user, message_flow_run_id, member, steps, end_id, end_message_flow_id, parent_message_key,
                   tag, result_key, flush_id, flush_message_flow_id, service_identity, user_details):
    try_or_defer(_order_received, service_user, message_flow_run_id, member, steps, end_id, end_message_flow_id,
                 parent_message_key, tag, result_key, flush_id, flush_message_flow_id, service_identity, user_details,
                 log_first_error=True)


@returns(NoneType)
@arguments(service_user=users.User, order_key=unicode, message=unicode)
def delete_order(service_user, order_key, message):
    from solutions.common.bizz.messaging import send_inbox_forwarders_message

    def txn():
        m = SolutionOrder.get(order_key)
        azzert(service_user == m.service_user)
        m.deleted = True
        m.put()
        return m
    order = db.run_in_transaction(txn)

    sm_data = []
    sm_data.append({u"type": u"solutions.common.orders.deleted", u'order_key': order_key})

    sln_settings = get_solution_settings(service_user)
    if message:
        if order.solution_inbox_message_key:
            sim_parent, _ = add_solution_inbox_message(service_user, order.solution_inbox_message_key, True, None, now(), message, mark_as_unread=False, mark_as_read=True, mark_as_trashed=True)
            send_inbox_forwarders_message(service_user, sim_parent.service_identity, None, message, {
                        'if_name': sim_parent.sender.name,
                        'if_email':sim_parent.sender.email
                    }, message_key=sim_parent.solution_inbox_message_key, reply_enabled=sim_parent.reply_enabled)

            sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, order.service_identity)

            sm_data.append({u"type": u"solutions.common.messaging.update",
                         u"message": serialize_complex_value(SolutionInboxMessageTO.fromModel(sim_parent, sln_settings, sln_i_settings, True), SolutionInboxMessageTO, False)})
        else:
            branding = get_solution_main_branding(service_user).branding_key
            member = MemberTO()
            member.alert_flags = Message.ALERT_FLAG_VIBRATE
            member.member = order.sender.email
            member.app_id = order.sender.app_id

            messaging.send(parent_key=None,
                           parent_message_key=None,
                           message=message,
                           answers=[],
                           flags=Message.FLAG_ALLOW_DISMISS,
                           members=[member],
                           branding=branding,
                           tag=None,
                           service_identity=order.service_identity)

    elif order.solution_inbox_message_key:
        sim_parent = SolutionInboxMessage.get(order.solution_inbox_message_key)
        if not sim_parent.trashed and not sim_parent.deleted:
            sim_parent.trashed = True
            sim_parent.put()
            deferred.defer(update_user_data_admins, service_user, order.service_identity)

        sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, order.service_identity)

        sm_data.append({u"type": u"solutions.common.messaging.update",
                     u"message": serialize_complex_value(SolutionInboxMessageTO.fromModel(sim_parent, sln_settings, sln_i_settings, True), SolutionInboxMessageTO, False)})

    send_message(service_user, sm_data, service_identity=order.service_identity)

@returns(NoneType)
@arguments(service_user=users.User, order_key=unicode, order_status=int, message=unicode)
def send_message_for_order(service_user, order_key, order_status, message):
    from solutions.common.bizz.messaging import send_inbox_forwarders_message

    azzert(order_status in SolutionOrder.ORDER_STATUSES)
    def txn():
        m = SolutionOrder.get(order_key)
        azzert(service_user == m.service_user)
        if m.status == SolutionOrder.STATUS_RECEIVED and m.status != order_status:
            m.status = order_status
            m.put()
        return m
    order = db.run_in_transaction(txn)

    sm_data = []
    sm_data.append({u"type": u"solutions.common.orders.update"})

    sln_settings = get_solution_settings(service_user)
    if message:
        if order.solution_inbox_message_key:
            sim_parent, _ = add_solution_inbox_message(service_user, order.solution_inbox_message_key, True, None, now(), message, mark_as_unread=False, mark_as_read=True)
            send_inbox_forwarders_message(service_user, sim_parent.service_identity, None, message, {
                        'if_name': sim_parent.sender.name,
                        'if_email':sim_parent.sender.email
                    }, message_key=sim_parent.solution_inbox_message_key, reply_enabled=sim_parent.reply_enabled)

            sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, order.service_identity)

            sm_data.append({u"type": u"solutions.common.messaging.update",
                         u"message": serialize_complex_value(SolutionInboxMessageTO.fromModel(sim_parent, sln_settings, sln_i_settings, True), SolutionInboxMessageTO, False)})
        else:
            sln_main_branding = get_solution_main_branding(service_user)
            branding = sln_main_branding.branding_key if sln_main_branding else None

            member = MemberTO()
            member.alert_flags = Message.ALERT_FLAG_VIBRATE
            member.member = order.sender.email
            member.app_id = order.sender.app_id

            messaging.send(parent_key=None,
                           parent_message_key=None,
                           message=message,
                           answers=[],
                           flags=Message.FLAG_ALLOW_DISMISS,
                           members=[member],
                           branding=branding,
                           tag=None,
                           service_identity=order.service_identity)

    elif order.solution_inbox_message_key:
        sim_parent = SolutionInboxMessage.get(order.solution_inbox_message_key)
        if not sim_parent.read:
            sim_parent.read = True
            sim_parent.put()
            deferred.defer(update_user_data_admins, service_user, order.service_identity)

        sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, order.service_identity)

        sm_data.append({u"type": u"solutions.common.messaging.update",
                     u"message": serialize_complex_value(SolutionInboxMessageTO.fromModel(sim_parent, sln_settings, sln_i_settings, True), SolutionInboxMessageTO, False)})

    send_message(service_user, sm_data, service_identity=order.service_identity)


@returns(NoneType)
@arguments(service_user=users.User, timeframe_id=(int, long, NoneType), day=int, time_from=int, time_until=int)
def put_order_weekday_timeframe(service_user, timeframe_id, day, time_from, time_until):
    sln_settings = get_solution_settings(service_user)
    if time_from == time_until:
        raise BusinessException(
            common_translate(sln_settings.main_language, SOLUTION_COMMON, 'time-start-end-equal'))
    if time_from >= time_until:
        raise BusinessException(
            common_translate(sln_settings.main_language, SOLUTION_COMMON, 'time-start-end-smaller'))

    sln_settings = get_solution_settings(service_user)
    if timeframe_id:
        sawt = SolutionOrderWeekdayTimeframe.get_by_id(timeframe_id, parent_key(service_user, sln_settings.solution))
        if not sawt:
            # Already deleted before channel update went through
            send_message(service_user, u"solutions.common.order.settings.timeframe.update")
            return
        sawt.day = day
        sawt.time_from = time_from
        sawt.time_until = time_until
    else:
        sawt = SolutionOrderWeekdayTimeframe.get_or_create(parent_key(service_user, sln_settings.solution), day,
                                                           time_from, time_until)
    sawt.put()

    sln_settings = get_solution_settings(service_user)
    sln_settings.updates_pending = True
    put_and_invalidate_cache(sln_settings)

    broadcast_updates_pending(sln_settings)
    send_message(service_user, u"solutions.common.order.settings.timeframe.update")


@returns(NoneType)
@arguments(service_user=users.User, timeframe_id=(int, long))
def delete_order_weekday_timeframe(service_user, timeframe_id):
    sln_settings = get_solution_settings(service_user)
    sawt = SolutionOrderWeekdayTimeframe.get_by_id(timeframe_id, parent_key(service_user, sln_settings.solution))
    if sawt:
        sawt.delete()
        sln_settings = get_solution_settings(service_user)
        sln_settings.updates_pending = True
        put_and_invalidate_cache(sln_settings)

        broadcast_updates_pending(sln_settings)
        send_message(service_user, u"solutions.common.order.settings.timeframe.update")

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

from types import NoneType

from rogerthat.dal import put_and_invalidate_cache
from rogerthat.rpc import users
from rogerthat.rpc.service import BusinessException
from rogerthat.to import ReturnStatusTO, RETURNSTATUS_TO_SUCCESS
from rogerthat.utils.channel import send_message
from mcfw.restapi import rest
from mcfw.rpc import returns, arguments
from solutions.common.bizz import broadcast_updates_pending
from solutions.common.bizz.order import delete_order, send_message_for_order, delete_order_weekday_timeframe, \
    put_order_weekday_timeframe
from solutions.common.consts import ORDER_TYPE_ADVANCED, SECONDS_IN_DAY, SECONDS_IN_MINUTE, SECONDS_IN_WEEK, \
    SECONDS_IN_HOUR
from solutions.common.dal import get_solution_settings
from solutions.common.dal.order import get_solution_orders, get_solution_order_settings
from solutions.common.models.order import SolutionOrderSettings, SolutionOrderWeekdayTimeframe
from solutions.common.to import SolutionOrderWeekdayTimeframeTO
from solutions.common.to.order import SolutionOrderTO, SolutionOrderSettingsTO


@rest("/common/order/settings/load", "get", read_only_access=True)
@returns(SolutionOrderSettingsTO)
@arguments()
def order_settings_load():
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    sln_order_settings = get_solution_order_settings(sln_settings)
    return SolutionOrderSettingsTO.fromModel(sln_order_settings, sln_settings.main_language)


@rest("/common/order/settings/put", "post")
@returns(ReturnStatusTO)
@arguments(text_1=unicode, order_ready_message=unicode, manual_confirmation=bool, order_type=int, leap_time=int,
           leap_time_type=int)
def put_order_settings(text_1, order_ready_message, manual_confirmation, order_type, leap_time=15,
                       leap_time_type=SECONDS_IN_MINUTE):
    service_user = users.get_current_user()
    if leap_time_type not in [SECONDS_IN_MINUTE, SECONDS_IN_HOUR, SECONDS_IN_DAY, SECONDS_IN_WEEK]:
        leap_time_type = SECONDS_IN_MINUTE
    try:
        sln_order_settings_key = SolutionOrderSettings.create_key(service_user)
        sln_order_settings = SolutionOrderSettings.get(sln_order_settings_key)
        if not sln_order_settings:
            sln_order_settings = SolutionOrderSettings(key=sln_order_settings_key)
        sln_order_settings.text_1 = text_1
        sln_order_settings.order_type = order_type
        sln_order_settings.leap_time = leap_time
        sln_order_settings.leap_time_type = leap_time_type
        sln_order_settings.order_ready_message = order_ready_message
        sln_order_settings.manual_confirmation = manual_confirmation
        sln_order_settings.put()

        sln_settings = get_solution_settings(service_user)
        sln_settings.updates_pending = True
        put_and_invalidate_cache(sln_order_settings, sln_settings)
        broadcast_updates_pending(sln_settings)
        if order_type == ORDER_TYPE_ADVANCED:
            SolutionOrderWeekdayTimeframe.create_default_timeframes_if_nessecary(service_user, sln_settings.solution)
        send_message(service_user, u"solutions.common.order.settings.update")
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest('/common/order/settings/timeframe/put', "post")
@returns(ReturnStatusTO)
@arguments(timeframe_id=(int, long, NoneType), day=int, time_from=int, time_until=int)
def save_order_weekday_timeframe(timeframe_id, day, time_from, time_until):
    service_user = users.get_current_user()
    try:
        put_order_weekday_timeframe(service_user, timeframe_id, day, time_from, time_until)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest("/common/order/settings/timeframe/delete", "post")
@returns(ReturnStatusTO)
@arguments(timeframe_id=(int, long))
def remove_order_weekday_timeframe(timeframe_id):
    service_user = users.get_current_user()
    try:
        delete_order_weekday_timeframe(service_user, timeframe_id)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)


@rest('/common/order/settings/timeframe/load', "get", read_only_access=True)
@returns([SolutionOrderWeekdayTimeframeTO])
@arguments()
def get_order_timeframes():
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    return [SolutionOrderWeekdayTimeframeTO.fromModel(f, sln_settings.main_language) for f in
            SolutionOrderWeekdayTimeframe.list(service_user, sln_settings.solution)]

@rest("/common/order/delete", "post")
@returns(ReturnStatusTO)
@arguments(order_key=unicode, message=unicode)
def order_delete(order_key, message):
    service_user = users.get_current_user()
    try:
        delete_order(service_user, order_key, message)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)

@rest("/common/orders/load", "get", read_only_access=True)
@returns([SolutionOrderTO])
@arguments()
def orders_load():
    service_user = users.get_current_user()
    session_ = users.get_current_session()
    service_identity = session_.service_identity
    return map(SolutionOrderTO.fromModel, get_solution_orders(service_user, service_identity))

@rest("/common/order/sendmessage", "post")
@returns(ReturnStatusTO)
@arguments(order_key=unicode, order_status=int, message=unicode)
def order_send_message(order_key, order_status, message):
    service_user = users.get_current_user()
    try:
        send_message_for_order(service_user, order_key, order_status, message)
        return RETURNSTATUS_TO_SUCCESS
    except BusinessException, e:
        return ReturnStatusTO.create(False, e.message)

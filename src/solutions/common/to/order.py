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

from mcfw.properties import bool_property, long_property, unicode_property
from solutions import translate as common_translate
from solutions.common import SOLUTION_COMMON
from solutions.common.consts import SECONDS_IN_MINUTE
from solutions.common.models.order import SolutionOrderSettings


class SolutionOrderSettingsTO(object):
    text_1 = unicode_property('1')
    order_type = long_property('2')
    leap_time = long_property('3')
    leap_time_type = long_property('4')
    order_ready_message = unicode_property('5')
    manual_confirmation = bool_property('6', default=False)

    @staticmethod
    def fromModel(obj, language):
        if obj is None:
            return None
        to = SolutionOrderSettingsTO()
        text_1 = None
        if obj:
            text_1 = obj.text_1
            to.order_type = obj.order_type
            to.leap_time = obj.leap_time
            to.leap_time_type = obj.leap_time_type
            to.order_ready_message = obj.order_ready_message
            to.manual_confirmation = obj.manual_confirmation
        else:
            to.order_type = SolutionOrderSettings.DEFAULT_ORDER_TYPE
            to.leap_time = 15
            to.leap_time_type = SECONDS_IN_MINUTE
        if not text_1:
            text_1 = common_translate(language, SOLUTION_COMMON, 'order-flow-details')

        to.text_1 = text_1
        if not to.order_ready_message:
            to.order_ready_message = common_translate(language, SOLUTION_COMMON, 'order-ready')
        return to


class SolutionOrderTO(object):
    key = unicode_property('1')
    description = unicode_property('2')
    status = long_property('3')
    sender_name = unicode_property('4')
    sender_avatar_url = unicode_property('5')
    timestamp = long_property('6')
    picture_url = unicode_property('7')
    phone_number = unicode_property('8')
    solution_inbox_message_key = unicode_property('9')
    takeaway_time = long_property('10')

    @staticmethod
    def fromModel(model):
        to = SolutionOrderTO()
        to.key = unicode(model.solution_order_key)
        to.description = model.description
        to.status = model.status
        to.sender_name = model.sender.name
        to.sender_avatar_url = model.sender.avatar_url
        to.timestamp = model.timestamp
        to.picture_url = model.picture_url
        to.phone_number = model.phone_number
        to.solution_inbox_message_key = model.solution_inbox_message_key
        to.takeaway_time = model.takeaway_time
        return to

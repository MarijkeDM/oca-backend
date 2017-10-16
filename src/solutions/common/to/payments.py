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

from mcfw.properties import unicode_property, bool_property

class PaymentSettingsTO(object):
    enabled = bool_property('1')
    optional = bool_property('2')


class PayconiqProviderTO(object):
    merchant_id = unicode_property('1')
    jwt = unicode_property('2')
    online_key = unicode_property('3')

    @classmethod
    def fromProvider(cls, obj):
        to = cls()
        if obj:
            d = json.loads(obj.settings)
            to.merchant_id = d.get('merchant_id')
            to.jwt = d.get('jwt')
            to.online_key = d.get('online_key')
        else:
            to.merchant_id = None
            to.jwt = None
            to.online_key = None
        return to
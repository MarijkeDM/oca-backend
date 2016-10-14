# -*- coding: utf-8 -*-
# Copyright 2016 Mobicage NV
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
# @@license_version:1.1@@

from mcfw.properties import unicode_property, bool_property


class CityAppProfileTO(object):
    uitdatabank_enabled = bool_property('0')
    uitdatabank_key = unicode_property('1')
    uitdatabank_region = unicode_property('2')
    gather_events = bool_property('3')

    @staticmethod
    def from_model(model):
        to = CityAppProfileTO()
        to.uitdatabank_enabled = model.uitdatabank_enabled
        to.uitdatabank_key = model.uitdatabank_key
        to.uitdatabank_region = model.uitdatabank_region
        to.gather_events = model.gather_events_enabled
        return to

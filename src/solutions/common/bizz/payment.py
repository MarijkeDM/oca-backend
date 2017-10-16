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

from google.appengine.ext import db
from solutions.common.bizz import broadcast_updates_pending
from solutions.common.dal import get_solution_settings


def get_payment_settings(service_user):
    sln_settings = get_solution_settings(service_user)
    if sln_settings.payment_enabled is None:
        return False, True
    return sln_settings.payment_enabled, sln_settings.payment_optional


def save_payment_settings(service_user, enabled, optional):
    def trans():
        sln_settings = get_solution_settings(service_user)
        sln_settings.payment_enabled = enabled
        sln_settings.payment_optional = optional
        sln_settings.updates_pending = True
        sln_settings.put()
        return sln_settings

    sln_settings = db.run_in_transaction(trans)
    broadcast_updates_pending(sln_settings)
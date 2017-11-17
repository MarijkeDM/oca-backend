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

from google.appengine.ext import db
from rogerthat.bizz.job import run_job
from rogerthat.utils import now
from shop.models import CustomerSignup


DAY = 24 * 3600


def all_pending_signups():
    # unverified signup is the one that its email address hasn't been verified yet
    # not done and doesn't have an inbox message, as inbox messages are sent on email successful verification
    return CustomerSignup.all(keys_only=True).filter('done', False).filter('inbox_message_key', None)


def remove_if_expired(signup_key, at):
    signup = CustomerSignup.get(signup_key)
    timestamp = signup.timestamp
    if not timestamp or (at - timestamp) > DAY:
        logging.info('Deleting CustomerSignup:\n%s', db.to_dict(signup))
        db.delete(signup)


def job():
    run_job(all_pending_signups, [], remove_if_expired, [now()])

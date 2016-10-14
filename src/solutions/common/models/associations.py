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

from google.appengine.ext import db


class AssociationStatistic(db.Model):
    customer_emails = db.StringListProperty(indexed=False)  # association service emails
    future_events_count = db.ListProperty(int, indexed=False)
    broadcasts_last_month = db.ListProperty(int, indexed=False)
    static_content_count = db.ListProperty(int, indexed=False)
    last_unanswered_questions_timestamps = db.ListProperty(int, indexed=False)
    generated_on = db.IntegerProperty(indexed=False)

    @classmethod
    def create_key(cls, city_app_id):
        return db.Key.from_path(cls.kind(), city_app_id)

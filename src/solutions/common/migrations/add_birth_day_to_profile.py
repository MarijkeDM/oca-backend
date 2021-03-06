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

from rogerthat.bizz.job import run_job
from rogerthat.models import UserProfile

def add_birth_day_to_profile():
    run_job(_data, [], _worker, [])

def _data():
    return UserProfile.all()

def _worker(profile):
    if profile.birthdate is None:
        return
    
    profile.birth_day = profile.get_birth_day_int(profile.birthdate)
    profile.put()

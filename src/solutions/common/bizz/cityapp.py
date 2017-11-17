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

from hashlib import sha1
from hmac import new as hmac
import json
import logging
from random import getrandbits
import time
from types import NoneType
from urllib import quote as urlquote
import urllib

from google.appengine.api import urlfetch
from mcfw.rpc import returns, arguments
from rogerthat.rpc import users
from rogerthat.utils.transactions import run_in_transaction
from solutions.common.dal.cityapp import get_cityapp_profile
from solutions.common.models.cityapp import CityAppProfile


@returns(NoneType)
@arguments(service_user=users.User, gather_events=bool, uitdatabank_secret=unicode, uitdatabank_key=unicode, uitdatabank_regions=[unicode])
def save_cityapp_settings(service_user, gather_events, uitdatabank_secret, uitdatabank_key, uitdatabank_regions):
    def trans():
        cap = get_cityapp_profile(service_user)
        cap.uitdatabank_secret = uitdatabank_secret
        cap.uitdatabank_key = uitdatabank_key
        cap.uitdatabank_regions = uitdatabank_regions
        cap.gather_events_enabled = gather_events
        cap.put()
    run_in_transaction(trans, False)

@returns(tuple)
@arguments(city_app_profile=CityAppProfile, page=(int, long), pagelength=(int, long), changed_since=(int, long, NoneType))
def get_uitdatabank_events(city_app_profile, page, pagelength, changed_since=None):
    if city_app_profile.uitdatabank_secret:
        return _get_uitdatabank_events_v2(city_app_profile, page, pagelength)
    return _get_uitdatabank_events_old(city_app_profile, page, pagelength, changed_since)


@returns(tuple)
@arguments(city_app_profile=CityAppProfile, page=(int, long), pagelength=(int, long), changed_since=(int, long, NoneType))
def _get_uitdatabank_events_old(city_app_profile, page, pagelength, changed_since=None):
    if not (city_app_profile.uitdatabank_key and city_app_profile.uitdatabank_regions):
        return False, "Not all fields are provided"

    url = "http://build.uitdatabank.be/api/events/search?"
    values = {'key' : city_app_profile.uitdatabank_key,
              'format' : "json",
              'regio' : city_app_profile.uitdatabank_regions[0],
              'changedsince' : time.strftime('%Y-%m-%dT%H.%M', time.gmtime(changed_since)) if changed_since else "",
              'page' : page,
              'pagelength' : pagelength }
    data = urllib.urlencode(values)
    logging.debug(url + data);
    result = urlfetch.fetch(url + data, deadline=60)
    r = json.loads(result.content)

    if not r:
        if changed_since or page != 1:
            return True, []
        return False, "0 upcoming events. Make sure your region is correct."

    if "error" in r[0]:
        return False, r[0]["error"]

    return True, r


@returns(tuple)
@arguments(city_app_profile=CityAppProfile, page=(int, long), pagelength=(int, long))
def _get_uitdatabank_events_v2(city_app_profile, page, pagelength):

    def encode(text):
        return urlquote(str(text), "~")

    secret = city_app_profile.uitdatabank_secret.encode("utf8")
    key = city_app_profile.uitdatabank_key.encode("utf8")
    cities = [c.encode("utf8") for c in city_app_profile.uitdatabank_regions]

    url = "https://www.uitid.be/uitid/rest/searchv2/search"
    headers = {}

    params = {
        "oauth_consumer_key": key,
        "oauth_timestamp": str(int(time.time())),
        "oauth_nonce": str(getrandbits(64)),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_version": "1.0",
    }

    url_params = {"q": " OR ".join(["city:%s" % city for city in cities]),
                  "rows": pagelength,
                  "start": (page - 1) * pagelength,
                  "datetype": "next3months",
                  "group": "event"}
    params.update(url_params)

    for k, v in params.items():
        if isinstance(v, unicode):
            params[k] = v.encode('utf8')

    params_str = "&".join(["%s=%s" % (encode(k), encode(params[k]))
                                                 for k in sorted(params)])

    base_string = "&".join(["GET", encode(url), encode(params_str)])

    signature = hmac("%s&" % secret, base_string, sha1)
    digest_base64 = signature.digest().encode("base64").strip()
    params["oauth_signature"] = encode(digest_base64)
    headers['Accept'] = "application/json"
    headers['Authorization'] = 'OAuth oauth_consumer_key="%s",oauth_signature_method="%s",oauth_timestamp="%s",oauth_nonce="%s",oauth_version="1.0",oauth_signature="%s"' % (
         encode(params['oauth_consumer_key']),
         encode(params['oauth_signature_method']),
         encode(params['oauth_timestamp']),
         encode(params['oauth_nonce']),
         params["oauth_signature"])

    data = urllib.urlencode(url_params)
    url = "%s?%s" % (url, data)
    logging.debug(url);
    result = urlfetch.fetch(url, headers=headers, deadline=30)
    if result.status_code != 200:
        return False, "Make sure your credentials are correct."

    r = json.loads(result.content)["rootObject"]

    if "error" in r[0]:
        return False, r[0]["error"]

    event_count = r[0]["Long"]
    if event_count == 0:
        if page != 1:
            return True, []
        return False, "0 upcoming events. Make sure your region is correct."
    return True, [e["event"] for e in r[1:]]

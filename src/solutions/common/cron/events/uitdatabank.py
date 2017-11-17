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

from collections import defaultdict
import datetime
from hashlib import sha1
from hmac import new as hmac
import json
import logging
from random import getrandbits
import time
from urllib import quote as urlquote
import urllib

import pytz

from google.appengine.api import urlfetch
from google.appengine.ext import db, deferred
from rogerthat.bizz.job import run_job
from rogerthat.consts import DEBUG
from rogerthat.dal import put_and_invalidate_cache, parent_key
from rogerthat.utils import now, get_epoch_from_datetime
from shop.constants import MAPS_QUEUE
from solutions.common.bizz.cityapp import get_uitdatabank_events
from solutions.common.dal import get_solution_settings
from solutions.common.models import SolutionSettings
from solutions.common.models.agenda import  Event
from solutions.common.models.cityapp import CityAppProfile
import webapp2


class CityAppSolutionEventsUitdatabank(webapp2.RequestHandler):

    def get(self):
        run_job(_get_cityapp_uitdatabank_enabled_query, [], _process_cityapp_uitdatabank_events, [1], worker_queue=MAPS_QUEUE)


def _get_cityapp_uitdatabank_enabled_query():
    return db.GqlQuery("SELECT __key__ FROM CityAppProfile WHERE uitdatabank_enabled = true")


def _process_cityapp_uitdatabank_events(cap_key, page):
    try:
        uitdatabank_actors = defaultdict(list)
        for sln_settings in SolutionSettings.all().filter("uitdatabank_actor_id !=", None):
            uitdatabank_actors[sln_settings.uitdatabank_actor_id].append(sln_settings)

        pagelength = 50
        cap = CityAppProfile.get(cap_key)
        if page == 1:
            run_time = now()
            services_to_update = set()
        else:
            run_time = cap.run_time
            services_to_update = set(cap.services_to_update)

        logging.info("process_cityapp_uitdatabank_events for %s page %s", cap.service_user, page)
        success, result = get_uitdatabank_events(cap, page, pagelength, cap.uitdatabank_last_query or None)
        if not success:
            logging.exception(result, _suppress=False)
            return

        sln_settings = get_solution_settings(cap.service_user)
        to_put = list()
        should_update_service = page != 1

        result_count = 0
        updated_events_count = 0
        for r in result:
            result_count += 1
            updated_events = _populate_uit_events(sln_settings, cap.uitdatabank_secret, cap.uitdatabank_key, r['cdbid'], uitdatabank_actors, cap.uitdatabank_last_query or None)
            if updated_events:
                services_to_update.update((event.service_user for event in updated_events))
                updated_events_count += 1
                should_update_service = True
                to_put.extend(updated_events)

        def trans_update_cap():
            cap = db.get(cap_key)
            cap.run_time = run_time
            cap.services_to_update = list(services_to_update)
            cap.put()
            return cap
        cap = db.run_in_transaction(trans_update_cap)

        logging.debug("Added/updated %s/%s events", updated_events_count, result_count)
        if to_put:
            put_and_invalidate_cache(*to_put)

        if result_count != 0:
            deferred.defer(_process_cityapp_uitdatabank_events, cap_key, page + 1)
        else:
            def trans_set_last_query():
                cap = db.get(cap_key)
                cap.uitdatabank_last_query = cap.run_time
                cap.put()
                return cap
            cap = db.run_in_transaction(trans_set_last_query)

            if should_update_service:
                for service_user in cap.services_to_update:
                    if service_user != sln_settings.service_user:
                        settings_to_put = get_solution_settings(service_user)
                    else:
                        settings_to_put = sln_settings
                    settings_to_put.put_identity_pending = True
                    settings_to_put.put()
    except Exception, e:
        logging.exception(str(e), _suppress=False)


def get_dates_v1(r_timestamp):
    r_timestart = r_timestamp["timestart"]
    start_date = datetime.datetime.strptime("%s %s" % (r_timestamp["date"], r_timestart), "%Y-%m-%d %H:%M:%S")
    start_date = get_epoch_from_datetime(start_date)
    if r_timestamp.get("timeend", None):
        end_date = time.strptime(r_timestamp["timeend"], '%H:%M:%S')
        end_date = long(datetime.timedelta(hours=end_date.tm_hour, minutes=end_date.tm_min,
                                           seconds=end_date.tm_sec).total_seconds())
    else:
        end_date = 0
    return start_date, end_date


def get_dates_v2(r_timestamp):
    r_timestart = r_timestamp["timestart"]
    timestamp = long((r_timestamp["date"] + r_timestart) / 1000)
    tz = pytz.timezone('Europe/Brussels')
    dt_with_tz = datetime.datetime.fromtimestamp(timestamp, tz)
    dt_without_tz = datetime.datetime(dt_with_tz.year, dt_with_tz.month, dt_with_tz.day, dt_with_tz.hour,
                                      dt_with_tz.minute, dt_with_tz.second)
    time_epoch = get_epoch_from_datetime(dt_without_tz)
    time_diff = _get_time_diff_uitdatabank(dt_with_tz, dt_without_tz)
    start_date = time_epoch - time_diff
    if r_timestamp.get("timeend", None):
        end_date = int(r_timestamp["timeend"] / 1000) - time_diff
    else:
        end_date = 0
    return start_date, end_date


def get_event_start_and_end_dates(timestamps, v2=False):
    event_start_dates = list()
    event_end_dates = list()

    def get_dates(r_timestamp):
        if v2:
            start_date, end_date = get_dates_v2(r_timestamp)
        else:
            start_date, end_date = get_dates_v1(r_timestamp)

        event_start_dates.append(start_date)
        event_end_dates.append(end_date)


    r_timestamp = timestamps["timestamp"]
    if isinstance(r_timestamp, dict):
        logging.debug("dict timestamp: %s", r_timestamp)
        r_timestart = r_timestamp.get("timestart", None)
        if not r_timestart:
            logging.info("Skipping event because it had no starttime (dict)")
            return None, None
        get_dates(r_timestamp)
    elif isinstance(r_timestamp, list):
        logging.debug("list timestamp: %s", r_timestamp)
        for r_ts in r_timestamp:
            if r_ts.get("timestart"):
                get_dates(r_ts)

    return event_start_dates, event_end_dates


def _populate_uit_events(sln_settings, uitdatabank_secret, uitdatabank_key, external_id, uitdatabank_actors, changed_since):
    logging.debug("process event with id: %s", external_id)
    detail_success, detail_result = _get_uitdatabank_events_detail(uitdatabank_secret, uitdatabank_key, external_id)
    if not detail_success:
        logging.warn("Failed to get detail for cdbid: %s\n%s" % (external_id, detail_result))
        return None

    if uitdatabank_secret and changed_since:
        if detail_result["lastupdated"] < (changed_since * 100):
            return None

    if DEBUG:
        logging.warn("detail result: %s", detail_result)

    event_parent_key = parent_key(sln_settings.service_user, sln_settings.solution)
    event = Event.all().ancestor(event_parent_key).filter("source =", Event.SOURCE_UITDATABANK_BE).filter("external_id =", external_id).get()
    if not event:
        event = Event(parent=event_parent_key,
                      source=Event.SOURCE_UITDATABANK_BE,
                      external_id=external_id)

    event.calendar_id = sln_settings.default_calendar
    events = [event]

    uitdatabank_created_by = detail_result.get("createdby", None)
    logging.debug("uitdatabank_created_by: %s", uitdatabank_created_by)
    uitdatabank_lastupdated_by = detail_result.get("lastupdatedby", None)
    logging.debug("uitdatabank_lastupdated_by: %s", uitdatabank_lastupdated_by)

    if uitdatabank_created_by or uitdatabank_lastupdated_by:
        if uitdatabank_created_by and uitdatabank_created_by not in uitdatabank_actors:
            uitdatabank_actors[uitdatabank_created_by] = []
        if uitdatabank_lastupdated_by and uitdatabank_lastupdated_by not in uitdatabank_actors:
            uitdatabank_actors[uitdatabank_lastupdated_by] = []

        origanizer_settings = []
        if uitdatabank_created_by:
            origanizer_settings.extend(uitdatabank_actors[uitdatabank_created_by])
        if uitdatabank_lastupdated_by and uitdatabank_created_by != uitdatabank_lastupdated_by:
            origanizer_settings.extend(uitdatabank_actors[uitdatabank_lastupdated_by])

        logging.debug("len(origanizer_settings): %s", len(origanizer_settings))
        for organizer_sln_settings in origanizer_settings:
            organizer_event_parent_key = parent_key(organizer_sln_settings.service_user, organizer_sln_settings.solution)
            organizer_event = Event.all().ancestor(organizer_event_parent_key).filter("source =", Event.SOURCE_UITDATABANK_BE).filter("external_id =", external_id).get()
            if not organizer_event:
                organizer_event = Event(parent=organizer_event_parent_key,
                                    source=Event.SOURCE_UITDATABANK_BE,
                                    external_id=external_id)

            organizer_event.calendar_id = organizer_sln_settings.default_calendar
            events.append(organizer_event)

    r_event_detail = detail_result["eventdetails"]["eventdetail"]
    if not r_event_detail:
        logging.warn('Missing eventdetail')
        return None

    if isinstance(r_event_detail, list):
        for x in r_event_detail:
            if x['lang'] == sln_settings.main_language:
                r_event_detail = x
                break
        else:
            r_event_detail = r_event_detail[0]

    event_title = r_event_detail["title"]
    event_description = r_event_detail.get("shortdescription", r_event_detail.get("longdescription", u""))

    if "physical" in detail_result["location"]["address"]:
        location = detail_result["location"]["address"]["physical"]
        if location.get("street", None):
            if uitdatabank_secret:
                event_place = "%s %s, %s %s" % (location["street"]["value"], location.get("housenr", ""), location["zipcode"], location["city"]["value"])
            else:
                event_place = "%s %s, %s %s" % (location["street"], location.get("housenr", ""), location["zipcode"], location["city"])
        else:
            if uitdatabank_secret:
                event_place = "%s %s" % (location["zipcode"], location["city"]["value"])
            else:
                event_place = "%s %s" % (location["zipcode"], location["city"])
    else:
        event_place = detail_result["location"]["address"]["virtual"]["title"]

    r_organizer = detail_result.get('organiser')
    for k in ('actor', 'actordetails', 'actordetail', 'title'):
        if not r_organizer:
            break
        r_organizer = r_organizer.get(k)
    event_organizer = r_organizer

    r_timestamps = detail_result["calendar"].get("timestamps")
    if not r_timestamps:
        logging.debug("skipping event because we could not determine starttime")
        return None

    event_start_dates, event_end_dates = get_event_start_and_end_dates(r_timestamps, v2=uitdatabank_secret)
    if not event_start_dates:
        logging.info("Skipping event because it had no starttime (list)")
        return None

    for event in events:
        event.title = event_title
        event.description = event_description
        event.place = event_place
        event.organize = event_organizer
        event.last_start_date = max(event_start_dates)
        event.start_dates = event_start_dates
        event.end_dates = event_end_dates
        event.first_start_date = event.get_first_event_date()
    return events

def _get_time_diff_uitdatabank(dt_with_tz, dt_without_tz):
    time_diff = int((dt_with_tz - pytz.UTC.localize(dt_without_tz)).total_seconds())
    if time_diff == -7200:
        return -3600 # Thre json response from uitdatabank is incorrect
    return time_diff


def _get_uitdatabank_events_detail(uitdatabank_secret, uitdatabank_key, cbd_id):
    if uitdatabank_secret:
        return _get_uitdatabank_events_detail_v2(uitdatabank_secret, uitdatabank_key, cbd_id)
    return _get_uitdatabank_events_detail_old(uitdatabank_key, cbd_id)


def _get_uitdatabank_events_detail_old(uitdatabank_key, cbd_id):
    url = "http://build.uitdatabank.be/api/event/%s?" % cbd_id
    values = {'key' : uitdatabank_key,
              'format' : "json" }
    data = urllib.urlencode(values)
    result = urlfetch.fetch(url + data, deadline=60)
    r = json.loads(result.content)

    if not isinstance(r, list):
        event = r.get("event")
        if event is not None:
            return True, event
    elif "error" in r[0]:
        return False, r[0]["error"]
    return False, "Unknown error occurred"


def _get_uitdatabank_events_detail_v2(uitdatabank_secret, uitdatabank_key, cbd_id):

    def encode(text):
        return urlquote(str(text), "~")

    secret = uitdatabank_secret.encode("utf8")
    key = uitdatabank_key.encode("utf8")
    url = "https://www.uitid.be/uitid/rest/searchv2/detail/event/%s" % cbd_id

    headers = {}

    params = {
        "oauth_consumer_key": key,
        "oauth_timestamp": str(long(time.time())),
        "oauth_nonce": str(getrandbits(64)),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_version": "1.0",
    }

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

    result = urlfetch.fetch(url, headers=headers, deadline=60)

    if result.status_code != 200:
        return False, "Unkown error occurred status code"

    r = json.loads(result.content)['rootObject']
    if "error" in r[0]:
        return False, r[0]["error"]
    event = r[0].get("event")
    if event is not None:
        return True, event

    return False, "Unknown error occurred end"

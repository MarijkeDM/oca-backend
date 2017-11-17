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

import base64
from datetime import date, datetime, timedelta
import json
import logging
import os
import re
import time
from types import FunctionType, NoneType
from zipfile import ZipFile, ZIP_DEFLATED

import dateutil.parser
from dateutil.relativedelta import relativedelta
from lxml import etree, html
import pytz

from apiclient.discovery import build
from google.appengine.api import images, urlfetch
from google.appengine.ext import db, deferred
from googleapiclient.errors import HttpError
import httplib2
from icalendar import Calendar, Event as ICalenderEvent, vCalAddress, vText
from mcfw.consts import MISSING
from mcfw.properties import object_factory
from mcfw.rpc import returns, arguments, serialize_complex_value
from oauth2client import client
from oauth2client.client import HttpAccessTokenRefreshError
from rogerthat.consts import DEBUG
from rogerthat.dal import parent_key, put_and_invalidate_cache
from rogerthat.dal.app import get_app_by_id
from rogerthat.models import App
from rogerthat.rpc import users
from rogerthat.rpc.rpc import APPENGINE_APP_ID
from rogerthat.rpc.service import BusinessException
from rogerthat.settings import get_server_settings
from rogerthat.to.messaging.flow import FLOW_STEP_MAPPING
from rogerthat.to.messaging.service_callback_results import PokeCallbackResultTO, FlowMemberResultCallbackResultTO, \
    TYPE_FLOW, FlowCallbackResultTypeTO
from rogerthat.to.service import SendApiCallCallbackResultTO, UserDetailsTO
from rogerthat.translations import DEFAULT_LANGUAGE
from rogerthat.utils import send_mail, file_get_contents, now, get_epoch_from_datetime, \
    replace_url_with_forwarded_server
from rogerthat.utils.app import create_app_user_by_email
from rogerthat.utils.channel import send_message
from rogerthat.utils.rfc3339 import rfc3339
from rogerthat.utils.service import create_service_identity_user
from solution_server_settings import get_solution_server_settings
from solutions import translate
from solutions import translate as common_translate
import solutions
from solutions.common import SOLUTION_COMMON
from solutions.common.bizz import broadcast_updates_pending, render_common_content, common_provision, put_branding, \
    assign_app_user_role, revoke_app_user_role
from solutions.common.bizz.inbox import create_solution_inbox_message, add_solution_inbox_message
from solutions.common.dal import get_solution_settings, get_event_by_id, is_reminder_set, get_solution_calendar_ids_for_user, \
    get_solution_main_branding, get_solution_calendars_for_user, get_solution_settings_or_identity_settings
from solutions.common.handlers import JINJA_ENVIRONMENT
from solutions.common.models import SolutionInboxMessage
from solutions.common.models.agenda import Event, EventReminder, SolutionCalendar, EventGuest, SolutionCalendarAdmin, \
    SolutionCalendarGoogleSync, SolutionGoogleCredentials
from solutions.common.models.properties import SolutionUser
from solutions.common.to import EventItemTO, EventGuestTO, SolutionGoogleCalendarStatusTO, SolutionGoogleCalendarTO, \
    SolutionInboxMessageTO


try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


API_METHOD_SOLUTION_EVENTS_ADDTOCALENDER = "solutions.events.addtocalender"
API_METHOD_SOLUTION_EVENTS_REMIND = "solutions.events.remind"
API_METHOD_SOLUTION_EVENTS_REMOVE = "solutions.events.remove"
API_METHOD_SOLUTION_EVENTS_GUEST_STATUS = "solutions.events.guest.status"
API_METHOD_SOLUTION_EVENTS_GUESTS = "solutions.events.guests"
API_METHOD_SOLUTION_CALENDAR_BROADCAST = "solutions.calendar.broadcast"

def _get_client_flow():
    if DEBUG:
        redirect_uri = "http://rt.dev:8080/common/events/google/oauth2callback"
    else:
        redirect_uri = "https://%s.appspot.com/common/events/google/oauth2callback" % APPENGINE_APP_ID
        redirect_uri = replace_url_with_forwarded_server(redirect_uri)

    solution_server_setting = get_solution_server_settings()
    flow = client.OAuth2WebServerFlow(client_id=solution_server_setting.solution_sync_calendar_events_client_id,
                                      client_secret=solution_server_setting.solution_sync_calendar_events_client_secret,
                                      scope='https://www.googleapis.com/auth/calendar.readonly email',
                                      redirect_uri=redirect_uri,
                                      approval_prompt='force')
    return flow

def get_google_authenticate_url(calendar_id):
    flow = _get_client_flow()
    url = flow.step1_get_authorize_url(state=calendar_id)
    return url

@returns(SolutionGoogleCalendarStatusTO)
@arguments(service_user=users.User, calendar_id=(int, long))
def get_google_calendars(service_user, calendar_id):
    sln_settings = get_solution_settings(service_user)
    def trans():
        sc = SolutionCalendar.get_by_id(calendar_id, parent_key(service_user, sln_settings.solution))
        if not sc:
            return None, None
        return sc.get_google_credentials(), sc.google_calendar_ids

    xg_on = db.create_transaction_options(xg=True)
    google_credentials, google_calendar_ids = db.run_in_transaction_options(xg_on, trans)

    result = SolutionGoogleCalendarStatusTO()
    result.enabled = False
    result.calendars = []
    if google_credentials:
        logging.debug("access_token_expired: %s", google_credentials.access_token_expired)
        if google_credentials.access_token_expired:
            return result

        http_auth = google_credentials.authorize(httplib2.Http())
        calendar_service = build('calendar', 'v3', http=http_auth)
        try:
            result.enabled = True
            calendar_list = calendar_service.calendarList().list().execute(http=http_auth)
            if calendar_list['items']:
                for c in calendar_list['items']:
                    calendar_to = SolutionGoogleCalendarTO()
                    calendar_to.key = c["id"]
                    calendar_to.label = c["summary"]
                    calendar_to.enabled = calendar_to.key in google_calendar_ids
                    result.calendars.append(calendar_to)
        except:
            result.enabled = False
            result.calendars = []
            logging.warn(u"Error while loading calendars", exc_info=1)

    return result

def save_google_credentials(service_user, calendar_id, code):
    flow = _get_client_flow()
    credentials = flow.step2_exchange(code=code)
    http_auth = credentials.authorize(httplib2.Http())
    userinfo_service = build('oauth2', 'v2', http=http_auth)
    try:
        user_info = userinfo_service.userinfo().get().execute()
        logging.info(user_info)
        if user_info and user_info.get('id'):
            deferred.defer(_save_google_credentials, service_user, calendar_id, user_info, credentials)
            return True
    except Exception, e:
        logging.error('An error occurred while saving google credentials: %s', e)
    return False

def _save_google_credentials(service_user, calendar_id, user_info, credentials):
    sln_settings = get_solution_settings(service_user)
    def trans():
        sgc_key = SolutionGoogleCredentials.createKey(user_info['id'])
        sgc = SolutionGoogleCredentials(key=sgc_key)
        sgc.email = user_info.get('email', None)
        sgc.name = user_info.get('name', None)
        sgc.gender = user_info.get('gender', None)
        sgc.picture = user_info.get('picture', None)
        sgc.credentials = credentials
        sgc.put()  # we still need to save this because other calendars can be using the same credential
        sc = SolutionCalendar.get_by_id(calendar_id, parent_key(service_user, sln_settings.solution))
        if not sc:
            return
        sc.google_credentials = user_info['id']
        sc.put()
    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans)

def update_events_from_google(service_user, calendar_id):
    sln_settings = get_solution_settings(service_user)
    def trans():
        sc = SolutionCalendar.get_by_id(calendar_id, parent_key(service_user, sln_settings.solution))
        if not sc:
            return None, None, None
        return str(sc.key()), sc.get_google_credentials(), sc.google_calendar_ids

    xg_on = db.create_transaction_options(xg=True)
    calendar_str_key, google_credentials, google_calendar_ids = db.run_in_transaction_options(xg_on, trans)

    if google_credentials and google_calendar_ids:
        logging.debug("access_token_expired: %s", google_credentials.access_token_expired)
        http_auth = google_credentials.authorize(httplib2.Http())
        calendar_service = build('calendar', 'v3', http=http_auth)

        date_now = datetime.now()
        time_min = rfc3339(date_now, utc=True)
        date_next_year = date_now + relativedelta(years=1)
        time_max = rfc3339(date_next_year, utc=True)

        for google_calendar_id in google_calendar_ids:
            page_token = None
            while True:
                try:
                    events = calendar_service.events().list(calendarId=google_calendar_id, maxResults=200,
                                                            pageToken=page_token, singleEvents=True, timeMin=time_min,
                                                            timeMax=time_max, showDeleted=True).execute(http=http_auth)
                except (HttpError, HttpAccessTokenRefreshError) as e:
                    logging.warning(u'Could not update google calendars for calendar_id %s and service_user %s: %s', google_calendar_id, service_user, e.message)
                    def trans_reset_credentials():
                        sc = SolutionCalendar.get_by_id(calendar_id, parent_key(service_user, sln_settings.solution))
                        if sc and sc.google_credentials:
                            sc.google_credentials = None
                            sc.put()
                    db.run_in_transaction_options(xg_on, trans_reset_credentials)
                    break
                page_token = events.get('nextPageToken')
                if events['items']:
                    deferred.defer(put_google_events, service_user, calendar_str_key, calendar_id, sln_settings.solution, not page_token, events['items'], sln_settings.main_language)
                if not page_token:
                    break

def put_google_events(service_user, calendar_str_key, calendar_id, solution, google_calendar_finished, google_events, language):
    to_put = []
    no_title_text = common_translate(language, SOLUTION_COMMON, '(No title)')
    for google_event in google_events:
        try:
            google_event_id = google_event["id"]
            event_parent_key = parent_key(service_user, solution)
            event = Event.all().ancestor(event_parent_key).filter("source =", Event.SOURCE_GOOGLE_CALENDAR).filter("external_id =", google_event_id).get()
            if not event:
                event = Event(parent=event_parent_key,
                              source=Event.SOURCE_GOOGLE_CALENDAR,
                              external_id=google_event_id)

            if google_event.get("status", "confirmed") == "cancelled":
                if not event.is_saved():
                    continue
                event.deleted = True
            elif not event.deleted:
                event.deleted = False
            event.title = google_event.get('summary', no_title_text)
            event.place = google_event.get("location", u"").replace(u"\n", u" ")
            event.organizer = google_event.get("organizer", {}).get("displayName", u"")
            event.description = google_event.get('description', u"")
            event.calendar_id = calendar_id
            event.external_link = google_event["htmlLink"]
            event.start_dates = list()
            event.end_dates = list()

            if google_event["start"].get("dateTime", None):
                start_date_with_tz = dateutil.parser.parse(google_event["start"]["dateTime"])
                end_date_with_tz = dateutil.parser.parse(google_event["end"]["dateTime"])

                day_difference = abs((end_date_with_tz - start_date_with_tz).days)
                if day_difference == 0:
                    start_epoch = get_epoch_from_datetime(datetime(start_date_with_tz.year, start_date_with_tz.month, start_date_with_tz.day, start_date_with_tz.hour, start_date_with_tz.minute))
                    event.start_dates.append(start_epoch)
                    end_epoch = get_epoch_from_datetime(datetime(end_date_with_tz.year, end_date_with_tz.month, end_date_with_tz.day, end_date_with_tz.hour, end_date_with_tz.minute))
                    end_date = datetime.fromtimestamp(end_epoch)
                    event.end_dates.append(int(timedelta(hours=end_date.hour, minutes=end_date.minute, seconds=end_date.second).total_seconds()))
# TODO: multi day event
#                 else:
#                     start_date = datetime.strptime(google_event["start"]["date"], '%Y-%m-%d')
#                     end_date = datetime.strptime(google_event["end"]["date"], '%Y-%m-%d')
#                     day_difference = abs((end_date - start_date).days)

            if event.start_dates:
                event.first_start_date = event.start_dates[0]
                event.last_start_date = event.start_dates[-1]
                to_put.append(event)
            else:
                logging.info("Skipping event because it had no start_dates")
                logging.debug(google_event)
        except:
            logging.warn('Failed to put Google Event: %s', google_event)
            raise

    if to_put:
        db.put(to_put)

    if google_calendar_finished:
        def trans():
            scgs = SolutionCalendarGoogleSync.get_by_key_name(service_user.email())
            if not scgs:
                return True  # update was run from saving a calendar
            if calendar_str_key in scgs.google_calendar_keys:
                scgs.google_calendar_keys.remove(calendar_str_key)
                if not scgs.google_calendar_keys:
                    scgs.delete()
                    return True
                scgs.put()
                return False

        if db.run_in_transaction(trans):
            from solutions.common.bizz.provisioning import populate_identity_and_publish
            sln_settings = get_solution_settings(service_user)
            sln_main_branding = get_solution_main_branding(service_user)
            deferred.defer(populate_identity_and_publish, sln_settings, sln_main_branding.branding_key)

@returns([Event])
@arguments(service_user=users.User, translate=FunctionType, solution=unicode)
def _put_default_event(service_user, translate, solution):
    event = Event(parent=parent_key(service_user, solution))

    now = time.mktime(date.timetuple(date.today()))
    event.title = u"Title"
    event.place = u"Place"
    event.description = u"Description"
    event.last_start_date = long(now + 7 * 24 * 60 * 60 + 20 * 60 * 60)
    event.start_dates = [event.last_start_date]
    event.end_dates = [long(4 * 60 * 60)]
    event.first_start_date = event.get_first_event_date()

    event.put()
    event2 = Event(parent=parent_key(service_user, solution))
    event2.title = u"Title2"
    event2.place = u"Place2"
    event2.description = u"Description2"
    event2.last_start_date = long(now + 14 * 24 * 60 * 60 + 20 * 60 * 60)
    event2.start_dates = [event2.last_start_date]
    event2.end_dates = [long(4 * 60 * 60)]
    event2.first_start_date = event2.get_first_event_date()

    event2.put()
    return [event, event2]

@returns(NoneType)
@arguments(service_user=users.User, new_event=EventItemTO)
def put_event(service_user, new_event):
    sln_settings = get_solution_settings(service_user)

    if not new_event.end_dates:
        sln_settings = get_solution_settings(service_user)
        raise BusinessException(common_translate(sln_settings.main_language, SOLUTION_COMMON, 'event-date-required'))

    if not new_event.title:
        sln_settings = get_solution_settings(service_user)
        raise BusinessException(common_translate(sln_settings.main_language, SOLUTION_COMMON, 'Title is required'))

    if new_event.external_link == MISSING:
        new_event.external_link = None

    if new_event.external_link:
        from solutions.common.bizz.messaging import validate_broadcast_url

        new_event.external_link = new_event.external_link.strip()
        if new_event.external_link:
            if not (new_event.external_link.startswith("http://") or new_event.external_link.startswith("https://")):
                new_event.external_link = "http://%s" % new_event.external_link
            validate_broadcast_url(new_event.external_link, sln_settings.main_language)
        else:
            new_event.external_link = None

    picture = new_event.picture
    if picture:
        picture = str(picture)
        meta, img_b64 = picture.split(',')
        img_str = base64.b64decode(img_b64)

        previous_len_img = len(img_b64)
        while len(img_b64) > 512 * 1024:
            img = images.Image(img_str)
            img.im_feeling_lucky()
            img_str = img.execute_transforms(output_encoding=images.JPEG)  # Reduces quality to 85%
            img_b64 = base64.b64encode(img_str)
            meta = "data:image/jpg;base64"

            if previous_len_img <= len(img_b64):
                break
            previous_len_img = len(img_b64)

        picture = "%s,%s" % (meta, img_b64)
    else:
        picture = None

    def trans():
        if new_event.id:
            event = get_event_by_id(service_user, sln_settings.solution, new_event.id)
            if new_event.new_picture:
                event.picture_version += 1
        else:
            event = Event(parent=parent_key(service_user, sln_settings.solution))
            event.picture_version = 0

        event.title = new_event.title
        event.place = new_event.place
        event.organizer = new_event.organizer
        event.description = new_event.description
        start_dates = []
        for start_date in new_event.start_dates:
            start_dates.append(start_date.toEpoch())

        start_dates_sorted, end_dates_sorted = zip(*sorted(zip(start_dates, new_event.end_dates)))
        startDates = list(start_dates_sorted)
        new_event.end_dates = list(end_dates_sorted)

        event.last_start_date = max(startDates)
        event.start_dates = start_dates
        event.end_dates = new_event.end_dates
        event.first_start_date = event.get_first_event_date()
        event.url = new_event.external_link
        event.picture = picture
        event.calendar_id = new_event.calendar_id
        sln_settings.updates_pending = True
        put_and_invalidate_cache(event, sln_settings)
        return sln_settings

    xg_on = db.create_transaction_options(xg=True)
    sln_settings = db.run_in_transaction_options(xg_on, trans)
    broadcast_updates_pending(sln_settings)


@returns(NoneType)
@arguments(service_user=users.User, event_id=(int, long))
def delete_event(service_user, event_id):
    def trans():
        settings = get_solution_settings(service_user)
        event = get_event_by_id(service_user, settings.solution, event_id)
        if event:
            if event.source == Event.SOURCE_CMS:
                event.delete()
            else:
                event.deleted = True
                event.put()
            settings.updates_pending = True
            put_and_invalidate_cache(settings)
        return settings

    xg_on = db.create_transaction_options(xg=True)
    settings = db.run_in_transaction_options(xg_on, trans)
    broadcast_updates_pending(settings)


@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_remind_event(service_user, email, method, params, tag, service_identity, user_details):
    settings = get_solution_settings(service_user)
    jsondata = json.loads(params)

    app_user = create_app_user_by_email(email, user_details[0].app_id)
    event_id = long(jsondata['eventId'])
    remind_before = int(jsondata['remindBefore'])
    if jsondata.get("eventStartEpoch", None):
        event_start_epoch = int(jsondata['eventStartEpoch'])
    else:
        event_start_epoch = get_event_by_id(service_user, settings.solution, event_id).start_dates[0]

    r = SendApiCallCallbackResultTO()
    if is_reminder_set(app_user, event_id, event_start_epoch, remind_before) is False:
        er = EventReminder()
        er.service_identity_user = create_service_identity_user(users.get_current_user(), service_identity)
        er.human_user = app_user
        er.remind_before = remind_before
        er.event_id = event_id
        er.event_start_epoch = event_start_epoch
        er.put()
        r.result = u"successfully reminded"
    else:
        r.result = u"already reminded"
    r.error = None
    return r


@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_add_to_calender_event(service_user, email, method, params, tag, service_identity, user_details):
    rogerthat_settings = get_server_settings()
    settings = get_solution_settings(service_user)
    service_name = settings.name

    app = get_app_by_id(user_details[0].app_id)

    jsondata = json.loads(params)
    emailSubject = "Event:  %s" % jsondata['eventTitle']
    if jsondata['eventPlace']:
        eventPlace = "Place: %s " % jsondata['eventPlace']
    else:
        eventPlace = ''
    emailBody = u"Title: %s \nDate: %s \nDescription: %s \n%s \n" % (jsondata['eventTitle'], jsondata['eventDate'], jsondata['eventDescription'], eventPlace)

    cal = Calendar()
    cal.add('prodid', '-//My calendar product//mxm.dk//')
    cal.add('version', '2.0')
    cal.add('method', 'REQUEST')
    event = ICalenderEvent()
    event.add('summary', jsondata['eventTitle'])
    event.add('description', jsondata['eventDescription'])
    event.add('location', jsondata['eventPlace'])
    startDate = datetime.utcfromtimestamp(int(jsondata['eventStart']))

    try:
        endDate = datetime.utcfromtimestamp(int(jsondata['eventEnd']))
    except TypeError:
        endDate = None

    nowDate = datetime.utcfromtimestamp(time.time())
    dtstart = datetime(startDate.year, startDate.month, startDate.day, startDate.hour, startDate.minute , startDate.second, tzinfo=pytz.utc)
    dtstamp = datetime(nowDate.year, nowDate.month, nowDate.day, nowDate.hour, nowDate.minute , nowDate.second, tzinfo=pytz.utc)
    event.add('dtstart', dtstart)
    if endDate:
        dtend = datetime(endDate.year, endDate.month, endDate.day, endDate.hour, endDate.minute , endDate.second, tzinfo=pytz.utc)
        event.add('dtend', dtend)
    event.add('dtstamp', dtstamp)

    event.add('uid', "%s %s" % (app.dashboard_email_address, jsondata['eventId']))

    organizer = vCalAddress('MAILTO:%s' % app.dashboard_email_address)
    organizer.params['cn'] = vText(service_name)
    event.add('organizer', organizer)

    cal.add_component(event)
    icall = cal.to_ical()

    attachments = []
    attachments.append(("event.ics",
                        base64.b64encode(icall)))

    from_ = rogerthat_settings.senderEmail if app.type == App.APP_TYPE_ROGERTHAT else ("%s <%s>" % (app.name, app.dashboard_email_address))
    send_mail(from_, email, emailSubject, emailBody, attachments=attachments)

    r = SendApiCallCallbackResultTO()
    r.result = u"successfully reminded"
    r.error = None
    return r


@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_event_remove(service_user, email, method, params, tag, service_identity, user_details):
    sln_settings = get_solution_settings(service_user)

    jsondata = json.loads(params)

    event_id = long(jsondata['eventId'])

    event = get_event_by_id(service_user, sln_settings.solution, event_id)
    r = SendApiCallCallbackResultTO()
    if event:
        event.deleted = True
        event.put()
        common_provision(service_user)
        r.result = u"Succesfully removed event"
    else:
        r.result = u"Event not found. Remove failed"
    r.error = None
    return r


def _send_event_notification(sln_settings, service_user, service_identity, user_details, event, event_guest):
    from solutions.common.bizz.messaging import send_inbox_forwarders_message

    status = translate(sln_settings.main_language, SOLUTION_COMMON, event_guest.status_str)
    status_message = translate(sln_settings.main_language, SOLUTION_COMMON, u'events_status_notification', status=status, event=event.title)

    create_chat = True
    if event_guest.chat_key:
        create_chat = SolutionInboxMessage.get(event_guest.chat_key) is None

    if create_chat:
        event_key = unicode(event.key())
        message = create_solution_inbox_message(service_user, service_identity,
                                                SolutionInboxMessage.CATEGORY_AGENDA,
                                                event_key, False, user_details, now(), status_message, True)
        event_guest.chat_key = message.solution_inbox_message_key
        event_guest.put()

        app_user = user_details[0].toAppUser()
    else:
        message, _ = add_solution_inbox_message(service_user, event_guest.chat_key, False,
                                                    user_details, now(), status_message)
        app_user = None

    send_inbox_forwarders_message(service_user, service_identity, app_user, status_message, {
            'if_name': user_details[0].name,
            'if_email':user_details[0].email
        }, message_key=message.solution_inbox_message_key, reply_enabled=message.reply_enabled, send_reminder=False)

    # show as last message
    sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
    message_to = SolutionInboxMessageTO.fromModel(message, sln_settings, sln_i_settings, True)
    send_message(service_user, u'solutions.common.messaging.update',
                 service_identity=service_identity,
                 message=serialize_complex_value(message_to, SolutionInboxMessageTO, False))


@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_event_guest_status(service_user, email, method, params, tag, service_identity, user_details):
    sln_settings = get_solution_settings(service_user)
    app_user = create_app_user_by_email(email, user_details[0].app_id)

    jsondata = json.loads(params)
    event_id = long(jsondata['eventId'])
    status = int(jsondata['status'])

    event = get_event_by_id(service_user, sln_settings.solution, event_id)
    r = SendApiCallCallbackResultTO()
    if event:
        eg_key = EventGuest.createKey(app_user, event.key())
        eg = EventGuest.get(eg_key)
        if not eg:
            eg = EventGuest(key=eg_key)
        eg.guest = SolutionUser.fromTO(user_details[0])
        eg.status = status
        eg.timestamp = now()
        eg.put()
        r.result = u"Succesfully update event status"

        if sln_settings.event_notifications_enabled and (eg.status == EventGuest.STATUS_GOING or eg.chat_key):
            _send_event_notification(sln_settings, service_user, service_identity, user_details,
                                     event=event, event_guest=eg)
    else:
        r.result = u"Event not found. Update status failed."
    r.error = None
    return r


@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_event_guests(service_user, email, method, params, tag, service_identity, user_details):
    sln_settings = get_solution_settings(service_user)
    app_user = create_app_user_by_email(email, user_details[0].app_id)

    jsondata = json.loads(params)
    event_id = long(jsondata['eventId'])
    include_details = int(jsondata['includeDetails'])

    event = get_event_by_id(service_user, sln_settings.solution, event_id)
    r = SendApiCallCallbackResultTO()
    if event:
        your_status = None
        eg = db.get(EventGuest.createKey(app_user, event.key()))
        if eg:
            your_status = eg.status

        guests = []
        if include_details == 1:
            for guest in event.guests:
                guests.append(EventGuestTO.fromEventGuest(guest))

        r.result = json.dumps(dict(event_id=event_id,
                                           include_details=include_details,
                                           guests_count_going=event.guests_count(EventGuest.STATUS_GOING),
                                           guests_count_maybe=event.guests_count(EventGuest.STATUS_MAYBE),
                                           guests_count_not_going=event.guests_count(EventGuest.STATUS_NOT_GOING),
                                           guests=serialize_complex_value(guests, EventGuestTO, True),
                                           your_status=your_status)).decode('utf8')
        r.error = None
    else:
        r.result = None
        r.error = u"Event not found"
    return r


@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_calendar_broadcast(service_user, email, method, params, tag, service_identity, user_details):
    from solutions.common.bizz.messaging import broadcast_send
    sln_settings = get_solution_settings(service_user)

    jsondata = json.loads(params)

    calendar_id = long(jsondata['calendarId'])
    message = jsondata['message']

    sc = SolutionCalendar.get_by_id(calendar_id, parent_key(service_user, sln_settings.solution))
    r = SendApiCallCallbackResultTO()
    if sc:
        broadcast_type = translate(sln_settings.main_language, SOLUTION_COMMON, u'calendar-broadcast-type',
                                   name=sc.name)
        broadcast_send(service_user, service_identity, broadcast_type, message, broadcast_on_facebook=False, broadcast_on_twitter=False, broadcast_to_all_locations=True)
        r.result = u"successfully broadcast"
    else:
        r.result = u"Calendar not found. Broadcast failed."
    r.error = None
    return r


@returns(SolutionCalendarAdmin)
@arguments(calendar_id=long, app_user=users.User, service_user=users.User, solution=unicode)
def create_calendar_admin(calendar_id, app_user, service_user, solution):
    """Create calendar admin and assign create events role."""
    from solutions.common.bizz.messaging import POKE_TAG_NEW_EVENT
    sc = SolutionCalendar.get_by_id(calendar_id, parent_key(service_user, solution))
    if sc:
        key = SolutionCalendarAdmin.createKey(app_user, sc.key())
        sca = db.get(key)
        if not sca:
            sca = SolutionCalendarAdmin(key=key)
        sca.app_user = app_user
        db.put(sca)
        assign_app_user_role(app_user, POKE_TAG_NEW_EVENT)
        return sca


@returns()
@arguments(calendar_id=long, app_user=users.User, service_user=users.User, solution=unicode)
def delete_calendar_admin(calendar_id, app_user, service_user, solution):
    """Delete a calendar admin and revoke create events role."""
    from solutions.common.bizz.messaging import POKE_TAG_NEW_EVENT
    sc = SolutionCalendar.get_by_id(calendar_id, parent_key(service_user, solution))
    if sc:
        key = SolutionCalendarAdmin.createKey(app_user, sc.key())
        sca = db.get(key)
        if sca:
            db.delete(sca)

    # check if the user is an admin of any other calendar
    # if not, just revoke the role
    other_calendars = get_solution_calendar_ids_for_user(service_user, solution,
                                                         app_user)

    if not other_calendars:
        revoke_app_user_role(app_user, POKE_TAG_NEW_EVENT)


@returns(PokeCallbackResultTO)
@arguments(service_user=users.User, email=unicode, tag=unicode, result_key=unicode, context=unicode,
           service_identity=unicode, user_details=[UserDetailsTO])
def solution_add_admin_to_calendar(service_user, email, tag, result_key, context, service_identity, user_details):
    from solutions.common.bizz.messaging import POKE_TAG_EVENTS_CONNECT_VIA_SCAN
    info = json.loads(tag[len(POKE_TAG_EVENTS_CONNECT_VIA_SCAN):])
    calendar_id = info.get("calendar_id")
    if not calendar_id:
        return

    sln_settings = get_solution_settings(service_user)
    app_user = user_details[0].toAppUser()
    create_calendar_admin(calendar_id, app_user, service_user, sln_settings.solution)
    send_message(service_user, u"solutions.common.calendar.update")


@returns(PokeCallbackResultTO)
@arguments(service_user=users.User, email=unicode, tag=unicode, result_key=unicode, context=unicode,
           service_identity=unicode, user_details=[UserDetailsTO])
def poke_new_event(service_user, email, tag, result_key, context, service_identity, user_details):
    from solutions.common.bizz.messaging import POKE_TAG_NEW_EVENT

    sln_settings = get_solution_settings(service_user)
    app_user = user_details[0].toAppUser()

    result = PokeCallbackResultTO()
    result.type = TYPE_FLOW
    result.value = FlowCallbackResultTypeTO()
    result.value.flow = get_create_event_flow_xml_for_user(sln_settings, app_user)
    result.value.force_language = None
    result.value.tag = POKE_TAG_NEW_EVENT
    return result

@returns(FlowMemberResultCallbackResultTO)
@arguments(service_user=users.User, message_flow_run_id=unicode, member=unicode,
           steps=[object_factory("step_type", FLOW_STEP_MAPPING)], end_id=unicode, end_message_flow_id=unicode,
           parent_message_key=unicode, tag=unicode, result_key=unicode, flush_id=unicode, flush_message_flow_id=unicode,
           service_identity=unicode, user_details=[UserDetailsTO])
def new_event_received(service_user, message_flow_run_id, member, steps, end_id, end_message_flow_id, parent_message_key,
                   tag, result_key, flush_id, flush_message_flow_id, service_identity, user_details):
    from solutions.common.bizz.messaging import _get_step_with_id

    logging.info("_flow_member_result_new_event: \n %s" % steps)

    calendar = _get_step_with_id(steps, 'message_calendar')

    title = _get_step_with_id(steps, 'message_title')
    if not title:
        logging.error("Did not find step with id 'title'. Can not process message_flow_member_result with tag %s" % tag)
        return None

    date_ = _get_step_with_id(steps, 'message_date')
    if not date_:
        logging.error("Did not find step with id 'date'. Can not process message_flow_member_result with tag %s" % tag)
        return None

    start_time = _get_step_with_id(steps, 'message_start_time')
    if not start_time:
        logging.error("Did not find step with id 'start_time'. Can not process message_flow_member_result with tag %s" % tag)
        return None

    end_time = _get_step_with_id(steps, 'message_end_time')
    if not end_time:
        logging.error("Did not find step with id 'end_time'. Can not process message_flow_member_result with tag %s" % tag)
        return None

    description = _get_step_with_id(steps, 'message_description')
    if not description:
        logging.error("Did not find step with id 'description'. Can not process message_flow_member_result with tag %s" % tag)
        return None

    place = _get_step_with_id(steps, 'message_place')
    if not place:
        logging.error("Did not find step with id 'place'. Can not process message_flow_member_result with tag %s" % tag)
        return None

    photo = _get_step_with_id(steps, 'message_photo')
    if not photo:
        logging.error("Did not find step with id 'photo'. Can not process message_flow_member_result with tag %s" % tag)
        return None

    sln_settings = get_solution_settings(service_user)
    app_user = user_details[0].toAppUser()
    calendars_ids_admin = get_solution_calendar_ids_for_user(service_user, sln_settings.solution, app_user)

    if len(calendars_ids_admin) == 0:
        logging.warn("User %s isn't a calendar admin anymore" % app_user.email())
        return None

    calendar_id = None
    if calendar and calendar.form_result.result:
        calendar_id = long(calendar.form_result.result.value)
    else:
        if sln_settings.default_calendar in calendars_ids_admin:
            calendar_id = sln_settings.default_calendar
        else:
            calendar_id = calendars_ids_admin[0]

    sc = SolutionCalendar.get_by_id(calendar_id, parent_key(service_user, sln_settings.solution))
    if not sc:
        logging.warn("Calendar %s does not exists anymore" % calendar_id)
        return None

    event = Event(parent=parent_key(service_user, sln_settings.solution))
    event.picture_version = 0
    event.title = title.form_result.result.value
    event.place = place.form_result.result.value
    event.description = description.form_result.result.value

    start_date = get_epoch_from_datetime(datetime.fromtimestamp(date_.form_result.result.value).date()) + start_time.form_result.result.value
    event.last_start_date = start_date
    event.start_dates = [start_date]
    event.end_dates = [end_time.form_result.result.value]
    event.first_start_date = event.get_first_event_date()
    event.calendar_id = calendar_id
    if photo.form_result:
        result = urlfetch.fetch(photo.form_result.result.value, {}, "GET", {}, False, False, deadline=10 * 60)
        if result.status_code != 200:
            logging.error("Failed to download photo upload for new event whith link: %s" % photo.form_result.result)
            picture = None
        else:
            img_str = result.content
            img_b64 = base64.b64encode(img_str)

            previous_len_img = len(img_b64)
            while len(img_b64) > 512 * 1024:
                img = images.Image(img_str)
                img.im_feeling_lucky()
                img_str = img.execute_transforms(output_encoding=images.JPEG)  # Reduces quality to 85%
                img_b64 = base64.b64encode(img_str)

                if previous_len_img <= len(img_b64):
                    break
                previous_len_img = len(img_b64)

            picture = "data:image/jpg;base64,%s" % img_b64
    else:
        picture = None
    event.picture = picture
    event.put()

    send_message(service_user, u"solutions.common.calendar.update")
    deferred.defer(common_provision, service_user)
    return None


def get_branding_resource(filename):
    path = os.path.join(os.path.dirname(solutions.__file__),
                        'common', 'templates', 'brandings',
                        filename)
    return file_get_contents(path)


def provision_events_branding(solution_settings, main_branding, language):
    """
    Args:
        solution_settings (SolutionSettings)
        main_branding (solutions.common.models.SolutionMainBranding)
        language (unicode)
    """
    if not solution_settings.events_branding_hash:
        logging.info("Storing EVENTS branding")
        stream = ZipFile(StringIO(main_branding.blob))
        try:
            new_zip_stream = StringIO()
            zip_ = ZipFile(new_zip_stream, 'w', compression=ZIP_DEFLATED)
            try:
                zip_.writestr("jquery.tmpl.min.js", get_branding_resource("app_jquery.tmpl.js"))
                zip_.writestr("moment-with-locales.min.js", get_branding_resource("moment-with-locales.min.js"))
                zip_.writestr("app-translations.js", JINJA_ENVIRONMENT.get_template("brandings/app_events_translations.js").render({'language': language}).encode("utf-8"))
                zip_.writestr("app.js", '\n\n'.join(map(get_branding_resource, ["app_polyfills.js", "app_events.js"])))

                for file_name in set(stream.namelist()):
                    str_ = stream.read(file_name)
                    if file_name == 'branding.html':
                        html_ = str_
                        # Remove previously added dimensions:
                        html_ = re.sub("<meta\\s+property=\\\"rt:dimensions\\\"\\s+content=\\\"\\[\\d+,\\d+,\\d+,\\d+\\]\\\"\\s*/>", "", html_)
                        html_ = re.sub('<head>', """<head>
<link href="jquery/jquery.mobile.inline-png-1.4.2.min.css" rel="stylesheet" media="screen"/>
<style type="text/css">
div.backgoundLight{background: url("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH3gEYDyEEzIMX+AAAACZpVFh0Q29tbWVudAAAAAAAQ3JlYXRlZCB3aXRoIEdJTVAgb24gYSBNYWOV5F9bAAAADUlEQVQI12NgYGCQBAAAHgAaOwrXiAAAAABJRU5ErkJggg==");}
div.backgoundDark{background: url("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH3gEYDyIY868YdAAAACZpVFh0Q29tbWVudAAAAAAAQ3JlYXRlZCB3aXRoIEdJTVAgb24gYSBNYWOV5F9bAAAADUlEQVQI12P4//+/JAAJFQMXEGL3cQAAAABJRU5ErkJggg==");}
</style>
<script type="text/javascript" src="jquery/jquery-1.11.0.min.js">
</script>
<script type="text/javascript" src="jquery/jquery.mobile-1.4.2.min.js">
</script>
<script type="text/javascript" src="jquery.tmpl.min.js">
</script>
<script type="text/javascript" src="moment-with-locales.min.js">
</script>
<script type="text/javascript" src="rogerthat/rogerthat-1.0.js">
</script>
<script type="text/javascript" src="rogerthat/rogerthat.api-1.0.js">
</script>
<script type="text/javascript" src="app-translations.js">
</script>
<script type="text/javascript" src="app.js">
</script>
""", html_)

                        doc = html.fromstring(html_)
                        h = doc.find('./head')

                        html__ = """<!DOCTYPE html>
<html>"""
                        html__ += etree.tostring(h)
                        html__ += render_common_content(language, 'brandings/events.tmpl', {})
                        html__ += "</html>"
                        zip_.writestr('app.html', html__.encode('utf8'))
                    else:
                        zip_.writestr(file_name, str_)
            finally:
                zip_.close()

            events_branding_content = new_zip_stream.getvalue()
            new_zip_stream.close()

            solution_settings.events_branding_hash = put_branding(u"Events App", base64.b64encode(events_branding_content)).id
            solution_settings.put()
        finally:
            stream.close()


@returns(unicode)
@arguments(app_user=users.User)
def get_create_event_flow_name(app_user):
    return u'agenda.new_event %s' % app_user.email()

def get_create_event_flow_xml_for_user(sln_settings, app_user):
    flow_name = get_create_event_flow_name(app_user)

    main_branding = get_solution_main_branding(sln_settings.service_user)
    calendars_admin = get_solution_calendars_for_user(sln_settings.service_user, sln_settings.solution, app_user)

    calendar_count = sum(1 for _ in calendars_admin)

    flow_params = dict(flow_name=flow_name, branding_key=main_branding.branding_key, language=sln_settings.main_language or DEFAULT_LANGUAGE, name=sln_settings.name, calendar_count=calendar_count, calendars=calendars_admin)
    flow = JINJA_ENVIRONMENT.get_template('flows/events_create.xml').render(flow_params)
    return flow

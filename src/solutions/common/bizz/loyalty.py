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
from datetime import datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import json
import logging
import os
import re
import time
from types import NoneType
import uuid
from zipfile import ZipFile, ZIP_DEFLATED

from PIL.Image import Image
from babel import Locale
from babel.dates import format_date, format_datetime, get_timezone
from lxml import etree, html
import pytz

from google.appengine.ext import deferred, db
from mcfw.properties import azzert
from mcfw.rpc import returns, arguments, serialize_complex_value
from rogerthat.bizz.friends import ACCEPT_AND_CONNECT_ID
from rogerthat.bizz.job import run_job
from rogerthat.bizz.rtemail import generate_user_specific_link, EMAIL_REGEX
from rogerthat.bizz.service import get_and_validate_service_identity_user
from rogerthat.dal import put_and_invalidate_cache, parent_key_unsafe
from rogerthat.dal.app import get_app_by_id
from rogerthat.dal.profile import get_profile_infos, get_user_profile
from rogerthat.models import Message, App
from rogerthat.rpc import users
from rogerthat.rpc.service import BusinessException
from rogerthat.service.api import messaging, friends, app, system
from rogerthat.settings import get_server_settings
from rogerthat.to.messaging import MemberTO, AnswerTO
from rogerthat.to.service import UserDetailsTO, SendApiCallCallbackResultTO
from rogerthat.utils import now, file_get_contents, is_flag_set, send_mail_via_mime, format_price, today, send_mail
from rogerthat.utils.app import create_app_user_by_email, get_app_user_tuple_by_email, get_app_user_tuple, \
    get_human_user_from_app_user
from rogerthat.utils.channel import send_message
from shop.constants import LOGO_LANGUAGES, STORE_MANAGER
from shop.dal import get_shop_loyalty_slides, get_customer
from shop.models import ShopLoyaltySlideNewOrder, Customer, Contact, RegioManagerTeam, Prospect, ShopTask
from solutions import translate as common_translate
import solutions
from solutions.common import SOLUTION_COMMON
from solutions.common.bizz import render_common_content, SolutionModule, put_branding
from solutions.common.dal import get_solution_main_branding, get_solution_settings, count_unread_solution_inbox_messages, \
    get_solution_settings_or_identity_settings
from solutions.common.dal.loyalty import get_solution_loyalty_slides, get_solution_loyalty_visits_for_revenue_discount, \
    get_solution_loyalty_visits_for_stamps, get_solution_loyalty_settings_or_identity_settings
from solutions.common.models import SolutionBrandingSettings, SolutionInboxMessage
from solutions.common.models.loyalty import SolutionLoyaltySlide, SolutionLoyaltySettings, \
    SolutionLoyaltyVisitRevenueDiscount, SolutionUserLoyaltySettings, SolutionLoyaltyScan, SolutionLoyaltyVisitLottery, \
    SolutionLoyaltyLottery, SolutionLoyaltyLotteryStatistics, SolutionLoyaltyVisitStamps, \
    SolutionLoyaltyVisitRevenueDiscountArchive, SolutionLoyaltyVisitLotteryArchive, SolutionLoyaltyVisitStampsArchive, \
    SolutionLoyaltyExport, SolutionLoyaltyIdentitySettings, SolutionCityWideLotteryVisit, \
    SolutionCityWideLotteryStatistics, CustomLoyaltyCard, CityPostalCodes
from solutions.common.models.news import NewsCoupon
from solutions.common.models.properties import SolutionUser
from solutions.common.to import TimestampTO, SolutionInboxMessageTO
from solutions.common.to.loyalty import LoyaltySlideTO, SolutionLoyaltyVisitTO, LoyaltySlideNewOrderTO
from solutions.common.utils import is_default_service_identity, create_service_identity_user_wo_default
from xhtml2pdf import pisa


try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


API_METHOD_SOLUTION_LOYALTY_LOAD = "solutions.loyalty.load"
API_METHOD_SOLUTION_LOYALTY_SCAN = "solutions.loyalty.scan"
API_METHOD_SOLUTION_LOYALTY_PUT = "solutions.loyalty.put"
API_METHOD_SOLUTION_LOYALTY_REDEEM = "solutions.loyalty.redeem"
API_METHOD_SOLUTION_LOYALTY_LOTTERY_CHANCE = "solutions.loyalty.lottery.chance"
API_METHOD_SOLUTION_LOYALTY_COUPLE = "solutions.loyalty.couple"
API_METHOD_SOLUTION_VOUCHER_RESOLVE = "solutions.voucher.resolve"
API_METHOD_SOLUTION_VOUCHER_PIN_ACTIVATE = "solutions.voucher.activate.pin"
API_METHOD_SOLUTION_VOUCHER_ACTIVATE = "solutions.voucher.activate"
API_METHOD_SOLUTION_VOUCHER_REDEEM = "solutions.voucher.redeem"
API_METHOD_SOLUTION_VOUCHER_CONFIRM_REDEEM = "solutions.voucher.redeem.confirm"


@returns(dict)
@arguments(service_user=users.User, service_identity=unicode, loyalty_type=(int, long))
def get_user_data_admins(service_user, service_identity, loyalty_type):
    users.set_user(service_user)
    try:
        si = system.get_identity(service_identity)
    finally:
        users.clear_user()
    user_data = {}
    user_data["loyalty"] = {}
    user_data["loyalty"]["uuid"] = uuid.uuid4().get_hex()

    slides = [LoyaltySlideTO.fromSolutionLoyaltySlideObject(c, show_footer=False) for c in get_shop_loyalty_slides(si.app_ids[0])]
    slides.extend([LoyaltySlideTO.fromSolutionLoyaltySlideObject(c) for c in get_solution_loyalty_slides(service_user, service_identity)])
    user_data["loyalty"]["slides"] = serialize_complex_value(slides, LoyaltySlideTO, True)
    user_data["loyalty"]["inbox_unread_count"] = count_unread_solution_inbox_messages(service_user, service_identity)

    slide_new_order = ShopLoyaltySlideNewOrder.get(ShopLoyaltySlideNewOrder.create_key(si.app_ids[0]))
    user_data["loyalty"]["slide_new_order"] = serialize_complex_value(LoyaltySlideNewOrderTO.fromSlideObject(slide_new_order), LoyaltySlideNewOrderTO, False) if slide_new_order else None

    user_data["loyalty_2"] = {}
    user_data["loyalty_2"]["winners"] = []
    for ll_info in SolutionLoyaltyLottery.load_active(service_user, service_identity):
        if ll_info.winner_info:
            user_data["loyalty_2"]["winners"].append({"key": str(ll_info.key()),
                                                      "date": serialize_complex_value(TimestampTO.fromEpoch(ll_info.end_timestamp), TimestampTO, False),
                                                      "user_details": serialize_complex_value(ll_info.winner_info, SolutionUser, False),
                                                      "winnings": ll_info.winnings})

    return user_data

@returns()
@arguments(app_ids=[unicode])
def update_all_user_data_admins(app_ids):
    run_job(_get_loyalty_settings, [], _update_all_user_data_admin_ss, [app_ids])

def _get_loyalty_settings():
    return SolutionLoyaltySettings.all(keys_only=True)

@returns()
@arguments(loyalty_settings_key=db.Key, app_ids=[unicode])
def _update_all_user_data_admin_ss(loyalty_settings_key, app_ids):
    service_user = users.User(loyalty_settings_key.parent().name())
    sln_settings = get_solution_settings(service_user)
    identities = [None]
    if sln_settings.identities:
        identities.extend(sln_settings.identities)
    for service_identity in identities:
        users.set_user(service_user)
        try:
            si = system.get_identity(service_identity)
            should_update = True
            if app_ids:
                should_update = False
                matched_app_ids = [app_id for app_id in app_ids if app_id in si.app_ids]
                if matched_app_ids:
                    should_update = True

            if should_update:
                update_user_data_admins(service_user, service_identity)
        finally:
            users.clear_user()

@returns()
@arguments(service_user=users.User, service_identity=unicode)
def update_user_data_admins(service_user, service_identity):

    def trans():
        sln_l_settings = SolutionLoyaltySettings.get_by_user(service_user)
        if sln_l_settings:
            sln_li_settings = get_solution_loyalty_settings_or_identity_settings(sln_l_settings, service_identity)
            return sln_l_settings.loyalty_type, sln_li_settings.admins, sln_li_settings.app_ids, sln_li_settings.names, sln_li_settings.functions
        return SolutionLoyaltySettings.LOYALTY_TYPE_REVENUE_DISCOUNT, [], [], [], []

    xg_on = db.create_transaction_options(xg=True)
    loyalty_type, admins, app_ids, names, functions = db.run_in_transaction_options(xg_on, trans)

    if admins:
        user_data = get_user_data_admins(service_user, service_identity, loyalty_type)
        slides_backup = [slide for slide in user_data["loyalty"]["slides"]]
        users.set_user(service_user)
        try:
            for i, admin in enumerate(admins):
                user_data["loyalty"]["name"] = names[i]
                user_data["loyalty"]["functions"] = functions[i]
                user_data["loyalty"]["slides"] = []
                for slide in slides_backup:
                    if slide["function_dependencies"]:
                        if is_flag_set(slide["function_dependencies"], functions[i]):
                            user_data["loyalty"]["slides"].append(slide)
                    else:
                        user_data["loyalty"]["slides"].append(slide)

                system.put_user_data(admin, json.dumps(user_data), service_identity, app_ids[i])
        finally:
            users.clear_user()

@returns()
@arguments(service_user=users.User, service_identity=unicode, admin=unicode, app_id=unicode)
def _update_user_data_admin(service_user, service_identity, admin, app_id):

    def trans():
        sln_l_settings = SolutionLoyaltySettings.get_by_user(service_user)
        if sln_l_settings:
            sln_li_settings = get_solution_loyalty_settings_or_identity_settings(sln_l_settings, service_identity)
            return sln_l_settings.loyalty_type, sln_li_settings.admins, sln_li_settings.names, sln_li_settings.functions
        return SolutionLoyaltySettings.LOYALTY_TYPE_REVENUE_DISCOUNT, [], [], []

    xg_on = db.create_transaction_options(xg=True)
    loyalty_type, admins, names, functions = db.run_in_transaction_options(xg_on, trans)

    if admins and admin in admins:
        user_data = get_user_data_admins(service_user, service_identity, loyalty_type)
        slides_backup = [slide for slide in user_data["loyalty"]["slides"]]
        users.set_user(service_user)
        try:
            i = admins.index(admin)
            user_data["loyalty"]["name"] = names[i]
            user_data["loyalty"]["functions"] = functions[i]
            user_data["loyalty"]["slides"] = []
            for slide in slides_backup:
                if slide["function_dependencies"]:
                    if is_flag_set(slide["function_dependencies"], functions[i]):
                        user_data["loyalty"]["slides"].append(slide)
                else:
                    user_data["loyalty"]["slides"].append(slide)
            system.put_user_data(admin, json.dumps(user_data), service_identity, app_id)
        finally:
            users.clear_user()

@returns()
@arguments(service_user=users.User, service_identity=unicode, email=unicode, app_id=unicode, loyalty_type=(int, long))
def update_user_data_user_loyalty(service_user, service_identity, email, app_id, loyalty_type=SolutionLoyaltySettings.LOYALTY_TYPE_REVENUE_DISCOUNT):
    user_data = {}
    app_user = create_app_user_by_email(email, app_id)
    user_data["loyalty"] = {}
    slvs_1 = get_solution_loyalty_visits_for_revenue_discount(service_user, service_identity, app_user)
    user_data["loyalty"]["visits"] = serialize_complex_value([SolutionLoyaltyVisitTO.fromModel(s) for s in slvs_1], SolutionLoyaltyVisitTO, True)

    user_data["loyalty_3"] = {}
    slvs_3 = get_solution_loyalty_visits_for_stamps(service_user, service_identity, app_user)
    user_data["loyalty_3"]["visits"] = serialize_complex_value([SolutionLoyaltyVisitTO.fromModel(s) for s in slvs_3], SolutionLoyaltyVisitTO, True)

    users.set_user(service_user)
    try:
        system.put_user_data(email, json.dumps(user_data), service_identity, app_id)
    finally:
        users.clear_user()

@returns()
@arguments(service_user=users.User, service_identity=unicode, slide_id=(int, long, NoneType), slide_name=unicode, slide_time=(int, long), gcs_filename=unicode, content_type=unicode)
def put_loyalty_slide(service_user, service_identity, slide_id, slide_name, slide_time, gcs_filename, content_type):
    service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
    def trans():
        p = parent_key_unsafe(service_identity_user, SOLUTION_COMMON)
        if slide_id:
            sli = SolutionLoyaltySlide.get_by_id(slide_id, parent=p)
        else:
            sli = SolutionLoyaltySlide(parent=p)
            sli.timestamp = now()

        sli.deleted = False
        sli.name = slide_name
        sli.time = slide_time
        if gcs_filename:
            sli.gcs_filename = gcs_filename
        if content_type:
            sli.content_type = content_type
        sli.put()

        deferred.defer(update_user_data_admins, service_user, service_identity, _transactional=True)

    db.run_in_transaction(trans)

@returns(NoneType)
@arguments(service_user=users.User, service_identity=unicode, slide_id=(int, long))
def delete_loyalty_slide(service_user, service_identity, slide_id):
    service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
    def trans():
        sli = SolutionLoyaltySlide.get_by_id(slide_id, parent=parent_key_unsafe(service_identity_user, SOLUTION_COMMON))
        if sli:
            sli.deleted = True
            sli.put()
            deferred.defer(update_user_data_admins, service_user, service_identity, _transactional=True)
    db.run_in_transaction(trans)

    send_message(service_user, u"solutions.common.loyalty.items.update", service_identity=service_identity)


@returns(NoneType)
@arguments(service_user=users.User, service_identity=unicode, admin_app_user_email=unicode)
def delete_loyalty_admin(service_user, service_identity, admin_app_user_email):
    from rogerthat.bizz.user import delete_account

    def trans():
        if is_default_service_identity(service_identity):
            sln_l_settings = SolutionLoyaltySettings.get_by_user(service_user)
        else:
            sln_l_settings = SolutionLoyaltyIdentitySettings.get_by_user(service_user, service_identity)

        if sln_l_settings:
            admin_user, app_id = get_app_user_tuple_by_email(admin_app_user_email)
            if admin_user.email() in sln_l_settings.admins:
                i = sln_l_settings.admins.index(admin_user.email())
                azzert(sln_l_settings.app_ids[i] == app_id)
                del sln_l_settings.admins[i]
                del sln_l_settings.app_ids[i]
                del sln_l_settings.names[i]
                del sln_l_settings.functions[i]
                sln_l_settings.put()
                deferred.defer(delete_account, users.User(admin_app_user_email), _transactional=True)
    db.run_in_transaction(trans)

    send_message(service_user, u"solutions.common.loyalty.settings.update", service_identity=service_identity)


@returns(NoneType)
@arguments(service_user=users.User, service_identity=unicode, admin_app_user_email=unicode, admin_name=unicode, admin_functions=(int, long))
def update_loyalty_admin(service_user, service_identity, admin_app_user_email, admin_name, admin_functions):
    sln_settings = get_solution_settings(service_user)

    def trans():
        if is_default_service_identity(service_identity):
            loyalty_settings = SolutionLoyaltySettings.get_by_user(service_user)
        else:
            loyalty_settings = SolutionLoyaltyIdentitySettings.get_by_user(service_user, service_identity)
        if loyalty_settings:
            admin_user, app_id = get_app_user_tuple_by_email(admin_app_user_email)
            admin_user_email = admin_user.email()
            if admin_user_email in loyalty_settings.admins:
                i = loyalty_settings.admins.index(admin_user_email)
                azzert(loyalty_settings.app_ids[i] == app_id)
                loyalty_settings.names[i] = admin_name

                if admin_functions == 0:
                    raise BusinessException(common_translate(sln_settings.main_language, SOLUTION_COMMON, 'select-at-least-one-function'))
                if is_flag_set(SolutionLoyaltySettings.FUNCTION_SCAN, admin_functions) and not is_flag_set(SolutionLoyaltySettings.FUNCTION_SLIDESHOW, admin_functions):
                    raise BusinessException(common_translate(sln_settings.main_language, SOLUTION_COMMON, 'scan-requires-slideshow'))

                loyalty_settings.functions[i] = admin_functions
                loyalty_settings.put()
                deferred.defer(_update_user_data_admin, service_user, service_identity, admin_user_email, app_id, _transactional=True)
    db.run_in_transaction(trans)

    send_message(service_user, u"solutions.common.loyalty.settings.update", service_identity=service_identity)

@returns(unicode)
@arguments(service_user=users.User, user_details=[UserDetailsTO], origin=unicode, data=unicode)
def loyalty_qr_register(service_user, user_details, origin, data):
    if data is None and origin == "qr":
        def trans():
            loyalty_settings = SolutionLoyaltySettings.get_by_user(service_user)
            return loyalty_settings is not None

        if db.run_in_transaction(trans):
            return ACCEPT_AND_CONNECT_ID

    raise NotImplementedError()

@returns()
@arguments(service_user=users.User, service_identity=unicode, user_details=[UserDetailsTO], origin=unicode)
def loyalty_qr_register_result(service_user, service_identity, user_details, origin):
    if origin == "qr":
        def trans():
            if is_default_service_identity(service_identity):
                loyalty_settings = SolutionLoyaltySettings.get_by_user(service_user)
            else:
                loyalty_settings = SolutionLoyaltyIdentitySettings.get_by_user(service_user, service_identity)

            if loyalty_settings:
                if user_details[0].email not in loyalty_settings.admins:
                    loyalty_settings.admins.append(user_details[0].email)
                    loyalty_settings.app_ids.append(user_details[0].app_id)
                    old_name_index = loyalty_settings.name_index if loyalty_settings.name_index else len(loyalty_settings.admins)
                    loyalty_settings.name_index = old_name_index + 1
                    loyalty_settings.names.append("Tablet %s" % (loyalty_settings.name_index + 1))
                    loyalty_settings.functions.append(SolutionLoyaltySettings.FUNCTION_SCAN | SolutionLoyaltySettings.FUNCTION_SLIDESHOW | SolutionLoyaltySettings.FUNCTION_ADD_REDEEM_LOYALTY_POINTS)
                    loyalty_settings.put()
                    deferred.defer(_update_user_data_admin, service_user, service_identity, user_details[0].email, user_details[0].app_id, _transactional=True)
                    return True
            return False

        if db.run_in_transaction(trans):
            send_message(service_user, u"solutions.common.loyalty.settings.update", service_identity=service_identity)


@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_loyalty_load(service_user, email, method, params, tag, service_identity, user_details):
    logging.debug("Received loyalty load call with params: %s", params)
    r = SendApiCallCallbackResultTO()
    try:
        jsondata = json.loads(params)
        if jsondata.get("user_details", None):
            app_id = jsondata["user_details"]["appId"]
            user_email = jsondata["user_details"]["email"]
        else:
            app_id = jsondata['app_id']
            user_email = jsondata['email']

        app_user = create_app_user_by_email(user_email, app_id)
        loyalty_type = jsondata['loyalty_type']
        slvs = []
        success = False
        if loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_REVENUE_DISCOUNT:
            slvs = get_solution_loyalty_visits_for_revenue_discount(service_user, service_identity, app_user)
            success = True
        elif loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_LOTTERY:
            logging.error("unimplemented loyalty type %s in load, we do not need visits for lottery", loyalty_type)
            slvs = []
            success = True
        elif loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_STAMPS:
            slvs = get_solution_loyalty_visits_for_stamps(service_user, service_identity, app_user)
            success = True
        else:
            logging.error("unimplemented loyalty type %s in load", loyalty_type)

        if success:
            r.result = json.dumps(dict(app_id=app_id,
                                       email=user_email,
                                       visits=serialize_complex_value([SolutionLoyaltyVisitTO.fromModel(s) for s in slvs], SolutionLoyaltyVisitTO, True))).decode('utf8')
            r.error = None
        else:
            r.result = None
            sln_settings = get_solution_settings(service_user)
            r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON , 'error-occured-unknown-try-again')
    except:
        logging.error("solutions.loyalty.load exception occurred", exc_info=True)
        r.result = None
        sln_settings = get_solution_settings(service_user)
        r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON , 'error-occured-unknown')
    return r

def get_user_details_for_js_jsondata(service_user, service_identity, jsondata):
    if jsondata.get("url", None):
        friendTO = friends.resolve(jsondata['url'], service_identity)
        if not friendTO:
            raise BusinessException("Could not resolve url (%s) for user %s" % (jsondata['url'], service_user))

        app_id = friendTO.app_id
        user_email = friendTO.email
        user_detail = UserDetailsTO()
        user_detail.email = friendTO.email
        user_detail.name = friendTO.name
        user_detail.language = friendTO.language
        user_detail.avatar_url = friendTO.avatar
        user_detail.app_id = friendTO.app_id
    else:
        if jsondata.get("user_details", None):
            app_id = jsondata["user_details"]["appId"]
            user_email = jsondata["user_details"]["email"]
            user_detail = None
        else:
            app_id = jsondata['app_id']
            user_email = jsondata['email']
            user_detail = None

    app_user = create_app_user_by_email(user_email, app_id)
    if not user_detail:
        # XXX: don't use get_profile_infos
        profile_info = get_profile_infos([app_user], allow_none_in_results=True)[0]
        if not profile_info or profile_info.isServiceIdentity:
            user_detail = None
        else:
            user_detail = UserDetailsTO.fromUserProfile(profile_info)

    return app_user, user_detail



@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_loyalty_scan(service_user, email, method, params, tag, service_identity, user_details):
    logging.debug("Received loyalty scan call with params: %s", params)
    r = SendApiCallCallbackResultTO()
    try:
        if is_default_service_identity(service_identity):
            loyalty_settings = SolutionLoyaltySettings.get_by_user(service_user)
        else:
            loyalty_settings = SolutionLoyaltyIdentitySettings.get_by_user(service_user, service_identity)
        jsondata = json.loads(params)

        try:
            app_user, user_detail = get_user_details_for_js_jsondata(service_user, service_identity, jsondata)
        except BusinessException, be:
            r.result = None
            r.error = be.message
            return r

        now_ = jsondata.get("timestamp", now())
        sls = SolutionLoyaltyScan(key=SolutionLoyaltyScan.create_key(app_user, service_user, service_identity))
        sls.tablet_email = email
        i = loyalty_settings.admins.index(email)
        sls.tablet_app_id = loyalty_settings.app_ids[i]
        sls.tablet_name = loyalty_settings.names[i]
        sls.user_name = user_detail.name
        sls.timestamp = now_
        sls.app_user_info = SolutionUser.fromTO(user_detail) if user_detail else None
        sls.put()

        r.result = u'success'
        r.error = None

        send_message(service_user, u"solutions.common.loyalty.scan.update", service_identity=service_identity)
    except:
        logging.error("solutions.loyalty.scan exception occurred", exc_info=True)
        r.result = None
        sln_settings = get_solution_settings(service_user)
        r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON , 'error-occured-unknown')
    return r

@returns(tuple)
@arguments(service_user=users.User, service_identity=unicode, admin_user=users.User, app_user=users.User, jsondata=dict, now_=(int, long), user_detail=UserDetailsTO)
def add_loyalty_for_user(service_user, service_identity, admin_user, app_user, jsondata, now_, user_detail=None):
    loyalty_type = jsondata['loyalty_type']
    success = is_put = False
    message = visit_key = custom_error_message_key = None

    if loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_REVENUE_DISCOUNT:
        success, is_put, message, visit_key = add_loyalty_for_user_revenu_discount(service_user, service_identity, admin_user, app_user, jsondata, now_, user_detail)
    elif loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_LOTTERY:
        success, is_put, message, visit_key = add_loyalty_for_user_lottery(service_user, service_identity, admin_user, app_user, jsondata, now_, user_detail)
    elif loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_STAMPS:
        success, is_put, message, visit_key = add_loyalty_for_user_stamps(service_user, service_identity, admin_user, app_user, jsondata, now_, user_detail)
    elif loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_CITY_WIDE_LOTTERY:
        sln_settings = get_solution_settings(service_user)
        if SolutionModule.LOYALTY in sln_settings.modules:
            city_app_id = _get_app_id_if_using_city_wide_tombola(service_user, service_identity, False)
            if city_app_id:
                success = is_put = True
                deferred.defer(add_city_wide_lottery_visit, service_user, service_identity, user_detail, loyalty_type, visit_key, now_, _countdown=5)
            else:
                custom_error_message_key = u"City wide lottery not enabled"
        else:
            custom_error_message_key = u"Loyalty not enabled"
    else:
        logging.error("unimplemented loyalty type %s in add", loyalty_type)

    if success:
        deferred.defer(update_user_data_user_loyalty, service_user, service_identity, user_detail.email, user_detail.app_id, loyalty_type, _countdown=5)
        if is_put and visit_key:
            deferred.defer(add_city_wide_lottery_visit, service_user, service_identity, user_detail, loyalty_type, visit_key, now_, _countdown=5)
        if message:
            deferred.defer(_send_message_to_user_for_loyalty_update, service_user, service_identity, admin_user, app_user, message, _countdown=5)
        send_message(service_user, u"solutions.common.loyalty.points.update", service_identity=service_identity)

    return success, is_put, custom_error_message_key

@returns(tuple)
@arguments(service_user=users.User, service_identity=unicode, admin_user=users.User, app_user=users.User, jsondata=dict, now_=(int, long), user_detail=UserDetailsTO)
def add_loyalty_for_user_revenu_discount(service_user, service_identity, admin_user, app_user, jsondata, now_, user_detail=None):
    loyalty_settings = SolutionLoyaltySettings.get_by_user(service_user)
    sln_settings = get_solution_settings(service_user)

    price = long(jsondata['price'])
    logging.debug("Saving new loyalty revenue discount visit for user: %s and price: %s", app_user, price)

    price_total = 0
    visits = 0
    for s in get_solution_loyalty_visits_for_revenue_discount(service_user, service_identity, app_user):
        visits += 1
        price_total += s.price

    service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
    slv = SolutionLoyaltyVisitRevenueDiscount(parent=parent_key_unsafe(service_identity_user, SOLUTION_COMMON))
    slv.admin_user = admin_user
    slv.app_user = app_user
    slv.app_user_info = SolutionUser.fromTO(user_detail) if user_detail else None
    slv.redeemed = False
    slv.timestamp = now_
    slv.price = price
    slv.put()
    visits += 1
    price_total += price

    price_total_str = format_price(price_total, sln_settings.currency)
    price_new_str = format_price(price, sln_settings.currency)

    if loyalty_settings.x_visits > visits:
        message = common_translate(sln_settings.main_language, SOLUTION_COMMON, u"loyalty-message-remaining-type-1")
        message = message % {'price_new': price_new_str,
                             'price_total': price_total_str,
                             'visits_remaining': loyalty_settings.x_visits - (visits - 1),
                             'discount': loyalty_settings.x_discount}
    else:
        message = common_translate(sln_settings.main_language, SOLUTION_COMMON, u"loyalty-message-next-type-1")
        message = message % {'price_new': price_new_str,
                             'price_total': price_total_str,
                             'discount': loyalty_settings.x_discount}

    deferred.defer(send_email_to_user_for_loyalty_update, service_user, service_identity, app_user, message)
    return True, True, message, slv.key()

@returns(tuple)
@arguments(service_user=users.User, service_identity=unicode , admin_user=users.User, app_user=users.User, jsondata=dict, now_=(int, long), user_detail=UserDetailsTO)
def add_loyalty_for_user_lottery(service_user, service_identity, admin_user, app_user, jsondata, now_, user_detail=None):
    logging.debug("Saving new loyalty lottery visit for user: %s", app_user)
    sln_settings = get_solution_settings(service_user)
    now_tz = int(time.mktime(datetime.fromtimestamp(now_, pytz.timezone(sln_settings.timezone)).timetuple()))
    timestamp_day = now_tz - (now_tz % (3600 * 24))

    slv_key = SolutionLoyaltyVisitLottery.create_key(service_user, service_identity, app_user, timestamp_day)
    def trans():
        is_put = False
        slv = SolutionLoyaltyVisitLottery.get(slv_key)
        if not slv:
            slv = SolutionLoyaltyVisitLottery(key=slv_key)

        if not slv.admin_user:
            slv.admin_user = admin_user
            slv.app_user = app_user
            slv.app_user_info = SolutionUser.fromTO(user_detail) if user_detail else None
            slv.redeemed = False
            slv.timestamp = now_
            slv.put()

            slls = SolutionLoyaltyLotteryStatistics.get_by_user(service_user, service_identity)
            if not slls:
                slls_key = SolutionLoyaltyLotteryStatistics.create_key(service_user, service_identity)
                slls = SolutionLoyaltyLotteryStatistics(key=slls_key)
                slls.count = []
                slls.app_users = []

            if app_user in slls.app_users:
                my_index = slls.app_users.index(app_user)
                slls.count[my_index] += 1
            else:
                slls.count.append(1)
                slls.app_users.append(app_user)
            slls.put()
            is_put = True
        else:
            logging.debug("already added a visit today")

        return is_put

    xg_on = db.create_transaction_options(xg=True)
    is_put = db.run_in_transaction_options(xg_on, trans)

    if user_detail:
        if is_put:
            ll_info = SolutionLoyaltyLottery.load_pending(service_user, service_identity)
            if ll_info:
                loot_datetime_tz = datetime.fromtimestamp(ll_info.end_timestamp, pytz.timezone(sln_settings.timezone))
                loot_date_str = format_datetime(loot_datetime_tz, format='medium', locale=sln_settings.main_language)
                message = common_translate(sln_settings.main_language, SOLUTION_COMMON, u"tnx-loyalty-lottery-visit")
                message = message % {'name': user_detail.name,
                                     'date': loot_date_str}
                deferred.defer(send_email_to_user_for_loyalty_update, service_user, service_identity, app_user, message)
            else:
                deferred.defer(send_styled_inbox_forwarders_email_lottery_not_configured, service_user, service_identity, user_detail)
        else:
            message = common_translate(sln_settings.main_language, SOLUTION_COMMON, u"loyalty-lottery-visit-only-once")
            deferred.defer(send_email_to_user_for_loyalty_update, service_user, service_identity, app_user, message)

    return True, is_put, None, slv_key

@returns(tuple)
@arguments(service_user=users.User, service_identity=unicode, admin_user=users.User, app_user=users.User, jsondata=dict, now_=(int, long), user_detail=UserDetailsTO)
def add_loyalty_for_user_stamps(service_user, service_identity, admin_user, app_user, jsondata, now_, user_detail=None):
    loyalty_settings = SolutionLoyaltySettings.get_by_user(service_user)
    sln_settings = get_solution_settings(service_user)

    count = jsondata['count']
    logging.debug("Saving new loyalty stamps visit for user: %s and count: %s", app_user, count)

    count_total = 0
    for s in get_solution_loyalty_visits_for_stamps(service_user, service_identity, app_user):
        count_total += s.count
    service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
    slv = SolutionLoyaltyVisitStamps(parent=parent_key_unsafe(service_identity_user, SOLUTION_COMMON))
    slv.admin_user = admin_user
    slv.app_user = app_user
    slv.app_user_info = SolutionUser.fromTO(user_detail) if user_detail else None
    slv.redeemed = False
    slv.timestamp = now_
    slv.count = count
    slv.put()
    count_total += count

    if loyalty_settings.x_stamps > count_total:
        message_key = u"loyalty-message-remaining-type-3"
        message_params = {}
        if count > 1:
            message_key = u"%s-more" % message_key
            message_params['new_stamps'] = count
        else:
            message_key = u"%s-one" % message_key

        if loyalty_settings.x_stamps > count_total + 1:
            message_key = u"%s-more" % message_key
            message_params['stamps_remaining'] = loyalty_settings.x_stamps - count_total
        else:
            message_key = u"%s-one" % message_key

        message = common_translate(sln_settings.main_language, SOLUTION_COMMON, message_key)
        if message_params:
            message = message % message_params
    else:
        if count > 1:
            message = common_translate(sln_settings.main_language, SOLUTION_COMMON, u"loyalty-message-next-type-3-more")
            message = message % {'new_stamps': count}
        else:
            message = common_translate(sln_settings.main_language, SOLUTION_COMMON, u"loyalty-message-next-type-3-one")

    deferred.defer(send_email_to_user_for_loyalty_update, service_user, service_identity, app_user, message)
    return True, True, message, slv.key()


@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_loyalty_put(service_user, email, method, params, tag, service_identity, user_details):
    logging.debug("Received loyalty put call with params: %s", params)
    r = SendApiCallCallbackResultTO()
    try:
        admin_user = user_details[0].toAppUser()
        jsondata = json.loads(params)

        try:
            app_user, user_detail = get_user_details_for_js_jsondata(service_user, service_identity, jsondata)
        except BusinessException, be:
            r.result = None
            r.error = be.message
            return r

        now_ = jsondata.get("timestamp", now())
        success, is_put, custom_error_message_key = add_loyalty_for_user(service_user, service_identity, admin_user, app_user, jsondata, now_, user_detail)
        if success:
            r_dict = dict(app_id=user_detail.app_id,
                          email=user_detail.email,
                          is_put=is_put)
            result = json.dumps(r_dict)
            r.result = result if isinstance(result, unicode) else result.decode("utf8")
            r.error = None
        else:
            r.result = None
            sln_settings = get_solution_settings(service_user)
            r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON , custom_error_message_key or 'error-occured-unknown-try-again')
    except:
        logging.error("solutions.loyalty.put exception occurred", exc_info=True)
        r.result = None
        sln_settings = get_solution_settings(service_user)
        r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON , 'error-occured-unknown')
    return r

@returns(tuple)
@arguments(service_user=users.User, service_identity=unicode, admin_user=users.User, app_user=users.User, jsondata=dict, now_=(int, long))
def redeem_loyalty_for_user_revenue_discount(service_user, service_identity, admin_user, app_user, jsondata, now_):
    should_update_user_data = False
    message = None
    loyalty_settings = SolutionLoyaltySettings.get_by_user(service_user)

    logging.debug("Redeeming %s loyalty revenue discount visits for user: %s", loyalty_settings.x_visits, app_user)

    def trans():
        models_to_put = []
        price_total = 0
        for s in get_solution_loyalty_visits_for_revenue_discount(service_user, service_identity, app_user, loyalty_settings.x_visits):
            price_total += s.price
            s.redeemed = True
            s.redeemed_admin_user = admin_user
            s.redeemed_timestamp = now_
            models_to_put.append(s)

        if models_to_put:
            db.put(models_to_put)
            return True, price_total
        return False, price_total

    send_message, price_total = db.run_in_transaction(trans)
    if send_message:
        should_update_user_data = True

        sln_settings = get_solution_settings(service_user)
        price_total_str = format_price(price_total, sln_settings.currency)
        message = common_translate(sln_settings.main_language, SOLUTION_COMMON, u"loyalty-message-redeemed-type-1")
        message = message % {'price_total': price_total_str,
                             'discount': loyalty_settings.x_discount}

    else:
        logging.warn("loyalty redeem of 0 visits")

    return True, should_update_user_data, message

@returns(tuple)
@arguments(service_user=users.User, service_identity=unicode, admin_user=users.User, app_user=users.User, jsondata=dict, now_=(int, long))
def redeem_loyalty_for_user_lottery(service_user, service_identity, admin_user, app_user, jsondata, now_):
    def trans():
        ll_info = db.get(jsondata["key"])
        if ll_info and not (ll_info.redeemed and ll_info.deleted):
            if not ll_info.claimed:
                ll_info.claimed = True
                deferred.defer(redeem_loyalty_lottery_visits, service_user, jsondata["key"], now_, _transactional=True)
            ll_info.redeemed = True
            ll_info.put()
            send_message(service_user, u"solutions.common.loyalty.lottery.update", service_identity=service_identity)
            deferred.defer(update_user_data_admins, service_user, service_identity, _transactional=True)

    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans)

    return True, False, None

@returns(tuple)
@arguments(service_user=users.User, service_identity=unicode, admin_user=users.User, app_user=users.User, jsondata=dict, now_=(int, long))
def redeem_loyalty_for_user_stamps(service_user, service_identity, admin_user, app_user, jsondata, now_):
    should_update_user_data = False
    message = None
    loyalty_settings = SolutionLoyaltySettings.get_by_user(service_user)
    total_cards_to_redeem = jsondata["count"]
    total_stamps_to_redeem = total_cards_to_redeem * loyalty_settings.x_stamps

    logging.debug("Redeeming %s loyalty stamps (%s cards) for user: %s", total_stamps_to_redeem, total_cards_to_redeem, app_user)

    def trans():
        models_to_put = []
        stamps_total = 0

        for s in get_solution_loyalty_visits_for_stamps(service_user, service_identity, app_user, total_stamps_to_redeem, True):
            stamps_total += s.count
            if stamps_total > total_stamps_to_redeem:
                stamps_left = stamps_total - total_stamps_to_redeem
                stamps_redeemed = s.count - stamps_left
                service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
                slv = SolutionLoyaltyVisitStamps(parent=parent_key_unsafe(service_identity_user, SOLUTION_COMMON))
                slv.admin_user = s.admin_user
                slv.app_user = s.app_user
                slv.app_user_info = s.app_user_info
                slv.timestamp = s.timestamp
                slv.redeemed = True
                slv.redeemed_timestamp = now_
                slv.redeemed_admin_user = admin_user
                slv.count = stamps_redeemed
                slv.winnings = loyalty_settings.stamps_winnings
                slv.x_stamps = loyalty_settings.x_stamps
                models_to_put.append(slv)
                s.count = stamps_left
            else:
                s.winnings = loyalty_settings.stamps_winnings
                s.redeemed = True
                s.redeemed_admin_user = admin_user
                s.redeemed_timestamp = now_
                s.x_stamps = loyalty_settings.x_stamps

            models_to_put.append(s)

            if stamps_total >= total_stamps_to_redeem:
                break

        if models_to_put:
            db.put(models_to_put)
            return True
        return False

    send_message = db.run_in_transaction(trans)
    if send_message:
        should_update_user_data = True

        sln_settings = get_solution_settings(service_user)
        if total_cards_to_redeem > 1:
            message = common_translate(sln_settings.main_language, SOLUTION_COMMON, u"loyalty-message-redeemed-type-3-more")
            message = message % {'count': total_cards_to_redeem,
                                 'winnings': loyalty_settings.stamps_winnings}
        else:
            message = common_translate(sln_settings.main_language, SOLUTION_COMMON, u"loyalty-message-redeemed-type-3-one")
            message = message % {'winnings': loyalty_settings.stamps_winnings}
    else:
        logging.warn("loyalty redeem of 0 stamps")

    return True, should_update_user_data, message

@returns(bool)
@arguments(service_user=users.User, service_identity=unicode, admin_user=users.User, app_user=users.User, jsondata=dict)
def redeem_loyalty_for_user(service_user, service_identity, admin_user, app_user, jsondata):
    loyalty_settings = SolutionLoyaltySettings.get_by_user(service_user)
    now_ = now()
    if loyalty_settings.loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_REVENUE_DISCOUNT:
        success, should_update_user_data, message = redeem_loyalty_for_user_revenue_discount(service_user, service_identity, admin_user, app_user, jsondata, now_)
    elif loyalty_settings.loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_LOTTERY:
        success, should_update_user_data, message = redeem_loyalty_for_user_lottery(service_user, service_identity, admin_user, app_user, jsondata, now_)
    elif loyalty_settings.loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_STAMPS:
        success, should_update_user_data, message = redeem_loyalty_for_user_stamps(service_user, service_identity, admin_user, app_user, jsondata, now_)
    else:
        success = False
        should_update_user_data = False
        message = None
        logging.error("unimplemented loyalty type %s in redeem", loyalty_settings.loyalty_type)

    if should_update_user_data:
        human_user, app_id = get_app_user_tuple(app_user)
        deferred.defer(update_user_data_user_loyalty, service_user, service_identity, human_user.email(), app_id, loyalty_settings.loyalty_type, _countdown=5)
        if message:
            deferred.defer(_send_message_to_user_for_loyalty_update, service_user, service_identity, admin_user, app_user, message, _countdown=5)
        send_message(service_user, u"solutions.common.loyalty.points.update", service_identity=service_identity)

    if success and message:
        deferred.defer(send_email_to_user_for_loyalty_update, service_user, service_identity, app_user, message)
    return success

@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_loyalty_redeem(service_user, email, method, params, tag, service_identity, user_details):
    logging.debug("Received loyalty redeem call with params: %s", params)
    r = SendApiCallCallbackResultTO()
    try:
        admin_user = user_details[0].toAppUser()
        jsondata = json.loads(params)
        if jsondata.get("user_details", None):
            app_id = jsondata["user_details"]["appId"]
            user_email = jsondata["user_details"]["email"]
        else:
            app_id = jsondata['app_id']
            user_email = jsondata['email']

        app_user = create_app_user_by_email(user_email, app_id)
        loyalty_type = jsondata['loyalty_type']

        loyalty_settings = SolutionLoyaltySettings.get_by_user(service_user)
        success = False
        if loyalty_settings.loyalty_type == loyalty_type:
            success = redeem_loyalty_for_user(service_user, service_identity, admin_user, app_user, jsondata)

        if success:
            r.result = unicode(json.dumps(dict(app_id=app_id,
                                               email=user_email)))
            r.error = None
        else:
            r.result = None
            sln_settings = get_solution_settings(service_user)
            r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON , 'error-occured-unknown-try-again')
    except:
        logging.error("solutions.loyalty.redeem exception occurred", exc_info=True)
        r.result = None
        sln_settings = get_solution_settings(service_user)
        r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON , 'error-occured-unknown')
    return r

@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_loyalty_lottery_chance(service_user, email, method, params, tag, service_identity, user_details):
    logging.debug("Received loyalty redeem call with params: %s", params)
    r = SendApiCallCallbackResultTO()
    try:
        jsondata = json.loads(params)
        app_user = create_app_user_by_email(jsondata["user_details"]['email'], jsondata["user_details"]['app_id'])
        total_visits, my_visits, chance = calculate_chance_for_user(service_user, service_identity, app_user)
        r.result = unicode(json.dumps(dict(total_visits=total_visits,
                                           my_visits=my_visits,
                                           chance=chance)))
        r.error = None
    except:
        logging.error("solutions.loyalty.lottery.chance exception occurred", exc_info=True)
        r.result = None
        sln_settings = get_solution_settings(service_user)
        r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON , 'error-occured-unknown')
    return r

@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode, service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_loyalty_couple(service_user, email, method, params, tag, service_identity, user_details):
    logging.debug("Received loyalty couple call with params: %s", params)
    r = SendApiCallCallbackResultTO()
    r.result = None
    r.error = None
    try:
        jsondata = json.loads(params)
        email = jsondata['email'].lower().strip()
        url = jsondata['url']
        if EMAIL_REGEX.match(email):
            put_result = app.put_loyalty_user(url, email)
            email = put_result.email
            if put_result.url != url:
                logging.info('Coupled custom loyalty card for QR with this content:\n%s', url)
                db.put(CustomLoyaltyCard(key=CustomLoyaltyCard.create_key(url),
                                         custom_qr_content=url,
                                         loyalty_qr_content=put_result.url,
                                         app_user=create_app_user_by_email(email, put_result.app_id)))
            r.result = unicode(json.dumps(dict()))
        else:
            sln_settings = get_solution_settings(service_user)
            r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'invalid_email_format', email=email)

    except:
        logging.error("solutions.loyalty.couple exception occurred", exc_info=True)
        sln_settings = get_solution_settings(service_user)
        r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON , 'error-occured-unknown')
    return r


@returns(tuple)
@arguments(service_user=users.User, service_identity=unicode, app_user=users.User)
def calculate_chance_for_user(service_user, service_identity, app_user):
    def trans():
        slls = SolutionLoyaltyLotteryStatistics.get_by_user(service_user, service_identity)
        if not slls:
            slls_key = SolutionLoyaltyLotteryStatistics.create_key(service_user, service_identity)
            slls = SolutionLoyaltyLotteryStatistics(key=slls_key)
            slls.count = []
            slls.app_users = []
            slls.put()
        return slls
    slls = db.run_in_transaction(trans)
    return _calculate_chance(slls, app_user)


@returns(tuple)
@arguments(city_app_id=unicode, app_user=users.User)
def calculate_city_wide_lottery_chance_for_user(city_app_id, app_user):
    def trans():
        slls = SolutionCityWideLotteryStatistics.get_by_app_id(city_app_id)
        if not slls:
            slls_key = SolutionCityWideLotteryStatistics.create_key(city_app_id)
            slls = SolutionCityWideLotteryStatistics(key=slls_key)
            slls.count = []
            slls.app_users = []
            slls.put()
        return slls
    slls = db.run_in_transaction(trans)
    return _calculate_chance(slls, app_user)


def _calculate_chance(slls, app_user):
    total_visits = sum(slls.count)
    if app_user in slls.app_users:
        my_index = slls.app_users.index(app_user)
        my_visits = slls.count[my_index]
    else:
        my_visits = 0

    if total_visits > 0:
        chance = (float(my_visits) / total_visits) * 100.0
    else:
        chance = 0
    return total_visits, my_visits, chance


def redeem_loyalty_lottery_visits(service_user, sll_key, now_):

    def trans():
        models_to_put = []
        sll = db.get(sll_key)
        slls = SolutionLoyaltyLotteryStatistics.get_by_user(service_user, sll.service_identity)
        if slls:
            sll.count = slls.count
            sll.app_users = slls.app_users
            models_to_put.append(sll)

            slls.count = []
            slls.app_users = []
            models_to_put.append(slls)

        for s in SolutionLoyaltyVisitLottery.load(service_user, sll.service_identity):
            s.redeemed = True
            s.redeemed_timestamp = now_
            models_to_put.append(s)

        if models_to_put:
            put_and_invalidate_cache(*models_to_put)

        send_message(service_user, u"solutions.common.loyalty.points.update", service_identity=sll.service_identity)

    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans)

@returns()
@arguments(service_user=users.User, key=unicode)
def delete_visit(service_user, key):

    def trans():
        visit = db.get(key)
        if visit is None:
            raise BusinessException("Could not find visit")

        human_user, app_id = get_app_user_tuple(visit.app_user)

        if visit.loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_REVENUE_DISCOUNT:
            visit_archive = visit.archive(SolutionLoyaltyVisitRevenueDiscountArchive)

        elif visit.loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_LOTTERY:
            visit_archive = visit.archive(SolutionLoyaltyVisitLotteryArchive)

            slls = SolutionLoyaltyLotteryStatistics.get_by_user(service_user, visit.service_identity)
            if slls:
                if visit.app_user in slls.app_users:
                    my_index = slls.app_users.index(visit.app_user)
                    slls.count[my_index] = slls.count[my_index] - 1
                    if slls.count[my_index] < 1:
                        del slls.app_users[my_index]
                        del slls.count[my_index]
                    slls.put()

        elif visit.loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_STAMPS:
            visit_archive = visit.archive(SolutionLoyaltyVisitStampsArchive)

        else:
            raise BusinessException("error-occured-unknown")

        deferred.defer(delete_city_wide_lottery_visit, service_user, visit.service_identity, human_user.email(), app_id, visit.loyalty_type, visit.key(), _countdown=5, _transactional=True)
        deferred.defer(update_user_data_user_loyalty, service_user, visit.service_identity, human_user.email(), app_id, visit.loyalty_type, _countdown=5, _transactional=True)
        deferred.defer(_send_delete_visit, service_user, visit.service_identity, visit.app_user, visit.timestamp, _countdown=5, _transactional=True)

        send_message(service_user, u"solutions.common.loyalty.points.update", visit.service_identity)
        visit_archive.put()
        visit.delete()

    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans)

def _send_delete_visit(service_user, service_identity, app_user, timestamp):
    sln_settings = get_solution_settings(service_user)
    dt = datetime.utcfromtimestamp(timestamp)
    message = common_translate(sln_settings.main_language, SOLUTION_COMMON, u'loyalty-message-delete-visit', date=format_date(dt, format='long', locale=sln_settings.main_language))
    deferred.defer(_send_message_to_user, service_user, service_identity, app_user, message)

def _send_message_to_user(service_user, service_identity, app_user, message):
    from rogerthat.bizz.messaging import CanOnlySendToFriendsException
    human_user, app_id = get_app_user_tuple(app_user)
    sln_main_branding = get_solution_main_branding(service_user)
    branding = sln_main_branding.branding_key if sln_main_branding else None

    member = MemberTO()
    member.alert_flags = Message.ALERT_FLAG_VIBRATE
    member.member = human_user.email()
    member.app_id = app_id

    users.set_user(service_user)
    try:
        messaging.send(parent_key=None,
                       parent_message_key=None,
                       message=message,
                       answers=[],
                       flags=Message.FLAG_ALLOW_DISMISS,
                       members=[member],
                       branding=branding,
                       tag=None,
                       service_identity=service_identity)
    except CanOnlySendToFriendsException:
        pass  # ignore
    finally:
        users.clear_user()

def _send_message_to_user_for_loyalty_update(service_user, service_identity, admin_user, app_user, message):
    from rogerthat.bizz.messaging import CanOnlySendToFriendsException
    from solutions.common.bizz.messaging import POKE_TAG_LOYALTY_REMINDERS

    suls = SolutionUserLoyaltySettings.get_by_user(app_user)
    if suls:
        if suls.reminders_disabled:
            return
        else:
            service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
            if service_identity_user.email() in suls.reminders_disabled_for:
                return

    human_user, app_id = get_app_user_tuple(app_user)
    sln_settings = get_solution_settings(service_user)
    sln_main_branding = get_solution_main_branding(service_user)
    branding = sln_main_branding.branding_key if sln_main_branding else None

    member = MemberTO()
    member.alert_flags = Message.ALERT_FLAG_VIBRATE
    member.member = human_user.email()
    member.app_id = app_id

    answers = []
    btn = AnswerTO()
    btn.action = None
    btn.caption = common_translate(sln_settings.main_language, SOLUTION_COMMON, u'loyalty-reminder-stop-for', name=sln_settings.name)
    btn.id = unicode(json.dumps(dict(email=human_user.email(),
                                     app_id=app_id,
                                     all=False)))
    btn.type = u'button'
    btn.ui_flags = 0
    answers.append(btn)

    users.set_user(service_user)
    try:
        messaging.send(parent_key=None,
                       parent_message_key=None,
                       message=message,
                       answers=answers,
                       flags=Message.FLAG_ALLOW_DISMISS,
                       members=[member],
                       branding=branding,
                       tag=POKE_TAG_LOYALTY_REMINDERS,
                       service_identity=service_identity)
    except CanOnlySendToFriendsException:
        pass  # ignore
    finally:
        users.clear_user()


@returns()
@arguments(service_user=users.User, status=int, answer_id=unicode, received_timestamp=int, member=unicode,
           message_key=unicode, tag=unicode, acked_timestamp=int, parent_message_key=unicode, result_key=unicode,
           service_identity=unicode, user_details=[UserDetailsTO])
def stop_loyalty_reminders(service_user, status, answer_id, received_timestamp, member, message_key, tag,
                                   acked_timestamp, parent_message_key, result_key, service_identity, user_details):
    if not answer_id:
        return  # status is STATUS_RECEIVED or user dismissed
    app_user = user_details[0].toAppUser()
    should_put = False
    suls_key = SolutionUserLoyaltySettings.createKey(app_user)
    suls = SolutionUserLoyaltySettings.get(suls_key)
    if not suls:
        suls = SolutionUserLoyaltySettings(key=suls_key)
        suls.reminders_disabled = False
        suls.reminders_disabled_for = []

    info = json.loads(answer_id)
    if info['all']:
        should_put = True
        suls.reminders_disabled = True
    else:
        service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
        service_identity_user_email = service_identity_user.email()
        if service_identity_user_email not in suls.reminders_disabled_for:
            should_put = True
            suls.reminders_disabled_for.append(service_identity_user_email)

    if should_put:
        suls.put()

def _replace_head_loyalty_revenue_discount(html_):
    html_ = re.sub('<head>', """<head>
    <link href="jquery/jquery.mobile.inline-png-1.4.2.min.css" rel="stylesheet" media="screen"/>
    <script>
        var LOYALTY_TYPE = %s;
    </script>
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
    """ % SolutionLoyaltySettings.LOYALTY_TYPE_REVENUE_DISCOUNT, html_)
    return html_

def _replace_head_loyalty_lottery(html_):
    html_ = re.sub('<head>', """<head>
    <script>
        var LOYALTY_TYPE = %s;
    </script>
    <script type="text/javascript" src="jquery/jquery-1.11.0.min.js">
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
    """ % SolutionLoyaltySettings.LOYALTY_TYPE_LOTTERY, html_)
    return html_

def _replace_head_loyalty_stamps(html_):
    html_ = re.sub('<head>', """<head>
    <link href="jquery/jquery.mobile.inline-png-1.4.2.min.css" rel="stylesheet" media="screen"/>
    <script>
        var LOYALTY_TYPE = %s;
    </script>
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
    """ % SolutionLoyaltySettings.LOYALTY_TYPE_STAMPS, html_)
    return html_

def provision_loyalty_branding(solution_settings, main_branding, language, loyalty_type):
    from solutions.common.handlers import JINJA_ENVIRONMENT
    if not solution_settings.loyalty_branding_hash:
        logging.info("Storing LOYALTY branding")
        stream = ZipFile(StringIO(main_branding.blob))
        try:
            new_zip_stream = StringIO()
            zip_ = ZipFile(new_zip_stream, 'w', compression=ZIP_DEFLATED)
            try:
                path = os.path.join(os.path.dirname(solutions.__file__), 'common', 'templates', 'brandings/app_jquery.tmpl.js')
                zip_.writestr("jquery.tmpl.min.js", file_get_contents(path))
                path = os.path.join(os.path.dirname(solutions.__file__), 'common', 'templates', 'brandings/moment-with-locales.min.js')
                zip_.writestr("moment-with-locales.min.js", file_get_contents(path))
                zip_.writestr("app-translations.js", JINJA_ENVIRONMENT.get_template("brandings/app_loyalty_translations.js").render({'language': language}).encode("utf-8"))
                path = os.path.join(os.path.dirname(solutions.__file__), 'common', 'templates', 'brandings/app_loyalty.js')
                zip_.writestr("app.js", file_get_contents(path))

                path = os.path.join(os.path.dirname(solutions.__file__), 'common', 'templates', 'brandings/loyalty_stamps_visit.png')
                zip_.writestr("loyalty_stamps_visit.png", file_get_contents(path))

                path = os.path.join(os.path.dirname(solutions.__file__), 'common', 'templates', 'brandings/loyalty_stamps_gift.png')
                zip_.writestr("loyalty_stamps_gift.png", file_get_contents(path))

                for file_name in set(stream.namelist()):
                    str_ = stream.read(file_name)
                    if file_name == 'branding.html':
                        html_ = str_
                        # Remove previously added dimensions:
                        html_ = re.sub("<meta\\s+property=\\\"rt:dimensions\\\"\\s+content=\\\"\\[\\d+,\\d+,\\d+,\\d+\\]\\\"\\s*/>", "", html_)
                        if loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_REVENUE_DISCOUNT:
                            template_name = 'brandings/loyalty_revenue_discount.tmpl'
                            html_ = _replace_head_loyalty_revenue_discount(html_)
                        elif loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_LOTTERY:
                            template_name = 'brandings/loyalty_lottery.tmpl'
                            html_ = _replace_head_loyalty_lottery(html_)
                        elif loyalty_type == SolutionLoyaltySettings.LOYALTY_TYPE_STAMPS:
                            template_name = 'brandings/loyalty_stamps.tmpl'
                            html_ = _replace_head_loyalty_stamps(html_)
                        else:
                            raise BusinessException(u"Unknown loyalty_type: %s" % loyalty_type)

                        doc = html.fromstring(html_)
                        h = doc.find('./head')

                        html__ = """<!DOCTYPE html>
<html>"""
                        html__ += etree.tostring(h)
                        branding_settings = SolutionBrandingSettings.get_by_user(solution_settings.service_user)
                        html__ += render_common_content(language, template_name, {"LOYALTY_TYPE": loyalty_type,
                                                                                  'show_identity_name': not branding_settings or branding_settings.show_identity_name})
                        html__ += "</html>"
                        zip_.writestr('app.html', html__.encode('utf8'))
                    else:
                        zip_.writestr(file_name, str_)
            finally:
                zip_.close()

            loyalty_branding_content = new_zip_stream.getvalue()
            new_zip_stream.close()

            solution_settings.loyalty_branding_hash = put_branding(u"Loyalty App", base64.b64encode(loyalty_branding_content)).id
            solution_settings.put()
        except:
            logging.error("Failure while parsing loyalty app branding", exc_info=1)
            raise
        finally:
            stream.close()

@returns(str)
@arguments()
def get_loyalty_slide_footer():
    with open(os.path.join(os.path.dirname(__file__), '..', 'templates', 'osa-loyalty-slide-footer.png'), 'r') as f:
        return str(f.read())

@returns()
@arguments(service_user=users.User, service_identity=unicode, tag=unicode, user_details=[UserDetailsTO], status=int)
def messaging_update_inbox_forwaring_reply(service_user, service_identity, tag, user_details, status):
    from solutions.common.bizz.messaging import POKE_TAG_INBOX_FORWARDING_REPLY
    from rogerthat.models.properties.messaging import MemberStatus

    if not is_flag_set(MemberStatus.STATUS_ACKED, status):
        return

    info_dict_str = tag[len(POKE_TAG_INBOX_FORWARDING_REPLY):]
    if not info_dict_str:
        return  # there is no info dict

    info = json.loads(info_dict_str)
    app_user = user_details[0].toAppUser()
    redeem_lottery_winner(service_user, service_identity, info['message_key'], app_user, user_details[0].name)

@returns(bool)
@arguments(service_user=users.User, service_identity=unicode, message_key=unicode, app_user=users.User, name=unicode)
def redeem_lottery_winner(service_user, service_identity, message_key, app_user, name):
    from solutions.common.bizz.inbox import add_solution_inbox_message
    from solutions.common.bizz.messaging import send_inbox_forwarders_message
    sim_parent = SolutionInboxMessage.get(message_key)
    if sim_parent.category == SolutionInboxMessage.CATEGORY_LOYALTY:
        sln_loyalty_lottery = db.get(sim_parent.category_key)
        if sln_loyalty_lottery and not(sln_loyalty_lottery.claimed or sln_loyalty_lottery.redeemed or sln_loyalty_lottery.deleted):
            if sln_loyalty_lottery.winner != app_user:
                return False

            if sim_parent.message_key_by_tag:
                message_key_by_tag = json.loads(sim_parent.message_key_by_tag)
                if message_key_by_tag.get(u"loyalty_lottery_loot", None):
                    with users.set_user(service_user):
                        messaging.seal(message_key_by_tag[u"loyalty_lottery_loot"], sim_parent.message_key, sim_parent.message_key, 1)

            sln_loyalty_lottery.claimed = True
            sln_loyalty_lottery.put()

            now_ = now()
            sln_settings = get_solution_settings(service_user)
            sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)

            msg_1 = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'loyalty-lottery-loot-receive')
            if sln_i_settings.opening_hours:
                msg_2 = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'opening-hours')
                msg = u"%s\n\n%s:\n%s" % (msg_1, msg_2, sln_i_settings.opening_hours)
            else:
                msg = msg_1

            sim_parent, _ = add_solution_inbox_message(service_user, sln_loyalty_lottery.solution_inbox_message_key, True, None, now_, msg, mark_as_read=True)
            send_inbox_forwarders_message(service_user, service_identity, None, msg, {
                    'if_name': name,
                    'if_email':get_human_user_from_app_user(app_user).email()
            }, message_key=sim_parent.solution_inbox_message_key, reply_enabled=sim_parent.reply_enabled, send_reminder=False)

            sm_data = []
            sm_data.append({u"type": u"solutions.common.loyalty.lottery.update"})

            sm_data.append({u"type": u"solutions.common.messaging.update",
                         u"message": serialize_complex_value(SolutionInboxMessageTO.fromModel(sim_parent, sln_settings, sln_i_settings, True), SolutionInboxMessageTO, False)})

            send_message(service_user, sm_data, service_identity=service_identity)

            deferred.defer(redeem_loyalty_lottery_visits, service_user, sim_parent.category_key, now_)
            return True
    return False

@returns(NoneType)
@arguments(service_user=users.User, service_identity=unicode, user_detail=UserDetailsTO)
def send_styled_inbox_forwarders_email_lottery_not_configured(service_user, service_identity, user_detail):
    sln_settings = get_solution_settings(service_user)
    sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
    if not sln_i_settings.inbox_mail_forwarders:
        return
    service_email = sln_settings.login.email() if sln_settings.login else service_user.email()

    settings = get_server_settings()

    users.set_user(service_user)
    try:
        si = system.get_identity(service_identity)
    finally:
        users.clear_user()

    app = get_app_by_id(si.app_ids[0])

    subject = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'loyalty-lottery-configure-email-subject')

    mimeRoot = MIMEMultipart('related')
    mimeRoot['Subject'] = subject
    mimeRoot['From'] = settings.senderEmail if app.type == App.APP_TYPE_ROGERTHAT else ("%s <%s>" % (app.name, app.dashboard_email_address))
    mimeRoot['To'] = ', '.join(sln_i_settings.inbox_mail_forwarders)

    mime = MIMEMultipart('alternative')
    mimeRoot.attach(mime)

    part_1_css = "line-height: 130%; color: #614e4e; border: 4px solid #6db59c; margin-top: -5px; padding: 1em; background-color: #9adbc4; font-size: 16px; font-family: Arial; border-radius: 0 0 15px 15px; -webkit-border-radius: 0 0 15px 15px; -moz-border-radius: 0 0 15px 15px;"
    button_css = "display: inline-block; margin-left: 0.5em; margin-right: 0.5em; -webkit-border-radius: 6px; -moz-border-radius: 6px; border-radius: 6px; font-family: Arial; color: #ffffff; font-size: 16px; background: #6db59c; padding: 10px 20px 10px 20px; text-decoration: none;"


    if_email_footer_1 = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'if-email-footer-1',
                                                    service_name=sln_settings.name,
                                                    app_name=app.name)
    if_email_footer_2 = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'if-email-footer-2')
    if_email_footer_3 = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'if-email-footer-3')
    if_email_footer_4 = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'if-email-footer-4')
    if_email_footer_5 = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'if-email-footer-5')
    if_email_footer_6 = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'if-email-footer-6')

    if_email_body_1_button = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'loyalty-lottery-configure-email-text',
                                                  name=user_detail.name,
                                                  email=service_email,
                                                  link="<a href='https://rogerth.at?email=%(service_email)s' style='%(button_css)s'>Dashboard</a>" %
                                                        {'service_email': sln_settings.login.email() if sln_settings.login else service_user.email(),
                                                         'button_css': button_css})

    if_email_body_1_url = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'loyalty-lottery-configure-email-text',
                                                  name=user_detail.name,
                                                  email=service_email,
                                                  link="https://rogerth.at?email=%(service_email)s" % {'service_email': service_email})

    body_html = """<!DOCTYPE html>
<html>
<body>
<div style="padding: 0; margin:0 auto; line-height: 100%%; overflow: hidden;">
    <img style="width: 100%%;" src="cid:osa-footer" />
    <div style="%(part_1_css)s">
        <p>%(if_email_body_1_button)s</p>
    </div>
    <div style="line-height: 130%%;">
        <br><br>
        %(if_email_footer_1)s<br><br>
        %(if_email_footer_2)s<br>
        %(if_email_footer_3)s<br>
        %(if_email_footer_4)s<br>
        %(if_email_footer_5)s<br>
        %(if_email_footer_6)s<br>
    </div>
</div>
</body>
</html>""" % {"part_1_css": part_1_css,
              'if_email_body_1_button': if_email_body_1_button,
              'if_email_footer_1': if_email_footer_1,
              'if_email_footer_2': if_email_footer_2,
              'if_email_footer_3': if_email_footer_3,
              'if_email_footer_4': if_email_footer_4,
              'if_email_footer_5': if_email_footer_5,
              'if_email_footer_6': if_email_footer_6
              }

    body = """%(if_email_body_1_url)s

--------------------

%(if_email_footer_1)s

%(if_email_footer_2)s
%(if_email_footer_3)s
%(if_email_footer_4)s
%(if_email_footer_5)s
%(if_email_footer_6)s
""" % {'if_email_body_1_url': if_email_body_1_url,
       'if_email_footer_1': if_email_footer_1,
       'if_email_footer_2': if_email_footer_2,
       'if_email_footer_3': if_email_footer_3,
       'if_email_footer_4': if_email_footer_4,
       'if_email_footer_5': if_email_footer_5,
       'if_email_footer_6': if_email_footer_6}

    mime.attach(MIMEText(body.encode('utf-8'), 'plain', 'utf-8'))
    mime.attach(MIMEText(body_html.encode('utf-8'), 'html', 'utf-8'))

    with open(os.path.join(os.path.dirname(solutions.__file__), 'common', 'templates', 'osa-footer-be.png'), 'r') as f:
        img_data = f.read()

    img = MIMEImage(img_data, 'png')
    img.add_header('Content-Id', '<osa-footer>')
    img.add_header("Content-Disposition", "inline", filename="Onze Stad App footer")
    mimeRoot.attach(img)

    send_mail_via_mime(settings.senderEmail, sln_i_settings.inbox_mail_forwarders, mimeRoot) # todo patch

@returns(str)
@arguments(app_user=users.User, email=unicode, name=unicode)
def generate_loyalty_no_mobiles_unsubscribe_email_link(app_user, email, name):
    data = dict(n=name, e=email, t=0, a="loyalty_no_mobiles_unsubscribe", c=None)
    return generate_user_specific_link('/unauthenticated/loyalty/no_mobiles/unsubscribe_email', app_user, data)

@returns(str)
@arguments(app_user=users.User, email=unicode, name=unicode, message_key=unicode)
def generate_loyalty_no_mobiles_lottery_winner_link(app_user, email, name, message_key):
    data = dict(n=name, e=email, t=0, a="loyalty_no_mobiles_lottery_winner", c=None, mk=message_key)
    return generate_user_specific_link('/unauthenticated/loyalty/no_mobiles/lottery_winner', app_user, data)

@returns(NoneType)
@arguments(service_user=users.User, service_identity=unicode, app_user=users.User, message=unicode, unsubscribe_enabled=bool, lottery_winner_message_key=unicode)
def send_email_to_user_for_loyalty_update(service_user, service_identity, app_user, message, unsubscribe_enabled=True, lottery_winner_message_key=None):
    from solutions.common.handlers import JINJA_ENVIRONMENT
    if unsubscribe_enabled:
        suls = SolutionUserLoyaltySettings.get_by_user(app_user)
        if suls:
            if suls.reminders_disabled:
                return
            else:
                service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
                if service_identity_user.email() in suls.reminders_disabled_for:
                    return

    user_profile = get_user_profile(app_user)
    if not user_profile:
        logging.info("User was deactivated: %s" , app_user.email())
        return

    human_user, app_id = get_app_user_tuple(app_user)
    with users.set_user(service_user):
        service_friend_status = friends.get_status(human_user.email(), app_id=app_id)
        if len(service_friend_status.devices) > 0:
            return

    sln_settings = get_solution_settings(service_user)
    app = get_app_by_id(app_id)
    server_settings = get_server_settings()

    subject = common_translate(sln_settings.main_language, SOLUTION_COMMON, "%(app_name)s has 1 new message for you", app_name=app.name)
    user_email = human_user.email()

    support_email = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'the_our_city_app_coach_email_address')
    support_html = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'the_our_city_app_coach_email_address_html', email=support_email)
    website_link = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'http://www.ourcityapps.com')
    install_info = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'loyalty_email_no_mobiles',
                                        app_name=app.name,
                                        support=support_email,
                                        website_link=website_link)
    install_info_html = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'loyalty_email_no_mobiles_html',
                                             app_name=app.name,
                                             support=support_html,
                                             website_link=website_link)
    team = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'the_our_city_app_team')

    service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
    service_identity_user_email = service_identity_user.email()
    unsubscribe_info = None
    unsubscribe_info_html = None
    if unsubscribe_enabled:
        unsubscribe_link = generate_loyalty_no_mobiles_unsubscribe_email_link(app_user, service_identity_user_email, sln_settings.name)
        unsubscribe_info = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'dont_receive_emails_unsubsubscribe', unsubscribe_link=unsubscribe_link)
        unsubscribe_info_html = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'dont_receive_emails_unsubsubscribe_html', unsubscribe_link=unsubscribe_link)

    lottery_winner_info = None
    lottery_winner_info_html = None
    if lottery_winner_message_key:
        confirm = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'Confirm')
        confirm_link = generate_loyalty_no_mobiles_lottery_winner_link(app_user, service_identity_user_email, sln_settings.name, lottery_winner_message_key)
        lottery_winner_info = "%s: %s" % (confirm, confirm_link)
        lottery_winner_info_html = "<a href=\"%s\">%s</a>" % (confirm_link, confirm)

    jinja_template = JINJA_ENVIRONMENT.get_template('emails/new_loyalty_email.tmpl')
    body = jinja_template.render({"profile":user_profile,
                                  "sln_settings":sln_settings,
                                  "message":message,
                                  "lottery_winner_info": lottery_winner_info,
                                  "install_info": install_info,
                                  "unsubscribe_info": unsubscribe_info,
                                  "team": team})

    jinja_template = JINJA_ENVIRONMENT.get_template('emails/new_loyalty_email_html.tmpl')
    body_html = jinja_template.render({"profile":user_profile,
                                       "sln_settings":sln_settings,
                                       "message":message,
                                       "lottery_winner_info": lottery_winner_info_html,
                                       "install_info": install_info_html,
                                       "unsubscribe_info": unsubscribe_info_html,
                                       "team": team})

    from_ = server_settings.senderEmail if app.type == App.APP_TYPE_ROGERTHAT else ("%s <%s>" % (app.name, app.dashboard_email_address))
    send_mail(from_, user_email, subject, body, html=body_html)


def create_loyalty_statistics_for_service(service_user, service_identity, first_day_of_last_month, first_day_of_current_month):
    from solutions.common.handlers import JINJA_ENVIRONMENT
    second_day_of_last_month = first_day_of_last_month + 86400
    customer = Customer.get_by_service_email(service_user.email())
    if not customer:
        return
    service_identity_user = get_and_validate_service_identity_user(service_user, service_identity)
    sln_settings = get_solution_settings(service_user)
    contact = Contact.get_one(customer)
    revenue_discounts_ds = SolutionLoyaltyVisitRevenueDiscount.get_for_time_period(service_user,
                                                                                   service_identity,
                                                                                   first_day_of_last_month,
                                                                                   first_day_of_current_month)
    lotery_visits_ds = SolutionLoyaltyLottery.get_for_time_period(service_user,
                                                                  service_identity,
                                                                  first_day_of_last_month,
                                                                  first_day_of_current_month)
    stamps_ds = SolutionLoyaltyVisitStamps.get_for_time_period(service_user,
                                                               service_identity,
                                                               first_day_of_last_month,
                                                               first_day_of_current_month)
    coupons_ds = NewsCoupon.list_by_service(service_identity_user)
    loyalty_settings = SolutionLoyaltySettings.get_by_user(service_user)
    revenue_discounts = {}
    total_spent = 0
    for r in revenue_discounts_ds:
        email_and_ts = r.app_user.email() + unicode(r.redeemed_timestamp)
        if email_and_ts in revenue_discounts:
            revenue_discounts[email_and_ts].price += r.price
        else:
            revenue_discounts[email_and_ts] = r
            r.datetime = format_datetime(r.redeemed_timestamp, 'EEE d MMM yyyy HH:mm',
                                         tzinfo=get_timezone(sln_settings.timezone), locale=customer.language)
        total_spent += r.price

    lottery = []
    for l in lotery_visits_ds:
        l.winnings = l.winnings.replace('\n', '<br />')
        l.datetime = format_datetime(l.winner_timestamp, 'EEE d MMM yyyy HH:mm',
                                     tzinfo=get_timezone(sln_settings.timezone), locale=customer.language)
        lottery.append(l)
    stamps = {}
    for s in stamps_ds:
        if s.redeemed_timestamp in stamps:
            stamps[s.redeemed_timestamp]["count"] += s.count
            t = stamps[s.redeemed_timestamp]["count"] / stamps[s.redeemed_timestamp]["x_stamps"]
            if t > 1:
                stamps[s.redeemed_timestamp]["winnings"] = u"%sx <br />%s" % (t, stamps[s.redeemed_timestamp]["original_winnings"])
        else:
            stamps[s.redeemed_timestamp] = {"redeemed_timestamp": s.redeemed_timestamp,
                                            "name": s.app_user_info.name,
                                            "email": s.app_user.email().split(':')[0],
                                            "datetime": format_datetime(s.redeemed_timestamp, 'EEE d MMM yyyy HH:mm',
                                                                        tzinfo=get_timezone(sln_settings.timezone), locale=customer.language),
                                            "x_stamps": s.x_stamps,
                                            "count": s.count,
                                            "original_winnings": s.winnings.replace('\n', '<br />') if s.winnings else u"",
                                            "winnings": s.winnings.replace('\n', '<br />') if s.winnings else u""}
    coupons = {}
    for coupon in coupons_ds:
        if coupon.redeemed_by:
            redeemed_by = coupon.redeemed_by.to_json_dict()
            for user in redeemed_by['users']:
                if first_day_of_last_month < user['redeemed_on'] < first_day_of_current_month:
                    if coupon.id not in coupons:
                        coupons[coupon.id] = {
                            'content': coupon.content,
                            'count': 0
                        }
                    coupons[coupon.id]['count'] += 1

    if len(revenue_discounts) == 0 and len(lottery) == 0 and len(stamps) == 0 and len(coupons) is 0:
        # customer did not use the loyalty system in this month
        return
    html_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')
    path = 'pdfs/loyalty_export.html'

    variables = {
        "customer": customer,
        'currency': sln_settings.currency,
        'contact': contact,
        'revenue_discounts': sorted(revenue_discounts.values(), key=lambda x: x.redeemed_timestamp),
        'total_spent': format_price(total_spent),
        'total_revenue_discount': format_price(total_spent / (100.0 / loyalty_settings.x_discount)),
        'x_discount': loyalty_settings.x_discount,
        'lotery': lottery,
        'stamps': sorted(stamps.values(), key=lambda x: x["redeemed_timestamp"]),
        'coupons': coupons.values(),
        'language': customer.language,
        'month': format_datetime(second_day_of_last_month, 'MMMM',
                                 tzinfo=get_timezone(sln_settings.timezone), locale=customer.language),
        'mobicage_country': Locale(customer.language).territories['BE'],
        'logo_path': 'templates/img/osa_white_' + customer.language + '_250.jpg' if customer.language in LOGO_LANGUAGES else 'templates/img/osa_white_en_250.jpg'
    }
    source_html = JINJA_ENVIRONMENT.get_template(path).render(variables)
    # Monkey patch problem in PIL
    orig_to_bytes = getattr(Image, "tobytes", None)
    try:
        if orig_to_bytes is None:
            Image.tobytes = Image.tostring
        output_stream = StringIO()
        pisa.CreatePDF(src=source_html, dest=output_stream, path=html_dir)
        month = datetime.fromtimestamp(second_day_of_last_month).month
        year = datetime.fromtimestamp(second_day_of_last_month).year
        export = SolutionLoyaltyExport(
            key=SolutionLoyaltyExport.create_key(service_user, service_identity, year, month),
            pdf=output_stream.getvalue(),
            year_month=year * 100 + month
        )
        export.put()
    finally:
        if orig_to_bytes is None:
            delattr(Image, "tobytes")


@returns()
@arguments(service_user=users.User, source=unicode)
def request_loyalty_device(service_user, source):
    # Create ShopTask
    from shop.bizz import create_task, broadcast_task_updates
    from shop.business.prospect import create_prospect_from_customer
    customer = get_customer(service_user)
    if customer.prospect_id:
        rmt, prospect = db.get(
            [RegioManagerTeam.create_key(customer.team_id), Prospect.create_key(customer.prospect_id)])
    else:
        prospect = create_prospect_from_customer(customer)
        rmt = RegioManagerTeam.get(RegioManagerTeam.create_key(customer.team_id))
    azzert(rmt.support_manager, 'No support manager found for team %s' % rmt.name)
    comment = u'Customer is interested in the Our City App terminal and wants a loyalty system.'
    if source:
        comment += u' Source: %s' % source
    task = create_task(prospect_or_key=prospect,
                       status=ShopTask.STATUS_NEW,
                       task_type=ShopTask.TYPE_SUPPORT_NEEDED,
                       address=None,
                       created_by=STORE_MANAGER.email(),
                       assignee=rmt.support_manager,
                       execution_time=today() + 86400 + 10 * 3600,  # tomorrow, 10:00 UTC
                       app_id=prospect.app_id,
                       comment=comment,
                       notify_by_email=True)
    task.put()

    broadcast_task_updates([rmt.support_manager])


@returns(unicode)
@arguments(service_user=users.User, service_identity=unicode, should_set_user=bool)
def _get_app_id_if_using_city_wide_tombola(service_user, service_identity, should_set_user=True):
    city_wide_lottery = {}
    for city in CityPostalCodes.all():
        if city.postal_codes:
            city_wide_lottery[city.app_id] = city.postal_codes
    if not city_wide_lottery:
        return None

    if should_set_user:
        users.set_user(service_user)
    try:
        identity = system.get_identity(service_identity)
        for i_app_id in identity.app_ids:
            if i_app_id not in city_wide_lottery:
                continue
            if not identity.search_config:
                continue
            if not identity.search_config.locations:
                continue
            for location in identity.search_config.locations:
                for postal_code in city_wide_lottery[i_app_id]:
                    if postal_code in location.address:
                        return i_app_id
    finally:
        if should_set_user:
            users.clear_user()
    return None


@returns()
@arguments(service_user=users.User, service_identity=unicode, user_detail=UserDetailsTO, loyalty_type=(int, long), visit_key=db.Key, now_=(int, long))
def add_city_wide_lottery_visit(service_user, service_identity, user_detail, loyalty_type, visit_key, now_):
    city_app_id = _get_app_id_if_using_city_wide_tombola(service_user, service_identity)
    if not city_app_id:
        return

    app_user = user_detail.toAppUser()
    sln_cwt_visit_parent_key = SolutionCityWideLotteryVisit.create_parent_key(city_app_id, service_user, service_identity, app_user)
    def trans():
        sln_cwt_visit = SolutionCityWideLotteryVisit(parent=sln_cwt_visit_parent_key)
        sln_cwt_visit.app_user = app_user
        sln_cwt_visit.app_user_info = SolutionUser.fromTO(user_detail)
        sln_cwt_visit.original_visit_key = unicode(visit_key) if visit_key else None
        sln_cwt_visit.original_loyalty_type = loyalty_type
        sln_cwt_visit.timestamp = now_
        sln_cwt_visit.redeemed = False
        sln_cwt_visit.redeemed_timestamp = 0
        sln_cwt_visit.put()

        slls = SolutionCityWideLotteryStatistics.get_by_app_id(city_app_id)
        if not slls:
            slls_key = SolutionCityWideLotteryStatistics.create_key(city_app_id)
            slls = SolutionCityWideLotteryStatistics(key=slls_key)
            slls.count = []
            slls.app_users = []

        if app_user in slls.app_users:
            my_index = slls.app_users.index(app_user)
            slls.count[my_index] += 1
        else:
            slls.count.append(1)
            slls.app_users.append(app_user)
        slls.put()

    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans)


@returns()
@arguments(service_user=users.User, service_identity=unicode, email=unicode, app_id=unicode, loyalty_type=(int, long), visit_key=db.Key)
def delete_city_wide_lottery_visit(service_user, service_identity, email, app_id, loyalty_type, visit_key):
    city_app_id = _get_app_id_if_using_city_wide_tombola(service_user, service_identity)
    if not city_app_id:
        return

    def trans():
        app_user = create_app_user_by_email(email, app_id)
        slls = SolutionCityWideLotteryStatistics.get_by_app_id(city_app_id)
        if slls:
            if app_user in slls.app_users:
                my_index = slls.app_users.index(app_user)
                slls.count[my_index] = slls.count[my_index] - 1
                if slls.count[my_index] < 1:
                    del slls.app_users[my_index]
                    del slls.count[my_index]
                slls.put()

        sln_cwt_visit = SolutionCityWideLotteryVisit.get_visit_by_original_visit_key(city_app_id, service_user, service_identity, app_user, unicode(visit_key))
        if sln_cwt_visit:
            sln_cwt_visit.delete()

    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans)


def send_postal_code_update_message(code, deleted):
    service_user = users.get_current_user()
    send_message(service_user, 'solutions.common.postal_code.update',
                 code=code, deleted=deleted)


@returns(CityPostalCodes)
@arguments(app_id=unicode)
def get_or_create_city_postal_codes(app_id):
    key = CityPostalCodes.create_key(app_id)
    city = db.get(key)
    if not city:
        city = CityPostalCodes(key=key)
    if not city.postal_codes:
        city.postal_codes = []
    city.app_id = app_id
    return city


@returns()
@arguments(app_id=unicode, postal_code=unicode)
def add_city_postal_code(app_id, postal_code):
    if not re.match('\d+', postal_code):
        raise ValueError
    city = get_or_create_city_postal_codes(app_id)
    if postal_code not in city.postal_codes:
        city.postal_codes.append(postal_code)
        city.put()
        send_postal_code_update_message(postal_code, False)


@returns()
@arguments(app_id=unicode, postal_code=unicode)
def remove_city_postal_code(app_id, postal_code):
    city = get_or_create_city_postal_codes(app_id)
    if postal_code in city.postal_codes:
        city.postal_codes.remove(postal_code)
        city.put()
        send_postal_code_update_message(postal_code, True)

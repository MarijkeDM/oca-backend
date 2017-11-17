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

from datetime import datetime
from dateutil.relativedelta import relativedelta
import json
import logging

from google.appengine.ext import db, deferred
from mcfw.rpc import returns, arguments
from rogerthat.bizz.job import run_job
from rogerthat.bizz.messaging import InvalidURLException
from rogerthat.consts import HIGH_LOAD_WORKER_QUEUE
from rogerthat.dal import parent_key_unsafe, put_in_chunks
from rogerthat.models import App
from rogerthat.rpc import users
from rogerthat.rpc.service import BusinessException
from rogerthat.service.api import qr, messaging, system
from rogerthat.to.friends import GetUserInfoResponseTO
from rogerthat.to.service import SendApiCallCallbackResultTO, UserDetailsTO
from rogerthat.utils import now, channel, get_epoch_from_datetime
from rogerthat.utils.app import get_app_user_tuple
from rogerthat.utils.transactions import run_in_xg_transaction
from solutions import translate as common_translate
from solutions.common import SOLUTION_COMMON
from solutions.common.dal import get_solution_settings
from solutions.common.dal.cityapp import get_service_users_for_city
from solutions.common.dal.city_vouchers import get_city_vouchers_settings
from solutions.common.models.city_vouchers import SolutionCityVoucher, SolutionCityVoucherQRCodeExport, \
    SolutionCityVoucherTransaction, SolutionCityVoucherRedeemTransaction, SolutionCityVoucherSettings
from solutions.common.models.loyalty import CustomLoyaltyCard
from solutions.common.utils import create_service_identity_user_wo_default


POKE_TAG_CITY_VOUCHER_QR = u"city_voucher_qr"


@returns()
@arguments(service_user=users.User, app_id=unicode)
def create_city_voucher_qr_codes(service_user, app_id):
    ancestor_key = SolutionCityVoucherQRCodeExport.create_parent_key(app_id)

    def trans():
        sln_qr_export = SolutionCityVoucherQRCodeExport(parent=ancestor_key)
        sln_qr_export.created = now()
        sln_qr_export.ready = False
        sln_qr_export.put()
        deferred.defer(_generate_vouchers, service_user, app_id, sln_qr_export.key(), _transactional=True)

    db.run_in_transaction(trans)


def _generate_vouchers(service_user, app_id, sln_qr_export_key):
    voucher_ancestor_key = SolutionCityVoucher.create_parent_key(app_id)
    now_ = now()
    voucher_to_put = list()
    for _ in xrange(100):
        voucher = SolutionCityVoucher(parent=voucher_ancestor_key)
        voucher.created = now_
        voucher_to_put.append(voucher)
    db.put(voucher_to_put)

    voucher_ids = []
    for voucher in voucher_to_put:
        voucher_key = voucher.key()
        voucher_ids.append(voucher_key.id())

    def trans():
        sln_qr_export = db.get(sln_qr_export_key)
        sln_qr_export.voucher_ids = voucher_ids
        sln_qr_export.put()
        deferred.defer(_generate_vouchers_qr_codes, service_user, app_id, sln_qr_export.key(), voucher_ids,
                       _transactional=True)

    db.run_in_transaction(trans)


def _generate_vouchers_qr_codes(service_user, app_id, sln_qr_export_key, voucher_ids):
    tags = list()
    for voucher_id in voucher_ids:
        data = dict(app_id=app_id, voucher_id=voucher_id)
        info = json.dumps(data).decode('utf8')
        tag = POKE_TAG_CITY_VOUCHER_QR + info
        tags.append(tag)

    users.set_user(service_user)
    try:
        qr_details = qr.bulk_create("City Voucher QR Code", tags, None)
    finally:
        users.clear_user()

    def trans():
        voucher_ancestor_key = SolutionCityVoucher.create_parent_key(app_id)
        vouchers = SolutionCityVoucher.get_by_id(voucher_ids, voucher_ancestor_key)
        to_put = list()
        for voucher, qr_detail in zip(vouchers, qr_details):
            voucher.image_uri = qr_detail.image_uri
            voucher.content_uri = qr_detail.content_uri
            _set_search_fields(voucher)
            to_put.append(voucher)

            history = SolutionCityVoucherTransaction(parent=voucher)
            history.created = voucher.created
            history.action = SolutionCityVoucherTransaction.ACTION_CREATED
            history.value = 0
            history.service_user = None
            history.service_identity = None
            to_put.append(history)

        sln_qr_export = db.get(sln_qr_export_key)
        sln_qr_export.ready = True
        to_put.append(sln_qr_export)
        put_in_chunks(to_put)
        channel.send_message(service_user, 'solutions.common.city.vouchers.qrcode_export.updated')

    run_in_xg_transaction(trans)


def _set_search_fields(voucher):
    search_fields = []
    if voucher.internal_account:
        search_fields.extend(voucher.internal_account)
    if voucher.cost_center:
        search_fields.append(voucher.cost_center)
    search_fields.extend(voucher.uid.split(" "))

    voucher.search_fields = [term.lower() for term in search_fields if term]


@returns()
@arguments(voucher_key=db.Key)
def re_index_voucher(voucher_key):
    voucher = SolutionCityVoucher.get(voucher_key)
    _set_search_fields(voucher)
    voucher.put()


def _all_vouchers(app_id=unicode):
    ancestor_key = SolutionCityVoucher.create_parent_key(app_id)
    return SolutionCityVoucher.all(keys_only=True).ancestor(ancestor_key)


@returns()
@arguments(app_id=unicode, queue=unicode)
def _re_index_all_vouchers(app_id, queue=HIGH_LOAD_WORKER_QUEUE):
    run_job(_all_vouchers, [app_id], re_index_voucher, [], worker_queue=queue)


def re_index_all_vouchers_all_apps(queue=HIGH_LOAD_WORKER_QUEUE):
    for app_key in App.all(keys_only=True):
        _re_index_all_vouchers(app_key.name(), queue)


@returns()
@arguments(app_id=unicode)
def put_city_voucher_settings(app_id):
    def trans():
        sln_city_voucher_settings_key = SolutionCityVoucherSettings.create_key(app_id)
        sln_city_voucher_settings = SolutionCityVoucherSettings.get(sln_city_voucher_settings_key)
        if sln_city_voucher_settings:
            raise BusinessException("Unable to put city voucher settings, already existing")
        sln_city_voucher_settings = SolutionCityVoucherSettings(key=sln_city_voucher_settings_key)
        sln_city_voucher_settings.put()

    db.run_in_transaction(trans)


@returns()
@arguments(app_id=unicode, username=unicode, pincode=unicode)
def put_city_voucher_user(app_id, username, pincode):
    if not username:
        raise BusinessException("Username is required")
    if len(pincode) != 4:
        raise BusinessException("Pincode should be exactly 4 characters")

    def trans():
        sln_city_voucher_settings = get_city_vouchers_settings(app_id)
        if not sln_city_voucher_settings:
            raise BusinessException("Unable to put city voucher user, settings not found")

        if username in sln_city_voucher_settings.usernames:
            index = sln_city_voucher_settings.usernames.index(username)
            del sln_city_voucher_settings.usernames[index]
            del sln_city_voucher_settings.pincodes[index]

        sln_city_voucher_settings.usernames.append(username)
        sln_city_voucher_settings.pincodes.append(pincode)
        sln_city_voucher_settings.put()

    db.run_in_transaction(trans)


@returns()
@arguments(app_id=unicode, username=unicode)
def delete_city_voucher_user(app_id, username):
    def trans():
        sln_city_voucher_settings = get_city_vouchers_settings(app_id)
        if not sln_city_voucher_settings:
            raise BusinessException("Unable to delete city voucher user, settings not found")
        if username not in sln_city_voucher_settings.usernames:
            raise BusinessException("Unable to delete city voucher user, user not found")

        index = sln_city_voucher_settings.usernames.index(username)
        del sln_city_voucher_settings.usernames[index]
        del sln_city_voucher_settings.pincodes[index]
        sln_city_voucher_settings.put()

    db.run_in_transaction(trans)


def _find_voucher(url, app_ids):
    poke_information = None
    city_service_user = None
    for app_id in app_ids:
        for city_service_user in get_service_users_for_city(app_id):
            with users.set_user(city_service_user):
                try:
                    poke_information = messaging.poke_information(url)
                    if poke_information:
                        break
                except InvalidURLException:
                    break
        else:
            continue  # we did not break

        break
    else:
        raise Exception("city_service_user not found for app_ids: %s" % app_ids)

    return poke_information, city_service_user


def _create_resolve_result(result_type, url, email, app_id):
    return dict(type=result_type,
                url=url,
                content=url,
                userDetails=dict(appId=app_id,
                                 email=email,
                                 name=email))


@returns(dict)
@arguments(service_user=users.User, service_identity=unicode, url=unicode)
def _resolve_voucher(service_user, service_identity, url):
    '''Lookup the provided URL. Can be a city voucher. Else it will be treated as a custom loyalty card.'''

    # 1/ Check if a custom loyalty card already exists for this URL
    custom_loyalty_card = CustomLoyaltyCard.get_by_url(url)
    if custom_loyalty_card and custom_loyalty_card.app_user:
        human_user, app_id = get_app_user_tuple(custom_loyalty_card.app_user)
        return _create_resolve_result(CustomLoyaltyCard.TYPE, url, human_user.email(), app_id)

    # 2/ Check if it's a city voucher
    si = system.get_identity(service_identity)
    poke_information, city_service_user = _find_voucher(url, si.app_ids)
    if not poke_information or not poke_information.tag.startswith(POKE_TAG_CITY_VOUCHER_QR):
        # 2.1/ Not a city voucher
        logging.debug('Unknown QR code scanned: %s. Loyalty device will create custom paper loyalty card.', url)
        user_info = GetUserInfoResponseTO()
        user_info.app_id = user_info.email = user_info.name = user_info.qualifiedIdentifier = u'dummy'
        return _create_resolve_result(u'unknown', url, u'dummy', u'dummy')

    # 2.2/ It is a city voucher
    data = json.loads(poke_information.tag[len(POKE_TAG_CITY_VOUCHER_QR):])
    ancestor_key = SolutionCityVoucher.create_parent_key(data["app_id"])
    sln_city_voucher = SolutionCityVoucher.get_by_id(data["voucher_id"], ancestor_key)
    if not sln_city_voucher:
        logging.debug("Could not find city voucher for data: %s", data)
        raise Exception("Could not find city voucher")

    sln_settings = get_solution_settings(service_user)

    r_dict = dict()
    r_dict["type"] = SolutionCityVoucher.TYPE
    r_dict["app_id"] = sln_city_voucher.app_id
    r_dict["voucher_id"] = sln_city_voucher.key().id()
    r_dict["uid"] = sln_city_voucher.uid
    if sln_city_voucher.activated:
        if sln_city_voucher.expired:
            raise BusinessException(common_translate(sln_settings.main_language, SOLUTION_COMMON, 'Voucher has expired'))
        r_dict["status"] = 1
        r_dict["value"] = sln_city_voucher.value
        r_dict["redeemed_value"] = sln_city_voucher.redeemed_value
    elif service_user == city_service_user:
        r_dict["status"] = 2
    else:
        raise BusinessException(common_translate(sln_settings.main_language, SOLUTION_COMMON, 'Voucher not activated'))

    return r_dict


@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode,
           service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_voucher_resolve(service_user, email, method, params, tag, service_identity, user_details):
    logging.debug("Received voucher resolve call with params: %s", params)
    r = SendApiCallCallbackResultTO()
    r.result = None
    r.error = None
    try:
        jsondata = json.loads(params)
        r_dict = _resolve_voucher(service_user, service_identity, jsondata['url'])
        result = json.dumps(r_dict)
        r.result = result if isinstance(result, unicode) else result.decode("utf8")
    except BusinessException, be:
        r.error = be.message
    except:
        logging.error("solutions.voucher.resolve exception occurred", exc_info=True)
        sln_settings = get_solution_settings(service_user)
        r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'error-occured-unknown')
    return r


@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode,
           service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_voucher_pin_activate(service_user, email, method, params, tag, service_identity, user_details):
    logging.debug("Received voucher pin activate call with params: %s", params)
    sln_settings = get_solution_settings(service_user)
    r = SendApiCallCallbackResultTO()
    r.result = None
    r.error = None
    try:
        jsondata = json.loads(params)

        city_service_users = get_service_users_for_city(jsondata["app_id"])
        if not city_service_users:
            raise Exception(u"No city_service_users")

        if service_user not in city_service_users:
            raise Exception(u"Normal service tried activating voucher")

        ancestor_key = SolutionCityVoucher.create_parent_key(jsondata["app_id"])
        sln_city_voucher = SolutionCityVoucher.get_by_id(jsondata["voucher_id"], ancestor_key)
        if not sln_city_voucher:
            raise Exception(u"sln_city_voucher was None")

        if sln_city_voucher.activated:
            raise Exception(u"sln_city_voucher was already activated")

        sln_city_voucher_settings = get_city_vouchers_settings(jsondata["app_id"])
        if not sln_city_voucher_settings:
            raise Exception(u"sln_city_voucher_settings was None")

        if jsondata["pin"] not in sln_city_voucher_settings.pincodes:
            r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'Pincode invalid')
            return r

        index = sln_city_voucher_settings.pincodes.index(jsondata["pin"])
        r_dict = dict()
        r_dict["username"] = sln_city_voucher_settings.usernames[index]
        result = json.dumps(r_dict)
        r.result = result if isinstance(result, unicode) else result.decode("utf8")
    except:
        logging.error("solutions.voucher.activate.pin exception occurred", exc_info=True)
        r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'error-occured-unknown')
    return r


@returns((int, long))
@arguments(app_id=unicode)
def get_expiration_date_from_today(app_id):
    settings = get_city_vouchers_settings(app_id)
    if settings.validity:
        expiration_date = datetime.utcnow().date() + relativedelta(months=settings.validity)
        return get_epoch_from_datetime(expiration_date)


@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode,
           service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_voucher_activate(service_user, email, method, params, tag, service_identity, user_details):
    logging.debug("Received voucher activate call with params: %s", params)
    sln_settings = get_solution_settings(service_user)
    r = SendApiCallCallbackResultTO()
    r.result = None
    r.error = None
    try:
        jsondata = json.loads(params)

        city_service_users = get_service_users_for_city(jsondata["app_id"])
        if not city_service_users:
            raise Exception(u"No city_service_users")

        if service_user not in city_service_users:
            raise Exception(u"Normal service tried activating voucher")

        def trans():
            ancestor_key = SolutionCityVoucher.create_parent_key(jsondata["app_id"])
            sln_city_voucher = SolutionCityVoucher.get_by_id(jsondata["voucher_id"], ancestor_key)
            if not sln_city_voucher:
                raise Exception(u"sln_city_voucher was None")

            if sln_city_voucher.activated:
                raise Exception(u"sln_city_voucher was already activated")

            value = jsondata["value"]
            if not isinstance(value, int) and isinstance(value, long):
                raise Exception(u"Value is not of expected type (int, long)")

            if value <= 0:
                raise Exception(u"Value needs to be bigger then 0")

            history = SolutionCityVoucherTransaction(parent=sln_city_voucher)
            history.created = now()
            history.action = SolutionCityVoucherTransaction.ACTION_ACTIVATED
            history.value = jsondata["value"]
            history.service_user = service_user
            history.service_identity = service_identity
            history.put()

            sln_city_voucher.activated = True
            sln_city_voucher.activation_date = now()
            sln_city_voucher.value = jsondata["value"]
            sln_city_voucher.internal_account = jsondata["internal_account"]
            sln_city_voucher.cost_center = jsondata["cost_center"]
            sln_city_voucher.username = jsondata["username"]
            sln_city_voucher.redeemed_value = 0
            sln_city_voucher.expiration_date = get_expiration_date_from_today(jsondata['app_id'])
            app_user_details = jsondata.get('app_user_details')
            if app_user_details:
                sln_city_voucher.owner = users.User(email=app_user_details['email'])
                sln_city_voucher.owner_name = app_user_details['name']
            sln_city_voucher.put()
            deferred.defer(re_index_voucher, sln_city_voucher.key(), _transactional=True)

        xg_on = db.create_transaction_options(xg=True)
        db.run_in_transaction_options(xg_on, trans)

        r.result = u'Successfully activated voucher'

    except:
        logging.error("solutions.voucher.activate exception occurred", exc_info=True)
        r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'error-occured-unknown')
    return r


@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode,
           service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_voucher_redeem(service_user, email, method, params, tag, service_identity, user_details):
    logging.debug("Received voucher redeem call with params: %s", params)
    sln_settings = get_solution_settings(service_user)
    r = SendApiCallCallbackResultTO()
    r.result = None
    r.error = None
    try:
        jsondata = json.loads(params)

        ancestor_key = SolutionCityVoucher.create_parent_key(jsondata["app_id"])
        sln_city_voucher = SolutionCityVoucher.get_by_id(jsondata["voucher_id"], ancestor_key)
        if not sln_city_voucher:
            raise Exception(u"sln_city_voucher was None")

        value = long(jsondata["value"])
        if (sln_city_voucher.value - sln_city_voucher.redeemed_value) < value:
            raise Exception(u"insufficient funds")

        service_identity_user = create_service_identity_user_wo_default(service_user, service_identity)
        sln_city_voucher_rt = SolutionCityVoucherRedeemTransaction(
            parent=parent_key_unsafe(service_identity_user, SOLUTION_COMMON))
        sln_city_voucher_rt.created = now()
        sln_city_voucher_rt.confirmed = False
        sln_city_voucher_rt.value = value
        sln_city_voucher_rt.voucher_key = unicode(sln_city_voucher.key())
        sln_city_voucher_rt.signature = sln_city_voucher.signature()
        sln_city_voucher_rt.put()

        r_dict = dict()
        r_dict["uid"] = sln_city_voucher.uid
        r_dict["voucher_redeem_key"] = unicode(sln_city_voucher_rt.key())
        r_dict["value"] = sln_city_voucher_rt.value

        result = json.dumps(r_dict)
        r.result = result if isinstance(result, unicode) else result.decode("utf8")
    except:
        logging.error("solutions.voucher.redeem exception occurred", exc_info=True)
        r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'error-occured-unknown')
    return r


@returns(SendApiCallCallbackResultTO)
@arguments(service_user=users.User, email=unicode, method=unicode, params=unicode, tag=unicode,
           service_identity=unicode,
           user_details=[UserDetailsTO])
def solution_voucher_confirm_redeem(service_user, email, method, params, tag, service_identity, user_details):
    logging.debug("Received voucher confirm redeem call with params: %s", params)
    sln_settings = get_solution_settings(service_user)
    r = SendApiCallCallbackResultTO()
    r.result = None
    r.error = None
    try:
        jsondata = json.loads(params)

        def trans():
            sln_city_voucher_rt = SolutionCityVoucherRedeemTransaction.get(jsondata["voucher_redeem_key"])
            if not sln_city_voucher_rt:
                raise Exception(u"sln_city_voucher_rt was None")

            sln_city_voucher = SolutionCityVoucher.get(sln_city_voucher_rt.voucher_key)
            if not sln_city_voucher:
                raise Exception(u"sln_city_voucher was None")

            if sln_city_voucher_rt.signature != sln_city_voucher.signature():
                raise Exception(u"Signature on the redeem transaction did not match the signature of the voucher")

            sln_city_voucher_rt.confirmed = True
            sln_city_voucher_rt.put()

            history = SolutionCityVoucherTransaction(parent=sln_city_voucher)
            history.created = now()
            history.action = SolutionCityVoucherTransaction.ACTION_REDEEMED
            history.value = -sln_city_voucher_rt.value
            history.service_user = service_user
            history.service_identity = service_identity
            history.put()

            sln_city_voucher.redeemed_value = sln_city_voucher.redeemed_value + sln_city_voucher_rt.value
            if sln_city_voucher.value < sln_city_voucher.redeemed_value:
                raise Exception(u"Insufficient funds")
            if sln_city_voucher.value == sln_city_voucher.redeemed_value:
                sln_city_voucher.redeemed = True
            sln_city_voucher.put()

            sum_all_transactions = 0
            for t in sln_city_voucher.load_transactions():
                sum_all_transactions += t.value
            sum_all_transactions += history.value

            if not sum_all_transactions >= 0:
                raise Exception("Insufficient funds")

            sum_voucher_values = sln_city_voucher.value - sln_city_voucher.redeemed_value

            if sum_all_transactions != sum_voucher_values:
                raise Exception(u"Sum of all transactions did not match")

            return sln_city_voucher.value - sln_city_voucher.redeemed_value

        xg_on = db.create_transaction_options(xg=True)
        value_left = db.run_in_transaction_options(xg_on, trans)

        r_dict = dict()
        r_dict["title"] = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'Transaction successful')
        r_dict["content"] = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'voucher_value_is',
                                             currency=sln_settings.currency, value=round(value_left / 100.0, 2))
        result = json.dumps(r_dict)
        r.result = result if isinstance(result, unicode) else result.decode("utf8")
    except:
        logging.error("solutions.voucher.redeem.confirm exception occurred", exc_info=True)
        r.error = common_translate(sln_settings.main_language, SOLUTION_COMMON, 'error-occured-unknown')
    return r

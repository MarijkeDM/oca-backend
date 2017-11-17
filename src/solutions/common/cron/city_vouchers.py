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

from __future__ import unicode_literals

import base64
from datetime import date, datetime
from functools import partial
import logging
import time

from babel.dates import format_datetime, get_timezone
from dateutil.relativedelta import relativedelta

from google.appengine.ext import db, deferred, webapp
from rogerthat.bizz.job import run_job
from rogerthat.consts import DAY
from rogerthat.models import Message
from rogerthat.rpc import users
from rogerthat.service.api import system, messaging
from rogerthat.to.messaging import MemberTO
from rogerthat.utils import send_mail
from rogerthat.utils import today
from shop.models import Customer
from solution_server_settings import get_solution_server_settings
from solutions import SOLUTION_COMMON, translate as common_translate
from solutions.common.bizz import SolutionModule
from solutions.common.dal import get_solution_settings, get_solution_main_branding
from solutions.common.models import SolutionSettings
from solutions.common.models.city_vouchers import SolutionCityVoucherTransaction, \
    SolutionCityVoucher, SolutionCityVoucherExport, SolutionCityVoucherExportMerchant
import xlwt


try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


class SolutionCityVouchersExportHandler(webapp.RequestHandler):

    def get(self):
        create_voucher_export_pdfs()


def create_voucher_export_pdfs():

    def get_last_month():
        today = date.today()
        d = today - relativedelta(months=1)
        return date(d.year, d.month, 1)

    first_day_of_last_month = int(time.mktime(get_last_month().timetuple()))
    first_day_of_current_month = int(time.mktime(date.today().replace(day=1).timetuple()))

    for sln_settings in SolutionSettings.all().filter('modules =', SolutionModule.CITY_VOUCHERS):
        deferred.defer(create_voucher_statistics_for_city_service, sln_settings.service_user,
                       sln_settings.main_language, first_day_of_last_month, first_day_of_current_month)


def format_timestamp(timestamp, sln_settings, format='EEE d MMM yyyy HH:mm'):
    return format_datetime(timestamp, format,
                           tzinfo=get_timezone(sln_settings.timezone),
                           locale=sln_settings.main_language)


def write_header(sheet, row, translate_fn, *header):
    for col, value in enumerate(header):
        sheet.write(row, col, translate_fn(value).capitalize())


def create_voucher_statistics_for_city_service(service_user, language, first_day_of_last_month, first_day_of_current_month):
    customer = Customer.get_by_service_email(service_user.email())
    translate = partial(common_translate, language, SOLUTION_COMMON)
    if not customer:
        logging.error("failed to create voucher statistics customer not found")
        return
    sln_settings = get_solution_settings(service_user)

    users.set_user(service_user)
    try:
        si = system.get_identity()
    finally:
        users.clear_user()
    app_id = si.app_ids[0]
    ancestor_key = SolutionCityVoucher.create_parent_key(app_id)

    qry = SolutionCityVoucherTransaction.all().ancestor(ancestor_key)
    qry.filter("action =", SolutionCityVoucherTransaction.ACTION_REDEEMED)
    qry.filter("created >=", first_day_of_last_month)
    qry.filter("created <", first_day_of_current_month)

    transactions = []
    merchant_transactions = dict()
    merchants = dict()
    unique_vouchers = dict()
    for t in qry:
        t.dt = format_timestamp(t.created, sln_settings)
        t.voucher = t.parent()
        transactions.append(t)
        if t.service_user not in merchant_transactions:
            merchant_transactions[t.service_user] = {"value": 0, "transactions": []}
        merchant_transactions[t.service_user]["value"] += t.value
        merchant_transactions[t.service_user]["transactions"].append(t.key())
        unique_vouchers[t.voucher.key()] = t.voucher

    for merchant_service_user in merchant_transactions.keys():
        merchants[merchant_service_user] = get_solution_settings(merchant_service_user)

    qry = SolutionCityVoucher.all().ancestor(ancestor_key)
    qry.filter("activated =", True)
    qry.filter("redeemed = ", False)
    vouchers = []
    expired_vouchers = []
    for v in qry:
        v.dt = format_timestamp(v.created, sln_settings)
        if v.expired:
            if v.expiration_date >= first_day_of_last_month and \
               v.expiration_date < first_day_of_current_month:
                expired_vouchers.append(v)
        else:
            vouchers.append(v)

    book = xlwt.Workbook(encoding="utf-8")

    # TAB 1
    sheet_transactions = book.add_sheet(translate("Transactions"))
    row = 0
    write_header(sheet_transactions, row, translate,
                 "Date", "Voucher", "Internal account", "Cost center",
                 "merchant", "Withdrawn value")

    for transaction in transactions:
        row += 1
        sheet_transactions.write(row, 0, transaction.dt)
        sheet_transactions.write(row, 1, transaction.voucher.uid)
        sheet_transactions.write(row, 2, transaction.voucher.internal_account)
        sheet_transactions.write(row, 3, transaction.voucher.cost_center)
        sheet_transactions.write(row, 4, merchants[transaction.service_user].name)
        sheet_transactions.write(row, 5, round(transaction.value / 100.0, 2))
    row += 2
    sheet_transactions.write(row, 0, translate("total"))
    sheet_transactions.write(row, 5, xlwt.Formula('SUM(F2:F%s)' % (row - 1)))

    # TAB 2
    sheet_merchants = book.add_sheet(translate("merchants"))
    row = 0
    sheet_merchants.write(row, 0, translate("merchant"))
    sheet_merchants.write(row, 1, translate("address"))
    sheet_merchants.write(row, 2, "IBAN")
    sheet_merchants.write(row, 3, "BIC")
    sheet_merchants.write(row, 4, translate("Total value to be paid"))
    for merchant_service_user in merchants.keys():
        merchant = merchants[merchant_service_user]
        row += 1
        sheet_merchants.write(row, 0, merchant.name)
        sheet_merchants.write(row, 1, merchant.address)
        sheet_merchants.write(row, 2, merchant.iban or u"")
        sheet_merchants.write(row, 3, merchant.bic or u"")
        sheet_merchants.write(row, 4, round(merchant_transactions[merchant_service_user]["value"] / 100.0, 2))

    row += 2
    sheet_merchants.write(row, 0, translate("total"))
    sheet_merchants.write(row, 4, xlwt.Formula('SUM(E2:E%s)' % (row - 1)))

    # TAB 3
    sheet_vouchers = book.add_sheet(translate("Vouchers in circulation"))
    row = 0
    write_header(sheet_vouchers, row, translate,
                 "Voucher", "Internal account", "Cost center", "Date", "Remaining value")

    for voucher in vouchers:
        unique_vouchers[voucher.key()] = voucher
        row += 1
        sheet_vouchers.write(row, 0, voucher.uid)
        sheet_vouchers.write(row, 1, voucher.internal_account)
        sheet_vouchers.write(row, 2, voucher.cost_center)
        sheet_vouchers.write(row, 3, voucher.dt)
        value = voucher.value - voucher.redeemed_value
        sheet_vouchers.write(row, 4, round(value / 100.0, 2))

    row += 2
    sheet_vouchers.write(row, 0, translate("total"))
    sheet_vouchers.write(row, 2, xlwt.Formula('SUM(E2:E%s)' % (row - 1)))

    # TAB 4
    expired_vouchers_sheet = book.add_sheet(translate("expired"))
    row = 0
    write_header(expired_vouchers_sheet, row, translate,
                 "Voucher", "Internal account", "Cost center",
                 "Date", "Expiration date", "Remaining value")

    for voucher in expired_vouchers:
        row += 1
        expired_vouchers_sheet.write(row, 0, voucher.uid)
        expired_vouchers_sheet.write(row, 1, voucher.internal_account)
        expired_vouchers_sheet.write(row, 2, voucher.cost_center)
        expired_vouchers_sheet.write(row, 3, format_timestamp(voucher.created, sln_settings))
        expired_vouchers_sheet.write(row, 4, format_timestamp(voucher.expiration_date, sln_settings,
                                                              format='yyyy-MM-dd'))
        value = voucher.value - voucher.redeemed_value
        expired_vouchers_sheet.write(row, 5, round(value / 100.0, 2))

    row += 2
    expired_vouchers_sheet.write(row, 0, translate("total"))
    expired_vouchers_sheet.write(row, 5, xlwt.Formula('SUM(F2:F%s)' % (row - 1)))

    # TAB 5
    sheet_voucher_details = book.add_sheet(translate("Voucher details"))
    row = 0
    for voucher in sorted(unique_vouchers.itervalues(), key=lambda v: v.created):
        voucher_transactions = [h for h in voucher.load_transactions()]
        sheet_voucher_details.write(row, 0, translate("Voucher"))
        sheet_voucher_details.write(row, 1, voucher.uid)
        sheet_voucher_details.write(row, 2, translate("Remaining value"))
        sheet_voucher_details.write(
            row, 3, xlwt.Formula('SUM(D%s:D%s)' % (row + 2,  row + 1 + len(voucher_transactions))))

        row += 1
        sheet_voucher_details.write(row, 0, translate("Internal account"))
        sheet_voucher_details.write(row, 1, voucher.internal_account)
        sheet_voucher_details.write(row, 2, translate("Cost center"))
        sheet_voucher_details.write(row, 3, voucher.cost_center)

        for history in reversed(voucher_transactions):
            merchant_service_user = history.service_user or service_user
            if merchant_service_user not in merchants:
                merchants[merchant_service_user] = get_solution_settings(merchant_service_user)

            row += 1
            dt = format_timestamp(history.created, sln_settings)

            sheet_voucher_details.write(row, 0, dt)
            sheet_voucher_details.write(row, 1, merchants[merchant_service_user].name)
            sheet_voucher_details.write(row, 2, history.action_str)
            if history.action == SolutionCityVoucherTransaction.ACTION_ACTIVATED or \
                    history.action == SolutionCityVoucherTransaction.ACTION_REDEEMED:
                sheet_voucher_details.write(row, 3, round(history.value / 100.0, 2))

        row += 2

    excel_file = StringIO()
    book.save(excel_file)
    excel_string = excel_file.getvalue()

    second_day_of_last_month = first_day_of_last_month + 86400
    d = datetime.fromtimestamp(second_day_of_last_month)

    sln_city_voucher_export_key = SolutionCityVoucherExport.create_key(app_id, d.year, d.month)
    sln_city_voucher_export = SolutionCityVoucherExport(key=sln_city_voucher_export_key)
    sln_city_voucher_export.xls = excel_string
    sln_city_voucher_export.year_month = d.year * 100 + d.month
    sln_city_voucher_export.put()

    for merchant_service_user in merchant_transactions.keys():
        deferred.defer(create_voucher_statistics_for_service, merchants[merchant_service_user], app_id, customer.language,
                       merchant_transactions[merchant_service_user]["transactions"], d.year, d.month)

    to_emails = sln_settings.inbox_mail_forwarders
    if to_emails:
        solution_server_settings = get_solution_server_settings()
        attachments = []
        attachments.append(('%s %s-%s.xls' % (translate('Vouchers'), d.year, d.month),
                            base64.b64encode(excel_string)))
        subject = translate('Vouchers export')
        message = translate('see_attachment_for_vouchers_export')
        send_mail(solution_server_settings.shop_export_email, to_emails, subject, message, attachments=attachments)


def create_voucher_statistics_for_service(sln_settings, app_id, language, transaction_keys, year, month):
    transactions = SolutionCityVoucherTransaction.get(transaction_keys)
    book = xlwt.Workbook(encoding="utf-8")
    translate = partial(common_translate, language, SOLUTION_COMMON)

    sheet_transactions = book.add_sheet(translate("Transactions"))
    row = 0
    write_header(sheet_transactions, row, translate,
                 "Date", "Voucher", "Withdrawn value")

    for transaction in transactions:
        transaction.dt = format_timestamp(transaction.created, sln_settings)
        transaction.voucher = transaction.parent()
        row += 1
        sheet_transactions.write(row, 0, transaction.dt)
        sheet_transactions.write(row, 1, transaction.voucher.uid)
        sheet_transactions.write(row, 2, round(transaction.value / 100.0, 2))
    row += 2
    sheet_transactions.write(row, 0, translate("total"))
    sheet_transactions.write(row, 2, xlwt.Formula('SUM(C2:C%s)' % (row - 1)))

    excel_file = StringIO()
    book.save(excel_file)
    excel_string = excel_file.getvalue()

    export_key = SolutionCityVoucherExportMerchant.create_key(sln_settings.service_user, None, year, month)
    export = SolutionCityVoucherExportMerchant(key=export_key)
    export.xls = excel_string
    export.year_month = year * 100 + month
    export.put()


class SolutionCityVoucherExpiredReminderHandler(webapp.RequestHandler):

    def get(self):
        expired_vouchers_reminder()


EXPIRED_VOUCHERS_REMINDER = [
    0,  # the same day
    DAY,  # the day before
    DAY * 28  # a month before
]


def city_vouchers_enabled_qry():
    return SolutionSettings.all(keys_only=True).filter('modules', SolutionModule.CITY_VOUCHERS).filter(
        'service_disabled', False
    )


def expired_vouchers_reminder():
    run_job(city_vouchers_enabled_qry, [], remind_user_with_expired_vouchers, [today()])


def expired_vouchers_qry(app_id, expired_at):
    parent = SolutionCityVoucher.create_parent_key(app_id)
    return SolutionCityVoucher.all(keys_only=True).ancestor(parent).filter(
        'expiration_date', expired_at)


def remind_user_with_expired_vouchers(sln_settings_key, today_timestamp):
    """Remind voucher owners (users) before the expiration date by n days"""
    sln_settings = SolutionSettings.get(sln_settings_key)
    if not sln_settings:
        return

    customer = Customer.get_by_service_email(sln_settings.service_user.email())
    if not customer:
        return

    for days in EXPIRED_VOUCHERS_REMINDER:
        run_job(expired_vouchers_qry, [customer.app_id, today_timestamp + days],
                send_expired_voucher_message, [sln_settings, days / DAY])


def send_expired_voucher_message(voucher_key, sln_settings, days):
    voucher = SolutionCityVoucher.get(voucher_key)
    if not voucher or days in voucher.expiration_reminders_sent:
        return

    language = sln_settings.main_language
    service_user = sln_settings.service_user
    branding = get_solution_main_branding(service_user).branding_key

    if voucher.owner:
        activation_date = format_timestamp(voucher.activation_date, sln_settings, format='medium')
        message = common_translate(language, SOLUTION_COMMON, u'voucher_expiration_message',
                                   days=days, date=activation_date)
        with users.set_user(sln_settings.service_user):
            member = MemberTO()
            member.alert_flags = Message.ALERT_FLAG_VIBRATE
            member.member = voucher.owner.email()
            member.app_id = voucher.app_id
            messaging.send(parent_key=None,
                           parent_message_key=None,
                           message=message,
                           answers=[],
                           flags=Message.FLAG_ALLOW_DISMISS,
                           members=[member],
                           branding=branding,
                           tag=None)

        voucher.expiration_reminders_sent.append(days)
        db.put(voucher)

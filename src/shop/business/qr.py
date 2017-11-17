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
import datetime
import logging
import zipfile

from babel.dates import format_date

from add_1_monkey_patches import DEBUG
from google.appengine.api import users as gusers
from google.appengine.ext.deferred import deferred
from mcfw.imaging import generate_qr_code
from mcfw.properties import azzert
from mcfw.rpc import arguments, returns
from rogerthat.bizz.profile import generate_unassigned_short_urls
from rogerthat.dal.app import get_app_by_id
from rogerthat.settings import get_server_settings
from rogerthat.translations import DEFAULT_LANGUAGE
from rogerthat.utils import send_mail
from shop.bizz import is_admin
from shop.exceptions import NoPermissionException, AppNotFoundException
from solution_server_settings import get_solution_server_settings
import xlwt


try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

@returns()
@arguments(app_id=unicode, amount=(int, long), mode=unicode)
def generate_unassigned_qr_codes_zip_for_app(app_id, amount, mode):
    current_user = gusers.get_current_user()
    if not is_admin(current_user):
        raise NoPermissionException('Generate unassigned QR codes for app')
    if not get_app_by_id(app_id):
        raise AppNotFoundException(app_id)
    if mode == 'svg':
        azzert(amount <= 500)  # for db entity put() limit is about 700
        f = _generate_unassigned_qr_codes_svgs_for_app
    else:
        f = _generate_unassigned_qr_codes_excel_for_app

    deferred.defer(f, app_id, amount, current_user.email())


def _generate_unassigned_qr_codes_excel_for_app(app_id, amount, user_email):
    logging.info('Generating %d qr code urls and saving to excel sheet' % amount)
    qr_codes = generate_unassigned_short_urls(app_id, amount)

    solution_server_settings = get_solution_server_settings()

    book = xlwt.Workbook(encoding="utf-8")

    qr_sheet = book.add_sheet('qrcodes')
    base_url = get_server_settings().baseUrl
    for i, short_url in enumerate(qr_codes):
        qr_sheet.write(i, 0, short_url.qr_code_content_with_base_url(base_url))
    excel_file = StringIO()
    book.save(excel_file)
    current_date = format_date(datetime.date.today(), locale=DEFAULT_LANGUAGE)

    subject = 'Generated QR code links (%d) for %s' % (amount, str(app_id))
    from_email = solution_server_settings.shop_export_email
    to_emails = [user_email]
    body_text = 'See attachment for the requested links to the QR codes.'
    attachments = []
    attachments.append(('%s generated QR codes(%d) %s.xls' % (str(app_id), amount, current_date),
                        base64.b64encode(excel_file.getvalue())))
    send_mail(from_email, to_emails, subject, body_text, attachments=attachments)
    
    


def _generate_unassigned_qr_codes_svgs_for_app(app_id, amount, user_email):
    logging.info('Generating %d qr code urls and rendering them as svg' % amount)
    qr_codes = generate_unassigned_short_urls(app_id, amount)
    base_url = get_server_settings().baseUrl
    stream = StringIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for i, short_url in enumerate(qr_codes):
            url = short_url.qr_code_content_with_base_url(base_url)
            qr_content = generate_qr_code(url, None, '000000', None, svg=True)
            zip_file.writestr('qr-%s.svg' % i, qr_content)
    stream.seek(0)
    zip_content = stream.getvalue()
    if DEBUG:
        from google.appengine.tools.devappserver2.python.stubs import FakeFile
        FakeFile.ALLOWED_MODES = frozenset(['a', 'r', 'w', 'rb', 'U', 'rU'])
        with open('qrcodes.zip', 'w') as f:
            f.write(zip_content)
    else:
        solution_server_settings = get_solution_server_settings()
        current_date = format_date(datetime.date.today(), locale=DEFAULT_LANGUAGE)
        subject = 'Generated QR code links (%d) for %s' % (amount, str(app_id))
        from_email = solution_server_settings.shop_export_email
        to_emails = [user_email]
        body_text = 'See attachment for the QR codes in SVG format.'
        attachments = []
        attachments.append(('%s generated QR codes(%d) %s.xls' % (str(app_id), amount, current_date),
                            base64.b64encode(zip_content)))
        send_mail(from_email, to_emails, subject, body_text, attachments=attachments)

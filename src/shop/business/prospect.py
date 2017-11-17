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
import string
import uuid

from babel.dates import format_datetime

from google.appengine.api import search
from google.appengine.ext import db
from mcfw.properties import azzert
from mcfw.rpc import arguments, returns
from mcfw.utils import normalize_search_string
from rogerthat.consts import OFFICIALLY_SUPPORTED_COUNTRIES
from rogerthat.dal import put_and_invalidate_cache
from rogerthat.dal.app import get_app_by_id
from rogerthat.dal.service import get_default_service_identity
from rogerthat.rpc import users
from rogerthat.rpc.service import BusinessException
from rogerthat.translations import DEFAULT_LANGUAGE
from rogerthat.utils import now, send_mail
from rogerthat.utils.location import GeoCodeZeroResultsException, coordinates_to_address, geo_code, \
    address_to_coordinates
from shop.bizz import broadcast_prospect_creation, create_task, broadcast_task_updates
from shop.constants import PROSPECT_INDEX
from shop.models import Prospect, ShopTask, ShopApp, RegioManagerTeam, Customer, Contact
from solution_server_settings import get_solution_server_settings
from solutions.common.bizz import OrganizationType
import xlwt


try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


def add_new_prospect_from_discovery(user_details, steps):
    kwargs = dict()
    simple_step_ids = ('name', 'location-manual')
    for step in steps:
        if step['step_type'] != 'form_step':
            continue

        step_id = step['step_id'][len('message_'):]  # cut off the 'message_' prefix
        if step_id in simple_step_ids:
            if step['form_result'] and step['form_result']['result']:
                value = step['form_result']['result']['value']
            else:
                value = ''
            kwargs[step_id] = value
        else:
            if step_id == 'location':
                if step['form_result']:
                    kwargs['latitude'] = step['form_result']['result']['latitude']
                    kwargs['longitude'] = step['form_result']['result']['longitude']
    if 'location-manual' in kwargs:
        try:
            lat, lon, place_id, postal_code, address = address_to_coordinates(kwargs['location-manual'])
        except GeoCodeZeroResultsException:
            logging.warn('Could not reverse geocode for address %s, no results found', kwargs['location-manual'])
            return
    else:
        lat = kwargs['latitude']
        lon = kwargs['longitude']
        try:
            address, postal_code, place_id = coordinates_to_address(lat, lon)
        except GeoCodeZeroResultsException:
            logging.warn('Could not reverse geocode for coordinates %d %d, no results found', lat, lon)
            return
    name = string.capwords(kwargs['name'])

    app = ShopApp.find_by_postal_code(postal_code)
    azzert(app, 'App not found for postal code %s' % postal_code)
    team = RegioManagerTeam.get_by_app_id(app.app_id)
    assignee = team.support_manager
    azzert(assignee, 'No support manager found for team %s' % team.name)

    def trans():
        prospect = Prospect(key_name=place_id,
                            name=name,
                            app_id=app.app_id,
                            type=[],
                            categories=[u'unclassified'],
                            address=address,
                            geo_point=db.GeoPt(lat, lon),
                            assignee=assignee,
                            status=Prospect.STATUS_ADDED_BY_DISCOVERY,
                            phone=''
                            )
        task = create_task(assignee, Prospect.create_key(place_id), assignee, now() + 86400, ShopTask.TYPE_CALL,
                           app.app_id, ShopTask.STATUS_NEW, address, u'Created prospect via discovery', None, None)
        db.put([prospect, task])
        return prospect

    prospect = db.run_in_transaction(trans)
    re_index_prospect(prospect)
    broadcast_prospect_creation(None, prospect)
    broadcast_task_updates([assignee])
    logging.info('Created new prospect via prospect discovery: %s, %s' % (prospect.name, prospect.address))


@returns()
@arguments(prospect=Prospect)
def re_index_prospect(prospect):
    index = search.Index(name=PROSPECT_INDEX)
    azzert(prospect, 'Prospect not found')
    try:
        index.delete(prospect.id)
    except ValueError:
        pass

    fields = [
        search.AtomField(name='key', value=prospect.id),
        search.TextField(name='name', value=prospect.name),
        search.TextField(name='address', value=prospect.address),
        search.TextField(name='phone', value=prospect.phone),
        search.TextField(name='email', value=prospect.email)
    ]
    index.put(search.Document(doc_id=prospect.id, fields=fields))


@returns([Prospect])
@arguments(query=unicode)
def search_prospects(query):
    """
    Uses the PROSPECT_INDEX search index to search for prospects based on their name, address, phone number and email.
    Args:
        query: The search query

    Returns:
        list(Prospect): List of prospects that match the search query.
    """
    if not query:
        return []
    search_index = search.Index(name=PROSPECT_INDEX)
    q = normalize_search_string(query)
    query = search.Query(query_string=q, options=search.QueryOptions(limit=20))

    search_result = search_index.search(query)
    prospect_keys = [Prospect.create_key(long(result.doc_id) if result.doc_id.isdigit() else result.doc_id) for result
                     in search_result.results]
    return Prospect.get(prospect_keys)


@returns(Prospect)
@arguments(customer=Customer)
def create_prospect_from_customer(customer):
    azzert(customer.prospect_id is None and customer.service_email)

    contact = Contact.get_one(customer.key())
    azzert(contact)

    si = get_default_service_identity(users.User(customer.service_email))

    prospect = Prospect(key_name=str(uuid.uuid4()) + str(uuid.uuid4()))
    prospect.name = customer.name
    prospect.address = ', '.join(filter(None, [customer.address1 + ((' ' + customer.address2) if customer.address2 else ''),
                                               customer.zip_code,
                                               customer.city,
                                               OFFICIALLY_SUPPORTED_COUNTRIES.get(customer.country, customer.country)]))
    prospect.phone = contact.phone_number
    prospect.email = contact.email
    prospect.type = ['establishment']
    if customer.organization_type == OrganizationType.EMERGENCY:
        prospect.type.append('health')
    prospect.customer_id = customer.id
    prospect.status = Prospect.STATUS_CUSTOMER
    prospect.app_id = si.app_id
    
    solution_server_settings = get_solution_server_settings()
    prospect.add_comment(u'Converted customer to prospect', users.User(solution_server_settings.shop_no_reply_email)) 
    try:
        result = geo_code(prospect.address)
    except GeoCodeZeroResultsException:
        try:
            result = geo_code(' '.join(filter(None, [customer.zip_code,
                                                     customer.city,
                                                     OFFICIALLY_SUPPORTED_COUNTRIES.get(customer.country,
                                                                                        customer.country)])))
        except GeoCodeZeroResultsException:
            logging.warn('Could not geo_code customer: %s', db.to_dict(customer))
            return

    prospect.geo_point = db.GeoPt(result['geometry']['location']['lat'],
                                  result['geometry']['location']['lng'])

    customer.prospect_id = prospect.id
    prospect.customer_id = customer.id

    logging.info('Creating prospect: %s', db.to_dict(prospect, dict(prospect_id=prospect.id)))
    put_and_invalidate_cache(customer, prospect)
    return prospect


def format_address(address):
    splitted = [x.strip() for x in address.split(',')]
    if len(splitted) == 3:
        return splitted[0], splitted[1]
    return address, ''


@returns(unicode)
@arguments(prospect_ids=[unicode], do_send_email=bool, recipients=[unicode])
def generate_prospect_export_excel(prospect_ids, do_send_email=True, recipients=None):
    if not prospect_ids:
        raise BusinessException('No prospects to export')
    azzert(not do_send_email or recipients)
    bold_style = xlwt.XFStyle()
    bold_style.font.bold = True
    column_name, column_address, column_city, column_phone, column_status, column_type, column_categories, column_comments = range(8)

    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet('Prospects')
    prospects = Prospect.get(map(Prospect.create_key, prospect_ids))
    app_id = None

    sheet.write(0, column_name, 'Name', bold_style)
    sheet.write(0, column_address, 'Address', bold_style)
    sheet.write(0, column_city, 'City', bold_style)
    sheet.write(0, column_phone, 'Phone', bold_style)
    sheet.write(0, column_status, 'Status', bold_style)
    sheet.write(0, column_type, 'Type', bold_style)
    sheet.write(0, column_categories, 'Category', bold_style)
    sheet.write(0, column_comments, 'Comments', bold_style)
    for i, prospect in enumerate(prospects):
        row = i + 1
        comments_str = '\n'.join(['* %s' % comment.text for comment in prospect.comments])
        sheet.write(row, column_name, prospect.name)
        formatted_address = format_address(prospect.address)
        sheet.write(row, column_address, formatted_address[0])
        sheet.write(row, column_city, formatted_address[1])
        sheet.write(row, column_phone, prospect.phone)
        sheet.write(row, column_status, Prospect.STATUS_TYPES[prospect.status])
        sheet.write(row, column_type, ', '.join(prospect.type))
        sheet.write(row, column_categories, ', '.join(prospect.categories))
        sheet.write(row, column_comments, comments_str)
        sheet.col(column_name).width = 5000
        sheet.col(column_address).width = 5000
        sheet.col(column_phone).width = 5000
        sheet.col(column_status).width = 5000
        sheet.col(column_type).width = 10000
        sheet.col(column_categories).width = 10000
        sheet.col(column_comments).width = 20000
        if not app_id:
            app_id = prospect.app_id
    excel = StringIO()
    book.save(excel)
    excel_string = excel.getvalue()

    if do_send_email:
        app = get_app_by_id(app_id)
        solution_server_settings = get_solution_server_settings()
        current_date = format_datetime(datetime.datetime.now(), locale=DEFAULT_LANGUAGE)
        subject = 'Exported prospects of %s %s' % (app.name, current_date)
        from_email = solution_server_settings.shop_export_email
        to_emails = recipients
        body_text = 'See attachment for the exported prospects'
        
        attachments = []
        attachments.append(('Prospects %s %s.xls' % (app.name, current_date),
                            base64.b64encode(excel_string)))
        
        send_mail(from_email, to_emails, subject, body_text, attachments=attachments)
    return excel_string

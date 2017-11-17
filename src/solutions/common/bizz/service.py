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

import logging

from google.appengine.ext import db
from google.appengine.ext.deferred import deferred
from mcfw.rpc import serialize_complex_value

from rogerthat.dal.service import get_service_identity
from rogerthat.consts import DAY, SCHEDULED_QUEUE
from rogerthat.models import ServiceIdentity, ServiceProfile
from rogerthat.to.service import UserDetailsTO
from rogerthat.utils.service import create_service_identity_user

from rogerthat.utils import channel, now, send_mail
from rogerthat.utils.transactions import run_in_xg_transaction
from shop.models import Product, RegioManagerTeam
from solutions import SOLUTION_COMMON, translate as common_translate
from solutions.common.bizz import SolutionModule, DEFAULT_BROADCAST_TYPES, ASSOCIATION_BROADCAST_TYPES
from solutions.common.bizz.createsend import send_smart_email
from solutions.common.bizz.inbox import add_solution_inbox_message, create_solution_inbox_message
from solutions.common.dal import get_solution_settings, get_solution_settings_or_identity_settings
from solutions.common.to import SolutionInboxMessageTO


# signup smart emails with the countdown (seconds) they should be sent after
# successfull registration
SMART_EMAILS = {
    '8dd5fe5f-02eb-40f9-b9fa-9a48d52952b4': 2 * 60,
    'f4e19feb-f394-47b4-880f-f7a5a0c163ac': 2 * DAY,
    'e6b456af-a811-4540-903c-5135cd6e4802': 4 * DAY,
    'c87c3b2c-e1e8-4680-914e-6f81f2bd37f5': 6 * DAY,
}


def get_allowed_broadcast_types(city_customer):
    """
    Args:
        city_customer (Customer)
    """
    if city_customer.can_only_edit_organization_type(ServiceProfile.ORGANIZATION_TYPE_NON_PROFIT):
        return ASSOCIATION_BROADCAST_TYPES
    else:
        return DEFAULT_BROADCAST_TYPES


def get_allowed_modules(city_customer):
    """
    Args:
        city_customer (Customer)
    """
    if city_customer.can_only_edit_organization_type(ServiceProfile.ORGANIZATION_TYPE_NON_PROFIT):
        return SolutionModule.ASSOCIATION_MODULES
    else:
        return SolutionModule.POSSIBLE_MODULES


def filter_modules(city_customer, modules, broadcast_types):
    """Given a modules list, it will return the mandatory and allowed modules and discard others.

    Args:
        city_customer (Customer): city customer
        modules (list of unicode)
        broadcast_type (list of unicode)
    """
    mods = [m for m in SolutionModule.MANDATORY_MODULES]
    mods.extend([m for m in modules if m in get_allowed_modules(city_customer)])
    modules = list(set(mods))

    if SolutionModule.BROADCAST in modules and not broadcast_types:
        modules.remove(SolutionModule.BROADCAST)

    return modules


def create_customer_with_service(city_customer, customer, service, name, address1, address2, zip_code,
                                 city, language,  organization_type, vat, website=None, facebook_page=None, force=False):
    """Given a customer and a service, will create the customer, contact and order."""
    from shop.bizz import put_customer_with_service
    customer_id = customer.id if customer else None
    if not customer and organization_type not in city_customer.editable_organization_types:
        organization_type = city_customer.editable_organization_types[0]

    if city_customer.can_only_edit_organization_type(ServiceProfile.ORGANIZATION_TYPE_NON_PROFIT):
        product_code = Product.PRODUCT_SUBSCRIPTION_ASSOCIATION
    else:
        product_code = Product.PRODUCT_FREE_SUBSCRIPTION

    team = RegioManagerTeam.get_by_id(city_customer.team_id)
    if not team.legal_entity.is_mobicage:
        if product_code == Product.PRODUCT_SUBSCRIPTION_ASSOCIATION:
            from shop.products import create_sjup_product
            p = create_sjup_product(team.legal_entity_id, "%s." % team.legal_entity_id)
            p.put()
            product_code = p.code
        else:
            from shop.products import create_free_product
            p = create_free_product(team.legal_entity_id, "%s." % team.legal_entity_id)
            p.put()
            product_code = p.code

    return put_customer_with_service(service, name, address1, address2, zip_code, city, city_customer.country, language,
                                     organization_type, vat, city_customer.team_id, product_code, customer_id,
                                     website, facebook_page, force=force)


def put_customer_service(customer, service, search_enabled, skip_module_check, skip_email_check, rollback=False):
    """Put the service, if rolllback is set, it will remove the customer in case of failure."""
    from shop.bizz import put_service
    customer_key = customer.key()

    def trans():
        put_service(customer, service, skip_module_check=skip_module_check, search_enabled=search_enabled,
                    skip_email_check=skip_email_check)

    try:
        run_in_xg_transaction(trans)
    except Exception as e:
        if rollback:
            db.delete(db.GqlQuery("SELECT __key__ WHERE ANCESTOR IS KEY('%s')" % customer_key).fetch(None))
        logging.debug('Unhandled exception: %s', e, exc_info=True)
        raise e


def new_inbox_message(sln_settings, message, parent_chat_key=None, service_identity=None, **kwargs):
    service_identity = service_identity or ServiceIdentity.DEFAULT
    service_user = sln_settings.service_user
    language = sln_settings.main_language
    si = get_service_identity(create_service_identity_user(service_user, service_identity))
    user_details = UserDetailsTO.create(service_user.email(), si.name, language, si.avatarUrl, si.app_id)

    if not parent_chat_key:
        category = kwargs.get('category')
        category_key = kwargs.get('category_key')
        reply_enabled = kwargs.get('reply_enabled', False)
        message = create_solution_inbox_message(service_user, service_identity, category, category_key,
                                                True, [user_details], now(), message, reply_enabled)
    else:
        message, _ = add_solution_inbox_message(service_user, parent_chat_key, False, [user_details], now(),
                                                message, **kwargs)
    return message


def send_inbox_message_update(sln_settings, message, service_identity=None):
    service_user = sln_settings.service_user
    sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)
    message_to = SolutionInboxMessageTO.fromModel(message, sln_settings, sln_i_settings, True)
    data = serialize_complex_value(message_to, SolutionInboxMessageTO, False)
    channel.send_message(service_user, u'solutions.common.messaging.update',
                         message=data, service_identity=service_identity)


def _send_signup_status_inbox_reply(sln_settings, parent_chat_key, approved, reason):
    lang = sln_settings.main_language
    if approved:
        message = common_translate(lang, SOLUTION_COMMON, u'approved')
    else:
        message = common_translate(lang, SOLUTION_COMMON, u'signup_request_denial_reason', reason=reason)

    inbox_message = new_inbox_message(sln_settings, message, parent_chat_key,
                                      mark_as_read=not approved,
                                      mark_as_trashed=approved)
    return inbox_message


def _schedule_signup_smart_emails(customer_email):
    for email_id, countdown in SMART_EMAILS.iteritems():
        deferred.defer(send_smart_email, email_id, [customer_email],
                       _countdown=countdown,
                       _queue=SCHEDULED_QUEUE)


def _send_approved_signup_email(city_customer, signup, lang):
    def trans(term, *args, **kwargs):
        return common_translate(lang, SOLUTION_COMMON, unicode(term), *args, **kwargs)

    subject = u'{} - {}'.format(trans('our-city-app'), trans('signup_application'))
    message = trans('signup_approval_email_message', name=signup.customer_name, city_name=city_customer.name)

    city_from = '%s <%s>' % (city_customer.name, city_customer.user_email)
    send_mail(city_from, signup.customer_email, subject, message)
    if signup.parent().language == 'nl':
        _schedule_signup_smart_emails(signup.customer_email)


def _send_denied_signup_email(city_customer, signup, lang, reason):
    subject = common_translate(city_customer.language, SOLUTION_COMMON,
                               u'signup_request_denied_by_city', city=city_customer.name)
    message = common_translate(city_customer.language, SOLUTION_COMMON,
                               u'signup_request_denial_reason', reason=reason)

    city_from = '%s <%s>' % (city_customer.name, city_customer.user_email)
    send_mail(city_from, signup.customer_email, subject, message)


def set_customer_signup_status(city_customer, signup, approved, reason=None):
    """Set the customer signup to done and move the inbox message to trash"""

    def trans():
        to_put = [signup]
        inbox_message = None
        signup.done = approved
        if signup.inbox_message_key:
            inbox_message = db.get(signup.inbox_message_key)
            if inbox_message:
                if approved:
                    inbox_message.trashed = True
                else:
                    inbox_message.read = True
                to_put.append(inbox_message)

        db.put(to_put)
        return inbox_message

    message = run_in_xg_transaction(trans)
    if message:
        service_user = signup.parent().service_user
        sln_settings = get_solution_settings(service_user)

        if approved:
            _send_approved_signup_email(city_customer, signup, sln_settings.main_language)
        else:
            _send_denied_signup_email(city_customer, signup, sln_settings.main_language, reason)

        status_reply_message = _send_signup_status_inbox_reply(sln_settings, signup.inbox_message_key, approved, reason)
        send_signup_update_messages(sln_settings, message, status_reply_message)


def send_signup_update_messages(sln_settings, *messages):
    service_identity = ServiceIdentity.DEFAULT
    sln_i_settings = get_solution_settings_or_identity_settings(sln_settings, service_identity)

    sm_data = [{u'type': u'solutions.common.customer.signup.update'}]
    for message in messages:
        message_to = SolutionInboxMessageTO.fromModel(message, sln_settings, sln_i_settings, True)
        sm_data.append({
            u'type': u'solutions.common.messaging.update',
            u'message': serialize_complex_value(message_to, SolutionInboxMessageTO, False)
        })

    channel.send_message(sln_settings.service_user, sm_data, service_identity=service_identity)

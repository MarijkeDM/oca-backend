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
from types import NoneType

from google.appengine.ext import db

from mcfw.properties import azzert
from mcfw.restapi import rest
from mcfw.rpc import returns, arguments
from rogerthat.models import ServiceProfile
from rogerthat.rpc import users
from rogerthat.rpc.service import BusinessException
from rogerthat.service.api import system
from rogerthat.to import ReturnStatusTO, RETURNSTATUS_TO_SUCCESS
from rogerthat.to.messaging import KeyValueTO
from rogerthat.utils.channel import send_message_to_session
from shop.bizz import create_customer_service_to, audit_log, dict_str_for_audit_log, search_customer, \
    update_contact
from shop.business.order import cancel_subscription
from shop.dal import get_customer
from shop.exceptions import DuplicateCustomerNameException, NotOperatingInCountryException, EmptyValueException, \
    InvalidEmailFormatException, NoPermissionException, ServiceNameTooBigException
from shop.jobs.migrate_user import migrate as migrate_user
from shop.models import Customer, Contact
from shop.to import CustomerTO
from solutions import translate, SOLUTION_COMMON
from solutions.common.bizz import OrganizationType, SolutionModule
from solutions.common.bizz.service import create_customer_with_service, filter_modules, get_allowed_broadcast_types, \
    get_allowed_modules, put_customer_service, set_customer_signup_status
from solutions.common.dal import get_solution_settings
from solutions.common.models import SolutionSettings
from solutions.common.to import ServiceTO
from solutions.common.to.qanda import ModuleTO
from solutions.common.to.services import CreateServiceStatusTO, ModuleAndBroadcastTypesTO, ServiceStatisticTO, \
    ServicesTO, ServiceListTO
from solutions.flex.bizz import get_services_statistics


@rest("/common/services/get_defaults", "get", read_only_access=True)
@returns(ModuleAndBroadcastTypesTO)
@arguments()
def get_modules_and_broadcast_types():
    city_service_user = users.get_current_user()
    city_customer = get_customer(city_service_user)
    lang = get_solution_settings(city_service_user).main_language
    modules = [ModuleTO.fromArray([k, SolutionModule.get_translated_description(lang, k)]) for k in
               get_allowed_modules(city_customer)]
    broadcast_types = [translate(lang, SOLUTION_COMMON, k) for k in get_allowed_broadcast_types(city_customer)]
    organization_types = [
        KeyValueTO(unicode(t), ServiceProfile.localized_singular_organization_type(t, lang, city_customer.app_id))
        for t in city_customer.editable_organization_types]
    return ModuleAndBroadcastTypesTO(modules, broadcast_types, organization_types)


@rest('/common/customer/signup/get_defaults', 'get')
@returns(ModuleAndBroadcastTypesTO)
@arguments(signup_key=unicode)
def rest_signup_get_modules_and_broadcast_types(signup_key):
    modules_and_broadcast_types = get_modules_and_broadcast_types()
    preselected_modules = []

    signup = db.get(signup_key)
    if signup:
        preselected_modules = signup.modules

    if preselected_modules:
        for module in modules_and_broadcast_types.modules:
            if module.key in preselected_modules:
                module.is_default = True

    return modules_and_broadcast_types


@rest("/common/services/search", "post")
@returns([CustomerTO])
@arguments(search_string=unicode)
def search_services(search_string):
    city_service_user = users.get_current_user()
    city_sln_settings = get_solution_settings(city_service_user)
    si = system.get_identity()
    app_id = si.app_ids[0]
    city_customer = get_customer(city_service_user)
    azzert(city_sln_settings.can_edit_services(city_customer))

    customers = []
    # if app id is set, the customer should have a service
    for c in search_customer(search_string, [app_id], None):
        # exclude own service and disabled services
        if c.service_email == city_service_user.email() or c.service_disabled_at:
            continue
        customers.append(CustomerTO.fromCustomerModel(c, False, False))

    return sorted(customers, key=lambda c: c.name.lower())


@rest("/common/services/get_all", "get", read_only_access=True)
@returns(ServicesTO)
@arguments(organization_type=int, cursor=unicode, limit=int)
def get_services(organization_type, cursor=None, limit=50):
    city_service_user = users.get_current_user()
    si = system.get_identity()
    # get all the services in this city
    app_id = si.app_ids[0]
    city_customer = get_customer(city_service_user)
    azzert(organization_type in city_customer.editable_organization_types)
    service_customers_qry = Customer.list_enabled_by_organization_type_in_app(app_id, organization_type)
    service_customers_qry.with_cursor(cursor)
    service_customers = service_customers_qry.fetch(limit)
    new_cursor = unicode(service_customers_qry.cursor())

    services = []
    statistics = get_services_statistics(app_id)
    sln_settings_keys = [SolutionSettings.create_key(city_service_user)]
    for customer in service_customers:
        if not customer.service_email:
            logging.error('Customer %d (%s) has default_app_id, but has no service!', customer.id, customer.name)
        elif customer.app_id == app_id:
            sln_settings_keys.append(SolutionSettings.create_key(users.User(customer.service_email)))
    sln_settings_list = db.get(sln_settings_keys)
    city_sln_settings = sln_settings_list.pop(0)  # type: SolutionSettings
    azzert(city_sln_settings.can_edit_services(city_customer))
    city_service_email = city_sln_settings.service_user.email()
    for customer in service_customers:
        service_email = customer.service_email
        # Exclude the city app's own service
        if customer.app_id == app_id and service_email != city_service_email:
            future_events_count = 0
            broadcasts_last_month = 0
            static_content_count = 0
            last_unanswered_question_timestamp = 0
            modules = []
            for sln_settings in sln_settings_list:
                if sln_settings.key().name() == service_email:
                    modules = sln_settings.modules
            if statistics:
                for mail in statistics.customer_emails:
                    if mail == service_email:
                        index = statistics.customer_emails.index(mail)
                        future_events_count = statistics.future_events_count[index]
                        broadcasts_last_month = statistics.broadcasts_last_month[index]
                        static_content_count = statistics.static_content_count[index]
                        last_unanswered_question_timestamp = statistics.last_unanswered_questions_timestamps[index]

            statistic = ServiceStatisticTO.create(future_events_count, broadcasts_last_month, static_content_count,
                                                  last_unanswered_question_timestamp)
            services.append(ServiceListTO(service_email, customer.name, statistic, modules, customer.id))
    generated_on = statistics.generated_on if statistics else None
    return ServicesTO(sorted(services, key=lambda x: x.name.lower()), generated_on, new_cursor)


@rest("/common/services/get", "get", read_only_access=True)
@returns((ServiceTO, ReturnStatusTO))
@arguments(service_email=unicode)
def get_service(service_email):
    city_service_user = users.get_current_user()
    city_customer = get_customer(city_service_user)
    service_user = users.User(email=service_email)
    customer = Customer.get_by_service_email(service_email)
    if not city_customer.can_edit_service(customer):
        logging.warn(u'Service %s tried to save service information for customer %d', city_service_user, customer.id)
        lang = get_solution_settings(city_service_user).main_language
        return ReturnStatusTO.create(False, translate(lang, SOLUTION_COMMON, 'no_permission'))
    contact = Contact.get_one(customer.key())
    solution_settings = get_solution_settings(service_user)
    return ServiceTO(customer.id, customer.name, customer.address1, customer.address2, customer.zip_code, customer.city,
                     customer.user_email, contact.phone_number, solution_settings.main_language,
                     solution_settings.modules, solution_settings.broadcast_types, customer.organization_type,
                     customer.vat, customer.website, customer.facebook_page)


@rest("/common/services/put", "post", read_only_access=False)
@returns(CreateServiceStatusTO)
@arguments(name=unicode, address1=unicode, address2=unicode, zip_code=unicode, city=unicode, user_email=unicode,
           telephone=unicode, language=unicode, modules=[unicode], broadcast_types=[unicode],
           customer_id=(int, long, NoneType), organization_type=(int, long), vat=unicode, website=unicode,
           facebook_page=unicode, force=bool)
def rest_put_service(name, address1, address2, zip_code, city, user_email, telephone, language, modules,
                     broadcast_types, customer_id=None, organization_type=OrganizationType.PROFIT, vat=None,
                     website=None, facebook_page=None, force=False):
    city_service_user = users.get_current_user()
    city_customer = get_customer(city_service_user)
    city_sln_settings = get_solution_settings(city_service_user)
    lang = city_sln_settings.main_language
    customer = Customer.get_by_id(customer_id) if customer_id else None
    # check if the current user is in fact a city app
    if customer and not city_customer.can_edit_service(customer):
        logging.warn(u'Service %s tried to save service information for customer %d', city_service_user, customer.id)
        return CreateServiceStatusTO.create(False, translate(lang, SOLUTION_COMMON, 'no_permission'))

    error_msg = warning_msg = None
    email_changed = False
    is_new_service = False

    try:
        modules = filter_modules(city_customer, modules, broadcast_types)
        service = create_customer_service_to(name, address1, address1, city, zip_code, user_email, language, city_sln_settings.currency,
                                             telephone, organization_type, city_customer.app_id, broadcast_types, modules)
        (customer, email_changed, is_new_service) \
            = create_customer_with_service(city_customer, customer, service, name, address1, address2, zip_code, city,
                                           language, organization_type, vat, website, facebook_page, force=force)
    except EmptyValueException as ex:
        val_name = translate(lang, SOLUTION_COMMON, ex.value_name)
        error_msg = translate(lang, SOLUTION_COMMON, 'empty_field_error', field_name=val_name)
    except ServiceNameTooBigException:
        error_msg = translate(lang, SOLUTION_COMMON, 'name_cannot_be_bigger_than_n_characters', n=50)
    except DuplicateCustomerNameException as ex:
        warning_msg = translate(lang, SOLUTION_COMMON, 'duplicate_customer', customer_name=ex.name)
    except NoPermissionException:
        error_msg = translate(lang, SOLUTION_COMMON, 'no_permission')
    except InvalidEmailFormatException as ex:
        error_msg = translate(lang, SOLUTION_COMMON, 'invalid_email_format', email=ex.email)
    except NotOperatingInCountryException as ex:
        error_msg = translate(lang, SOLUTION_COMMON, 'not_operating_in_country', country=ex.country)
    except BusinessException as ex:
        logging.debug('Failed to create service, BusinessException', exc_info=True)
        error_msg = ex.message
    except:
        logging.exception('Failed to create service')
        error_msg = translate(lang, SOLUTION_COMMON, 'failed_to_create_service')
    finally:
        if error_msg:
            return CreateServiceStatusTO.create(False, error_msg)
        elif warning_msg:
            return CreateServiceStatusTO.create(False, warningmsg=warning_msg)

    try:
        put_customer_service(customer, service, skip_module_check=True, search_enabled=False,
                             skip_email_check=True, rollback=is_new_service)
    except EmptyValueException as ex:
        val_name = translate(lang, SOLUTION_COMMON, ex.value_name)
        error_msg = translate(lang, SOLUTION_COMMON, 'empty_field_error', field_name=val_name)
    except:
        logging.exception('Could not save service service information')
        error_msg = translate(lang, SOLUTION_COMMON, 'failed_to_create_service')
    finally:
        if error_msg:
            if is_new_service:
                logging.warn('Failed to save new service service information, changes would be reverted...')
            return CreateServiceStatusTO.create(False, error_msg)
        else:
            if email_changed:
                migrate_user(users.User(customer.user_email), users.User(customer.user_email), users.User(user_email),
                             customer.service_email)
                customer.user_email = user_email
                customer.put()
            variables = dict_str_for_audit_log({
                'user_email': user_email,
                'modules': modules,
            })
            audit_log(customer_id, 'put_service', variables, city_service_user)
            return CreateServiceStatusTO.create()


@rest('/common/services/delete', 'post', read_only_access=False)
@returns(ReturnStatusTO)
@arguments(service_email=unicode)
def rest_delete_service(service_email):
    city_service_user = users.get_current_user()
    city_customer = get_customer(city_service_user)
    customer = Customer.get_by_service_email(service_email)
    if not city_customer.can_edit_service(customer):
        lang = get_solution_settings(city_service_user).main_language
        logging.warn(u'Service %s tried to save service information for customer %d', city_service_user, customer.id)
        return ReturnStatusTO.create(False, translate(lang, SOLUTION_COMMON, 'no_permission'))
    cancel_subscription(customer.id, Customer.DISABLED_REASONS[Customer.DISABLED_ASSOCIATION_BY_CITY], True)
    session = users.get_current_session()
    service_identity = session.service_identity
    send_message_to_session(city_service_user, session,
                            [{u"type": u"solutions.common.services.deleted",
                              u'service_email': service_email,
                              u'service_organization_type': customer.organization_type}],
                            si=service_identity)
    return RETURNSTATUS_TO_SUCCESS


def _fill_signup_data(signup, *prop_names):
    """Old signups may have data stored in customer_<prop_name> instead of company_<prop-name>"""
    for prop_name in prop_names:
        company_prop_name = 'company_' + prop_name
        current_value = getattr(signup, company_prop_name)
        if not current_value:
            setattr(signup, company_prop_name, getattr(signup, 'customer_' + prop_name))


def _update_signup_contact(customer, signup):
    contact = Contact.get_one(customer.key())
    first_name, _, last_name = signup.customer_name.partition(' ')
    update_contact(customer.id, contact.id, first_name, last_name, signup.customer_email,
                   signup.customer_telephone)


@rest('/common/signup/services/create', 'post', read_only_access=False)
@returns(CreateServiceStatusTO)
@arguments(signup_key=unicode, modules=[unicode], broadcast_types=[unicode], force=bool)
def rest_create_service_from_signup(signup_key, modules=None, broadcast_types=None, force=False):
    signup = db.get(signup_key)

    city_service_user = users.get_current_user()
    city_customer = get_customer(city_service_user)
    city_sln_settings = get_solution_settings(city_service_user)
    lang = city_sln_settings.main_language

    azzert(city_sln_settings.can_edit_services(city_customer))
    if not signup:
        return CreateServiceStatusTO.create(False, translate(lang, SOLUTION_COMMON, 'signup_not_found'))

    error_msg = warning_msg = None
    try:
        if not modules:
            modules = signup.modules

        if not broadcast_types:
            broadcast_types = []

        _fill_signup_data(signup, 'email', 'telephone', 'website', 'facebook_page')
        modules = filter_modules(city_customer, modules, broadcast_types)
        service = create_customer_service_to(signup.company_name, signup.company_address1, None, signup.company_city,
                                             signup.company_zip_code, signup.company_email, lang, city_sln_settings.currency,
                                             signup.company_telephone, signup.company_organization_type, city_customer.app_id,
                                             broadcast_types, modules=modules)
        customer = create_customer_with_service(city_customer, None, service, signup.company_name,
                                                signup.customer_address1, None, signup.company_zip_code,
                                                signup.company_city, lang, signup.company_organization_type,
                                                signup.company_vat, signup.company_website,
                                                signup.company_facebook_page, force=force)[0]

        # update the contact, as it should be created by now
        _update_signup_contact(customer, signup)

    except EmptyValueException as ex:
        val_name = translate(lang, SOLUTION_COMMON, ex.value_name)
        error_msg = translate(lang, SOLUTION_COMMON, 'empty_field_error', field_name=val_name)
    except ServiceNameTooBigException:
        error_msg = translate(lang, SOLUTION_COMMON, 'name_cannot_be_bigger_than_n_characters', n=50)
    except DuplicateCustomerNameException as ex:
        warning_msg = translate(lang, SOLUTION_COMMON, 'duplicate_customer', customer_name=ex.name)
    except NoPermissionException:
        error_msg = translate(lang, SOLUTION_COMMON, 'no_permission')
    except InvalidEmailFormatException as ex:
        error_msg = translate(lang, SOLUTION_COMMON, 'invalid_email_format', email=ex.email)
    except NotOperatingInCountryException as ex:
        error_msg = translate(lang, SOLUTION_COMMON, 'not_operating_in_country', country=ex.country)
    except BusinessException as ex:
        logging.debug('Failed to create service, BusinessException', exc_info=True)
        error_msg = ex.message
    except:
        logging.exception('Failed to create service')
        error_msg = translate(lang, SOLUTION_COMMON, 'failed_to_create_service')
    finally:
        if error_msg:
            return CreateServiceStatusTO.create(False, error_msg)
        elif warning_msg:
            return CreateServiceStatusTO.create(False, warningmsg=warning_msg)
        else:
            try:
                put_customer_service(customer, service, skip_module_check=True, search_enabled=False,
                                     skip_email_check=True, rollback=True)
            except EmptyValueException as ex:
                val_name = translate(lang, SOLUTION_COMMON, ex.value_name)
                error_msg = translate(lang, SOLUTION_COMMON, 'empty_field_error', field_name=val_name)
            except:
                logging.exception('Could not save service service information')
                error_msg = translate(lang, SOLUTION_COMMON, 'failed_to_create_service')
            finally:
                if error_msg:
                    return CreateServiceStatusTO.create(False, error_msg)
                else:
                    set_customer_signup_status(city_customer, signup, approved=True)
                    return CreateServiceStatusTO.create(success=True)

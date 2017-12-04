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

from mcfw.restapi import rest_functions
from rogerthat.wsgi import RogerthatWSGIApplication
from shop import view
from shop.handlers import StaticFileHandler, GenerateQRCodesHandler
from shop.view import BizzAdminHandler, OrdersHandler, OrderPdfHandler, ChargesHandler, QuestionsHandler, \
    QuestionsDetailHandler, InvoicePdfHandler, authorize_manager, FindProspectsHandler, ProspectsHandler, \
    HistoryTasksHandler, ProspectsUploadHandler, LoyaltySlidesHandler, UploadLoyaltySlideHandler, \
    OpenInvoicesHandler, TasksHandler, LoginAsCustomerHandler, RegioManagersHandler, ExportEmailAddressesHandler, \
    LoyaltySlidesNewOrderHandler, UploadLoyaltySlideNewOrderHandler, CustomersHandler, HintsHandler, \
    SalesStatisticsHandler, OrderableAppsHandler, SignupAppsHandler, shopOauthDecorator, ShopLogoutHandler, \
    ExpiredSubscriptionsHandler, LegalEntityHandler, CityVouchersHandler
from solutions.djmatic import restapi_overview
from solutions.djmatic.handlers import DJMaticOverviewHandler

handlers = [
    ('/djmatic_overview', DJMaticOverviewHandler),
    ('/internal/shop/?', BizzAdminHandler),
    ('/internal/shop/logout', ShopLogoutHandler),
    ('/internal/shop/invoices/open', OpenInvoicesHandler),
    ('/internal/shop/orders', OrdersHandler),
    ('/internal/shop/order/pdf', OrderPdfHandler),
    ('/internal/shop/charges', ChargesHandler),
    ('/internal/shop/prospects', ProspectsHandler),
    ('/internal/shop/prospects_find', FindProspectsHandler),
    ('/internal/shop/prospects/upload', ProspectsUploadHandler),
    ('/internal/shop/history/tasks', HistoryTasksHandler),
    ('/internal/shop/regio_managers', RegioManagersHandler),
    ('/internal/shop/tasks', TasksHandler),
    ('/internal/shop/questions', QuestionsHandler),
    ('/internal/shop/questions/(.*)', QuestionsDetailHandler),
    ('/internal/shop/invoice/pdf', InvoicePdfHandler),
    ('/internal/shop/loyalty/slides', LoyaltySlidesHandler),
    ('/internal/shop/loyalty/slides/new_order', LoyaltySlidesNewOrderHandler),
    ('/internal/shop/loyalty/slide/upload', UploadLoyaltySlideHandler),
    ('/internal/shop/loyalty/slide/new_order/upload', UploadLoyaltySlideNewOrderHandler),
    ('/internal/shop/city/vouchers', CityVouchersHandler),
    ('/internal/shop/login_as', LoginAsCustomerHandler),
    ('/internal/shop/contacts_export', ExportEmailAddressesHandler),
    ('/internal/shop/customers', CustomersHandler),
    ('/internal/shop/expired_subscriptions', ExpiredSubscriptionsHandler),
    ('/internal/shop/legal_entities', LegalEntityHandler),
    ('/internal/shop/stats', SalesStatisticsHandler),
    ('/internal/shop/hints', HintsHandler),
    ('/internal/shop/apps', OrderableAppsHandler),
    ('/internal/shop/signup_apps', SignupAppsHandler),
    ('/internal/shop/stat/(.*)', StaticFileHandler),
    ('/internal/shop/customers/generate-qr', GenerateQRCodesHandler),
    (shopOauthDecorator.callback_path, shopOauthDecorator.callback_handler())  # /shop/oauth2callback
]
handlers.extend(rest_functions(restapi_overview))
handlers.extend(rest_functions(view, authorized_function=authorize_manager))

app = RogerthatWSGIApplication(handlers, uses_session=False, name="main_google_authenticated", google_authenticated=True)

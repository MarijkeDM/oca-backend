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

from webapp2_extras.routes import RedirectRoute

from bob.handlers import SetIosAppIdHandler
from mcfw.consts import NOT_AUTHENTICATED
from mcfw.restapi import rest_functions
from rogerthat.handlers.blobstore import CloudStorageBlobstoreHandler
from rogerthat.wsgi import RogerthatWSGIApplication
from server_migration import ServicerMigrationHandler
from shop.callbacks import ProspectDiscoverCallbackHandler
from shop.handlers import ExportInvoicesHandler, ExportProductsHandler, ProspectCallbackHandler, \
    BeaconsAppValidateUrlHandler, CustomerMapHandler, CustomerMapServicesHandler, CustomerSigninHandler, \
    CustomerSignupHandler, CustomerSetPasswordHandler, CustomerResetPasswordHandler
import shop.handlers
from solutions.common.handlers.callback.twitter import SolutionsCallbackTwitterHandler
from solutions.common.handlers.launcher import GetOSALaucherAppsHandler, GetOSALaucherAppHandler
from solutions.common.handlers.loyalty import LoyaltySlideDownloadHandler, LoyaltyNoMobilesUnsubscribeEmailHandler, \
    LoyaltyLotteryConfirmWinnerHandler
from solutions.common.handlers.menu import ViewMenuItemImageHandler
import solutions.common.restapi
import solutions.djmatic.api
from solutions.djmatic.handlers import DJMaticHomeHandler
from solutions.flex.handlers import FlexHomeHandler
from version.handler import VersionsHandler

handlers = [
    ('/djmatic/', DJMaticHomeHandler),
    ('/flex/', FlexHomeHandler),
    ('/unauthenticated/loyalty/slide', LoyaltySlideDownloadHandler),
    ('/unauthenticated/loyalty/no_mobiles/unsubscribe_email', LoyaltyNoMobilesUnsubscribeEmailHandler),
    ('/unauthenticated/loyalty/no_mobiles/lottery_winner', LoyaltyLotteryConfirmWinnerHandler),
    ('/unauthenticated/osa/launcher/apps', GetOSALaucherAppsHandler),
    ('/unauthenticated/osa/launcher/app/download', GetOSALaucherAppHandler),
    ('/unauthenticated/osa/callback/twitter', SolutionsCallbackTwitterHandler),
    ('/bob/api/apps/set_ios_app_id', SetIosAppIdHandler),
    ('/solutions/djmatic/api/1', solutions.djmatic.api.DJMaticApiHandler),
    ('/shop/invoices/export', ExportInvoicesHandler),
    ('/shop/products/export', ExportProductsHandler),
    ('/shop/prospects/callback', ProspectCallbackHandler),
    ('/shop/prospects/discover/callback', ProspectDiscoverCallbackHandler),
    ('/shop/beacons/app/validate_url', BeaconsAppValidateUrlHandler),
    ('/customers/map/([a-z-_]+)/services', CustomerMapServicesHandler),
    ('/customers/map/([a-z-_]+)', CustomerMapHandler),
    ('/customers/setpassword', CustomerSetPasswordHandler),
    ('/customers/resetpassword', CustomerResetPasswordHandler),
    RedirectRoute('/customers/signin', name='customers_login', handler=CustomerSigninHandler, strict_slash=True),
    RedirectRoute('/customers/signup', name='signup', handler=CustomerSignupHandler, strict_slash=True),
    RedirectRoute('/ourcityapp', name='ourcityapp', redirect_to_name='customers_login', strict_slash=True),
    ('/solutions/common/public/attachment/view/(.*)', CloudStorageBlobstoreHandler),
    ('/solutions/common/public/menu/image/(.*)', ViewMenuItemImageHandler),
    ('/server_migration/(.*)', ServicerMigrationHandler),
    ('/version', VersionsHandler)
]

handlers.extend(rest_functions(solutions.common.restapi, authentication=NOT_AUTHENTICATED))
handlers.extend(rest_functions(shop.handlers, authentication=NOT_AUTHENTICATED))

app = RogerthatWSGIApplication(handlers, name="main_unauthenticated")

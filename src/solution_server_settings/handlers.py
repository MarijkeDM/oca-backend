# -*- coding: utf-8 -*-
# Copyright 2016 Mobicage NV
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
# @@license_version:1.1@@

import logging
import os
import urllib

from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from rogerthat.models.utils import model_to_yaml, populate_model_by_yaml
from rogerthat.rpc.service import BusinessException
from solution_server_settings import get_solution_server_settings


class SolutionServerSettingsHandler(webapp.RequestHandler):

    def redirect(self, url, permanent=False):
        return super(SolutionServerSettingsHandler, self).redirect(str(url), permanent)

    def get(self):
        result = self.request.get("result", "")
        settings = get_solution_server_settings()
        path = os.path.join(os.path.dirname(__file__), 'settings.html')
        self.response.out.write(template.render(path, dict(result=result,
                                                           settings=model_to_yaml(settings))))

    def post(self):
        settings_yaml = self.request.get("settings", "")

        try:
            settings = populate_model_by_yaml(get_solution_server_settings(), settings_yaml)
            settings.put()

            result = "Settings saved successfully!"
        except Exception, e:
            if not isinstance(e, BusinessException):
                logging.exception('Error happened while updating setting')
            result = 'ERROR: %s' % e.message

        self.redirect("/admin/settings?" + urllib.urlencode(dict(result=result)))

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
from lxml import html

from google.appengine.api import urlfetch
from google.appengine.ext import db, deferred

from solutions.common.cron.news import BROADCAST_TYPE_NEWS, transl, create_news_item
from solutions.common.dal import get_solution_settings
from solutions.common.models import SolutionNewsScraperSettings


def check_for_news(service_user):
    deferred.defer(_check_for_news, service_user)

def _check_for_news(service_user):
    sln_settings = get_solution_settings(service_user)
    if BROADCAST_TYPE_NEWS not in sln_settings.broadcast_types:
        logging.error("check_for_news_in_be_lede failed no broadcast type found with name '%s'", BROADCAST_TYPE_NEWS)
        return

    broadcast_type = transl(BROADCAST_TYPE_NEWS, sln_settings.main_language)

    url = u"http://www.lede.be/nieuwsoverzicht.Aspx"
    response = urlfetch.fetch(url, deadline=60)
    if response.status_code != 200:
        logging.error("Could not check for news in be_lede.\n%s" % response.content)
        return

    tree = html.fromstring(response.content.decode("utf8"))

    sln_news_scraper_settings_key = SolutionNewsScraperSettings.create_key(service_user)

    def trans():
        sln_news_scraper_settings = SolutionNewsScraperSettings.get(sln_news_scraper_settings_key)
        if not sln_news_scraper_settings:
            return []

        return sln_news_scraper_settings.urls

    urls = db.run_in_transaction(trans)

    news_items = tree.xpath('//div[@class="nwsOverview"]')[0].getchildren()[3].getchildren()

    for li in news_items:
        for item in li.getchildren():
            if item.tag == "a":
                url = item.xpath("@href")[0]
                if not (url.startswith("http://") or url.startswith("https://")):
                    url = u"http://www.lede.be%s" % url

                url = unicode(url) if not isinstance(url, unicode) else url
                if url in urls:
                    continue
                message = _get_news_details(url)
                title = u'%s' % item.text

                def trans():
                    sln_news_scraper_settings = SolutionNewsScraperSettings.get(sln_news_scraper_settings_key)
                    if not sln_news_scraper_settings:
                        sln_news_scraper_settings = SolutionNewsScraperSettings(key=sln_news_scraper_settings_key)
                        sln_news_scraper_settings.urls = []

                    if url not in sln_news_scraper_settings.urls:
                        sln_news_scraper_settings.urls.append(url)
                        sln_news_scraper_settings.put()
                        deferred.defer(create_news_item, sln_settings, broadcast_type, message, title, url,
                                       _transactional=True)

                db.run_in_transaction(trans)


def _get_news_details(url):
    logging.debug(url)
    response = urlfetch.fetch(url, deadline=60)
    if response.status_code != 200:
        logging.error("Could not get news details in be_lede.\n%s" % response.content)
        return

    tree = html.fromstring(response.content.decode("utf8"))

    text_list = []
    for p in tree.xpath('//div[@class="nwsShort"]'):
        text_list.append(p.text_content())

    return u"\n".join(text_list)

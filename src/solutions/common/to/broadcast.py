# -*- coding: utf-8 -*-
# COPYRIGHT (C) 2011-2016 MOBICAGE NV
# ALL RIGHTS RESERVED.
#
# ALTHOUGH YOU MAY BE ABLE TO READ THE CONTENT OF THIS FILE, THIS FILE
# CONTAINS CONFIDENTIAL INFORMATION OF MOBICAGE NV. YOU ARE NOT ALLOWED
# TO MODIFY, REPRODUCE, DISCLOSE, PUBLISH OR DISTRIBUTE ITS CONTENT,
# EMBED IT IN OTHER SOFTWARE, OR CREATE DERIVATIVE WORKS, UNLESS PRIOR
# WRITTEN PERMISSION IS OBTAINED FROM MOBICAGE NV.
#
# THE COPYRIGHT NOTICE ABOVE DOES NOT EVIDENCE ANY ACTUAL OR INTENDED
# PUBLICATION OF SUCH SOURCE CODE.
#
# @@license_version:1.9@@
from mcfw.properties import unicode_property, typed_property, bool_property, long_property, unicode_list_property
from rogerthat.to.messaging import AttachmentTO
from shop.to import ProductTO
from solutions.common.to import TimestampTO, UrlTO


class SolutionScheduledBroadcastTO(object):
    key = unicode_property('1')
    scheduled = typed_property('2', TimestampTO, False)
    broadcast_type = unicode_property('3')
    message = unicode_property('4')
    target_audience_enabled = bool_property('5')
    target_audience_min_age = long_property('6')
    target_audience_max_age = long_property('7')
    target_audience_gender = unicode_property('8')
    attachments = typed_property('9', AttachmentTO, True)
    urls = typed_property('10', UrlTO, True)

    @staticmethod
    def fromModel(model):
        ssb = SolutionScheduledBroadcastTO()
        ssb.key = unicode(model.key_str)
        ssb.scheduled = TimestampTO.fromEpoch(model.broadcast_epoch)
        ssb.broadcast_type = model.broadcast_type
        ssb.message = model.message
        ssb.target_audience_enabled = model.target_audience_enabled
        ssb.target_audience_min_age = model.target_audience_min_age
        ssb.target_audience_max_age = model.target_audience_max_age
        ssb.target_audience_gender = model.target_audience_gender
        ssb.attachments = model.attachments
        ssb.urls = model.urls or list()
        return ssb


class SubscriptionInfoTO(object):
    expiration_date = unicode_property('1')
    months_left = long_property('2')
    has_signed = bool_property('3')

    def __init__(self, expiration_date=None, months_left=None, has_signed=False):
        self.expiration_date = expiration_date
        self.months_left = months_left
        self.has_signed = has_signed


class BroadcastOptionsTO(object):
    broadcast_types = unicode_list_property('1')
    editable_broadcast_types = unicode_list_property('2')
    news_promotion_product = typed_property('3', ProductTO, False)
    extra_city_product = typed_property('4', ProductTO, False)
    news_enabled = bool_property('5')
    subscription_info = typed_property('6', SubscriptionInfoTO, False)
    can_order_extra_apps = bool_property('7')

    def __init__(self, broadcast_types=None, editable_broadcast_types=None, news_promotion_product=None,
                 extra_city_product=None, news_enabled=False, subscription_info=None, can_order_extra_apps=True):
        if editable_broadcast_types is None:
            editable_broadcast_types = []
        if broadcast_types is None:
            broadcast_types = []
        self.broadcast_types = broadcast_types
        self.editable_broadcast_types = editable_broadcast_types
        self.news_promotion_product = news_promotion_product
        self.extra_city_product = extra_city_product
        self.news_enabled = news_enabled
        self.subscription_info = subscription_info
        self.can_order_extra_apps = can_order_extra_apps
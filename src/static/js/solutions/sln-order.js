/*
 * Copyright 2017 Mobicage NV
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * @@license_version:1.2@@
 */

$(function () {
    var STATUS_RECEIVED = 1;
    var STATUS_COMPLETED = 2;

    var solutionInboxMessageOrders = {};
    var solutionInboxMessageOrderRequests = {};
    var ordersDict = {};
    var orders = [];
    var showAllOrders = false;

    var channelUpdates = function (data) {
        switch (data.type) {
            case 'solutions.common.orders.update':
                loadOrders();
                break;
            case 'solutions.common.orders.deleted':
                fadeOutMessageAndUpdateBadge(data.order_key);
                break;
            case 'solutions.common.order.settings.update':
                reLoadOrderSettings();
                break;
            case 'solutions.common.order.settings.timeframe.update':
                loadorderTimeframes();
                break;
        }
    };

    $("#ordersShowTodo, #ordersShowAll").click(function () {
        showAllOrders = !showAllOrders;
        updateShowHideOrders();
    });

    var settingsSection = $('#section_settings_order');
    settingsSection.find('input[type=radio]').change(putOrderSettings);

    var updateShowHideOrders = function () {
        $("#ordersShowTodo").toggleClass('btn-success', !showAllOrders)
            .html(showAllOrders ? '&nbsp;' : CommonTranslations.TODO);
        $("#ordersShowAll").toggleClass('btn-success', showAllOrders)
            .html(showAllOrders ? CommonTranslations.ALL : '&nbsp;');
        renderOrders();
    };

    var reLoadOrderSettings = function () {
        sln.call({
            url: "/common/order/settings/load",
            type: "GET",
            success: function (data) {
                var originalOrderType = orderSettings.order_type;
                orderSettings = data;
                var headerMenuElement = $('#topmenu').find('li[menu=menu]');
                if(originalOrderType != data.order_type) {
                    if(data.order_type === CONSTS.ORDER_TYPE_ADVANCED) {
                        headerMenuElement.removeClass('hide');
                    } else if(MODULES.indexOf('menu') === -1) {
                        headerMenuElement.addClass('hide');
                    }
                    if (modules.menu) {
                        modules.menu.loadMenu(modules.menu.renderMenu);
                    }
                }
                renderOrderSettings(data);
            }

        });
    };

    function renderOrderSettings(data) {
        $("#order_settings_text1").val(data.text_1);
        settingsSection.find('input[type=radio][value=' + data.order_type + ']').prop('checked', true);
        $('#order_leaptime').val(data.leap_time);
        $('#order_leaptime_type').val(data.leap_time_type);
        if (data.order_type === CONSTS.ORDER_TYPE_SIMPLE) {
            $('#order_timeframes_container').slideUp();
            $('#intro_text_container').slideDown();
        } else if (data.order_type === CONSTS.ORDER_TYPE_ADVANCED) {
            loadorderTimeframes();
            $('#order_timeframes_container').slideDown();
            $('#intro_text_container').slideUp();
        }
    }

    function putOrderSettings() {
        var leapTime = parseInt($('#order_leaptime').val());
        if (isNaN(leapTime)) {
            leapTime = 60;
        }
        var leapTimeType = parseInt($('#order_leaptime_type').val());
        sln.call({
            url: "/common/order/settings/put",
            type: "POST",
            data: {
                data: JSON.stringify({
                    text_1: $("#order_settings_text1").val(),
                    order_type: parseInt($('#section_settings_order').find('input[name=setting_advanced_order_fields]:checked').val()),
                    leap_time: leapTime,
                    leap_time_type: leapTimeType
                })
            },
            success: function (data) {
                if (!data.success) {
                    return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                }
            }
        });
    }

    var getActionsForOrder = function (order) {
        var toolbar = $('<div class="btn-toolbar"></div>');
        var group = $('<div class="btn-group"></div>');

        if (order.status == STATUS_RECEIVED) {
            var btnReady = $('<button action="ready" class="btn btn-large btn-success"><i class="icon-ok icon-white"></i></button>').attr("order_key", order.key).click(
                function(event) {
                    event.stopPropagation();
                    var orderKey = $(this).attr("order_key");
                    readyOrderPressed(orderKey);
                }
            );
            group.append(btnReady);
        }
        if (order.status !== STATUS_COMPLETED) {
            var btnDelete = $('<button action="delete" class="btn btn-large btn-warning"><i class="fa fa-times"></i></button>')
                .attr("order_key", order.key).click(orderDeletePressed);
            group.append(btnDelete);
        }
        toolbar.append(group);
        return toolbar;
    };

    var loadOrders = function () {
        solutionInboxMessageOrders = {};
        sln.call({
            url: "/common/orders/load",
            type: "GET",
            success: function (data) {
                $.each(data, function (i, o) {
                    o.date_time = sln.formatDate(o.timestamp, false);
                    o.takeaway_time_formatted = o.takeaway_time ? sln.formatDate(o.takeaway_time, false) : '';
                    ordersDict[o.key] = o;

                    if (o.solution_inbox_message_key) {
                        solutionInboxMessageOrders[o.solution_inbox_message_key] = o;
                        if (solutionInboxMessageOrderRequests[o.solution_inbox_message_key]) {
                            sln.setInboxActions(o.solution_inbox_message_key, getActionsForOrder(o));
                            delete solutionInboxMessageOrderRequests[o.solution_inbox_message_key];
                        }
                    }
                });
                orders = data;
                renderOrders();
            }
        });
    };

    function filterOrders(order) {
        if (showAllOrders) {
            return true;
        }
        return order.status === STATUS_RECEIVED;
    }

    var renderOrders = function () {
        var orderElement = $("#orders-list");
        var localOrders = orders.filter(filterOrders);
        var html = $.tmpl(templates.order_list, {
            orders: localOrders,
            advancedOrder: orderSettings.order_type === CONSTS.ORDER_TYPE_ADVANCED,
            formatHtml: sln.formatHtml
        });
        orderElement.html(html);
        orderElement.find('button[action="view"]').click(function () {
            var orderKey = $(this).attr("order_key");
            orderViewPressed(orderKey);
        });
        orderElement.find('button[action="delete"]').click(orderDeletePressed);
        var badge = $('.sln-orders-badge');
        if (showAllOrders) {
            badge.text('');
        } else {
            badge.text(localOrders.length || '');
        }
        sln.resize_header();
    };

    var fadeOutMessageAndUpdateBadge = function (orderKey) {
        $('#order').find('tr[order_key="' + orderKey + '"]').fadeOut('normal', function() {
            $(this).remove();
        });
        var badge = $('.sln-orders-badge');
        var newBadgeValue = badge.text() - 1;
        badge.text(newBadgeValue > 0 ? newBadgeValue : '');
        sln.resize_header();
    };

    var orderViewPressed = function (orderKey) {
        var order = ordersDict[orderKey];
        order.takeaway_time_formatted = sln.format(new Date(order.takeaway_time * 1000));
        var html = $.tmpl(templates.order, {
            header: CommonTranslations.DETAILS,
            closeBtn: CommonTranslations.CLOSE,
            sendMessageBtn: CommonTranslations.REPLY,
            sendOrderReadyBtn: CommonTranslations.READY_FOR_COLLECTION,
            order_key: orderKey,
            order: order,
            advancedOrder: orderSettings.order_type === CONSTS.ORDER_TYPE_ADVANCED,
            CommonTranslations: CommonTranslations,
            formatHtml: sln.formatHtml
        });
        var modal = sln.createModal(html);

        $('button[action="sendmessage"]', html).click(function () {
            modal.modal('hide');
            sln.inputBox(function (message) {
                sln.call({
                    url: "/common/order/sendmessage",
                    type: "POST",
                    data: {
                        data: JSON.stringify({
                            order_key: orderKey,
                            order_status: STATUS_RECEIVED,
                            message: message
                        })
                    },
                    success: function (data) {
                        if (!data.success) {
                            return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                        }
                    }
                });
            }, CommonTranslations.REPLY, null, CommonTranslations.REPLY_TO_MORE_INFO.replace("%(username)s", order.sender_name));
        });

        if (order.status == STATUS_COMPLETED) {
            $('button[action="sendorderready"]', html).hide();
        }

        $('button[action="sendorderready"]', html).click(function () {
            modal.modal('hide');
            readyOrderPressed(orderKey);
        });
    };

    var readyOrderPressed = function (orderKey) {
        sln.inputBox(function (message, btn) {
            var msg = message;
            if (btn == 2) {
                msg = "";
            }
            sln.call({
                url: "/common/order/sendmessage",
                type: "POST",
                data: {
                    data: JSON.stringify({
                        order_key: orderKey,
                        order_status: STATUS_COMPLETED,
                        message: msg
                    })
                },
                success: function (data) {
                    if (!data.success) {
                        return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                    }
                }
            });
        }, CommonTranslations.READY, CommonTranslations.READY, null, CommonTranslations.REPLY_ORDER_READY, null, CommonTranslations.dont_send_message);
    };

    var orderDeletePressed = function (event) {
        event.stopPropagation();
        var orderKey = $(this).attr("order_key");
        sln.inputBox(function (message, btn) {
            var msg = message;
            if (btn == 2) {
                msg = "";
            }
            sln.call({
                url: "/common/order/delete",
                type: "POST",
                data: {
                    data: JSON.stringify({
                        order_key: orderKey,
                        message: msg
                    })
                },
                success: function (data) {
                    if (!data.success) {
                        return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                    }
                    fadeOutMessageAndUpdateBadge(orderKey);
                    var order = ordersDict[orderKey];
                    delete solutionInboxMessageOrders[order.solution_inbox_message_key];
                    sln.setInboxActions(order.solution_inbox_message_key, undefined);
                }
            });
        }, CommonTranslations.DELETE, CommonTranslations.DELETE, null, CommonTranslations.REPLY_ORDER_CANCEL, null, CommonTranslations.dont_send_message);
    };

    var initorderTimeframeModal = function (day, time_from, time_until) {
        settingsSection.find('#dates').val(day);
        settingsSection.find('#timepickerEnabledFrom').timepicker('setTime', sln.intToTime(time_from));
        settingsSection.find('#timepickerEnabledUntil').timepicker('setTime', sln.intToTime(time_until));
    };

    var loadorderTimeframes = function () {
        sln.call({
            url: "/common/order/settings/timeframe/load",
            type: "GET",
            success: function (data) {
                var timeframes = $("#order_timeframes");

                data.sort(function (tf1, tf2) {
                    if (tf1.day < tf2.day)
                        return -1;
                    if (tf1.day > tf2.day)
                        return 1;

                    if (tf1.time_from < tf2.time_from)
                        return -1;
                    if (tf1.time_from > tf2.time_from)
                        return 1;

                    if (tf1.time_until < tf2.time_until)
                        return -1;
                    if (tf1.time_until > tf2.time_until)
                        return 1;

                    return 0;
                });

                $.each(data, function (i, d) {
                    d.time_from_str = sln.intToTime(d.time_from, false);
                    d.time_until_str = sln.intToTime(d.time_until, false);
                });

                var html = $.tmpl(templates.timeframe_template, {
                    timeframes: data,
                    type: 'order'
                });
                timeframes.find('tbody').html(html);
                $.each(data, function (i, d) {
                    $("#" + d.id).data("timeframe", d);
                });

                timeframes.find('button[action="edit"]').click(function () {
                    var timeframeId = $(this).attr("timeframe_id");
                    $("#save_order_timeframe").attr("timeframe_id", timeframeId);
                    $("#orderTimeframeModalLabel").text(CommonTranslations.TIMEFRAME_UPDATE);
                    var timeframe = $("#" + timeframeId).data("timeframe");
                    initorderTimeframeModal(timeframe.day, timeframe.time_from, timeframe.time_until);
                });
                timeframes.find('button[action="delete"]').click(function () {
                    var timeframeId = $(this).attr("timeframe_id");
                    sln.call({
                        url: "/common/order/settings/timeframe/delete",
                        type: "POST",
                        data: {
                            data: JSON.stringify({
                                timeframe_id: parseInt(timeframeId)
                            })
                        },
                        success: function (data) {
                            if (!data.success) {
                                return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                            }
                        }
                    });
                });
            }
        });
    };

    $("#create_order_timeframe").click(function () {
        $("#save_order_timeframe").attr("timeframe_id", null);
        $("#orderTimeframeModalLabel").text(CommonTranslations.TIMEFRAME_CREATE);
        initorderTimeframeModal(0, 9 * 3600, 18 * 3600);
    });

    $("#save_order_timeframe").click(function () {
        var old_timeframe_id = $(this).attr("timeframe_id");
        var day = parseInt(settingsSection.find("#dates").val());
        var fromPicker = settingsSection.find("#timepickerEnabledFrom").data("timepicker");
        var timeFrom = fromPicker.hour * 3600 + fromPicker.minute * 60;
        var untilPicker = settingsSection.find("#timepickerEnabledUntil").data("timepicker");
        var timeUntil = untilPicker.hour * 3600 + untilPicker.minute * 60;

        if (timeFrom == timeUntil) {
            return sln.alert(CommonTranslations.TIME_START_END_EQUAL);
        }
        if (timeFrom >= timeUntil) {
            return sln.alert(CommonTranslations.TIME_START_END_SMALLER);
        }
        sln.call({
            url: "/common/order/settings/timeframe/put",
            type: "POST",
            data: {
                data: JSON.stringify({
                    timeframe_id: old_timeframe_id ? parseInt(old_timeframe_id) : null,
                    day: day,
                    time_from: timeFrom,
                    time_until: timeUntil
                })
            },
            success: function (data) {
                if (!data.success) {
                    return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                }
                $("#orderTimeframeModal").modal('hide');
            }
        });
    });

    settingsSection.find('#timepickerEnabledFrom').timepicker({
        defaultTime: "09:00",
        showMeridian: false,
        minuteStep: 5
    });
    settingsSection.find('#timepickerEnabledUntil').timepicker({
        defaultTime: "18:00",
        showMeridian: false,
        minuteStep: 5
    });
    
    var loadPayconiq = function () {
        sln.call({
            url: "/common/payments/payconiq",
            type: "GET",
            success: function (data) {
            	$("#payconicMerchantId").val(data.merchant_id ? ata.merchant_id : '' );
            	$("#payconicOnlineKey").val(data.online_key ? data.online_key : '');
            	$("#payconiqAccessToken").val(data.jwt ? data.jwt : '');
            }
        });
    };

    $("#payconiqSave").click(function () {
    	sln.call({
            url: "/common/payments/payconiq",
            type: "POST",
            data: {
                data: JSON.stringify({
                	merchant_id: $("#payconicMerchantId").val(),
                    online_key: $("#payconicOnlineKey").val(),
                    jwt: $("#payconiqAccessToken").val()
                })
            },
            success: function (data) {
                if (!data.success) {
                    return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                }
            }
        });
    });

    sln.registerMsgCallback(channelUpdates);
    loadOrders();
    renderOrderSettings(orderSettings); // orderSettings defined in index.html
    updateShowHideOrders();
    loadPayconiq();

    sln.registerInboxActionListener("order", function (chatId) {
        var o = solutionInboxMessageOrders[chatId];
        if (o) {
            sln.setInboxActions(o.solution_inbox_message_key, getActionsForOrder(o));
        } else {
            solutionInboxMessageOrderRequests[chatId] = chatId;
        }
    });
    sln.configureDelayedInput($("#order_settings_text1"), putOrderSettings);
    sln.configureDelayedInput($("#order_leaptime"), putOrderSettings);
    sln.configureDelayedInput($("#order_leaptime_type"), putOrderSettings);
});

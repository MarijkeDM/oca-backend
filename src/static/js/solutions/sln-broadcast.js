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
    'use strict';
    var TMPL_HINT_SET_FACEBOOK_PAGE = '<div class="alert alert-info">'
        + '    <button id="set_facebook_page" type="button" class="btn btn-info pull-right">${CommonTranslations.SET_NOW}</button>' //
        + '    <h4>${CommonTranslations.HINT}</h4> ${CommonTranslations.SET_FACEBOOK_PAGE_AND_START_SHARING}'
        + '</div>';

    var ATTACHMENT_TEMPLATE = '{{each attachments}}'
        + ' <tr>'
        + '     <td><div class="span4">${$value.name}</div> <div class="btn-group pull-right">'
        + '         <a href="${$value.download_url}" target="_blank"> <button action="link" class="btn"><i class="fa fa-external-link"></i></button></a>'
        + '         <button key="${$index}" download_url="${$value.download_url}" action="delete" class="btn"><i class="fa fa-trash"></i></button>'
        + '     </div></td>' //
        + ' </tr>' //
        + '{{/each}}';

    var URL_TEMPLATE = '{{each urls}}'
        + ' <tr>'
        + '     <td><div class="span4">${$value.name}</div> <div class="btn-group pull-right">'
        + '         <a href="${$value.url}" target="_blank"> <<button action="link" class="btn"><i class="fa fa-external-link"></i></button></a>'
        + '         <button key="${$index}" url="${$value.url}" action="delete" class="btn"><i class="fa fa-trash"></i></button>'
        + '     </div></td>' //
        + ' </tr>' //
        + '{{/each}}';

    var GENDER_MALE_OR_FEMALE = "MALE_OR_FEMALE";

    var totalReachData;
    var targetAudienceEnabled = false;
    var targetAudienceMinAge = 0;
    var targetAudienceMaxAge = 0;
    var targetAudienceGender = GENDER_MALE_OR_FEMALE;
    var randomReachCount;

    var DEFAULT_TIME_EPOCH = 20 * 3600;
    var broadcastTimeEpoch = DEFAULT_TIME_EPOCH,
        NEWS_TYPE_NORMAL = 1,
        NEWS_TYPE_QR = 2,
        newsTypes = {
            1: T('normal'),
            2: T('coupon')
        };
    var hasMoreNews = false;
    var isLoadingNews = false;
    var msgAttachments = [];
    var msgUrls = [];

    var elemPageNews = $('#broadcast_page_news'),
        elemPageMessage = $('#broadcast_page_message'),
        elemInputBroadcastTarget = $('#input-broadcast-target'),
        elemTargetAudience = $('#target_audience');

    var steps = [{
        text: T('news_type'),
        description: T('news_type_explanation')
    }, {
        text: T('Content'),
        description: T('news_content_explanation')
    }, {
        text: T('image_optional'),
        description: T('news_image_explanation')
    }, {
        text: T('Label'),
        description: T('news_label_explanation')
    }, {
        text: T('action_button'),
        description: T('news_action_button_explanation'),
        type: NEWS_TYPE_NORMAL
    }, {
        text: T('delayed_broadcast'),
        description: T('news_schedule_explanation')
    }, {
        text: T('target_audience'),
        description: T('news_target_audience_explanation')
    }, {
        text: T('checkout'),
        description: ''
    }];

    var validation = {
        rules: {
            news_checkbox_apps: {
                required: true
            }
        },
        errorPlacement: function (error, element) {
            if (element.attr('name') === 'news_checkbox_apps') {
                error.insertAfter($(element).parent().parent());
            } else {
                error.insertAfter(element);
            }
        }
    };
    var currentStep;
    var elemBroadcastOnTwitter = $("#broadcast_message_on_twitter").find("input");
    LocalCache.news = {
        promotedNews: {},
        statistics: {}
    };

    init();

    var numberOnlyCheckKeyup = function (e) {
        if (/\D/g.test($(this).val())) {
            $(this).val($(this).val().replace(/\D/g, ''));
        }
        if (!$(this).val()) {
            if ($(this).attr("id") == "age-min") {
                $(this).val('0');
            } else {
                $(this).val('100');
            }
        }
        displayReach();
    };

    var plusClick = function (elem) {
        return function (e) {
            elem.val(parseInt(elem.val()) + 1);
            displayReach();
        };
    };
    var minClick = function (elem) {
        return function (e) {
            var current = parseInt(elem.val());
            if (current > 0)
                elem.val(current - 1);
            else
                elem.val(0);
            displayReach();
        };
    };

    function addAttachment() {
        var html = $.tmpl(templates.addattachment, {
            t: CommonTranslations,
            website: false
        });

        var modal = sln.createModal(html, function () {
            $('#attachmentName').focus().select();
        });

        $('button[action="submit"]', modal).click(function () {
            var fileInput = $('#attachment-files', modal)[0];
            if(fileInput.files[0] === undefined) {
                sln.alert(T('please_select_attachment'), null, CommonTranslations.ERROR);
                return;
            }
            sln.showProcessing(CommonTranslations.UPLOADING_TAKE_A_FEW_SECONDS);
            var formElement = document.querySelector('#attachment-form');
            var request = new XMLHttpRequest();
            request.open('POST', '/common/broadcast/attachment/upload');
            request.send(new FormData(formElement));
        });
    }

    function attachmentUploaded(url, name) {
        // Hide the modal, add attachment
        $('#addAttachmentModal').modal('hide');
        if(modules.news && modules.news.enabled) {
            // set the attachment name and trigger a keyup
            // to re-render the preview
            $('#news_action_attachment_caption').val(name);
            $('#news_action_attachment_caption').keyup();
            // set the attachment value/url
            $('#news_action_attachment_value').val(url);
            // hide the add button and show remove button
            $('#news_action_remove_attachment').show();
            $('#news_action_add_attachment').hide();
        } else {
            msgAttachments.push({
                download_url: url,
                name: name
            });
            displayAttachments();
        }
    }

    function attachmentUploadFailed(error) {
        $('#addAttachmentModal').modal('hide');
        sln.alert(error, null, CommonTranslations.ERROR);
    }

    var attachmentDeletePressed = function () {
        var key = $(this).attr("key");
        msgAttachments.splice(key, 1);
        displayAttachments();
    };

    var displayAttachments = function () {
        if (msgAttachments.length > 0) {
            var attachments = $("#attachments").find("tbody");
            var html = $.tmpl(ATTACHMENT_TEMPLATE, {
                attachments: msgAttachments
            });
            attachments.empty().append(html);
            $('#attachments').show().find('button[action="delete"]').click(attachmentDeletePressed);
        } else {
            $("#attachments").hide();
        }
    };

    var addUrl = function () {
        var html = $.tmpl(templates.addattachment, {
            t: CommonTranslations,
            website: true
        });

        var modal = sln.createModal(html, function () {
            $('#attachmentUrl').focus();
        });
        $('button[action="submit"]', modal).prop('disabled', true);

        sln.configureDelayedInput($('#attachmentUrl', modal), function () {
            $('#attachmentUrl', modal).removeClass("success");
            $('#attachmentUrl', modal).removeClass("error");
            $("#attachment-error", modal).hide();
            $("#attachment-validating", modal).show();
            $('button[action="submit"]', modal).prop('disabled', true);

            sln.call({
                url: "/common/broadcast/validate/url",
                type: "POST",
                data: {
                    data: JSON.stringify({
                        url: $('#attachmentUrl', modal).val()
                    })
                },
                success: function (data) {
                    $("#attachment-validating", modal).hide();
                    $('#attachmentUrl', modal).val(data.url);
                    if (!data.success) {
                        $("#attachment-error", modal).show();
                        $("#attachment-error-msg", modal).html(sln.htmlize(data.errormsg));
                        $('#attachmentUrl', modal).addClass("error");
                        return;
                    }
                    $('#attachmentUrl', modal).addClass("success");
                    $('button[action="submit"]', modal).prop('disabled', false);
                },
                error: sln.showAjaxError
            });
        });

        $('button[action="submit"]', modal).click(
            function () {
                var url = $("#attachmentUrl", modal).val();
                var urlName = $("#attachmentName", modal).val();

                var urlValid = sln.validate($("#urlerror", modal), $("#attachmentUrl", modal),
                    CommonTranslations.URL_IS_REQUIRED);
                var nameValid = sln.validate($("#nameerror", modal), $("#attachmentName", modal),
                    CommonTranslations.NAME_IS_REQUIRED);

                if (!(urlValid && nameValid))
                    return;

                msgUrls.push({
                    url: url,
                    name: urlName
                });
                displayUrls();
                modal.modal('hide');
            });
    };

    var urlDeletePressed = function () {
        var key = $(this).attr("key");
        msgUrls.splice(key, 1);
        displayUrls();
    };

    var displayUrls = function () {
        if (msgUrls.length > 0) {
            $("#urls").show();
            var urls = $("#urls tbody");
            var html = $.tmpl(URL_TEMPLATE, {
                urls: msgUrls
            });
            urls.empty().append(html);
            $('#urls button[action="delete"]').click(urlDeletePressed);
        } else {
            $("#urls").hide();
        }
    };

    var defaultBroadcastChecks = function (bt, message) {
        if (!bt.val()) {
            sln.alert(CommonTranslations.BROADCAST_TYPE_REQUIRED);
            return false;
        }

        if (!message.val()) {
            sln.alert(CommonTranslations.PLEASE_ENTER_A_MESSAGE);
            return false;
        }

        var checkTargetAudience = $('#configure_target_audience input');
        if (checkTargetAudience.prop('checked')) {
            targetAudienceEnabled = true;
            targetAudienceMinAge = parseInt($("#age_min").val());
            targetAudienceMaxAge = parseInt($("#age_max").val());
            targetAudienceGender = $("#gender").val();

            if (targetAudienceMinAge > targetAudienceMaxAge) {
                sln.alert(CommonTranslations.AGE_MIN_MAX_LESS);
                return false;
            }
        } else {
            targetAudienceEnabled = false;
            targetAudienceMinAge = 0;
            targetAudienceMaxAge = 0;
            targetAudienceGender = GENDER_MALE_OR_FEMALE;
        }
        return true;
    };

    var broadcast = function () {
        var bt = $('#broadcast input[name=broadcast_types]:checked');
        var message = $('#broadcast #broadcast_message');
        var allOk = defaultBroadcastChecks(bt, message);
        if (!allOk)
            return;

        var twitterEnabled = elemBroadcastOnTwitter.prop('checked');
        if (twitterEnabled) {
            var twitterUsername = elemBroadcastOnTwitter.val();
            if (twitterUsername === "") {
                sln.alert(CommonTranslations.TWITTER_PAGE_REQUIRED);
                return;
            }
        }

        var checkFacebook = $('#broadcast #broadcast_message_on_facebook input');
        if (checkFacebook.prop('checked')) {
            var facebookPageId = $("#broadcast_message_on_facebook input").val();
            if (facebookPageId == "") {
                sln.alert(CommonTranslations.FACEBOOK_PLACE_REQUIRED);
                return;
            } else {
                FB.login(function (response) {
                    if (response.authResponse) {
                        var fbAccessToken = response.authResponse.accessToken;
                        var userId = response.authResponse.userID;
                        var params = "/" + userId + "/accounts?access_token=" + fbAccessToken;
                        FB.api(params,
                            function (response) {
                                if (response && !response.error) {
                                    var userIsAdmin = false;
                                    var userHasModeratePermissions = false;
                                    for (var i = 0; i < response.data.length; i++) {
                                        if (response.data[i].id === facebookPageId) {
                                            userIsAdmin = true;
                                            if (response.data[i].perms.indexOf("MODERATE_CONTENT") > 0) {
                                                userHasModeratePermissions = true;
                                            }
                                            break;
                                        }
                                    }
                                    if (userIsAdmin && userHasModeratePermissions) {
                                        var fbRequest = {message: message.val(), access_token: fbAccessToken};
                                        if (msgAttachments.length > 0) {
                                            fbRequest["link"] = msgAttachments[0].download_url;
                                        } else if (msgUrls.length > 0) {
                                            fbRequest["link"] = msgUrls[0].download_url;
                                        }

                                        FB.api("/" + facebookPageId + "/feed", "post", fbRequest,
                                            function (response) {
                                                console.log("response broadcast", response, fbRequest);
                                                if (response && !response.error) {
                                                    doBroadcastToRogerthat(bt.val(), message.val(), true, targetAudienceEnabled,
                                                        targetAudienceMinAge, targetAudienceMaxAge, targetAudienceGender,
                                                        msgAttachments, msgUrls, null, twitterEnabled);
                                                }
                                                else {
                                                    sln.confirm(sln.htmlize(CommonTranslations.FACEBOOK_VISIBILITY_APP)
                                                            .replace("%(fb_url)s", '<a href="https://www.facebook.com/settings?tab=applications" target="_blank">https://www.facebook.com/settings?tab=applications</a>'),
                                                        function () {
                                                            // Retry
                                                            broadcast();
                                                        }, function () {
                                                            // Continue
                                                            doBroadcastToRogerthat(bt.val(), message.val(), false, targetAudienceEnabled,
                                                                targetAudienceMinAge, targetAudienceMaxAge, targetAudienceGender,
                                                                msgAttachments, msgUrls, null, twitterEnabled);
                                                        }, CommonTranslations.RETRY, CommonTranslations.CONTINUE_WITHOUT_FACEBOOK_POST, CommonTranslations.INSUFFICIENT_PERMISSIONS);
                                                }
                                            }
                                        );
                                    }
                                    else {
                                        if (!userIsAdmin) {
                                            sln.alert(CommonTranslations.FACEBOOK_ADMIN_REQUIRED);
                                            // or you didn't grant us permissions
                                        }
                                        else if (!userHasModeratePermissions) {
                                            sln.alert(CommonTranslations.FACEBOOK_ADMIN_PERMISSIONS_REQUIRED);
                                        }
                                    }
                                }
                                else {
                                    // Error occurred while getting accounts
                                    doBroadcastToRogerthat(bt.val(), message.val(), false, targetAudienceEnabled,
                                        targetAudienceMinAge, targetAudienceMaxAge, targetAudienceGender, msgAttachments, msgUrls, null, twitterEnabled);
                                }
                            }
                        );
                    } else {
                        // The person cancelled the login dialog
                        doBroadcastToRogerthat(bt.val(), message.val(), false, targetAudienceEnabled,
                            targetAudienceMinAge, targetAudienceMaxAge, targetAudienceGender, msgAttachments, msgUrls, null, twitterEnabled);
                    }
                }, {scope: 'manage_pages,publish_actions'});
            }
        } else {
            doBroadcastToRogerthat(bt.val(), message.val(), false, targetAudienceEnabled, targetAudienceMinAge,
                targetAudienceMaxAge, targetAudienceGender, msgAttachments, msgUrls, null, twitterEnabled);
        }
    };

    var to_epoch = function (textField) {
        return Math.floor(textField.data('datepicker').date.valueOf() / 1000);
    };

    var scheduleBroadcast = function () {
        var bt = $('#broadcast input[name=broadcast_types]:checked');
        var message = $('#broadcast #broadcast_message');
        var allOk = defaultBroadcastChecks(bt, message);
        if (!allOk)
            return;

        var html = $.tmpl(templates.broadcast_schedule, {
            header: CommonTranslations.SCHEDULE_BROADCAST,
            cancelBtn: CommonTranslations.CANCEL,
            submitBtn: CommonTranslations.SEND,
            CommonTranslations: CommonTranslations
        });

        $('#broadcast-time', html).timepicker({
            defaultTime: "20:00",
            showMeridian: false
        });
        broadcastTimeEpoch = DEFAULT_TIME_EPOCH;

        $('#broadcast-time', html).on('changeTime.timepicker', function (e) {
            broadcastTimeEpoch = e.time.hours * 3600 + e.time.minutes * 60;
        });

        var twitterEnabled = elemBroadcastOnTwitter.prop('checked');
        if (twitterEnabled) {
            var twitterUsername = elemBroadcastOnTwitter.val();
            if (twitterUsername == "") {
                sln.alert(CommonTranslations.TWITTER_PAGE_REQUIRED);
                return;
            }
        }

        var checkFacebook = $('#broadcast #broadcast_message_on_facebook input');
        if (checkFacebook.prop('checked')) {
            $("#broadcast-note", html).show();
        } else {
            $("#broadcast-note", html).hide();
        }

        $('.date', html).datepicker({
            format: sln.getLocalDateFormat()
        }).datepicker('setValue', sln.today());

        var modal = sln.createModal(html);

        $('button[action="submit"]', modal).click(
            function () {
                var selectDate = new Date(((to_epoch($("#broadcast-date", html))) + broadcastTimeEpoch) * 1000);
                var broadcastDate = {
                    year: selectDate.getFullYear(),
                    month: selectDate.getMonth() + 1,
                    day: selectDate.getDate(),
                    hour: selectDate.getHours(),
                    minute: selectDate.getMinutes()
                };
                modal.modal('hide');
                doBroadcastToRogerthat(bt.val(), message.val(), false, targetAudienceEnabled, targetAudienceMinAge,
                    targetAudienceMaxAge, targetAudienceGender, msgAttachments, msgUrls, broadcastDate,
                    twitterEnabled);
            });
    };

    var lastDisplayReachInvocation = 0;
    var displayReach = function () {
        lastDisplayReachInvocation = new Date().getTime();
        $("#broadcastReachCalculation").show();
        $("#broadcastReach").hide();
        setTimeout(function () {
            if ((new Date().getTime() - lastDisplayReachInvocation) < 1000)
                return;
            var targetAudienceMinAge = null;
            var targetAudienceMaxAge = null;
            var targetAudienceGender = null;
            if (targetAudienceEnabled) {
                targetAudienceMinAge = parseInt($("#age_min").val());
                targetAudienceMaxAge = parseInt($("#age_max").val());
                targetAudienceGender = $("#gender").val();
            }
            var broadcastToAllLocations = $("#broadcast_message_to_all_locations input").prop('checked');
            sln.call({
                url: "/common/broadcast/subscribed",
                type: "get",
                data: {
                    broadcast_type: $("input[type='radio'][name='broadcast_types']:checked").val(),
                    min_age: targetAudienceMinAge,
                    max_age: targetAudienceMaxAge,
                    gender: targetAudienceGender,
                    broadcast_to_all_locations: broadcastToAllLocations
                },
                success: function (data) {
                    totalReachData = data;
                    $("#broadcastReached").text(totalReachData.subscribed_users);
                    $("#broadcastTotal").text(totalReachData.total_users);
                    $("#broadcastReachCalculation").hide();
                    $("#broadcastReach").show();
                },
                error: sln.showAjaxError
            });
        }, 1000);
    };

    function renderBroadcastTypes() {
        var html = $.tmpl(templates.broadcast_types, {
            broadcast_types: LocalCache.broadcastOptions.broadcast_types
        });
        $("#broadcast_types").html(html);
        $("#broadcast").find("input[name=broadcast_types]:radio").change(function () {
            displayReach();
        });
        modules.settings.renderBroadcastSettings(); // Defined in sln-settings
    }

    function getBroadcastOptions(callback, force) {
        if (LocalCache.broadcastOptions && !force) {
            callback(LocalCache.broadcastOptions);
        } else {
            sln.call({
                url: "/common/broadcast/options",
                type: "GET",
                success: function (data) {
                    LocalCache.broadcastOptions = data;
                    if (callback) {
                        callback(LocalCache.broadcastOptions);
                    }
                }
            });
        }
    }

    function getAppStatistics(callback) {
        if (LocalCache.appStatistics) {
            callback(LocalCache.appStatistics);
        } else {
            sln.call({
                url: '/common/statistics/apps',
                type: 'GET',
                success: function (data) {
                    LocalCache.appStatistics = data;
                    callback(LocalCache.appStatistics);
                }
            });
        }
    }

    $(document).on("click", '#scheduled_broadcasts tbody button[action="delete"]', function () {
        var key = $(this).attr("key");

        sln.call({
            url: "/common/broadcast/scheduled/delete",
            type: "POST",
            data: {
                data: JSON.stringify({
                    key: key
                })
            },
            success: function (data) {
                if (!data.success) {
                    sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                    return;
                }
                loadScheduledBroadcasts();
            }
        });
    });

    var loadScheduledBroadcasts = function () {
        sln.call({
            url: "/common/broadcast/scheduled/load",
            type: "GET",
            success: function (data) {
                $("#scheduled_broadcasts").toggle(!!data.length);
                if (data.length !== 0) {
                    $.each(data, function (i, d) {
                        var broadcastDate = new Date(d.scheduled.year, d.scheduled.month - 1, d.scheduled.day,
                            d.scheduled.hour, d.scheduled.minute);

                        d.date = sln.parseDateToDateTime(broadcastDate);
                        d.htmlMessage = sln.htmlize(d.message);
                    });

                    var html = $.tmpl(templates.broadcast_schedule_items, {
                        data: data,
                        CommonTranslations: CommonTranslations
                    });

                    $("#scheduled_broadcasts").find("tbody").html(html);
                }
            }
        });
    };

    function doBroadcastToRogerthat(broadcast_type, message, broadcast_on_facebook, target_audience_enabled,
                                    target_audience_min_age, target_audience_max_age, target_audience_gender, msg_attachments, msg_urls,
                                    broadcast_date, broadcast_on_twitter) {
        sln.showProcessing(CommonTranslations.SENDING_DOT_DOT_DOT);

        var broadcastToAllLocations = $("#broadcast_message_to_all_locations input").prop('checked');

        sln.call({
            url: "/common/broadcast",
            type: "POST",
            data: {
                data: JSON.stringify({
                    broadcast_type: broadcast_type,
                    message: message,
                    broadcast_on_facebook: broadcast_on_facebook,
                    target_audience_enabled: target_audience_enabled,
                    target_audience_min_age: target_audience_min_age,
                    target_audience_max_age: target_audience_max_age,
                    target_audience_gender: target_audience_gender,
                    msg_attachments: msg_attachments,
                    msg_urls: msg_urls,
                    broadcast_date: broadcast_date,
                    broadcast_on_twitter: broadcast_on_twitter,
                    broadcast_to_all_locations: broadcastToAllLocations
                })
            },
            success: function (data) {
                sln.hideProcessing();
                if (data.success) {
                    $('#broadcast #broadcast_message').val('');
                    $('#broadcast input[name=broadcast_types]:checked').prop('checked', false);
                    $('#broadcast_message_on_facebook input').prop('checked', broadcast_on_facebook);
                    $("#broadcast_message_to_all_locations input").prop('checked', false);
                    $('#configure_target_audience input').prop('checked', false);
                    elemTargetAudience.css("display", "none");
                    targetAudienceEnabled = false;
                    $("#broadcastReached").text(0);
                    $("#broadcastTotal").text(0);
                    msgAttachments = [];
                    msgUrls = [];
                    totalReachData = undefined;
                    displayAttachments();
                    displayUrls();
                    $("#char_count").text(0);
                    elemBroadcastOnTwitter.removeProp("disabled");
                    elemBroadcastOnTwitter.attr("_status", "enabled");
                    $("#twitter_disabled_reason_chars").hide();

                    if (broadcast_date === null) {
                        sln.alert(CommonTranslations.BROADCAST_SEND_SUCCESSFULLY, null, CommonTranslations.SUCCESS);
                    } else {
                        sln.alert(CommonTranslations.BROADCAST_PLANNED_SUCCESSFULLY, null, CommonTranslations.SUCCESS);
                    }
                } else {
                    sln.alert(data.errormsg.replace("\n", "<br><br>"), null, CommonTranslations.FAILED);
                }
            },
            error: sln.showAjaxError
        });
    }

    function channelUpdates(data) {
        switch (data.type) {
            case 'solutions.common.settings.facebookPageChanged':
                $("#broadcast_message_on_facebook").find("input").val(data.facebook_page || '');
                $(".sln-broadcast-hint").toggle(!!data.facebook_page);
                break;
            case 'solutions.common.settings.updates_pending':
                if (!data.updatesPending) {
                    getBroadcastOptions(false, true);
                }
                break;
            case 'solutions.common.broadcast.scheduled.updated':
                loadScheduledBroadcasts();
                break;
            case 'solutions.common.twitter.updated':
                $("#broadcast_message_on_twitter").find("input").val(data.username ? data.username : "");
                break;
            case 'solutions.common.broadcast.attachment.upload.success':
                sln.hideProcessing();
                attachmentUploaded(data.url, data.name);
                break;
            case 'solutions.common.broadcast.attachment.upload.failed':
                sln.hideProcessing();
                attachmentUploadFailed(data.message);
                break;
        }
    }

    function setFacebookPage() {
        $("#topmenu").find("li").removeClass("active");
        var li = $("li[menu=settings]").addClass("active");

        $("div.page").hide();
        $("div#" + li.attr("menu")).show();

        var new_position = $('.sln-set-facebook-place').offset();
        if (new_position === undefined) {
            return;
        }
        window.scrollTo(new_position.left, new_position.top);
    }

    $("#set_facebook_page").click(setFacebookPage);
    $("#age_min").keyup(numberOnlyCheckKeyup);
    $("#age_max").keyup(numberOnlyCheckKeyup);

    $("#age_max_plus").click(plusClick($("#age_max")));
    $("#age_min_plus").click(plusClick($("#age_min")));
    $("#age_max_min").click(minClick($("#age_max")));
    $("#age_min_min").click(minClick($("#age_min")));

    $('#broadcast button#broadcast-button').click(broadcast);
    $('#broadcast button#schedule-broadcast-button').click(scheduleBroadcast);

    $('#configure_target_audience').find('input').change(function () {
        targetAudienceEnabled = !!this.checked;
        elemTargetAudience.toggle(targetAudienceEnabled);
        displayReach();
    });

    $("#broadcast_message_to_all_locations input").change(function () {
        displayReach();
    });

    $("#gender").change(displayReach);
    $("#add_attachment").click(addAttachment);
    $("#add_url").click(addUrl);

    $("li[menu=broadcast] a").click(function () {
        displayAttachments();
        displayUrls();
    });

    $("#broadcast_message").on(
        "keyup change",
        function () {
            var l = $("#broadcast_message").val().length;
            $("#char_count").text(l);
            var _previous_status = elemBroadcastOnTwitter .attr("_status");
            if (l > 140) {
                if (_previous_status != "disabled") {
                    elemBroadcastOnTwitter .prop("disabled", "disabled");
                    elemBroadcastOnTwitter .attr("_backup_selected",
                        elemBroadcastOnTwitter .prop("checked"));
                    elemBroadcastOnTwitter .prop("checked", false);
                    elemBroadcastOnTwitter .attr("_status", "disabled");
                    $("#twitter_disabled_reason_chars").show();
                }
            } else {
                if (_previous_status != "enabled") {
                    elemBroadcastOnTwitter .removeProp("disabled");
                    var twB = elemBroadcastOnTwitter .attr("_backup_selected");
                    if (twB == "true") {
                        elemBroadcastOnTwitter .prop("checked", true);
                    } else if (twB == "false") {
                        elemBroadcastOnTwitter .prop("checked", false);
                    }

                    elemBroadcastOnTwitter .attr("_status", "enabled");
                    $("#twitter_disabled_reason_chars").hide();
                }
            }
        });

    function init() {
        ROUTES['broadcast'] = router;
        elemInputBroadcastTarget.change(displayReach);
        sln.registerMsgCallback(channelUpdates);

        if (!modules.menu) {
            modules.menu = {
                getMenu: returnNothing
            };
        }
        if (!modules.sandwich) {
            modules.sandwich = {
                getSandwichSettings: returnNothing
            };
        }
    }

    function returnNothing(callback) {
        callback();
    }

    function router(urlHash) {
        var page = urlHash[1];
        getBroadcastOptions(function (broadcastOptions) {
            if(!modules.news) {
                modules.news = {};
            }
            modules.news.enabled = broadcastOptions.news_enabled;
            // determine what to show depending if news is enabled or not
            if (!broadcastOptions.news_enabled) {
                elemPageNews.hide();
                elemPageMessage.show();
                renderBroadcastTypes(broadcastOptions);
                var html_hint = $.tmpl(TMPL_HINT_SET_FACEBOOK_PAGE, {
                    CommonTranslations: CommonTranslations
                });

                $('.sln-broadcast-hint').html(html_hint);
                if (!$('#broadcast_message_on_facebook').find('input').val()) {
                    $('.sln-broadcast-hint').hide();
                }
                loadScheduledBroadcasts();
            } else {
                if (['overview', 'edit', 'add'].indexOf(page) === -1) {
                    page = 'add';
                    window.location.hash = '#/' + urlHash[0] + '/' + page;
                    return;
                }
                elemPageNews.show().empty();
                elemPageMessage.hide();
            }
            if (page === 'overview') {
                showNewsOverview();
            } else if (page === 'edit') {
                showEditNews(urlHash[2]);
            } else if (page === 'add') {
                showEditNews();
            }
        });
    }

    function showNewsOverview(loadMore) {
        if (loadMore) {
            elemPageNews.append(TMPL_LOADING_SPINNER);
            $('#load_more_news').hide();
        } else {
            elemPageNews.html(TMPL_LOADING_SPINNER);
        }
        if (LocalCache.newsItems && !loadMore) {
            renderNewsOverview(LocalCache.newsItems.result);
        } else {
            isLoadingNews = true;
            sln.call({
                url: '/common/news',
                data: {
                    cursor: loadMore ? LocalCache.newsItems.cursor : undefined
                },
                type: 'GET',
                success: function (data) {
                    if (LocalCache.newsItems) {
                        LocalCache.newsItems.result = LocalCache.newsItems.result.concat(data.result);
                        LocalCache.newsItems.cursor = data.cursor;
                    } else {
                        LocalCache.newsItems = data;
                    }
                    var uniqueNews = {};
                    LocalCache.newsItems.result.map(function (item) {
                        uniqueNews[item.id] = item;
                    });
                    hasMoreNews = data.result.length > 0;
                    renderNewsOverview(LocalCache.newsItems.result);
                    isLoadingNews = false;
                },
                error: function () {
                    elemPageNews.html(T('error_while_loading_news_try_again_later'));
                    isLoadingNews = false;
                }
            });
        }
    }

    function getNewsItem(newsId) {
        return LocalCache.newsItems.result.filter(function (n) {
            return n.id === newsId;
        })[0];
    }

    function showEditNews(newsId) {
        newsId = parseInt(newsId);
        var newsItem;
        randomReachCount = Math.floor(Math.random() * (5001 - 1500) + 1500);
        if (newsId) {
            if (!LocalCache.newsItems || !LocalCache.newsItems.result) {
                window.location.hash = '#/broadcast/overview';
                return;
            }
            newsItem = getNewsItem(newsId);
        }
        if (LocalCache.serviceMenu) {
            renderNewsPage(LocalCache.serviceMenu, newsItem);
            return;
        }
        sln.call({
            url: '/common/get_menu',
            type: 'GET',
            success: function (serviceMenu) {
                LocalCache.serviceMenu = serviceMenu;
                renderNewsPage(serviceMenu, newsItem);
            }
        });
    }

    function validateLoadMoreNews() {
        var lastNewsItem = $('.news-card').last();
        if(sln.isOnScreen(lastNewsItem) && hasMoreNews && !isLoadingNews) {
            showNewsOverview(true);
        }
    }

    //show more news when scolling down
    $(window).scroll(function() {
        validateLoadMoreNews();
    });

    function renderNewsOverview(newsItems) {
        newsItems.map(function (n) {
            n.datetime = sln.format(new Date(n.timestamp * 1000));
        });
        var html = $.tmpl(templates['broadcast/broadcast_news_overview'], {
            newsItems: newsItems,
            scheduledAt: scheduledAt
        });
        elemPageNews.html(html);
        $('#load_more_news').click(validateLoadMoreNews).toggle(hasMoreNews);
        $('.delete_news_button').click(deleteNews);
        $('.show_more_stats_button').click(showMoreStatsClicked);

        function scheduledAt(datetime) {
            return T('scheduled_for_datetime', {datetime: sln.format(new Date(datetime * 1000))});
        }

        // show more news if the last news item is visible
        validateLoadMoreNews();
    }

    /*
    fill the missing time data with the previous row value
    :param timeData: an array of time data
    */
    function fillMissingTimeData(timeData) {
        var columns = Object.keys(timeData[0]).length;
        $.each(timeData, function (i, row) {
            var rowLength = Object.keys(row).length;
            if (rowLength < columns) {
                // row[0] is a date
                // timeData[i -1] is the previous row
                var prevRow = timeData[i - 1];
                for (var j = 1; j < columns; j++) {
                    if (row[j] === undefined) {
                        if(prevRow) {
                            row[j] = prevRow[j];
                        } else {
                            row[j] = 0;
                        }
                    }
                }
            }
        });
    }

    function showMoreStatsClicked() {
        var dis = $(this);
        // buttons receive clicks even while they're disabled
        if(dis.attr('disabled')) return;

        var newsId = parseInt(dis.attr('news_id'));
        var property = dis.attr('property_name');
        var container = $('#show_more_stats_' + newsId);
        var containerHidden = container.css('display') == 'none';
        // same button is the button with green color
        // rgb(139, 197, 63) = #8bc53f
        var sameButton = dis.css('color') == 'rgb(139, 197, 63)';

        // empty container and set all buttons to the default color
        $('.show_more_stats_button[news_id=' + newsId + ']').css('color', '');
        container.empty();

        // hide only if the same button clicked
        if (!containerHidden && sameButton) {
            container.slideUp();
        } else {
          var spinner = $(TMPL_LOADING_SPINNER).css('position', 'relative');
          container.append(spinner);
          container.slideDown();
          // color the button with green
          dis.css('color', '#8bc53f');

          var stats = LocalCache.news.statistics[newsId];
          if(stats === undefined) {
              sln.call({
                    url: '/common/news/statistics',
                    data: {
                        news_id: newsId
                    },
                    type: 'GET',
                    success: function (newsItem) {
                        LocalCache.news.statistics[newsId] = newsItem.statistics;
                        spinner.remove();
                        renderStatistics(dis, container, newsId, newsItem.statistics, property);
                    }
              });
          } else {
              spinner.remove();
              renderStatistics(dis, container, newsId, stats, property);
          }
       }
    }

    /*
    groups the time stats with day date instead of time

    :param timeStats: an array of stats objects {timestamp: xxxx, amount: xxx}

    :returns: a map with keys as date strings
              and values are amounts
    */
    function groupTimeStatsByDay(timeStats) {
        // map for ensuring the insertion order
        var group = new Map();

        for(var i = 0; i < timeStats.length; i++) {
            var date = new Date(timeStats[i].timestamp * 1000);
            date.setHours(0, 0, 0, 0);
            if(group[date] !== undefined) {
                group[date] += timeStats[i].amount;
            } else {
                group[date] = timeStats[i].amount;
            }
        }

        return group;
    }

    function renderStatistics(dis, container, newsId, statistics, property) {
        google.charts.load('current', {'packages': ['corechart', 'annotationchart']});
        google.charts.setOnLoadCallback(drawCharts);
        function drawCharts() {
            var lineOptions = {
                  displayZoomButtons: false,
                  displayRangeSelector: false,
              },
              barOptions = {
                  title: T('age'),
                  legend: {
                      position: 'bottom'
                  },
                  width: 600,
                  hAxis: {
                      showTextEvery: 3
                  },
                  isStacked: true
              },
              pieOptions = {
                  title: T('gender'),
                  width: 300,
                  legend: {
                      position: 'bottom'
                  }
              };
            var ageData, genderData, timeData;
            // structure:
            // [
            //     ['App', 'rogerthat', 'be-loc'],
            //     ['0-5', 0, 42],
            //     ['5-10', 0, 420],
            // ]
            var hasGenderData = false;
            for (var appCounter = 0; appCounter < statistics.length; appCounter++) {
                var statisticsInApp = statistics[appCounter];
                var appId = statisticsInApp.app_id;
                var stats = statisticsInApp[property];
                var j, len;
                if (appCounter === 0) {
                    ageData = [
                        [T('age')]
                    ];
                    genderData = [
                        [T('gender'), T(property)]
                    ];
                    timeData = [{
                        0: {label: T('Date'), type: 'date'}
                    }];
                    for (j = 0, len = stats.age.length; j < len; j++) {
                        ageData.push([stats.age[j].key]);
                    }
                    for (j = 0, len = stats.gender.length; j < len; j++) {
                        genderData.push([T(stats.gender[j].key), 0]);
                    }
                }
                var app = ALL_APPS.filter(function (p) {
                    return p.id === appId;
                })[0];
                var appName = app ? app.name : appId;
                ageData[0].push(appName);
                timeData[0][appCounter + 1] = appName;
                for (j = 0; j < stats.age.length; j++) {
                    ageData[j + 1].push(stats.age[j].value);
                }
                for (j = 0; j < stats.gender.length; j++) {
                    genderData[j + 1][1] += stats.gender[j].value;
                    hasGenderData = hasGenderData || genderData[j + 1][1] !== 0;
                }

                j = 0;
                var timeByDayDate = groupTimeStatsByDay(stats.time);
                for(var dateStr in timeByDayDate) {
                    if(timeData[j + 1]  === undefined) {
                        timeData[j + 1] = {
                            // must be date object in annotation charts
                            0: new Date(dateStr)
                        };
                    }
                    // set amount
                    if(j > 0) {
                        // sum with previous amount if not the first
                        var prev = timeData[j][appCounter + 1];
                        timeData[j + 1][appCounter + 1] = prev + timeByDayDate[dateStr];
                    } else {
                        timeData[j + 1][appCounter + 1] = timeByDayDate[dateStr];
                    }
                    j++;
                }
            }
            // apps differ in recorded time amounts, also
            // time spans (app1: 5 months, app2: 1 year)...etc
            // this will fill the missing values
            // because the data is accumulative
            fillMissingTimeData(timeData);
            // append and show the divs first
            var template = $.tmpl(templates['broadcast/news_stats_row'],{
              news_id: newsId
            });
            container.append(template);
            var ageElem = document.getElementById('stats_age_graph_' + newsId);
            var ageTable = google.visualization.arrayToDataTable(ageData);
            var ageChart = new google.visualization.ColumnChart(ageElem);
            ageChart.draw(ageTable, barOptions);
            var genderElem = document.getElementById('stats_gender_graph_' + newsId);
            if (hasGenderData) {
                var genderTable = google.visualization.arrayToDataTable(genderData);
                var genderChart = new google.visualization.PieChart(genderElem);
                genderChart.draw(genderTable, pieOptions);
            } else {
                genderElem.innerHTML = '<i>' + T('not_enough_data') + '</i>';
            }
            var timeElem = document.getElementById('stats_time_graph_' + newsId);
            $.each(timeData, function (i, td) {
                timeData[i] = $.map(td, function (value, index) {
                    return [value];
                });
            });
            if (timeData.length > 2) {
                var timeTable = google.visualization.arrayToDataTable(timeData);
                var timeChart = new google.visualization.AnnotationChart(timeElem);
                timeChart.draw(timeTable, lineOptions);
            }
        }
    }

    function deleteNews() {
        var dis = $(this);
        var newsId = parseInt(dis.attr('news_id'));
        var newsItem = LocalCache.newsItems.result.filter(function (n) {
            return n.id === newsId;
        })[0];
        if (!newsItem || newsItem.published) {
            dis.remove();
            return;
        }
        confirmDeleteNews(function () {
            sln.call({
                url: '/common/news/delete',
                method: 'post',
                data: {
                    news_id: newsId
                },
                success: success
            });
        });

        function confirmDeleteNews(callback) {
            var msg = T('confirm_delete_news', {news_title: newsItem.title || newsItem.qr_code_caption});
            sln.confirm(msg, callback);
        }

        function success(response) {
            if (!response.success) {
                sln.alert(response.error || T('error-occured-unknown-try-again'));
            } else {
            	dis.remove();
                $('#news_item_' + newsId).remove();
                // remove the news item from cache
                var newsItemIndex = $.inArray(newsItem, LocalCache.newsItems.result);
                if( newsItemIndex > -1) {
                    LocalCache.newsItems.result.splice(newsItemIndex, 1);
                }
            }
        }
    }

    function renderNewsPage(serviceMenu, newsItem) {
        getBroadcastOptions(function (broadcastOptions) {
            getAppStatistics(function (appStatistics) {
                modules.menu.getMenu(function (menu) {
                    if (orderSettings.order_type !== CONSTS.ORDER_TYPE_ADVANCED) {
                        menu = null;
                    }
                    modules.sandwich.getSandwichSettings(function (sandwichSettings) {
                        render(broadcastOptions, appStatistics, menu, sandwichSettings);
                    });
                });
            });
        });

        function getActionButtonValue(actionButton) {
            if (!actionButton) {
                return '';
            }
            if (actionButton.id === 'url') {
                return actionButton.action;
            }
            return actionButton.action.split('://')[1];
        }

        function render(broadcastOptions, appStatistics, menu, sandwichSettings) {
            var actionButtonId, actionButton, actionButtonLabel, flowParams, canOrderApps, result,
                restaurantReservationDate, selectedSandwich, actionButtonValue;
            restaurantReservationDate = new Date().getTime() / 1000;
            var promotionProduct = broadcastOptions.news_promotion_product;
            actionButton = newsItem ? newsItem.buttons[0] : null;
            actionButtonId = actionButton ? actionButton.id : null;
            actionButtonValue = getActionButtonValue(actionButton);
            actionButtonLabel = actionButton ? actionButton.caption : '';
            canOrderApps = broadcastOptions.subscription_info.has_signed && broadcastOptions.can_order_extra_apps;
            result = getTotalReach(canOrderApps, appStatistics, newsItem);
            var apps = result[0],
                totalReach = result[1];
            if (actionButton) {
                try {
                    flowParams = JSON.parse(actionButton.flow_params);
                } catch (e) {
                    console.error(e);
                }
            }
            if (flowParams) {
                if (flowParams.advancedOrder && flowParams.advancedOrder.categories && menu) {
                    for (var i = 0; i < menu.categories.length; i++) {
                        var category = menu.categories[i],
                            flowParamCategory = flowParams.advancedOrder.categories[category.id];
                        if (flowParamCategory) {
                            for (var j = 0; j < category.items.length; j++) {
                                var item = category.items[j],
                                    flowParamItem = flowParamCategory.items[item.id];
                                if (flowParamItem) {
                                    item.selectedAmount = flowParamItem.value;
                                }
                            }
                        }
                    }
                } else if (flowParams.reservationDate) {
                    restaurantReservationDate = flowParams.reservationDate;
                } else if (flowParams.sandwichType) {
                    selectedSandwich = {
                        type: flowParams.sandwichType,
                        topping: flowParams.sandwichTopping,
                        options: flowParams.sandwichOptions
                    };
                }
            }
            var allowedButtonActions = [{
                value: 'url',
                type: 'url',
                translation: T('WEBSITE'),
                defaultLabel: T('open_website')
            }, {
                value: 'phone',
                type: 'tel',
                translation: T('phone_number'),
                defaultLabel: T('Call')
            }, {
                value: 'email',
                type: 'email',
                translation: T('email_address'),
                defaultLabel: T('send_email')
            }, {
                value: 'attachment',
                type: 'url',
                translation: T('Attachment'),
                defaultLabel:T('Attachment')
            }
            ];
            actionButton = {
                id: actionButtonId,
                value: actionButtonValue,
                label: actionButtonLabel
            };
            var params = {
                T: T,
                serviceMenu: serviceMenu,
                canPromote: canOrderApps,
                canSendNewsItem: broadcastOptions.next_news_item_time * 1000 < new Date().getTime(),
                nextNewsItemTime: broadcastOptions.next_news_item_time,
                broadcastTypes: broadcastOptions.editable_broadcast_types,
                promotionProduct: broadcastOptions.news_promotion_product,
                product_counts_labels: promotionProduct.possible_counts.map(function (c) {
                    return T('days_amount', {amount: c});
                }),
                product_prices: promotionProduct.possible_counts.map(function (c) {
                    return LEGAL_ENTITY_CURRENCY + ' ' + (c * promotionProduct.price / 100);
                }),
                newsItem: newsItem || {
                    type: NEWS_TYPE_NORMAL
                },
                actionButton: actionButton,
                newsTypes: newsTypes,
                apps: apps,
                totalReach: totalReach,
                menu: menu,
                UNIT_SYMBOLS: UNIT_SYMBOLS,
                UNITS: UNITS,
                CURRENCY: CURRENCY,
                CONSTS: CONSTS,
                CommonTranslations: CommonTranslations,
                restaurantReservationDate: restaurantReservationDate,
                sandwichSettings: sandwichSettings,
                selectedSandwich: selectedSandwich || {},
                isFlagSet: sln.isFlagSet,
                allowedButtonActions: allowedButtonActions,
                roles: broadcastOptions.roles,
            };
            var html = $.tmpl(templates['broadcast/broadcast_news'], params);
            $('#broadcast_page_news').html(html);
            newsEventHandlers(newsItem, appStatistics, broadcastOptions);
        }
    }

    function pollCCInfo(callback) {
        getCreditCardInfo(function (data) {
            if (!data) {
                // data not available yet. Try again in 500 ms...
                console.info('Credit card info not available yet. Retrying...');
                setTimeout(function () {
                    pollCCInfo(callback);
                }, 500);
            } else {
                callback(data);
            }
        });

    }

    function getCreditCardInfo(callback) {
        var options = {
            method: 'get',
            url: '/common/billing/card/info',
            success: callback
        };
        sln.call(options);
    }

    function getTotalReach(canOrderApps, appStatistics, originalNewsItem, newAdditionalApps) {
        newAdditionalApps = newAdditionalApps || [];
        var apps;
        if (canOrderApps) {
            apps = JSON.parse(JSON.stringify(ALL_APPS)).filter(function (a) {
                return a.id !== 'rogerthat';
            });
        } else {
            apps = JSON.parse(JSON.stringify(ALL_APPS)).filter(function (a) {
                return a.id !== 'rogerthat' && ACTIVE_APPS.indexOf(a.id) !== -1;
            });
        }
        var totalReach = 0;
        $.each(apps, function (i, app) {
            var stats = appStatistics.filter(function (a) {
                return a.app_id === app.id;
            })[0];
            if (stats) {
                app.visible = true;
                if (isDemoApp) {
                	app.total_user_count = randomReachCount;
                } else {
                    app.total_user_count = stats.total_user_count;
                }
                var hasOrderedApp = originalNewsItem && originalNewsItem.app_ids.indexOf(app.id) !== -1;
                if (hasOrderedApp || isPresentInApp(app.id) && !originalNewsItem) {
                    app.checked = 'checked';
                }
                if (hasOrderedApp) {
                    app.disabled = 'disabled';
                }
                if (hasOrderedApp || newAdditionalApps.indexOf(app.id) !== -1) {
                    totalReach += app.total_user_count;
                }
            } else {
                app.visible = false;
            }
        });
        return [apps, totalReach];
    }

    function newsEventHandlers(originalNewsItem, appStatistics, broadcastOptions) {
        var elemRadioNewsType = $('input[name=news_select_type]'),
            elemInputTitle = $('#news_input_title'),
            elemInputMessage = $('#news_input_message'),
            elemSelectBroadcastType = $('#news_select_broadcast_type'),
            elemInputImage = $('#news_input_image'),
            elemInputUseCoverPhoto = $('#news_button_cover_photo'),
            elemSelectButton = $('#select_broadcast_button'),
            elemCheckboxPromote = $('#checkbox_promote'),
            elemImagePreview = $('#news_image_preview'),
            elemImageEditorContainer = $('#news_image_editor_container'),
            elemButtonRemoveImage = $('#news_button_remove_image'),
            elemButtonSaveImage = $('#news_button_save_image'),
            elemButtonSubmit = $('#news_submit'),
            elemButtonPrevious = $('#news_back'),
            elemButtonNext = $('#news_next'),
            elemForm = $('#form_broadcast_news'),
            elemNewsFormContainer = $('#news_form_container'),
            elemStepTitle = $('#step_title'),
            elemStepDescription = $('#step_content_explanation'),
            elemNewsPreview = $('#news_preview'),
            elemNewsActionOrder = $('#news_action_order'),
            elemNewsActionAddAttachment = $('#news_action_add_attachment'),
            elemNewsActionRemoveAttachment = $('#news_action_remove_attachment'),
            elemNewsActionAttachmentCaption = $('#news_action_attachment_caption'),
            elemNewsActionAttachmentValue = $('#news_action_attachment_value'),
            elemCheckboxesApps = elemForm.find('input[name=news_checkbox_apps]'),
            elemCheckboxesRoles = elemForm.find('#roles').find('input[type=checkbox]'),
            elemNewsActionRestaurantDatepicker = $('#news_action_restaurant_reservation_datepicker'),
            elemNewsActionRestaurantTimepicker = $('#news_action_restaurant_reservation_timepicker'),
            elemNewsActionSandwichType = $('#news_action_sandwich_bar_types'),
            elemNewsActionSandwichTopping = $('#news_action_sandwich_bar_toppings'),
            elemNewsActionSandwichOptions = $('input[name=news_action_sandwich_bar_options]'),
            elemActionButtonInputs = $('.news_action').find('[news_action_render_preview]'),
            elemCheckboxSchedule = $('#news_send_later'),
            elemInputScheduleDate = $('#news_scheduled_at_date'),
            elemInputScheduleTime = $('#news_scheduled_at_time'),
            elemScheduledAtError = $('#news_scheduled_at_error'),
            elemInputActionButtonUrl = $('#news_action_url_value'),
            elemCheckPostToFacebook = $('#post_to_facebook'),
            elemCheckPostToTwitter = $('#post_to_twitter'),
            elemFacebookPage = $('#facebook_page'),
            elemConfigureTargetAudience = $('#configure_target_audience'),
            hasSignedOrder = broadcastOptions.subscription_info.has_signed,
            restaurantReservationDate;

        var itemIsPublished = originalNewsItem && originalNewsItem.published;

        elemButtonSaveImage.hide();
        elemButtonRemoveImage.toggle(!(!originalNewsItem || !originalNewsItem.image_url));
        elemButtonSubmit.hide();

        var renderPreview = sln.debounce(doRenderPreview, 250);
        elemCheckboxPromote.change(paidContentChanged);
        elemButtonSubmit.click(newsFormSubmitted);
        elemInputImage.change(imageChanged);
        elemInputUseCoverPhoto.click(useCoverPhoto);
        elemButtonRemoveImage.click(removeImage);
        elemCheckboxesApps.change(appsChanged);
        elemCheckboxSchedule.change(scheduleChanged);
        elemButtonPrevious.click(previousStep);
        elemButtonNext.click(nextStep);
        // Prepares the form for validation
        elemForm.validate(validation);

        elemRadioNewsType.change(newsTypeChanged);
        elemSelectBroadcastType.change(renderPreview);
        elemSelectButton.change(actionButtonChanged);
        elemInputTitle.on('input paste keyup', renderPreview);
        elemInputMessage.on('input paste keyup', renderPreview);
        elemActionButtonInputs.on('input paste keyup', renderPreview);

        elemInputActionButtonUrl.keyup(actionButtonUrlChanged);

        elemNewsActionAddAttachment.click(addAttachment);
        elemNewsActionRemoveAttachment.click(removeAttachment);

        restaurantReservationDate = new Date(parseInt(elemNewsActionRestaurantDatepicker.attr('data-date')) * 1000);
        elemNewsActionRestaurantDatepicker.datepicker({
            format: sln.getLocalDateFormat(),
            startDate: restaurantReservationDate.toLocaleDateString()
        }).datepicker('setValue', restaurantReservationDate);
        elemNewsActionRestaurantTimepicker.timepicker({
            showMeridian: false
        }).timepicker('setTime', restaurantReservationDate.getHours() + ':' + restaurantReservationDate.getMinutes());
        var scheduleDate;
        if (originalNewsItem && originalNewsItem.scheduled_at !== 0) {
            scheduleDate = new Date(originalNewsItem.scheduled_at * 1000);
        } else {
            scheduleDate = new Date();
            scheduleDate.setDate(scheduleDate.getDate() + 1);
            scheduleDate.setHours(scheduleDate.getHours() - 1);
            scheduleDate.setMinutes(0);
        }
        elemInputScheduleDate.datepicker({
            format: sln.getLocalDateFormat()
        }).datepicker('setValue', scheduleDate);
        elemInputScheduleDate.parent().find('span').click(function () {
            if (!elemInputScheduleDate.attr('disabled')) {
                elemInputScheduleDate.datepicker('show');
            }
        });

        elemCheckPostToFacebook.change(checkForFacebookLogin);
        elemCheckPostToTwitter.change(checkForTwitterLogin);

        $("#age_max_plus").click(plusClick($("#age_max")));
        $("#age_min_plus").click(plusClick($("#age_min")));
        $("#age_max_min").click(minClick($("#age_max")));
        $("#age_min_min").click(minClick($("#age_min")));

        elemConfigureTargetAudience.change(configureTargetAudience);
        function configureTargetAudience() {
            if(elemConfigureTargetAudience.is(':checked')) {
                $('#target_audience').show();
            } else {
                $('#target_audience').hide();
            }
        }

        function checkFacebookPermissions(permissionsList) {
            var errors = [];

            if(permissionsList.indexOf('manage_pages') === -1 ||
               permissionsList.indexOf('publish_pages') === -1) {
                errors.push(T('facebook-manage-pages-required'));
            }
            if(permissionsList.indexOf('publish_actions') === -1) {
                errors.push(T('facebook-publish-actions-required'));
            }

            if(errors.length > 0) {
                sln.alert(errors.join('<br/>'));
                return false;
            } else {
                return true;
            }
        }

        function loginToFacebook() {
            FB.login(function (response) {
                if(response && response.authResponse) {
                    if(checkFacebookPermissions(response.authResponse.grantedScopes)) {
                        loadFacebookPages(response.authResponse.accessToken);
                    } else {
                        elemCheckPostToFacebook.attr('checked', false);
                    }
                } else {
                    elemCheckPostToFacebook.attr('checked', false);
                }
                sln.hideProcessing();
            },
            {
                scope: 'manage_pages,publish_pages,publish_actions',
                return_scopes: true
            });
        }

        function checkForFacebookLogin() {
            if(elemCheckPostToFacebook.is(':checked')) {
                sln.showProcessing(CommonTranslations.LOADING_DOT_DOT_DOT);
                loginToFacebook();
            } else {
                elemFacebookPage.hide();
            }
        }

        function checkForTwitterLogin() {
            if(elemCheckPostToTwitter.is(':checked')) {
                var userName = elemBroadcastOnTwitter.val();
                if(!userName) {
                    sln.alert(CommonTranslations.TWITTER_PAGE_REQUIRED);
                    elemCheckPostToTwitter.attr('checked', false);
                }
            }
        }

        function loadFacebookPages(userAccessToken) {
            elemFacebookPage.html('');
            var param = '/me/accounts?access_token=' + userAccessToken;
            FB.api(param, function(response) {
                if(!response || response.error) {
                    elemCheckPostToFacebook.attr('checked', false);
                    return;
                }
                $.each(response.data, function(i, page) {
                    if($.inArray('CREATE_CONTENT', page.perms) > -1) {
                        elemFacebookPage.append($('<option>', {text: page.name, value: page.access_token}));
                    }
                });
                elemFacebookPage.append($('<option>', {text: T('my-timeline'), value: userAccessToken}));
                elemFacebookPage.show();
                sln.hideProcessing();
            });
        }

        elemInputScheduleTime.timepicker({
            showMeridian: false
        }).timepicker('setTime', scheduleDate.getHours() + ':' + scheduleDate.getMinutes());
        currentStep = 0;
        stepChanged(getNewsFormData());
        appsChanged();

        if (originalNewsItem && originalNewsItem.image_url) {
            elemImageEditorContainer.show();
        }

        function newsTypeChanged() {
            if (!elemInputTitle.val()) {
                elemInputTitle.val(T('news_coupon_default_text', {
                    merchant_name: LocalCache.settings.name
                }));
            }
            renderPreview();
        }

        function actionButtonChanged() {
            var selectedAction = (elemSelectButton.val() || '').split('.');
            $('.news_action').hide();
            var defaultActions = ['url', 'email', 'phone', 'attachment'];
            var isDefaultAction = defaultActions.includes(selectedAction[0]);
            if (selectedAction[0].startsWith('__sln__') || isDefaultAction) {
                var showElem = true;
                if (isDefaultAction) {
                    $('#news_action_' + selectedAction[0]).toggle(showElem);
                } else {
                    if (orderSettings.order_type !== CONSTS.ORDER_TYPE_ADVANCED && selectedAction[1] === 'order') {
                        showElem = false;
                    }
                    $('#news_action_' + selectedAction[1]).toggle(showElem);
                }
            } else if (selectedAction[0] === 'reserve1') {
                $('#news_action_restaurant_reservation').show();
            }


            renderPreview();
        }

        function actionButtonUrlChanged() {
            var url = elemInputActionButtonUrl.val();
            if (url && !url.startsWith('http://') && !url.startsWith('https://') && url.length > 8) {
                elemInputActionButtonUrl.val('http://' + url);
            }
        }

        function removeAttachment() {
            // reset action button to none and
            elemSelectButton.find('option:eq(0)').prop('selected', 'true');
            // reset the previous values
            elemNewsActionAttachmentValue.val('');
            elemNewsActionAttachmentCaption.val(T('Attachment'));
            // show add button
            elemNewsActionAddAttachment.show();
            elemNewsActionRemoveAttachment.hide();
            // then trigger change event to re-render the preview
            actionButtonChanged();
        }

        function shouldPay(callback) {
            var shouldShowPaymentScreen = false;
            var selectedAppIds = [];
            elemCheckboxesApps.filter(':checked').each(function () {
                selectedAppIds.push(this.value);
            });
            var originalApps = originalNewsItem ? originalNewsItem.app_ids : [];
            for (var i = 0; i < selectedAppIds.length; i++) {
                if (!isPresentInApp(selectedAppIds[i])) {
                    shouldShowPaymentScreen = true;
                    break;
                }
            }
            if (!shouldShowPaymentScreen && elemCheckboxPromote.prop('checked')) {
                getPromotedCost(selectedAppIds, true, function (data) {
                    $.each(data, function (i, costInApp) {
                        if (originalApps.indexOf(costInApp.app_id) === -1 && costInApp.remaining_free === 0) {
                            shouldShowPaymentScreen = true;
                        }
                    });
                    callback(shouldShowPaymentScreen);
                });
            } else {
                callback(shouldShowPaymentScreen);
            }
        }

        function paidContentChanged() {
            shouldPay(function (pay) {
                elemButtonNext.toggle(pay);
                elemButtonSubmit.toggle(!pay);
            });
            if (elemCheckboxPromote.prop('checked')) {
                var allAppIds = ALL_APPS.map(function (app) {
                    return app.id;
                });
                getPromotedCost(allAppIds, true, function (promotedCosts) {
                    $.each(promotedCosts, function (i, promotedCost) {
                        if (promotedCost.remaining_free !== 0) {
                            var text = T('x_free_promoted_items_remaining', {amount: promotedCost.remaining_free});
                            $('#free_promoted_' + promotedCost.app_id).html('<br />' + text);
                        }
                    });
                });
            } else {
                $('.free_promoted_text').empty();
            }
        }

        function getNewsFormData() {
            var data = {
                title: elemInputTitle.val().trim() || '',
                message: elemInputMessage.val().trim() || '',
                broadcast_type: elemSelectBroadcastType.val().trim(),
                sponsored: elemCheckboxPromote.prop('checked'),
                type: parseInt(elemRadioNewsType.filter(':checked').val())
            };
            if (elemImagePreview.attr('src')) {
                // update image or leave old image
                if (elemImagePreview.attr('src').indexOf('data:image/jpeg') === 0) {
                    data.image = elemImagePreview.attr('src');
                }
            } else {
                // delete image
                data.image = null;
            }

            if (data.type === NEWS_TYPE_QR) {
                data.qr_code_caption = data.title;
                data.title = null;
            }
            var selectedActionButtonId = elemSelectButton.val() || '';
            if (selectedActionButtonId) {
                var actionPrefix = 'smi',
                    actionValue = selectedActionButtonId,
                    actionCaption = elemSelectButton.find(':selected').text().trim();
                switch (selectedActionButtonId) {
                    case 'attachment':
                    case 'url':
                        var url_or_attachment = selectedActionButtonId === 'url' ? 'url' : 'attachment';
                        var elemValue = $('#news_action_' + url_or_attachment + '_value');
                        actionValue = elemValue.val();
                        actionCaption = $('#news_action_' + url_or_attachment + '_caption').val();
                        try {
                            var splitAction = actionValue.match(/https?:\/\/(.*)/);
                            var isHttps = splitAction.length ? splitAction[0].indexOf('https') === 0 : false;
                            actionPrefix = isHttps ? 'https' : 'http';
                            actionValue = splitAction[1];
                        } catch (e) {
                            console.warn(e);
                            actionValue = elemValue.val();
                            actionPrefix = 'http';
                        }
                        break;
                    case 'email':
                        actionPrefix = 'mailto';
                        actionValue = $('#news_action_email_value').val();
                        actionCaption = $('#news_action_email_caption').val();
                        break;
                    case 'phone':
                        actionPrefix = 'tel';
                        actionValue = $('#news_action_phone_value').val();
                        actionCaption = $('#news_action_phone_caption').val();
                        break;
                }
                var actionButton = {
                    id: selectedActionButtonId,
                    caption: actionCaption,
                    action: actionPrefix + '://' + actionValue,
                    flow_params: ''
                };
                var flowParams = {};
                switch (selectedActionButtonId) {
                    case '__sln__.order':
                        /**
                         * Structure
                         *
                         * "categories" : {
                         *     "category-1-uuid":{
                         *         "items:{
                         *             "product-1-uuid":{
                         *                 "value": 50
                         *             }
                         *         }
                         *     }
                         * }
                         **/
                        flowParams.advancedOrder = {};
                        var categories = {};
                        elemNewsActionOrder.find('input').each(function () {
                            var input = $(this);
                            var amount = parseInt(input.val()) || 0;
                            if (amount) {
                                var categoryId = input.data('category');
                                var productId = input.data('product');
                                if (!categories[categoryId]) {
                                    categories[categoryId] = {
                                        items: {}
                                    };
                                }
                                if (!categories[categoryId].items[productId]) {
                                    categories[categoryId].items[productId] = {};
                                }
                                categories[categoryId].items[productId] = {
                                    value: amount
                                };
                            }
                        });
                        flowParams.advancedOrder.categories = categories;
                        break;
                    case '__sln__.sandwich_bar':
                        flowParams.sandwichType = 'type_' + elemNewsActionSandwichType.val();
                        flowParams.sandwichTopping = 'topping_' + elemNewsActionSandwichTopping.val();
                        flowParams.sandwichOptions = [];
                        elemNewsActionSandwichOptions.filter(':checked').each(function () {
                            flowParams.sandwichOptions.push('option_' + this.value);
                        });
                        break;
                    case 'reserve1':
                        if (elemNewsActionRestaurantDatepicker.data('datepicker')) {
                            var date = elemNewsActionRestaurantDatepicker.data('datepicker').date;
                        } else {
                            date = new Date();
                            date.setHours(date.getHours() + 2);
                            date.setMinutes(0);
                        }
                        if (elemNewsActionRestaurantTimepicker.data('timepicker')) {
                            date.setHours(elemNewsActionRestaurantTimepicker.data('timepicker').hour);
                            date.setMinutes(elemNewsActionRestaurantTimepicker.data('timepicker').minute);
                        }
                        flowParams.reservationDate = parseInt(date.getTime() / 1000);
                        break;
                }
                actionButton.flow_params = JSON.stringify(flowParams);
                data.action_button = actionButton;
            }
            var newAppIds = [];
            elemCheckboxesApps.filter(':checked').each(function () {
                if (!originalNewsItem
                    || (originalNewsItem && originalNewsItem.app_ids.indexOf(this.value) === -1)
                    || !originalNewsItem.sticky && data.sponsored) {
                    newAppIds.push(this.value);
                }
            });
            if (elemCheckboxSchedule.prop('checked') && !itemIsPublished) {
                var scheduledDate = new Date(elemInputScheduleDate.data('datepicker').date.getTime());
                var time = elemInputScheduleTime.data('timepicker');
                scheduledDate.setHours(time.hour);
                scheduledDate.setMinutes(time.minute);
                data.scheduled_at = parseInt(scheduledDate.getTime() / 1000);
            }
            data.app_ids = newAppIds;

            if(elemCheckPostToFacebook.is(':checked')) {
                data.broadcast_on_facebook = true;
                data.facebook_access_token = elemFacebookPage.val();
            } else {
                data.broadcast_on_facebook = false;
            }

            if(elemCheckPostToTwitter.is(':checked')) {
                data.broadcast_on_twitter = true;
            } else {
                data.broadcast_on_twitter = false;
            }

            if(elemConfigureTargetAudience.is(':checked')) {
                data.target_audience = {
                    min_age: parseInt($('#age_min').val()),
                    max_age: parseInt($('#age_max').val()),
                    gender: parseInt($('#gender').val()),
                    connected_users_only: $('#connected_users_only').is(':checked')
                };
            }
            data.role_ids = []
            elemCheckboxesRoles.filter(':checked').each(function() {
                data.role_ids.push(parseInt($(this).val()));
            });
            return data;
        }

        function newsFormSubmitted(e) {
            e.preventDefault();
            var data = getNewsFormData();
            // validate the scheduled date/time again
            // as the user may publish after the scheduled date/time has passed
            if(!validateScheduledAt(data)) {
                sln.alert(T('date_must_be_in_future'), null, CommonTranslations.ERROR);
                previousStep();
                return;
            }
            // check for facebook access token even if the post on facebook is checked
            if(!elemCheckPostToFacebook.is(':disabled')) {
                if(data.broadcast_on_facebook && !data.facebook_access_token) {
                    sln.alert(T('Login with facebook first'), null, CommonTranslations.ERROR);
                    return;
                }
            }
            submitNews(data);
        }

        function getPromotedCost(appIds, promoted, callback) {
            var cacheStr = appIds.sort().join(',');
            if (!promoted || !appIds) {
                callback();
                return;
            } else if (LocalCache.news.promotedNews[cacheStr]) {
                callback(LocalCache.news.promotedNews[cacheStr]);
                return;
            }
            sln.call({
                url: '/common/news/promoted_cost',
                method: 'post',
                data: {
                    app_ids: appIds
                },
                success: function (data) {
                    LocalCache.news.promotedNews[cacheStr] = data;
                    callback(data);
                }
            });
        }

        function showNewsOrderPage(data) {
            var checkoutContainer = $('#tab7');
            checkoutContainer.html(TMPL_LOADING_SPINNER);
            // apologies for this monstrosity
            getCreditCardInfo(function (creditCardInfo) {
                getBroadcastOptions(function (broadcastOptions) {
                    getPromotedCost(data.app_ids, data.sponsored, function (promotedCostList) {
                        var promotionProduct = broadcastOptions.news_promotion_product,
                            extraAppProduct = broadcastOptions.extra_city_product,
                            fromDate = new Date(),
                            untilDate = new Date();
                        untilDate.setDate(fromDate.getDate() + 7);
                        var orderItems = [],
                            orderItemNumber = 0;
                        if (data.app_ids) {
                            for (var i = 0; i < data.app_ids.length; i++) {
                                var currentAppId = data.app_ids[i];
                                var appName = ALL_APPS.filter(function (p) {
                                    return p.id === currentAppId;
                                })[0].name;
                                if (data.sponsored) {
                                    var promotedCount = promotedCostList.filter(function (item) {
                                        return item.app_id === currentAppId;
                                    })[0];
                                    var comment;
                                    if (promotedCount.remaining_free > 0) {
                                        if (promotedCount.remaining_free === 1) {
                                            comment = T('this_is_the_last_free_promoted_news_item', {
                                                app_name: appName
                                            });
                                        } else {
                                            // No need to bill for something that is free.
                                            continue;
                                        }
                                    } else {
                                        comment = promotionProduct.default_comment
                                            .replace('%(post_title)s', data.title || data.qr_code_caption)
                                            .replace('%(from_date)s', sln.format(fromDate))
                                            .replace('%(until_date)s', sln.format(untilDate))
                                            .replace('%(app_name)s', appName);
                                    }

                                    var sponsoredOrderItem = {
                                        count: promotedCount.count,
                                        description: promotionProduct.description,
                                        comment: comment,
                                        number: orderItemNumber,
                                        price: promotionProduct.price,
                                        product: promotionProduct.code,
                                        app_id: currentAppId
                                    };
                                    sponsoredOrderItem.service_visible_in = sponsoredOrderItem.comment;
                                    orderItems.push(sponsoredOrderItem);
                                    orderItemNumber++;
                                }
                                if (!isPresentInApp(currentAppId)) {
                                    var extraCityOrderItem = {
                                        count: broadcastOptions.subscription_info.months_left,
                                        description: extraAppProduct.description,
                                        comment: T('service_visible_in_app', {
                                            app_name: appName,
                                            subscription_expiration_date: broadcastOptions.subscription_info.expiration_date,
                                            amount_of_months: broadcastOptions.subscription_info.months_left,
                                            extra_city_price: CURRENCY + (extraAppProduct.price / 100).toFixed(2)
                                        }),
                                        app_id: currentAppId,
                                        price: extraAppProduct.price,
                                        product: extraAppProduct.code,
                                        number: orderItemNumber
                                    };
                                    extraCityOrderItem.service_visible_in = extraCityOrderItem.comment;
                                    orderItems.push(extraCityOrderItem);
                                    orderItemNumber++;
                                }
                            }
                        }
                        renderNewsOrderPage(orderItems, creditCardInfo);
                    });
                });
            });

            function renderNewsOrderPage(orderItems, creditCardInfo) {
                if (!creditCardInfo) {
                    creditCardInfo = false;
                }
                var totalExclVat = 0, vat = 0, total = 0;
                $.each(orderItems, function (i, orderItem) {
                    var tot = orderItem.price * orderItem.count / 100;
                    var vatTemp = tot * VAT_PCT / 100;
                    totalExclVat += tot;
                    vat += vatTemp;
                    total += tot + vatTemp;
                });
                var html = $.tmpl(templates['shop/shopping_cart'], {
                    items: orderItems,
                    vatPct: VAT_PCT,
                    totalExclVat: totalExclVat.toFixed(2),
                    vat: vat.toFixed(2),
                    total: total.toFixed(2),
                    checkout: true,
                    creditCard: creditCardInfo,
                    t: CommonTranslations,
                    LEGAL_ENTITY_CURRENCY: LEGAL_ENTITY_CURRENCY,
                    customBackButton: T('back')
                });
                checkoutContainer.html(html);
                var elemBroadcast = $('#broadcast');
                elemBroadcast.find('#change-creditcard, #link-cc, #add-creditcard').click(function () {
                    callBackAfterCCLinked = function () {
                        pollCCInfo(function (ccinfo) {
                            creditCardInfo = ccinfo ? ccinfo : false; // when undefined, it shows 'loading'.
                            renderNewsOrderPage(orderItem, creditCardInfo);
                        });
                    };
                    manageCreditCard();
                });
                elemBroadcast.find('#checkout').click(function () {
                    // show loading instead of 'pay with creditcard'
                    var $this = $(this);
                    if ($this.is(':disabled')) {
                        return;
                    }
                    if (creditCardInfo) {
                        loading();
                        submitNews(data, orderItems);
                    } else {
                        callBackAfterCCLinked = function () {
                            pollCCInfo(function (ccinfo) {
                                creditCardInfo = ccinfo ? ccinfo : false; // when undefined, it shows 'loading'.
                                if (creditCardInfo) {
                                    loading();
                                    submitNews(data, orderItems);
                                }
                            });
                        };
                        manageCreditCard();
                    }
                    function loading() {
                        $this.find('.normal').hide();
                        $this.find('.loading').show();
                        $this.attr('disabled', true);
                    }
                });
                elemBroadcast.find('#shopping_cart_back_button').click(previousStep);
            }
        }

        function submitNews(newsItem, orderItems) {
            if (elemButtonSubmit.attr('disabled')) {
                return;
            }
            if (!elemForm.valid()) {
                return;
            }
            orderItems = orderItems || [];
            var data = newsItem;
            data.order_items = orderItems;
            data.news_id = originalNewsItem ? originalNewsItem.id : undefined;
            elemButtonSubmit.attr('disabled', true);

            if (data.scheduled_at > 0) {
                sln.showProcessing(CommonTranslations.LOADING_DOT_DOT_DOT);
            } else {
                sln.showProcessing(CommonTranslations.PUBLISHING_DOT_DOT_DOT);
            }
            sln.call({
                url: '/common/news',
                method: 'post',
                data: data,
                success: function (result) {
                    sln.hideProcessing();
                    if(result.errormsg && !result.success) {
                        sln.alert(result.errormsg, null, CommonTranslations.ERROR);
                        // re-enable the submit button
                        elemButtonSubmit.attr('disabled', false);
                        return;
                    }
                    LocalCache.news.promotedNews = {};
                    elemButtonSubmit.attr('disabled', false);
                    var text;
                    if (result.published) {
                        if (originalNewsItem) {
                            text = T('news_item_saved');
                        } else {
                            text = T('news_item_published');
                        }
                    } else {
                        text = T('news_item_scheduled_for_datetime', {
                            datetime: sln.format(new Date(result.scheduled_at * 1000))
                        });
                    }
                    sln.alert(text, gotoNewsOverview, CommonTranslations.SUCCESS);
                    $.each(orderItems, function (i, orderItem) {
                        if (orderItem.app_id) {
                            ACTIVE_APPS.push(orderItem.app_id);
                        }
                    });
                    if (originalNewsItem) {
                        for (var prop in originalNewsItem) {
                            if (originalNewsItem.hasOwnProperty(prop)) {
                                originalNewsItem[prop] = result[prop];
                            }
                        }
                    } else {
                        if (LocalCache.newsItems && LocalCache.newsItems.result) {
                            LocalCache.newsItems.result.unshift(result);
                        }
                    }
                    function gotoNewsOverview() {
                        window.location.hash = '#/broadcast/overview';
                    }
                },
                error: function () {
                    sln.hideProcessing();
                    elemButtonSubmit.attr('disabled', false);
                    var btn = $('#checkout');
                    btn.find('.normal').hide();
                    btn.find('.loading').show();
                    btn.attr('disabled', true);
                    sln.alert(T('could_not_publish_newsitem'));
                }
            });
        }

        function useCoverPhoto() {
            function toDataUrl(src, callback) {
                var img = new Image();
                img.crossOrigin = 'Anonymous';
                img.onload = function () {
                    var canvas = document.createElement('CANVAS');
                    var ctx = canvas.getContext('2d');
                    var dataURL;
                    canvas.height = this.height;
                    canvas.width = this.width;
                    ctx.drawImage(this, 0, 0);
                    dataURL = canvas.toDataURL('image/jpeg');
                    callback(dataURL);
                };
                img.src = src;
                // force onload event for cached images
                if (img.complete || img.complete === undefined) {
                    img.src = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";
                    img.src = src;
                }
            }

            toDataUrl('/common/settings/my_logo', function (dataUrl) {
                elemImagePreview.attr('src', dataUrl).css({'max-width': 350, height: 131.25});
                elemImagePreview.cropper('destroy');
                elemInputImage.val('');
                elemInputUseCoverPhoto.hide();
                elemButtonSaveImage.hide();
                elemImageEditorContainer.show();
                elemButtonRemoveImage.show();
                renderPreview();
            });
        }

        function removeImage() {
            elemImagePreview.cropper('destroy');
            elemInputImage.val('');
            elemImageEditorContainer.hide();
            elemInputUseCoverPhoto.show();
            doRenderPreview();
        }

        function imageChanged() {
            var CROP_OPTIONS = {
                viewMode: 1,
                dragMode: 'crop',
                rotatable: true,
                autoCropArea: 1.0,
                minContainerWidth: 480,
                minContainerHeight: 180,
                aspectRatio: 16 / 6,
                preview: '.news_image'
            };
            sln.readFile(this, elemImagePreview, 'dataURL', function () {
                $('.news_image').show().find('img').remove();
                elemImagePreview.css({'max-width': 480, height: 180});
                elemImagePreview.cropper('destroy');
                elemImagePreview.cropper(CROP_OPTIONS);
                elemImageEditorContainer.show();
                elemButtonRemoveImage.show();
                elemButtonSaveImage.show().unbind('click').click(resizeImage);
            });
        }
        function resizeImage(event) {
            if (elemInputImage.get(0).files.length !== 0) {
                var croppedImageCanvas = elemImagePreview.cropper('getCroppedCanvas', {
                    width: 1440
                });
                var resizedImageDataUrl = croppedImageCanvas.toDataURL('image/jpeg', 0.8);
                elemImagePreview.attr('src', resizedImageDataUrl).css({'max-width': 350, height: 131.25});
                elemImagePreview.cropper('destroy');
                elemButtonSaveImage.hide();
                elemInputImage.val('');
                if (event) {
                    renderPreview();
                }
            }
        }

        function appsChanged(e) {
            var selectedAppIds = [];
            elemCheckboxesApps.filter(':checked').each(function () {
                selectedAppIds.push(this.value);
            });
            var result = getTotalReach(hasSignedOrder, appStatistics, originalNewsItem, selectedAppIds);
            var totalReach = result[1];
            $('#news_total_reach, .news_reach > b').text(totalReach);
            // check if 'next' or 'send' button should be shown.
            if (e) {
                paidContentChanged();
            }
        }

        function scheduleChanged() {
            var checked = elemCheckboxSchedule.prop('checked');
            elemInputScheduleDate.prop('disabled', !checked);
            elemInputScheduleTime.prop('disabled', !checked);
        }

        function previousStep() {
            if (elemButtonPrevious.attr('disabled')) {
                return;
            }
            var data = getNewsFormData();
            currentStep--;
            for (var i = currentStep; currentStep >= 0; i--) {
                if (!steps[i].type || steps[i].type === data.type) {
                    currentStep = i;
                    break;
                }
            }
            if (currentStep === 1) {
                // When going back, ensure we save the image to avoid errors.
                resizeImage();
            }
            stepChanged(data);
        }

        function validateScheduledAt(data) {
            var error = '';
            if (data.scheduled_at && !itemIsPublished) {
                var now = new Date();
                if (data.scheduled_at <= (now.getTime() / 1000)) {
                    error = T('date_must_be_in_future');
                } else {
                    now.setDate(now.getDate() + 30);
                    if (data.scheduled_at > now.getTime() / 1000) {
                        error = T('broadcast-schedule-too-far-in-future');
                    }
                }
            }
            elemScheduledAtError.html(error);
            return !error;
        }

        function requestLoyaltyDevice() {
            modules.loyalty.requestLoyaltyDevice('News coupons');
        }

        function autoRequireActionButtonRoles() {
            var tag = elemSelectButton.val();
            var menuItem = LocalCache.serviceMenu.items.filter(function(item) {
                return item.tag === tag;
            })[0];

            if (!menuItem) {
                return;
            }

            $.each(menuItem.roles, function() {
                elemCheckboxesRoles.parent().find('input[type=checkbox][value=' + this + ']').prop('required', true);
            });
        }

        function nextStep() {
            if (elemButtonNext.attr('disabled')) {
                return;
            }
            var data = getNewsFormData();
            // Validate the current step before going to the next.
            if (!elemForm.valid()) {
                return;
            }
            if (currentStep === 0) {
                // type step (normal/coupon)
                if (data.type === NEWS_TYPE_QR && !MODULES.includes('loyalty')) {
                    var message = T('contact_support_to_order_tablet_for_news_coupons');
                    var positiveCaption = T('request_loyalty_device');
                    var negativeCaption = T('CLOSE');
                    var title = T('ERROR');
                    sln.confirm(message, requestLoyaltyDevice, null, positiveCaption, negativeCaption, title);
                    return;
                }
                // do not show post to social media if news type is coupon
                var elemPostToSocialMedia = $('#post_to_social_media');
                if(data.type === NEWS_TYPE_QR) {
                    elemCheckPostToFacebook.attr('checked', false);
                    elemCheckPostToTwitter.attr('checked', false);
                    elemPostToSocialMedia.hide();
                } else {
                    elemPostToSocialMedia.show();
                }
            }
            // Image step
            if (currentStep === 2) {
                resizeImage();
            }

            // check if the attachment is provided
            // the attachment url is hidden
            if(currentStep === 4) {
                elemCheckboxesRoles.prop('required', false);

                if(data.action_button) {
                    if(data.action_button.id === 'attachment') {
                        var attachmentUrl = $('#news_action_attachment_value').val().trim();
                        if(attachmentUrl === '') {
                            sln.alert(T('please_add_attachment'), null, CommonTranslations.ERROR);
                            return;
                        }
                    }

                    if(data.action_button.action.startsWith('smi')) {
                        autoRequireActionButtonRoles();
                    }
                }
            }
            if (currentStep === 5) {
                // schedule step
                var valid = validateScheduledAt(data);
                if (!valid) {
                    return;
                }
            }
            currentStep++;
            for (var i = currentStep; currentStep < steps.length; i++) {
                if (!steps[i].type || steps[i].type === data.type) {
                    currentStep = i;
                    break;
                }
            }
            stepChanged(data);
        }

        function stepChanged(data) {
            var LAST_STEP = steps.length - 1;
            var step = steps[currentStep];
            var isLastStep = currentStep === LAST_STEP;
            if (LAST_STEP - 1 === currentStep) {
                paidContentChanged();
            } else {
                elemButtonSubmit.hide();
                elemButtonNext.toggle(!isLastStep);
            }

            if (isLastStep) {
                shouldPay(function (pay) {
                    if (pay) {
                        elemNewsFormContainer.removeClass('span6').addClass('span12');
                        showNewsOrderPage(data);
                    } else {
                        elemNewsFormContainer.removeClass('span12').addClass('span6');
                    }
                });
            } else {
                elemNewsFormContainer.removeClass('span12').addClass('span6');
            }
            elemButtonPrevious.attr('disabled', 0 === currentStep).toggle(!isLastStep);
            $('.tab-pane').removeClass('active');
            $('#tab' + currentStep).addClass('active');
            elemStepTitle.text(step.text);
            elemStepDescription.html(step.description);
            elemNewsPreview.toggle(!isLastStep);
            elemButtonSubmit.text(geSubmitButtonText(data));
            renderPreview();
            LocalCache.temporaryNewsItem = data;

            if(currentStep === 1) {
                elemInputTitle.focus();
            }
        }

        function geSubmitButtonText(data) {
            var key;
            if (originalNewsItem) {
                key = 'Save';
            } else if (data.scheduled_at) {
                key = 'schedule';
            } else {
                key = 'publish';
            }
            return T(key);
        }

        function doRenderPreview() {
            getSettings(r);
            function r(settings) {
                var newsItem = getNewsFormData();
                var imageUrl = elemImagePreview.attr('src') || '';
                if (imageUrl.indexOf('http') === 0) {
                    newsItem.image_url = imageUrl;
                }
                newsItem.title = newsItem.title || T('events-title');
                var selectedAppIds = [];
                elemCheckboxesApps.filter(':checked').each(function () {
                    selectedAppIds.push(this.value);
                });
                var result = getTotalReach(hasSignedOrder, appStatistics, originalNewsItem, selectedAppIds);
                var totalReach = result[1];
                var html = $.tmpl(templates['broadcast/broadcast_news_preview'], {
                    newsItem: newsItem,
                    htmlize: sln.htmlize,
                    settings: settings,
                    reach: totalReach,
                    currentDatetime: sln.formatDate(new Date().getTime() / 1000)
                });
                elemNewsPreview.html(html);
                var elemShowMore = $('#news_read_more_text'),
                    elemNewsContent = $('#news_content');
                var hasMore = elemNewsContent.prop('scrollHeight') > 125;
                var moreOrLess = hasMore;

                function showMoreOrLess(more) {
                    elemShowMore.find('.read_more_text').toggle(!more);
                    elemShowMore.find('.read_less_text').toggle(more);
                    if (!hasMore) {
                        elemShowMore.hide();
                    } else {
                        if (more) {
                            elemShowMore.slideDown();
                        }
                    }
                    if (hasMore) {
                        var height = more ? elemNewsContent.prop('scrollHeight') + 'px' : '100px';
                        elemNewsContent.animate({
                            'max-height': height
                        });
                    }
                }

                elemShowMore.toggle(hasMore);
                elemShowMore.find('.read_more_text').toggle(hasMore);
                elemShowMore.find('.read_less_text').toggle(!hasMore);

                $('.read_more_trigger').click(function () {
                    showMoreOrLess(moreOrLess);
                    moreOrLess = !moreOrLess;
                });
            }
        }
    }

    function getSettings(callback) {
        if (LocalCache.settings) {
            callback(LocalCache.settings);
        } else {
            sln.call({
                url: "/common/settings/load",
                type: "GET",
                success: function (settings) {
                    LocalCache.settings = settings;
                    callback(LocalCache.settings);
                }
            });
        }
    }

    function isPresentInApp(app_id) {
        return ACTIVE_APPS.indexOf(app_id) !== -1;
    }
});

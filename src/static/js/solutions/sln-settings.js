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

// Settings module
$(function () {
    'use strict';
    var AVATAR_URL = '/common/settings/my_avatar';
    var LOGO_URL = '/common/settings/my_logo';
    var searchEnabled = true;
    var searchEnabledCheck = true;
    var eventsEnabled = true;
    var eventNotificationsEnabled = false;
    var inboxEmailRemindersEnabled = true;
    var fbAccessToken;
    var TMPL_SET_AVATAR = '<label>' + CommonTranslations.AVATAR + ': ' + CommonTranslations.CLICK_TO_CHANGE
        + '</label><div id="avatar_div"><img src="/common/settings/my_avatar" class="settings_avatar"></div>';
    var TMPL_SET_LOGO = '<label>' + CommonTranslations.LOGO + ': ' + CommonTranslations.CLICK_TO_CHANGE
        + '</label><div id="logo_div"><img src="/common/settings/my_logo"></div>';
    var TMPL_SET_NAME = '<label>' + CommonTranslations.NAME + ':</label><input type="text" placeholder="'
        + CommonTranslations.ENTER_DOT_DOT_DOT + '">';
    var TMPL_SET_PHONE_NUMBER = '<label>' + CommonTranslations.PHONE_NUMBER
        + ':</label><input type="text" placeholder="' + CommonTranslations.ENTER_DOT_DOT_DOT + '">';
    var TMPL_SET_FACEBOOK_ACTION_URL = '<label>' + CommonTranslations.WEBSITE
        + ':</label><input type="text" placeholder="' + CommonTranslations.ENTER_DOT_DOT_DOT + '">';
    var TMPL_SET_FACEBOOK_PLACE = '<label>'
        + CommonTranslations.FACEBOOK_PAGE
        + ':</label> <a href="#fbLogin" id="facebookPlaceStep1">'
        + CommonTranslations.LOGIN_WITH_FACEBOOK_FIRST
        + '</a>'
        + '<div id="facebookPlaceStep2"><input type="text" id="place-input" autocomplete="off" />	<input type="hidden" id="place-input-id" value="" /></div>';

    var TMPL_SET_DESCRIPTION = '<label>' + CommonTranslations.DESCRIPTION
        + ':</label><textarea class="span6" placeholder="' + CommonTranslations.ENTER_DOT_DOT_DOT
        + '" rows="6"></textarea>';
    var TMPL_SET_OPENINGHOURS = '<label>' + CommonTranslations.OPENING_HOURS
        + ':</label><textarea class="span6" placeholder="' + CommonTranslations.ENTER_DOT_DOT_DOT
        + '" rows="6"></textarea>';
    var TMPL_SET_ADDRESS = '<label>' + CommonTranslations.ADDRESS + ':</label>'
        + '<div id="address_geocode_error" style="display:none">'
        + '  <div class="alert alert-warning">' + CommonTranslations.address_geocode_error + '\n' + CommonTranslations.eg
        + '     <div style="padding:10px"><b>' + sln.htmlize(CommonTranslations.sample_address) + '</b></div>'
        + '  </div></div><textarea class="span6" placeholder="' + CommonTranslations.ENTER_DOT_DOT_DOT + '" rows="4"></textarea>';

    var TMPL_SET_EMAIL = '<label>' + CommonTranslations.EMAIL_ADDRESS + ':</label><input type="text" placeholder="'
        + CommonTranslations.ENTER_DOT_DOT_DOT + '">';

    var TMPL_UPDATES_PENDING = '<div class="alert">'
        + '    <button id="publish_changes" type="button" class="btn btn-warning pull-right">'
        + CommonTranslations.PUBLISH_CHANGES //
        + '    </button>' //
        + '    <button id="try_publish_changes" type="button" class="btn btn-warning pull-right" style="margin-right: 5px;">'
        + CommonTranslations.TRY //
        + '    </button>' //
        + '    <h4>' + CommonTranslations.WARNING + '</h4>' + CommonTranslations.UNPERSISTED_CHANGES //
        + '</div>';

    var TMPL_USER_ROW = '<tr user_key=${user_key}>'
        + '<td style="width: 75%;"">${email}</td>'
        + '<td><button class="btn btn-danger pull-right" action="delete_user"><i class="fa fa-trash"></i></button></td>'
        + '</tr>';

    var TMPL_REQUIRED_PENDING = '<div class="alert alert-danger">' //
        + '    <h4>' //
        + CommonTranslations.REQUIRED //
        + '    </h4>' //
        + '    <ul id="required_fields"></ul>' //
        + '</div>';

    var TMPL_SET_CURRENY = '<label>' + CommonTranslations.CURRENCY + ':</label>' //
        + '<select name="currency">' //
        + '<option value="">' + CommonTranslations.SELECT_CURRENCY + '</option>' //
        + '<option value="&#x20ac;">&#x20ac;</option>' //
        + '<option value="&#xa3;">&#xa3;</option>' //
        + '<option value="&#x24;">&#x24;</option>' //
        + '</select><br />';

    var TMPL_SET_VISIBLE = '<div class="btn-group">' //
        + '    <button class="btn btn-success" id="serviceVisible">' //
        + CommonTranslations.VISIBLE //
        + '    </button>' //
        + '    <button class="btn" id="serviceInvisible">&nbsp;</button>' //
        + '</div>';

    var TMPL_SET_SEARCH_KEYWORDS = '<label>' //
        + 'Search keywords:' + '    <a data-toggle="tooltip" data-placement="right" data-title="'
        + CommonTranslations.SEARCH_KEYWORDS_HINT + '">' + '        <i class="icon-info-sign"></i>' //
        + '    </a>' //
        + '</label>' //
        + '<textarea class="span6" placeholder="' + CommonTranslations.ENTER_DOT_DOT_DOT + '" rows="4"></textarea>';

    var TMPL_SET_EVENTS_VISIBLE = '<div class="btn-group">'
        + '      <button class="btn btn-success" id="eventsVisible">' + CommonTranslations.VISIBLE + '</button>'
        + '      <button class="btn" id="eventsInvisible">&nbsp;</button>' + '</div>';

    var TMPL_EVENT_NOTIFICATIONS = '<div class="btn-group">'
        + '      <button class="btn" id="disableEventsNotifications">&nbsp;</button>'
        + '      <button class="btn btn-danger" id="enableEventsNotifications">' + CommonTranslations.enable_notifications + '</button>'
        + '</div>';

    var TMPL_SET_INBOX_EMAIL_REMINDERS_ENABLED = '<div class="btn-group">' //
        + '    <button class="btn btn-success" id="inboxEmailRemindersEnabled">' //
        + CommonTranslations.EMAIL_REMINDERS_ENABLED //
        + '    </button>' //
        + '    <button class="btn" id="inboxEmailRemindersDisabled">&nbsp;</button>' //
        + '</div>';

    var INBOX_FORWARDER_TEMPLATE = '{{each forwarders}}' //
        + '<li>' //
        + '{{if ($value.type == "email")}}<i class="icon-envelope"></i> ' //
        + '{{else ($value.type == "mobile")}}<i class="icon-user"></i> ' //
        + '{{/if}}' //
        + '${$value.label} <a fw_type="${$value.type}" user_key="${$value.key}" href="#" action="delete_user_forwarding">'
        + CommonTranslations.DELETE + '</a>' //
        + '</li>' //
        + '{{/each}}';

    var mobileInboxForwardsSearch = {};
    var appUserRolesSearch = {};
    var tryPublishChangesUserSearch = {};

    var TMPL_MOBILE_INBOX_FORWARDER_INPUT = '<div class="modal hide fade" tabindex="-1" role="dialog" aria-labelledby="myModalLabel" aria-hidden="true">'
        + '    <div class="modal-header">'
        + '        <button type="button" class="close" data-dismiss="modal" aria-hidden="true">&times;</button>'
        + '        <h3 id="myModalLabel">${header}</h3>'
        + '    </div>'
        + '    <div class="modal-body" style="overflow-y: visible;">'
        + '        <input id="mobile_inbox_forwarder" type="text" style="width: 514px" placeholder="${placeholder}" value="${value}" />'
        + '    </div>'
        + '    <div class="modal-footer">'
        + '        <button action="cancel" class="btn" data-dismiss="modal" aria-hidden="true">${cancelBtn}</button>'
        + '        <button action="submit" class="btn btn-primary">${submitBtn}</button>' //
        + '    </div>' //
        + '</div>';

    init();

    function init() {
        ROUTES['settings'] = router;
        modules.settings = {
            renderBroadcastSettings: renderBroadcastSettings
        };
        LocalCache.settings = {};
    }

    function router(urlHash) {
        var page = urlHash[1];
        if (['general', 'branding', 'broadcast', 'app', 'roles'].indexOf(page) === -1) {
            page = 'general';
            window.location.hash = '#/' + urlHash[0] + '/' + page;
            return;
        }
        $('#settings').find('li[section=' + page + ']').find('a').click();

        if (page === 'branding') {
            showSettingsBranding();
        } else if (page === 'broadcast') {
            renderBroadcastSettings();
        } else if (page === 'app') {
            renderAppSettings();
        } else if (page == 'roles') {
            renderRolesSettings();
        }
    }

    var publishChanges = function() {
        // publish changes to all users
        publishChangesToUsers(null);
    }
    modules.settings.publishChanges = publishChanges;

    var tryPublishChanges = function() {
        var html = $.tmpl(templates['settings/try_publish_changes'], {
        });

        var modal = sln.createModal(html, function (modal) {
            $('#app_user_email_input', modal).focus();
        });

        function getUserKeys() {
            var keys = [];
            $('#selected_users > tbody > tr', modal).each(function(i, el) {
                keys.push($(el).attr('user_key'));
            });
            return keys;
        }

        function addUser(userKey) {
            var email = userKey.split(':')[0];
            var userRow = $.tmpl(TMPL_USER_ROW, {
                email: email,
                user_key: userKey
            });

            $('button[action=delete_user]', userRow).click(function() {
                $(this).parent().closest('tr').remove();
            });

            $('#selected_users > tbody', modal).append(userRow);
        }

        // prefill last selected users
        var lastSelectedUserKeys = []
        if(LocalCache.settings.try_publish_user_keys) {
            $.each(LocalCache.settings.try_publish_user_keys, function(i, userKey) {
                addUser(userKey);
            });
        }

        var publishButton = $('#try_publish', modal);
        var searchInput = $('#app_user_email', modal);
        sln.userSearch(searchInput, tryPublishChangesUserSearch, function(userKey) {
            var addedKeys = getUserKeys();
            if(addedKeys.indexOf(userKey) === -1) {
                addUser(userKey);
                searchInput.val('');
            }
        });

        publishButton.click(function() {
            var userKeys = getUserKeys(),
                members = [];

            $.each(userKeys, function(i, key) {
                var userKey = key.split(':');
                members.push({
                    member: userKey[0], /* email */
                    app_id: userKey[1]  /* app_id */
                });
            });
            if(!members.length) {
                sln.alert(CommonTranslations.select_1_user_at_least, null, CommonTranslations.ERROR);
                return;
            }

            saveTryPublishUsers(userKeys);
            publishChangesToUsers(members);
            modal.modal('hide');
        });
    };

    var showDefaultSettingsWarning = function(defaults) {
        if(defaults.length) {
            var warning = CommonTranslations.default_settings_warning + '<br/><br/>';
            for(var i=0; i < defaults.length; i++) {
                warning += '<b>' + CommonTranslations[defaults[i]] + '</b><br/>';
                warning += CommonTranslations[('default_settings_warning_' + defaults[i]).toLowerCase()];
                warning += '<br/><br/>'
            }
            sln.alert(warning, null, CommonTranslations.ERROR);
        }
    };

    var validateDefaultSettings = function(callback) {
        sln.call({
            url: '/common/settings/defaults/all',
            method: 'get',
            success: function(defaults) {
                if(defaults.length) {
                    showDefaultSettingsWarning(defaults);
                } else {
                    callback();
                }
            },
            error: sln.showAjaxError
        });
    }

    var publishChangesToUsers = function (friends) {
        function publish() {
            validateDefaultSettings(function() {
                var args = {};
                if(friends && friends.length) {
                    args.friends = friends;
                }
                sln.showProcessing(CommonTranslations.PUBLISHING_DOT_DOT_DOT);
                sln.call({
                    url: "/common/settings/publish_changes",
                    type: "POST",
                    data: args,
                    success: function (data) {
                        sln.hideProcessing();
                        if (data.success && !args.friends) {
                            toggleUpdatesPending(false);
                        } else if(!data.success){
                            sln.alert(sln.htmlize(data.errormsg), null, T('ERROR'));
                        }
                    },
                    error: function (XMLHttpRequest, textStatus, errorThrown) {
                        sln.hideProcessing();
                        sln.showAjaxError(XMLHttpRequest, textStatus, errorThrown);
                    }
                });
            });
        }

        function setSearchEnabled(neverCheckAgain, enabled) {
            if (neverCheckAgain) {
                searchEnabledCheck = false;
            }
            setServiceVisible(enabled);
            if (!searchEnabledCheck || enabled) {
                saveSettings(publish);
            } else {
                publish();
            }
        }

        if (!searchEnabled && searchEnabledCheck) {
            // ask the user to enable search for this service before publishing
            sln.confirm(CommonTranslations.enable_search_before_publishing, function(neverCheckAgain) {
                setSearchEnabled(neverCheckAgain, true);
            }, function(neverCheckAgain) {
                setSearchEnabled(neverCheckAgain, false);
            }, CommonTranslations.YES, CommonTranslations.NO, CommonTranslations.visibility, null, true);
        } else {
            publish();
        }
    };

    var saveTryPublishUsers = function(userKeys) {
        if(userKeys.length) {
            LocalCache.settings.try_publish_user_keys = userKeys;

            sln.call({
                url: '/common/settings/publish_changes/users',
                type: 'POST',
                data: {
                    user_keys: userKeys
                },
                success: function() {},
                error: sln.showAjaxError
            });
        }
    }

    var toggleUpdatesPending = function (updatesPending) {
        if (updatesPending) {
            $(".sln-updates-pending-warning").fadeIn('slow');
        } else {
            $(".sln-updates-pending-warning").fadeOut('fast');
        }
    };

    var loadSettings = function () {
        sln.call({
            url: "/common/settings/load",
            type: "GET",
            success: function (data) {
                LocalCache.settings = data;
                $('.sln-set-name input').data('updateVal')(data.name);
                $('.sln-set-phone-number input').data('updateVal')(data.phone_number);
                $('.sln-set-currency select').val(data.currency);
                $('.sln-set-description textarea').data('updateVal')(data.description);
                $('.sln-set-openinghours textarea').data('updateVal')(data.opening_hours);
                $('.sln-set-address textarea').data('updateVal')(data.address);
                $('.sln-set-timezone select').val(data.timezone);
                $('.sln-set-search-keywords textarea').val(data.search_keywords);
                $('.sln-set-email-address input').val(data.email_address);
                var fbActionUrl = $('.sln-set-facebook-action-url input');
                var fbPlace = $('.sln-set-facebook-place #place-input');
                var fbPlaceId = $('.sln-set-facebook-place #place-input-id');
                if (fbActionUrl.size() > 0)
                    fbActionUrl.data('updateVal')(data.facebook_action);
                if (fbPlace.size() > 0)
                    fbPlace.val(data.facebook_name);
                if (fbPlaceId.size() > 0)
                    fbPlaceId.val(data.facebook_page);
                searchEnabled = data.search_enabled;
                searchEnabledCheck = data.search_enabled_check;
                setServiceVisible(searchEnabled);
                eventsEnabled = data.events_visible;
                setEventsVisible(eventsEnabled);
                setEventNotifications(data.event_notifications_enabled);
                inboxEmailRemindersEnabled = data.inbox_email_reminders;
                setInboxEmailRemindersStatus(inboxEmailRemindersEnabled);
                setupTwitter(data.twitter_username);
                toggleUpdatesPending(data.updates_pending);

                if (MODULES.indexOf('billing') !== -1 && $('.sln-set-iban input').length) {
                    $('.sln-set-iban input').data('updateVal')(data.iban);
                    $('.sln-set-bic input').data('updateVal')(data.bic);
                }

                if(data.publish_changes_users) {
                    LocalCache.settings.try_publish_user_keys = data.publish_changes_users;
                }
                renderHolidays(data);
            },
            error: sln.showAjaxError
        });
    };

    var channelUpdates = function (data) {
        if (data.type == 'solutions.common.settings.updates_pending') {
            toggleUpdatesPending(data.updatesPending);
        } else if (data.type == 'solutions.common.inbox.new.forwarder.via.scan') {
            inboxLoadForwarders();
        } else if (data.type == 'solutions.common.twitter.updated') {
            setupTwitter(data.username);
        } else if (data.type == 'solutions.common.locations.update') {
            if (!isLoyaltyTablet) {
                if (service_identity != data.si) {
                    window.location.reload();
                }
            }
        } else if (data.type === 'solutions.common.settings.avatar.updated') {
            avatarUpdated();
        } else if (data.type === 'solutions.common.settings.logo.updated') {
            logoUpdated();
        } else if (data.type === 'solution.common.settings.roles.updated') {
            renderRolesSettings();
        }
    };

    window.fbAsyncInit = function () {
        // init the FB JS SDK
        sln.call({
            url: '/common/settings/facebook/app/id',
            method: 'get',
            success: function(app_id) {
                if(!app_id) {
                    console.error('Cannot get facebook app id');
                    $('.sln-set-facebook-place').hide();
                    return;
                }
                FB.init({
                    appId: app_id, // App ID
                    status: true, // Check Facebook Login status
                    cookie: true, // enable cookies to allow the server to access the session
                    xfbml: true
                });
            },
            error: sln.showAjaxError
        });
    };

    // Load the SDK asynchronously
    (function (d, s, id) {
        var js, fjs = d.getElementsByTagName(s)[0];
        if (d.getElementById(id)) {
            return;
        }
        js = d.createElement(s);
        js.id = id;
        js.src = "//connect.facebook.net/en_US/all.js";
        fjs.parentNode.insertBefore(js, fjs);
    }(document, 'script', 'facebook-jssdk'));

    var loginFacebookPages = function () {
        FB.login(function (response) {
            if (response.authResponse) {
                if(response.authResponse.grantedScopes.indexOf('manage_pages') == -1) {
                    sln.alert(T('facebook-manage-pages-required'));
                    return;
                }

                if(response.authResponse.grantedScopes.indexOf('publish_actions') == -1) {
                    sln.alert(T('facebook-publish-actions-required'))
                    return;
                }
                fbAccessToken = response.authResponse.accessToken;
                $("#facebookPlaceStep1").css('visibility', 'hidden');
                $("#facebookPlaceStep2").css('visibility', 'visible');
                loadFacebookPages();
            }
        },
        {
            scope: 'manage_pages,publish_actions',
            return_scopes: true
        });
    };

    var fbPlaces = {};
    var fbPlacesLabels = [];

    var loadFacebookPages = function () {
        $('#place-input').typeahead(
            {
                source: function (query, process) {
                    var place_id = $('.sln-set-facebook-place #place-input-id');
                    if (place_id.val()) {
                        place_id.val("");
                        saveSettings();
                    }
                    var searchType = (SOLUTION == "djmatic") ? "place" : "page";
                    FB.api('/search?q=' + encodeURIComponent(query) + "&type=" + searchType + "&access_token="
                        + encodeURIComponent(fbAccessToken), function (res) {
                        fbPlaces = {};
                        fbPlacesLabels = [];
                        $.each(res.data, function (item, ix, list) {
                            fbPlacesLabels.push(ix.id);
                            fbPlaces[ix.id] = {
                                id: ix.id,
                                name: ix.name,
                                category: ix.category

                            };
                        });
                        process(fbPlacesLabels);
                    });
                },
                matcher: function () {
                    return true;
                },
                highlighter: function (item) {
                    var p = fbPlaces[item];

                    var typeahead_wrapper = $('<div class="typeahead_wrapper"></div>');
                    var typeahead_photo = $('<img class="typeahead_photo" src="" />').attr("src",
                        'https://graph.facebook.com/' + p.id + '/picture?width=50&height=50');
                    typeahead_wrapper.append(typeahead_photo);
                    var typeahead_labels = $('<div class="typeahead_labels"></div>');
                    var typeahead_primary = $('<div class="typeahead_primary"></div>').text(p.name);
                    typeahead_labels.append(typeahead_primary);
                    var typeahead_secondary = $('<div class="typeahead_secondary"></div>').text(p.category);
                    typeahead_labels.append(typeahead_secondary);
                    typeahead_wrapper.append(typeahead_labels);

                    return typeahead_wrapper;
                },
                updater: function (item) {
                    $('.sln-set-facebook-place #place-input-id').val(item);
                    var p = fbPlaces[item];
                    $('.sln-set-facebook-place #place-input').val(p.name);
                    saveSettings();
                    return p.name;
                }
            }).keyup(function () {
            var place_id = $('.sln-set-facebook-place #place-input-id');
            if ($(this).val().trim() == '' && place_id.val()) {
                place_id.val("");
                saveSettings();
            }
        });

    };

    /* Bulk invite */

    var testBulkInvites = function () {
        $("#bulkInviteEmailList").empty();
        var emails = extractEmails($('#blukEmails').val());
        var numberOfEmails = 0;
        if (emails != null) {
            $.each(emails, function (index, email) {
                $("#bulkInviteEmailList").append('<li>' + email + '</li>');
                numberOfEmails++;
            });
            $("#bulkInvite").show();
            $('#bulkInviteEmailList li').click(deleteEmailFromList);
        }
        $("#sendBulkEmailInvitations").val(numberOfEmails)
            .text(CommonTranslations.SEND_INVITATION_TO_X_EMAILS.replace("%(amount)d", numberOfEmails));
    };

    var deleteEmailFromList = function () {
        $(this).remove();
        var numberOfEmails = $("#sendBulkEmailInvitations").val() - 1;
        $("#sendBulkEmailInvitations").val(numberOfEmails)
            .text(CommonTranslations.SEND_INVITATION_TO_X_EMAILS.replace("%(amount)d", numberOfEmails));
    };

    var sendBulkInvites = function () {
        var emails = [];
        $.each($('#bulkInviteEmailList li'), function (index) {
            emails.push($(this).text());
        });
        if (emails.length > 0) {
            sln.showProcessing(CommonTranslations.SENDING_DOT_DOT_DOT);
            $('#sendBulkEmailInvitations').off('click');
            sln.call({
                url: "/common/bulkinvite",
                type: "POST",
                data: {
                    data: JSON.stringify({
                        emails: emails,
                        invitation_message: $('#bulkInvitationMessage').val()
                    })
                },
                success: function (data) {
                    sln.hideProcessing();
                    if (data.success) {
                        $("#bulkInvite").hide();
                        $('#blukEmails').val("");
                        $("#bulkInviteEmailList").empty();
                        $("#sendBulkEmailInvitations").val(0)
                            .click(sendBulkInvites)
                            .text(CommonTranslations.SEND_INVITATION_TO_X_EMAILS.replace("%(amount)d", 0));
                        sln.alert(CommonTranslations.ALL_INVITES_WERE_SENT_SUCCESSFULLY, null,
                            CommonTranslations.INVITES_SENT, null);
                    }
                },
                error: sln.showAjaxError
            });
        }
    };

    var extractEmails = function (text) {
        var matches = text.match(/([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+)/gi);
        var emails = [];
        if (matches) {
            emails = matches.sort(sln.caseInsensitiveStringSort).reduce(function (a, b) {
                if (a.indexOf(b) < 0) {
                    a.push(b);
                }
                return a;
            }, []); // this empty array becomes the starting value for a

        }
        return emails;
    };

    function settingTabPress() {
        var settingsElem = $("#settings");
        settingsElem.find('li').removeClass("active");
        var li = $(this).parent().addClass("active");
        settingsElem.find("section").hide();
        settingsElem.find("section#" + li.attr("section")).show();
    }

    function serviceVisible() {
        setServiceVisible(!searchEnabled);
        saveSettings();
    }

    function serviceInvisible() {
        setServiceVisible(!searchEnabled);
        saveSettings();
    }

    function setServiceVisible(newSearchEnabled) {
        searchEnabled = newSearchEnabled;
        if (newSearchEnabled) {
            $('#section_general #serviceVisible').addClass("btn-success").text(CommonTranslations.SERVICE_VISIBLE);
            $('#section_general #serviceInvisible').removeClass("btn-danger").html('&nbsp;');
        } else {
            $('#section_general #serviceVisible').removeClass("btn-success").html('&nbsp;');
            $('#section_general #serviceInvisible').addClass("btn-danger").text(CommonTranslations.SERVICE_INVISIBLE);
        }
    }

    function eventsVisible() {
        setEventsVisible(!eventsEnabled);
        saveSettings();
    }

    function eventsInvisible() {
        setEventsVisible(!eventsEnabled);
        saveSettings();
    }

    function setEventsVisible(newEventsEnabled) {
        eventsEnabled = newEventsEnabled;
        if (newEventsEnabled) {
            $('#eventsVisible').addClass("btn-success").text(CommonTranslations.AGENDA_ENABLED);
            $('#eventsInvisible').removeClass("btn-danger").html('&nbsp;');
            $("#topmenu li[menu|='events']").css('display', 'block');
        } else {
            $('#eventsVisible').removeClass("btn-success").html('&nbsp;');
            $('#eventsInvisible').addClass("btn-danger").text(CommonTranslations.AGENDA_DISABLED);
            $("#topmenu li[menu|='events']").css('display', 'none');
        }
        sln.resize_header();
    }

    function setEventNotifications(enabled) {
        eventNotificationsEnabled = enabled;
        if (enabled) {
            $('#disableEventsNotifications').addClass("btn-success").text(CommonTranslations.disable_notifications);
            $('#enableEventsNotifications').removeClass("btn-danger").html('&nbsp;');
        } else {
            $('#disableEventsNotifications').removeClass("btn-success").html('&nbsp;');
            $('#enableEventsNotifications').addClass("btn-danger").text(CommonTranslations.enable_notifications);
        }
    }

    function enableEventsNotifications() {
        setEventNotifications(!eventNotificationsEnabled);
        saveEventNotificationsSettings();
    }

    function disableEventsNotifications() {
        setEventNotifications(!eventNotificationsEnabled);
        saveEventNotificationsSettings();
    }

    function saveEventNotificationsSettings() {
        sln.call({
            url: '/common/settings/events/notifications/save',
            type: 'POST',
            data: {
                notifications_enabled: eventNotificationsEnabled
            },
            success: function(data) {},
            error: sln.showAjaxError
        });
    }

    function inboxLoadForwarders() {
        sln.call({
            url: "/common/inbox/forwarders/load",
            type: "GET",
            success: function (data) {
                var inboxForwarders = $("#mobile_inbox_forwarders");
                var html = $.tmpl(INBOX_FORWARDER_TEMPLATE, {
                    forwarders: data
                });
                inboxForwarders.empty().append(html);
                $('#mobile_inbox_forwarders a[action="delete_user_forwarding"]').click(function () {
                    var userKey = $(this).attr("user_key");
                    var fwType = $(this).attr("fw_type");
                    sln.call({
                        url: "/common/inbox/forwarders/delete",
                        type: "POST",
                        data: {
                            data: JSON.stringify({
                                key: userKey,
                                forwarder_type: fwType
                            })
                        },
                        success: function (data) {
                            if (!data.success) {
                                return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                            }
                            inboxLoadForwarders();
                        },
                        error: sln.showAjaxError
                    });
                });
            },
            error: sln.showAjaxError
        });
    }

    var addInboxForwarder = function (key, type) {
        sln.showProcessing(CommonTranslations.LOADING_DOT_DOT_DOT);
        sln.call({
            url: "/common/inbox/forwarders/add",
            type: "POST",
            data: {
                data: JSON.stringify({
                    key: key,
                    forwarder_type: type
                })
            },
            success: function (data) {
                sln.hideProcessing();
                if (!data.success) {
                    return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                }
                inboxLoadForwarders();
            },
            error: sln.showAjaxError
        });
    };

    $("#add_email_inbox_forwarder").click(function () {
        sln.input(function (value) {
            addInboxForwarder(value, 'email');
        }, CommonTranslations.EMAIL_ADDRESS);
    });

    var setInboxEmailRemindersStatus = function (newInboxEmailRemindersStatus) {
        inboxEmailRemindersEnabled = newInboxEmailRemindersStatus;
        if (newInboxEmailRemindersStatus) {
            $('#inboxEmailRemindersEnabled').addClass("btn-success").text(CommonTranslations.EMAIL_REMINDERS_ENABLED);
            $('#inboxEmailRemindersDisabled').removeClass("btn-danger").html('&nbsp;');
        } else {
            $('#inboxEmailRemindersEnabled').removeClass("btn-success").html('&nbsp;');
            $('#inboxEmailRemindersDisabled').addClass("btn-danger").text(CommonTranslations.EMAIL_REMINDERS_DISABLED);
        }
    };

    var inboxEmailReminderEnabled = function () {
        setInboxEmailRemindersStatus(!inboxEmailRemindersEnabled);
        saveSettings();
    };

    var inboxEmailReminderDisabled = function () {
        setInboxEmailRemindersStatus(!inboxEmailRemindersEnabled);
        saveSettings();
    };

    $(".sln-inbox-email-reminders").html(TMPL_SET_INBOX_EMAIL_REMINDERS_ENABLED);
    $('#inboxEmailRemindersEnabled').click(inboxEmailReminderEnabled);
    $('#inboxEmailRemindersDisabled').click(inboxEmailReminderDisabled);

    $("#add_mobile_inbox_forwarder").click(function () {
        var html = $.tmpl(TMPL_MOBILE_INBOX_FORWARDER_INPUT, {
            header: CommonTranslations.ADD_MOBILE_INBOX_FORWARDERS,
            cancelBtn: CommonTranslations.CANCEL,
            submitBtn: CommonTranslations.ADD,
            placeholder: CommonTranslations.ENTER_DOT_DOT_DOT,
            value: ""
        });
        var modal = sln.createModal(html, function (modal) {
            $('input', modal).focus();
        });
        $('button[action="submit"]', modal).click(function () {
            var key = $(this).attr("user_key");
            addInboxForwarder(key, 'mobile');
            modal.modal('hide');
        });

        $('button[action="submit"]', modal).hide();

        var searchInput = $('#mobile_inbox_forwarder', html);
        sln.userSearch(searchInput, mobileInboxForwardsSearch, function(user_key) {
            $('button[action="submit"]', modal).attr("user_key", user_key);
            $('button[action="submit"]', modal).show();
        });
    });

    $(document).on("click", "#twitter-login", function () {
        sln.call({
            url: "/common/twitter/auth_url",
            type: "GET",
            success: function (data) {
                window.open(data, "", "width=700, height=500");
            },
            error: sln.showAjaxError
        });
    });

    $(document).on("click", "#twitter-logout", function () {
        sln.call({
            url: "/common/twitter/logout",
            type: "GET",
            success: function (data) {
                setupTwitter(null);
            },
            error: sln.showAjaxError
        });
    });

    var setupTwitter = function (twitter_username) {
        var d_0 = $('<label>' + CommonTranslations.TWITTER_PAGE + ':</label>');
        $(".sln-set-twitter_profile").empty().append(d_0);
        if (twitter_username == null) {
            var d_1 = $('<img id="twitter-login" style="cursor: pointer;" src="/static/images/solutions/sign-in-with-twitter-gray.png" width="158" heigth="28">');
            $(".sln-set-twitter_profile").append(d_1);
        } else {
            var d_2 = $('<p></p>');
            var d_2_1 = $('<a target="_blank"></a>');
            d_2_1.attr("href", "https://twitter.com/" + twitter_username);
            d_2_1.text("@" + twitter_username);
            d_2.append(d_2_1);
            var d_2_2 = $('<button id="twitter-logout" style="margin-left: 20px;" type="button" class="btn btn-small btn-warning">'
                + CommonTranslations.LOGOUT + '</button>');
            d_2.append(d_2_2);
            $(".sln-set-twitter_profile").append(d_2);
        }
    };

    /* HOLIDAYS */

    var to_epoch = function (textField) {
        return Math.floor(textField.data('datepicker').date.valueOf() / 1000);
    };

    var addHoliday = function () {
        var html = $.tmpl(templates.holiday_addholiday, {
            header: CommonTranslations.ADD_HOLIDAY,
            cancelBtn: CommonTranslations.CANCEL,
            submitBtn: CommonTranslations.SAVE,
            CommonTranslations: CommonTranslations
        });

        $('.date', html).datepicker({
            format: sln.getLocalDateFormat()
        }).datepicker('setValue', sln.today());

        var modal = sln.createModal(html);
        $('button[action="submit"]', modal).click(function () {
            sln.call({
                url: "/common/settings/holiday/add",
                type: "POST",
                data: {
                    data: JSON.stringify({
                        holiday: {
                            start: to_epoch($("#holiday-start")), // beginning of the day
                            end: to_epoch($("#holiday-end")) + 86399
                            // end of the day
                        }
                    })
                },
                success: function (data) {
                    if (!data.success) {
                        sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                        return;
                    }
                    loadSettings();
                    modal.modal('hide');
                },
                error: sln.showAjaxError
            });
        });
    };

    var saveOOFMessage = function (oofMessage) {
        sln.call({
            url: "/common/settings/holiday/out_of_office_message",
            type: "POST",
            data: {
                data: JSON.stringify({
                    message: oofMessage
                })
            },
            success: function (data) {
                if (!data.success) {
                    sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                }
                loadSettings();
            },
            error: sln.showAjaxError
        });
    };

    var deleteHoliday = function () {
        var epochStart = $(this).parents('tr').data('epochStart');
        sln.confirm(CommonTranslations.HOLIDAY_REMOVE_CONFIRMATION, function () {
            sln.call({
                url: "/common/settings/holiday/delete",
                type: "POST",
                data: {
                    data: JSON.stringify({
                        holiday: {
                            start: epochStart
                        }
                    })
                },
                success: function (data) {
                    if (!data.success) {
                        sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                    }
                    loadSettings();
                },
                error: sln.showAjaxError
            });
        }, null, CommonTranslations.YES, CommonTranslations.NO);
    };

    var renderHolidays = function (sln_settings) {
        $("#oof-message").val(sln_settings.holiday_out_of_office_message);

        var $holidays = $("#holidays");
        $holidays.empty();
        var holidays = [];
        $.each(sln_settings.holidays, function (i, holiday) {
            if (i % 2 == 0) {
                holidays[i / 2] = {
                    start: sln.formatDate(holiday, false, false, false),
                    epochStart: holiday
                };
            } else {
                holidays[(i - 1) / 2].end = sln.formatDate(holiday, false, false, false);
            }
        });
        var html = $.tmpl(templates.holiday_holiday, {
            holidays: holidays,
            CommonTranslations: CommonTranslations
        });
        $.each(holidays, function (i, holiday) {
            $($("tr", html).get(i)).data('epochStart', holiday.epochStart);
        });
        $holidays.append(html);
        $("#holidays button").click(deleteHoliday);
    };

    $("#addholiday").click(addHoliday);
    sln.configureDelayedInput($("#oof-message"), saveOOFMessage);



    /* END HOLIDAYS */

    $(".sln-set-avatar").html(TMPL_SET_AVATAR);
    $("#avatar_div").click(uploadAvatar);
    $(".sln-set-logo").html(TMPL_SET_LOGO);
    $('#logo_div').click(uploadLogo).css({'width': '320px', 'height': (320 * SLN_LOGO_HEIGHT / SLN_LOGO_WIDTH) + 'px'});
    $(".sln-set-name").html(TMPL_SET_NAME);
    $(".sln-set-email-address").html(TMPL_SET_EMAIL);
    $(".sln-set-phone-number").html(TMPL_SET_PHONE_NUMBER);
    $(".sln-set-facebook-place").html(TMPL_SET_FACEBOOK_PLACE);
    $("#facebookPlaceStep1").click(loginFacebookPages);
    $("#facebookPlaceStep2").css('visibility', 'hidden');

    $(".sln-set-facebook-action-url").html(TMPL_SET_FACEBOOK_ACTION_URL);
    $(".sln-set-description").html(TMPL_SET_DESCRIPTION);
    $(".sln-set-openinghours").html(TMPL_SET_OPENINGHOURS);
    $('.sln-set-address').html(TMPL_SET_ADDRESS);
    $('.sln-set-currency').html(TMPL_SET_CURRENY);
    $(".sln-updates-pending-warning").html(TMPL_UPDATES_PENDING).hide();
    $(".sln-updates-pending-warning #publish_changes").click(publishChanges);
    $(".sln-updates-pending-warning #try_publish_changes").click(tryPublishChanges);

    $(".sln-required-warning").html(TMPL_REQUIRED_PENDING).hide();

    $("#settings").find("li a").click(settingTabPress);
    $(".sln-set-visibility").html(TMPL_SET_VISIBLE);
    $(".sln-set-search-keywords").html(TMPL_SET_SEARCH_KEYWORDS);
    $('.sln-set-search-keywords a[data-toggle="tooltip"]').tooltip();
    $(".sln-set-events-visibility").html(TMPL_SET_EVENTS_VISIBLE);
    $(".sln-set-events-notifications").html(TMPL_EVENT_NOTIFICATIONS);
    $('#section_general').find('#serviceVisible').click(serviceVisible);
    $('#section_general').find('#serviceInvisible').click(serviceInvisible);
    $('#eventsVisible').click(eventsVisible);
    $('#eventsInvisible').click(eventsInvisible);
    $('#enableEventsNotifications').click(enableEventsNotifications);
    $('#disableEventsNotifications').click(disableEventsNotifications);

    sln.configureDelayedInput($('.sln-set-name input'), saveSettings);
    sln.configureDelayedInput($('.sln-set-phone-number input'), saveSettings);
    sln.configureDelayedInput($('.sln-set-currency select'), saveSettings);
    sln.configureDelayedInput($('.sln-set-facebook-action-url input'), saveSettings);
    sln.configureDelayedInput($('.sln-set-description textarea'), saveSettings);
    sln.configureDelayedInput($('.sln-set-openinghours textarea'), saveSettings);
    sln.configureDelayedInput($('.sln-set-address textarea'), saveSettings);
    sln.configureDelayedInput($('.sln-set-timezone select'), saveSettings, null, false);
    sln.configureDelayedInput($('.sln-set-search-keywords textarea'), saveSettings);
    sln.configureDelayedInput($('.sln-set-email-address input'), saveSettings);
    // billing tab
    sln.configureDelayedInput($('.sln-set-iban input'), saveSettings);
    sln.configureDelayedInput($('.sln-set-bic input'), saveSettings);

    loadSettings();
    inboxLoadForwarders();

    sln.registerMsgCallback(channelUpdates);

    // Bulk invite
    sln.configureDelayedInput($('#blukEmails'), testBulkInvites, $("#blukEmailsLabel"), false);
    $('#sendBulkEmailInvitations').click(sendBulkInvites);

    // Fix screen
    $(window).resize(sln.resize_header);
    sln.resize_header();


    var settingsBranding,
        COLOR_REGEX = /^(([A-F0-9]{2}){3})$/i;

    function showSettingsBranding() {
        // Only render when it's not cached in the DOM yet
        if (!settingsBranding) {
            renderSettingsBranding();
        }
    }

    function renderSettingsBranding() {
        $('#branding_settings').html(TMPL_LOADING_SPINNER);
        getSettingsBranding(function (settings) {
            var elemBrandingSettings = $('#branding_settings');
            settingsBranding = settings;
            var html = $.tmpl(templates['settings/settings_branding'], {
                t: CommonTranslations,
                brandingSettings: settingsBranding.branding_settings
            });
            elemBrandingSettings.html(html);
            renderSettingsBrandingPreview();

            //bind events

            var elemColorScheme = $("#color_scheme"),
                elemShowName = $('#show_name'),
                elemInputShowAvatar = $('#show_avatar');

            elemColorScheme.change(function () {
                settingsBranding.branding_settings.color_scheme = elemColorScheme.val();
                recolorPreviewFrame();
            });

            elemShowName.change(function () {
                var showName = this.checked;
                settingsBranding.branding_settings.show_identity_name = showName;
                $("#preview_frame").contents().find('body').toggleClass('show_identity_name', showName);
                resizeBranding();
            });

            elemInputShowAvatar.change(function () {
                var showAvatar = this.checked;
                settingsBranding.branding_settings.show_avatar = showAvatar;
                $("#preview_frame").contents().find('body').toggleClass('show_avatar', showAvatar);
                resizeBranding();
            });

            $('#logo_div').click(function () {
                // uploadLogo is globally defined in sln-settings.js
                uploadLogo(renderSettingsBranding);
            });

            $('#save_button', elemBrandingSettings).click(function () {
                var $this = $(this);
                $this.text(CommonTranslations.SAVING_DOT_DOT_DOT);
                sln.call({
                    url: "/common/settings/branding",
                    type: "POST",
                    data: {
                        branding_settings: settingsBranding.branding_settings
                    },
                    success: function (data) {
                        $this.text(CommonTranslations.SAVE);
                        if (!data.success) {
                            return sln.alert(data.errormsg);
                        }
                    },
                    error: function () {
                        $this.text(CommonTranslations.ERROR);
                        setTimeout(function () {
                            $this.text(CommonTranslations.SAVE);
                        }, 10000);
                        sln.showAjaxError();
                    }
                });
            });

            $('.color-picker', elemBrandingSettings).on('input', colorPickerChanged);
            $('.color', elemBrandingSettings).on('input', colorChanged);
            sln.fixColorPicker($('#text_color'), $("#text_color_picker"), fixedColourPickerChanged);
            sln.fixColorPicker($('#background_color'), $("#background_color_picker"), fixedColourPickerChanged);
            sln.fixColorPicker($('#menu_item_color'), $("#menu_item_color_picker"), fixedColourPickerChanged);

            function colorPickerChanged() {
                var pickerInput = $(this);
                var pickerId = pickerInput.attr('id').replace('_picker', '');
                var colour = pickerInput.val().substring(1);
                var colourValid = colour && COLOR_REGEX.test(colour);
                var colourPicker = $('#' + pickerId);
                colourPicker.parent().parent().toggleClass('error', !colourValid);
                if (colourValid) {
                    settingsBranding.branding_settings[pickerId] = colour;
                    colourPicker.val(colour);
                    recolorPreviewFrame();
                }
            }

            function colorChanged() {
                var colorInput = $(this);
                var colour = colorInput.val().replace('#', '');
                var colorInputId = colorInput.attr('id');
                var colourValid = colour && COLOR_REGEX.test(colour);
                colorInput.parent().parent().toggleClass('error', !colourValid);
                if (colourValid) {
                    settingsBranding.branding_settings[colorInputId] = colour;
                    $('#' + colorInputId + '_picker').val('#' + colour);
                    recolorPreviewFrame();
                }
            }

            function fixedColourPickerChanged() {
                var colorInput = $(this);
                var colorInputText = colorInput.find('input[type=text]');
                var colour = colorInputText.val().replace('#', '');
                var colourValid = colour && COLOR_REGEX.test(colour);
                colorInput.parent().parent().toggleClass('error', !colourValid);
                if (colourValid) {
                    settingsBranding.branding_settings[colorInputText.attr('id')] = colour;
                    recolorPreviewFrame();
                }
            }
        });
    }

    function getSettingsBranding(callback) {
        if (!settingsBranding) {
            loadSettingsBranding(callback);
        } else {
            callback(settingsBranding);
        }
    }

    function loadSettingsBranding(callback) {
        sln.call({
            url: "/common/settings/branding_and_menu",
            type: "GET",
            success: callback
        });
    }

    var previewRenderingTimeout;

    function recolorPreviewFrame() {
        var css = {
            'background-color': '#' + settingsBranding.branding_settings.background_color,
            'color': '#' + settingsBranding.branding_settings.text_color,
            'overflow': 'hidden'
        };
        var canvas = $('#canvas').css('background-color', '#' + settingsBranding.branding_settings.background_color);
        $('#preview_frame').contents().find('body').css(css);

        if (previewRenderingTimeout) {
            clearTimeout(previewRenderingTimeout);
        }
        previewRenderingTimeout = setTimeout(function () {
            $('.service-menu-preview').find('td')
                .removeClass().addClass('rt-cs-' + settingsBranding.branding_settings.color_scheme)
                .find('span').css('background-color', '#' + settingsBranding.branding_settings.menu_item_color)
                .find('i.fa').css('color', '#' + settingsBranding.branding_settings.background_color);
            canvas.find('td').find('img').each(function () {
                var $this = $(this);
                var src = $this.attr('src');
                $this.attr('src', src.split('=')[0] + '=' + settingsBranding.branding_settings.menu_item_color);
            });
        }, 300);
    }

    function renderSettingsBrandingPreview() {
        var html = $.tmpl(templates['settings/settings_branding_preview'], {
            t: CommonTranslations,
            brandingSettings: settingsBranding.branding_settings,
            menuItems: settingsBranding.menu_item_rows
        });
        $('#branding_settings_preview').html(html);


        //bind events
        var elemIframe = $('#preview_frame').load(function () {
            var contents = elemIframe.contents();
            contents.find('body').toggleClass('show_identity_name', settingsBranding.branding_settings.show_identity_name);
            contents.find('body').toggleClass('show_avatar', settingsBranding.branding_settings.show_avatar);
            contents.find('#avatar').css('background-image', 'url(' + AVATAR_URL + ')');
            contents.find('#logo').attr('src', LOGO_URL);
            resizeBranding();
            recolorPreviewFrame();
            setTimeout(resizeBranding, 200);
            setTimeout(resizeBranding, 2000);
            setTimeout(resizeBranding, 5000);
        });
    }

    function resizeBranding() {
        var elemIFrame = $("#preview_frame").height(50);
        var iframeDocument = elemIFrame.contents().first();
        if (iframeDocument && iframeDocument.length) {
            var height = iframeDocument.height();
            elemIFrame.height(height);
        }
    }

    function uploadImage(popupHeader, updateUrl, width, height, successCallback, circle_preview) {
        var html = $.tmpl(templates['settings/upload_image'], {
            header: popupHeader,
            width: width,
            height: height,
            circle_preview: circle_preview,
        });
        var modal = sln.createModal(html);
        var imageElem = $('#avatarUpload', modal);
        var imagePreview = $('.cropped_image_preview img', modal);
        var selectedFile = null;
        $('#newAvatar', modal).change(fileSelected);

        function fileSelected() {
            var CROP_OPTIONS = {
                viewMode: 1,
                dragMode: 'crop',
                rotatable: true,
                autoCropArea: 1.0,
                minContainerWidth: width,
                minContainerHeight: height,
                aspectRatio: width / height,
                preview: '.cropped_image_preview'
            };
            sln.readFile(this, imageElem, 'dataURL', function () {
                imagePreview.parent().show();
                imagePreview.attr('src', imageElem.attr('src'));
                imageElem.cropper('destroy');
                imageElem.cropper(CROP_OPTIONS);
            });
            selectedFile = this.value;
        }


        $('button[action="submit"]', modal).click(function () {
            if (!selectedFile) {
                sln.alert(T('No image selected yet'));
                return;
            }
            var options = {
                width: width,
                height: height
            };
            var image = imageElem.cropper('getCroppedCanvas', options).toDataURL('image/png');
            sln.showProcessing();
            sln.call({
                url: updateUrl,
                data: {
                    image: image
                },
                type: 'POST',
                success: function (errorMsg) {
                    sln.hideProcessing();
                    if (errorMsg) {
                        sln.alert(errorMsg, null, CommonTranslations.ERROR);
                    } else {
                        modal.modal('hide');

                        if (typeof successCallback === 'function') {
                            successCallback();
                        }
                    }
                }
            });
        });
    }

    function saveSettings(callback) {
        var allOK = true;
        $('#required_fields').empty();
        // Check name
        if ($('.sln-set-name').attr('required_setting') && !$('.sln-set-name input').val()) {
            $('.sln-set-name input').addClass("error");
            $('#required_fields').append('<li>' + CommonTranslations.NAME_IS_REQUIRED + '</li>');
            allOK = false;
        } else {
            $('.sln-set-name input').removeClass("error");
        }
        // Check phone_number
        if ($('.sln-set-phone-number').attr('required_setting') && !$('.sln-set-phone-number input').val()) {
            $('.sln-set-phone-number input').addClass("error");
            $('#required_fields').append('<li>' + CommonTranslations.PHONE_REQUIRED + '</li>');
            allOK = false;
        } else {
            $('.sln-set-phone-number input').removeClass("error");
        }

        if (!allOK) {
            $(".sln-required-warning").fadeIn('slow');
            $(".sln-updates-pending-warning").fadeOut('fast');
            return;
        }
        $(".sln-required-warning").fadeOut('fast');
        // do post
        var data = JSON.stringify({
            name: $('.sln-set-name input').val(),
            phone_number: $('.sln-set-phone-number input').val(),
            currency: $('.sln-set-currency select').val(),
            facebook_action: $('.sln-set-facebook-action-url input').val(),
            facebook_name: $('.sln-set-facebook-place #place-input').val(),
            facebook_page: $('.sln-set-facebook-place #place-input-id').val(),
            description: $('.sln-set-description textarea').val(),
            opening_hours: $('.sln-set-openinghours textarea').val(),
            address: $('.sln-set-address textarea').val(),
            search_enabled: searchEnabled,
            search_enabled_check: searchEnabledCheck,
            search_keywords: $('.sln-set-search-keywords textarea').val(),
            email_address: $('.sln-set-email-address input').val(),
            timezone: $('.sln-set-timezone select').val(),
            events_visible: eventsEnabled,
            event_notifications_enabled: eventNotificationsEnabled,
            inbox_email_reminders: inboxEmailRemindersEnabled,
            iban: $('.sln-set-iban input').val(),
            bic: $('.sln-set-bic input').val()
        });
        sln.call({
            url: "/common/settings/save",
            type: "POST",
            data: {
                data: data
            },
            success: function (data) {
                if (!data.success) {
                    return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                }
                if (typeof callback === 'function') {
                    callback();
                }
                if(data.result === null){
                    $("#address_geocode_error").hide();
                } else if(data.result.address_geocoded){
                    $("#address_geocode_error").hide();
                } else{
                    $("#address_geocode_error").show();
                }
            },
            error: sln.showAjaxError
        });
    }

    function uploadLogo(successCallback) {
        var popupHeader = T('Change logo');
        var updateUrl = '/common/settings/logo';
        // SLN_LOGO_WIDTH & SLN_LOGO_HEIGHT defined in common/bizz/settings.py and rendered as js var in index.html
        uploadImage(popupHeader, updateUrl, SLN_LOGO_WIDTH, SLN_LOGO_HEIGHT, successCallback);
    }

    function uploadAvatar() {
        var popupHeader = T('Change avatar');
        var previewWidth = 150;
        var previewHeight = 150;
        var updateUrl = '/common/settings/avatar';
        var url = $(".sln-set-avatar").attr('url');
        if (url) {
            updateUrl = url;
        }
        uploadImage(popupHeader, updateUrl, previewWidth, previewHeight, null, true);
    }

    function moveElementInArray(array, old_index, new_index) {
        if (new_index >= array.length) {
            var k = new_index - array.length;
            while ((k--) + 1) {
                array.push(undefined);
            }
        }
        array.splice(new_index, 0, array.splice(old_index, 1)[0]);
    }

    function getbroadcastOptions(callback) {
        if (LocalCache.broadcastOptions) {
            callback(LocalCache.broadcastOptions);
        } else {
            sln.call({
                url: "/common/broadcast/options",
                type: "GET",
                success: function (data) {
                    LocalCache.broadcastOptions = data;
                    callback(data);
                }
            });
        }
    }

    function addBroadcastNewsPublisher() {
        $('li[section=section_settings_roles]').find('a').click();
        renderRolesSettings();
        // show the add roles dialog with only news publisher option
        addRoles(false, false, true);
    }

    // add broadcast news publisher
    $('#broadcast_add_news_publisher').click(addBroadcastNewsPublisher);
    // add broadcast type
    $('#settings_add_extra_broadcast_type').click(addBroadcastType);
    $('#settings_extra_broadcast_type').on('input', function() {
        // check for broadcast type if exists or empty
        var broadcastOptions = LocalCache.broadcastOptions;
        var value = $(this).val().trim();
        var alreadyExists = broadcastOptions && broadcastOptions.editable_broadcast_types.indexOf(value) !== -1;

        if(value.length < 3 || !broadcastOptions || alreadyExists) {
            $('#settings_add_extra_broadcast_type').attr('disabled', true);
        } else {
            $('#settings_add_extra_broadcast_type').attr('disabled', false);
        }
    });

    function renderBroadcastSettings() {
        getbroadcastOptions(function (broadcastOptions) {
            var html = $.tmpl(templates.broadcast_settings_list, {
                broadcastTypes: broadcastOptions.editable_broadcast_types,
                t: CommonTranslations
            });
            $('#section_settings_broadcast > div[name=broadcast_types]').html(html);
            var listElem = $('#broadcast-types-sortable-list');
            listElem.find('button[data-action=up]').click(function () {
                var $this = $(this);
                var oldIndex = broadcastOptions.editable_broadcast_types.indexOf($this.attr('data-value'));
                var newIndex = oldIndex - 1;
                moveElementInArray(broadcastOptions.editable_broadcast_types, oldIndex, newIndex);
                renderBroadcastSettings();
            });
            listElem.find('button[data-action=down]').click(function () {
                var $this = $(this);
                var oldIndex = broadcastOptions.editable_broadcast_types.indexOf($this.attr('data-value'));
                var newIndex = oldIndex + 1;
                moveElementInArray(broadcastOptions.editable_broadcast_types, oldIndex, newIndex);
                renderBroadcastSettings();
            });
            listElem.find('button[data-action=delete]').click(function() {
                addOrRemoveBroadcastType($(this).data('value'), true);
            });
            $('#btn-save-broadcast-settings').click(saveBroadcastSettings);
        });
    }

    function addBroadcastType() {
        var broadcastTypeInput = $('#settings_extra_broadcast_type');
        var broadcastType = broadcastTypeInput.val().trim();

        addOrRemoveBroadcastType(broadcastType, false, function() {
            broadcastTypeInput.val('');
            $('#settings_add_extra_broadcast_type').attr('disabled', true);
        });
    }

    function addOrRemoveBroadcastType(broadcastType, shouldDelete, callback) {
        function doAddOrRemove() {
            if (broadcastType) {
                sln.call({
                    url: '/common/settings/broadcast/add_or_remove_type',
                    type: 'POST',
                    showProcessing: true,
                    data: {
                        broadcast_type: broadcastType,
                        delete: !!shouldDelete
                    },
                    success: function(data) {
                        if(data.success) {
                            if(typeof callback === 'function') {
                                callback();
                            }
                            LocalCache.broadcastOptions = null;
                            renderBroadcastSettings();
                        } else {
                            sln.alert(T[sln.errormsg]);
                        }
                    },
                    error: sln.showAjaxError
                });
            }
        }

        if (shouldDelete) {
            var confirmMessage = CommonTranslations.confirm_delete_x.replace('%(x)s', broadcastType);
            sln.confirm(confirmMessage, doAddOrRemove);
        } else {
            doAddOrRemove();
        }
    }

    function saveBroadcastSettings() {
        var statusText = $('#save-broadcast-settings-status');
        statusText.text(CommonTranslations.SAVING_DOT_DOT_DOT);
        sln.call({
            url: '/common/settings/broadcast/change_order',
            method: 'post',
            data: {
                data: JSON.stringify({broadcast_types: LocalCache.broadcastOptions.editable_broadcast_types})
            },
            success: function () {
                statusText.text(CommonTranslations.SAVE);
            },
            error: function () {
                statusText.text(CommonTranslations.ERROR);
            }
        });
    }

    function avatarUpdated() {
        // Update in branding preview and in 'general' settings
        var avatarUrl = AVATAR_URL + '?_=' + new Date().getTime();
        $('#avatar_div').find('.settings_avatar').attr('src', avatarUrl);
        $('#preview_frame').contents().find('#avatar').css('background-image', 'url(' + avatarUrl + ')');
    }

    function logoUpdated() {
        // Update in branding preview and in 'general' settings
        var logoUrl = LOGO_URL + '?_=' + new Date().getTime();
        $('#logo_div').find('img').attr('src', logoUrl);
        $('#preview_frame').contents().find('#logo').attr('src', logoUrl);
    }

    function getAppSettings(callback) {
        if (LocalCache.settings.app) {
            callback(LocalCache.settings.app);
        } else {
            sln.call({
                url: '/common/settings/app',
                success: function (data) {
                    LocalCache.settings.app = data;
                    callback(data);
                }
            });
        }
    }

    function saveAppSettings() {
        var birthdayMessageEnabled = $('#birthday_message_enabled').prop('checked'),
            birthdayMessage = $('#birthday_message').val();
        sln.call({
            url: '/common/settings/app',
            method: 'post',
            data: {
                settings: {
                    birthday_message_enabled: birthdayMessageEnabled,
                    birthday_message: birthdayMessage
                }
            },
            success: function (data) {
                LocalCache.settings.app = data;
            }
        });
    }

    function renderAppSettings() {
        getAppSettings(render);
        function render(appSettings) {
            var html = $.tmpl(templates['settings/app_settings'], {
                settings: appSettings,
                sln: sln
            });
            $('#section_app_settings').html(html);
            $('#birthday_message_enabled').change(saveAppSettings);
            sln.configureDelayedInput($('#birthday_message'), saveAppSettings);
        }
    }

    function getAllUserRoles(callback) {
        sln.call({
            url: '/common/users/roles/load',
            success: callback,
            error: sln.showAjaxError
        });
    }

    function addRoles(inboxEnabled, agendaEnabled, broadcastEnabled) {
        // get the available calendars first
        if(agendaEnabled) {
            sln.call({
                url: '/common/calendar/load',
                success: showAddRolesModal,
                error: sln.showAjaxError
            });
        }
        else {
            showAddRolesModal([]);
        }

        function showAddRolesModal(calendars) {
            var html = $.tmpl(templates['settings/app_user_add_roles'], {
                calendars: calendars,
                inbox_enabled: inboxEnabled,
                agenda_enabled: agendaEnabled,
                broadcast_enabled: broadcastEnabled
            });

            var modal = sln.createModal(html, function (modal) {
                $('#app_user_email_input', modal).focus();
            });

            // show inbox forwarder type if inbox forwarder
            $('#is_inbox_forwarder', modal).change(function() {
                if($(this).is(':checked')) {
                    $('#forwarder_type_selection', modal).show();
                } else {
                    $('#forwarder_type_selection', modal).hide();
                }
            });

            // show calendars selection if calendar admin
            $('#is_calendar_admin', modal).change(function() {
                if($(this).is(':checked')) {
                    $('#calendar_selection', modal).show();
                } else {
                    $('#calendar_selection', modal).hide();
                }
            });

            // search the existing users
            // just like events add admin or add inbox forwarer
            var searchInput = $('#app_user_email_input', modal);
            sln.userSearch(searchInput, appUserRolesSearch,
            function(user_key) {
                $('button[action="submit"]', modal).attr("user_key", user_key);
            },
            function(query) {
                $('button[action="submit"]', modal).attr("user_key", "");
            });

            $('button[action="submit"]', modal).click(function() {
                var userKey = $(this).attr('user_key');
                var inboxForwarder, calendarAdmin, newsPublisher;
                inboxForwarder = $('#is_inbox_forwarder').is(':checked');
                calendarAdmin = $('#is_calendar_admin').is(':checked');
                newsPublisher = $('#is_news_publisher').is(':checked');
                var forwarderType = $('input[name=forwarder_type]:checked').attr('forwarder_type');
                // user selected no roles
                if(!(inboxForwarder || calendarAdmin || newsPublisher)) {
                    sln.alert(CommonTranslations.roles_please_select_one_role_at_least, null, CommonTranslations.ERROR);
                    return;
                }

                // if the user key is not set, then it's an email address
                // this email address can be for a non-existing user
                // so he/she cannot has any role other than email inbox forwarder
                if(!userKey) {
                    if((inboxForwarder && (forwarderType == 'mobile')) || calendarAdmin || newsPublisher) {
                        // we need a valid user (not just an email) in these cases
                        sln.alert(CommonTranslations.roles_please_provide_user, null, CommonTranslations.ERROR);
                        return;
                    }
                    // this is an email inbox forwarder
                    // so check the input email address
                    userKey = $('#app_user_email_input').val();
                    if(!userKey) {
                        sln.alert(CommonTranslations.roles_please_provide_email, null, CommonTranslations.ERROR);
                        return;
                    }
                }

                calendars = []
                if(calendarAdmin) {
                    // get calendars
                    $('#calendar_selection', modal).find('input[type=checkbox]:checked').each(function() {
                        calendars.push({
                            id: parseInt($(this).attr('calendar_id'))
                        });
                    });

                    if(calendars.length < 1) {
                        sln.alert(CommonTranslations.calendar_please_select_one_at_least, null, CommonTranslations.ERROR);
                        return;
                    }
                }

                // only add a forwarder type per time
                // to disable other roles for any email that doesn't exist as a user
                var forwarderTypes = [forwarderType];
                sln.call({
                    url: '/common/users/roles/add',
                    method: 'post',
                    showProcessing: true,
                    data: {
                        key: userKey,
                        user_roles: {
                            inbox_forwarder: inboxForwarder,
                            calendar_admin: calendarAdmin,
                            news_publisher: newsPublisher,
                            forwarder_types: forwarderTypes,
                            calendars: calendars
                        }
                    },
                    success: function(data) {
                        if(!data.success) {
                            sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                        } else {
                            modal.modal('hide');
                            renderRolesSettings();
                        }
                    },
                    error: sln.showAjaxError
                });
            });
        }
    }

    function renderRolesSettings() {
        // check if inbox, agenda and broadcast modules are enabled
        // cannot figure out another way to check it from the client side!
        var inboxEnabled = $('#section_settings_inbox').length > 0
        var agendaEnabled = $('#section_settings_agenda').length > 0
        var broadcastEnabled = $('#section_settings_broadcast').length > 0

        var container = $('#section_settings_roles');
        container.html(TMPL_LOADING_SPINNER);

        getAllUserRoles(render);
        function render(data) {
            var html = $.tmpl(templates['settings/app_user_roles'], {
                t: CommonTranslations,
                roles: data,
                inbox_enabled: inboxEnabled,
                agenda_enabled: agendaEnabled,
                broadcast_enabled: broadcastEnabled
            });

            $('#add_user_roles', html).click(function() {
                addRoles(inboxEnabled, agendaEnabled, broadcastEnabled);
            });

            $('button[action=delete_roles]', html).click(deleteRoles);
            function deleteRoles() {
                var key = $(this).attr('user_key');
                var email = key.split(':')[0];
                var row = $('tr[user_key="' + key + '"]', html);
                var forwarderTypes = $('input[name=inbox]', row).attr('forwarder_types');
                var calendarIds = $('input[name=calendar]', row).attr('calendar_ids');

                if(!forwarderTypes) {
                    forwarderTypes = [];
                } else {
                    forwarderTypes = forwarderTypes.split(',');
                }

                if(!calendarIds) {
                    calendarIds = []
                } else {
                    calendarIds = calendarIds.split(',').map(function(i) {
                        return parseInt(i);
                    });
                }

                var confirmMessage = CommonTranslations.roles_delete_confirmation.replace('%(email)s', email);
                sln.confirm(confirmMessage, doDelete, null, null, null, null);
                function doDelete() {
                    sln.call({
                        url: '/common/users/roles/delete',
                        showProcessing: true,
                        method: 'post',
                        data: {
                            key: key,
                            forwarder_types: forwarderTypes,
                            calendar_ids: calendarIds
                        },
                        success: function(data) {
                            if(!data.success) {
                                sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                            } else {
                                renderRolesSettings();
                            }
                        },
                        error: sln.showAjaxError
                    });
                }


            }

            $('#app_users_count', html).text(data.length);
            container.html(html);
        }
    }
});

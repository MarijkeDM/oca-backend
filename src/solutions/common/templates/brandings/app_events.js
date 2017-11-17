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

(function () {
    'use strict';
    var events = null;
    var eventsDict = {};
    var calendarsDict = {};
    var removedEvents = [];
    var guestsDict = {};

    var HOUR = 60 * 60;
    var DAY = 24 * HOUR;

    var eventsTemplate = '{{each(i, d) days}}'
        + '<li data-role="list-divider" role="heading" class="ui-li ui-li-divider ui-bar-a ui-li-has-count">'
        + '${d.date} <span class="ui-li-count ui-btn-up-c ui-btn-corner-all">${d.events.length}</span>'
        + '</li>'
        + '{{each(i, e) d.events}}'
        + '<li class="eventItem" event_id="${e.event.id}" event_date="${e.date}" onclick="">'

        + '<a href="#detail" data-transition="slide" class="ui-btn ui-btn-icon-right ui-icon-carat-r">'
        + '<p class="ui-li-aside ui-li-desc" style="top: 0.3em;"><strong>${e.time}</strong></p>'
        + '<h2 class="ui-li-heading">${e.event.title}</h2>'
        + '<p class="ui-li-desc">${e.event.description}</p>'
        + '</a>'
        + '</li>'
        + '{{/each}}'
        + '{{/each}}';
    var language = window.navigator.languages ? window.navigator.languages[0] : null;
    language = language || window.navigator.language || window.navigator.browserLanguage || window.navigator.userLanguage;
    moment.locale(language);

    $(document).ready(init);

    function init() {
        if (typeof rogerthat === 'undefined') {
            document.body.innerHTML = EventsTranslations.ROGERTHAT_FUNCTION_UNSUPPORTED_UPDATE;
            return;
        }
        rogerthat.callbacks.ready(onRogerthatReady);
        rogerthat.callbacks.backPressed(backPressed);
    }

    function backPressed() {
        console.log("BACK pressed");
        var activePage = $.mobile.activePage.attr('id');
        var newPage = null;
        if (activePage == "events") {
        } else if (activePage == "detail") {
            newPage = "events";
        } else if (activePage === "broadcast") {
            newPage = "events";
        } else if (activePage === "calendars") {
            newPage = "events";
        } else if (activePage === "guests") {
            newPage = "detail";
        }

        if (newPage === null) {
            return false;
        }
        setTimeout(function () {
            $.mobile.changePage('#' + newPage);
        }, 100); // need to do this async
        return true; // we handled the back press
    }

    function caseInsensitiveStringSort(a, b) {
        var lowerCaseA = a.toLowerCase();
        var lowerCaseB = b.toLowerCase();
        if (lowerCaseA < lowerCaseB)
            return -1;
        if (lowerCaseA > lowerCaseB)
            return 1;
        return 0;
    }

    function smartSort(a, b) {
        var wordsA = a.split(' ');
        var wordsB = b.split(' ');
        for (var i = 0; i < Math.min(wordsA.length, wordsB.length); i++) {
            var wordA = wordsA[i];
            var wordB = wordsB[i];
            var numberA = parseFloat(wordA);
            var numberB = parseFloat(wordB);
            var aIsNumeric = !isNaN(wordA) && !isNaN(numberA) && isFinite(wordA);
            var bIsNumeric = !isNaN(wordB) && !isNaN(numberB) && isFinite(wordB);

            if (aIsNumeric && bIsNumeric) {
                // wordA and wordB are both numbers
                if (numberA == numberB)
                    continue;
                return numberA - numberB;
            } else if (aIsNumeric) {
                // only wordA is a number
                return -1;
            } else if (bIsNumeric) {
                // only wordB is a number
                return 1;
            }
            // wordA and wordB are both non-numeric strings
            var cmp = caseInsensitiveStringSort(wordA, wordB);
            if (cmp === 0)
                continue;
            return cmp;
        }
        // if we reach this point, then a and b are equal until
        // Math.min(wordsA.length, wordsB.length)
        // the string with the fewest words is smaller than the other string
        return wordsA.length - wordsB.length;
    }

    function getAdminCalendars() {
        var accountKey = rogerthat.user.account;
        if (rogerthat.system.appId != "rogerthat") {
            accountKey = accountKey + ":" + rogerthat.system.appId;
        }
        var calendars = [];
        $.each(rogerthat.service.data.solutionCalendars, function (i, calendar) {
            var keys = [];
            $.each(calendar.admins, function (i, admin) {
                keys.push(admin.key);
            });
            if ($.inArray(accountKey, keys) > -1) {
                calendars.push(calendar.id);
            }
        });
        return calendars;
    }

    function createGuestDetailListItem(guest) {
        var li = $('<li class="guestItem" style="padding: 0; border: 1px solid #ddd;" onclick=""></li>');
        li.data("guest", guest);
        var div = $('<div></div>');
        var avatar = $('<img style="height: 3em;width: 3em; float: left;">').attr("src", guest.avatar_url);
        div.append(avatar);
        var name = $('<h2 style="line-height: 3em;margin: 0;margin-left: 4em;"></h2>').text(guest.name);
        div.append(name);
        return li.append(div);
    }

    function isSameDay(a, b) {
        return (a.getDate() == b.getDate()
        && a.getMonth() == b.getMonth()
        && a.getFullYear() == b.getFullYear());
    }

    function toDateObject(startOrEndDate) {
        // get a Date object from start/end objects
        return new Date(startOrEndDate.year, startOrEndDate.month - 1, startOrEndDate.day, startOrEndDate.hour, startOrEndDate.minute);
    }

    function getNextStartAndEndTime(event, now, full_end_date) {
        var checkdate = now - DAY;
        for (var i in event.start_dates) {
            var endDate = event.end_dates_timestamps[i];
            if (checkdate < new Date(endDate.year, endDate.month - 1, endDate.day, endDate.hour, endDate.minute).getTime() / 1000) {
                if (full_end_date) {
                    return {"start": event.start_dates[i], "end": event.end_dates_timestamps[i]};
                } else {
                    return {"start": event.start_dates[i], "end": event.end_dates[i]};
                }
            }
        }
        if (full_end_date) {
            return {
                "start": event.start_dates[event.start_dates.length - 1],
                "end": event.end_dates_timestamps[event.end_dates_timestamps.length - 1]
            };
        } else {
            return {
                "start": event.start_dates[event.start_dates.length - 1],
                "end": event.end_dates[event.end_dates.length - 1]
            };
        }
    }

    function getUpcomingStartAndEndDates(event, now, full_end_date, allow_empty) {
        var checkdate = now;
        var upcoming = [];
        for (var i in event.start_dates) {
            var endDate = event.end_dates_timestamps[i];
            if (checkdate < new Date(endDate.year, endDate.month - 1, endDate.day, endDate.hour, endDate.minute).getTime() / 1000) {
                if (full_end_date) {
                    upcoming.push({"start": event.start_dates[i], "end": event.end_dates_timestamps[i]});
                } else {
                    upcoming.push({"start": event.start_dates[i], "end": event.end_dates[i]});
                }
            }
        }
        if (!allow_empty && upcoming.length === 0) {
            if (full_end_date) {
                return [{
                    "start": event.start_dates[event.start_dates.length - 1],
                    "end": event.end_dates_timestamps[event.end_dates_timestamps.length - 1]
                }];
            } else {
                return [{
                    "start": event.start_dates[event.start_dates.length - 1],
                    "end": event.end_dates[event.end_dates.length - 1]
                }];
            }
        }
        return upcoming;
    }

    function hideRemindMePopupOverlay() {
        var elem = $('#remind-me-popup');
        elem.popup('close');  // needs to be double for first close
        elem.popup('close');
    }

    function showRemindMePopupOverlay(event) {
        $("#remind-me-invalid-time").hide();
        $("#remind-me-valid").hide();
        $("#remind-me-popup-content-day").hide();
        $("#remind-me-popup-content-4-hours").hide();
        $("#remind-me-popup-content-1-hour").hide();

        var nowDate = new Date();
        var n = nowDate.getTimezoneOffset() * 60 * 1000;
        var now = parseInt(nowDate.getTime() - n) / 1000;

        var eventStart = event.start_date.getTime() / 1000;
        var nothingSet = true;

        $("#detail").data("event-start-epoch", eventStart);

        if ((now + DAY) < eventStart) {
            $("#remind-me-popup-content-day").show();
            nothingSet = false;
        }
        if ((now + HOUR * 4) < eventStart) {
            $("#remind-me-popup-content-4-hours").show();
            nothingSet = false;
        }
        if ((now + HOUR) < eventStart) {
            $("#remind-me-popup-content-1-hour").show();
            nothingSet = false;
        }

        if (nothingSet) {
            $("#remind-me-invalid-time").show();
        } else {
            $("#remind-me-valid").show();
        }

        $("#remind-me-popup").popup("open", {positionTo: 'window'});
    }

    function showEventInvitationSent() {
        $('#event-invitation-sent-popup').popup("open", {positionTo: 'window'});
    }

    function hideEventRemovePopupOverlay() {
        var elem = $('#event-remove-popup');
        elem.popup('close');  // needs to be double for first close
        elem.popup('close');
    }

    function hideEventInvitationSent() {
        var elem = $('#event-invitation-sent-popup');
        elem.popup('close');
    }

    function onRogerthatReady() {
        console.log("onRogerthatReady()");
        var modules = rogerthat.service.data.settings.modules;
        if (modules && modules.indexOf('broadcast') === -1) {
            $('#broadcast-to-calendar').remove();
        }
        rogerthat.api.callbacks.resultReceived(onReceivedApiResult);
        rogerthat.callbacks.serviceDataUpdated(loadEvents);

        rogerthat.user.data.agenda = null;
        if (!rogerthat.user.data.calendar) {
            rogerthat.user.data.calendar = {};
        }


        loadEvents();

        function addToCalender(event) {
            var eventDate = event.start_date;
            var eventEndDate = event.end_date;
            var eventStart = eventDate.getTime() / 1000;
            var eventEnd = eventEndDate.getTime() / 1000;

            var addToCalenderParams = {
                'eventId': event.id,
                'eventTitle': event.title,
                'eventDescription': event.description,
                'eventStart': eventStart,
                'eventEnd': eventEnd,
                'eventPlace': event.place,
                'eventDate': parseDateToEventDateTime(eventDate),
            };
            var paramsss = JSON.stringify(addToCalenderParams);
            rogerthat.api.call("solutions.events.addtocalender", paramsss, "");

            setTimeout(showEventInvitationSent, 100);
        }

        var now = (new Date().getTime()) / 1000;
        $(document).on("click", ".eventItem", function () {
            var eventId = parseInt($(this).attr("event_id"));
            var eventDate = $(this).attr("event_date");
            var event = eventsDict[eventId][eventDate];
            $("#detail").data("event", event);

            var calendar = calendarsDict[event.calendar_id];
            var adminCalendars = getAdminCalendars();

            if ($.inArray(calendar.id, adminCalendars) >= 0) {
                $("#event-remove").show();
            } else {
                $("#event-remove").hide();
            }

            $('#detail [data-role="content"]').css("background-color", "#fff");
            $("#detail .event-detail-picture").hide();
            if (event.picture) {
                $.ajax({
                    url: event.picture,
                    success: function (data) {
                        if (data && data.success) {
                            $("#detail .event-detail-picture").show();
                            var img = $("#detail .event-detail-picture img");
                            img.attr('src', data.picture);
                            img.slideDown();
                        }
                    }
                });
            }

            $("#detail .event-detail-title").text(event.title);

            var upcomingEvents = getUpcomingStartAndEndDates(event, now, true);
            var eventDate = new Date(upcomingEvents[0].start.year, upcomingEvents[0].start.month - 1, upcomingEvents[0].start.day, upcomingEvents[0].start.hour, upcomingEvents[0].start.minute);

            if (upcomingEvents.length == 1) {
                $("#detail .event-detail-date p").text(parseDateToEventDateTime(eventDate));
            } else {
                var d = "";
                $.each(upcomingEvents, function (ui, upcoming_event) {
                    var upcomingEventDate = toDateObject(upcoming_event.start);
                    if(upcomingEventDate.getTime() == event.start_date.getTime()) {
                        d += "- <b>" + parseDateToEventDateTime(upcomingEventDate) + "</b><br>";
                    } else {
                        d += "- " + parseDateToEventDateTime(upcomingEventDate) + "<br>";
                    }
                });

                $("#detail .event-detail-date p").html(d);
            }

            if (event.place) {
                $("#detail .event-detail-place").show();
                $("#detail .event-detail-place p").text(event.place);
            } else {
                $("#detail .event-detail-place").hide();
            }

            if (event.organizer) {
                $("#detail .event-detail-organizer").show();
                $("#detail .event-detail-organizer p").text(EventsTranslations.EVENTS_ORGANIZER + ": " + event.organizer);
            } else {
                $("#detail .event-detail-organizer").hide();
            }

            $("#detail .event-detail-description p").html(htmlize(event.description));

            if (event.external_link) {
                $("#detail #event-detail-read").attr("href", event.external_link);
            } else {
                $("#detail #event-detail-read").hide();
            }

            $("#event-detail-calendar").hide();
            $("#detail .event-detail-guests-loading").show();
            $("#detail .event-detail-guests").hide();

            if (guestsDict[event.id] === undefined) {
                var participantsParams = {
                    'eventId': event.id,
                    'includeDetails': 0
                };

                var paramsss = JSON.stringify(participantsParams);
                rogerthat.api.call("solutions.events.guests", paramsss, "");
            } else {
                loadGuests(event.id);
            }
        });

        $(document).on("click", "#detail #event-detail-calendar", function () {
            console.log("#detail #event-detail-calendar");
            var event = $("#detail").data("event");
            addToCalender(event);
        });

        $(document).on("click", "#detail #event-detail-remind", function () {
            console.log("#detail #event-detail-remind");
            var event = $("#detail").data("event");
            showRemindMePopupOverlay(event);
        });

        $(document).on("click", ".remindOptionsSelector", function () {
            console.log("#detail .remindOptionsSelector");
            var event = $("#detail").data("event");
            var eventStartEpoch = parseInt($("#detail").data("event-start-epoch"));
            var remindMeSeconds = parseInt($(this).attr("remindmeseconds"));

            hideRemindMePopupOverlay();

            console.log("eventId: " + event.id);
            console.log("eventStartEpoch: " + eventStartEpoch);
            console.log("remindSeconds: " + remindMeSeconds);

            var remindmeLaterParams = {
                'eventId': event.id,
                'remindBefore': remindMeSeconds,
                'eventStartEpoch': eventStartEpoch
            };

            var paramsss = JSON.stringify(remindmeLaterParams);

            rogerthat.api.call("solutions.events.remind", paramsss, "");
        });

        $(document).on("click", ".eventRemoveOptionSelector", function () {
            var shouldRemove = parseInt($(this).attr("delete"));
            if (shouldRemove == 1) {
                var event = $("#detail").data("event");
                removedEvents.push(event.id);

                var eventRemoveParams = {
                    'eventId': event.id
                };

                var paramsss = JSON.stringify(eventRemoveParams);

                rogerthat.api.call("solutions.events.remove", paramsss, "");
                loadEvents();
            }
            hideEventRemovePopupOverlay();
        });

        $(document).on("change", "input[name=radio-choice-guests]:radio", function () {
            var event = $("#detail").data("event");
            var status = parseInt($('input[name=radio-choice-guests]:checked').val());

            if (guestsDict[event.id].your_status) {
                if (guestsDict[event.id].your_status == 1) {
                    guestsDict[event.id].guests_count_going -= 1;
                } else if (guestsDict[event.id].your_status == 2) {
                    guestsDict[event.id].guests_count_maybe -= 1;
                } else if (guestsDict[event.id].your_status == 3) {
                    guestsDict[event.id].guests_count_not_going -= 1;
                }
            }
            guestsDict[event.id].your_status = status;
            guestsDict[event.id].include_details = 0;

            if (status == 1) {
                guestsDict[event.id].guests_count_going += 1;
            } else if (status == 2) {
                guestsDict[event.id].guests_count_maybe += 1;
            } else if (status == 3) {
                guestsDict[event.id].guests_count_not_going += 1;
            }

            loadGuests(event.id);

            var guestStatusParams = {
                'eventId': event.id,
                'status': status
            };

            var paramsss = JSON.stringify(guestStatusParams);

            rogerthat.api.call("solutions.events.guest.status", paramsss, "");
        });

        $(document).on("click", ".closeRemindMePopup", function () {
            hideRemindMePopupOverlay();
        });

        $(document).on("click", ".closeEventRemovePopup", function () {
            hideEventRemovePopupOverlay();
        });

        $(document).on("click", ".closeEventInvitationSent", function() {
            hideEventInvitationSent();
        });

        $(document).on("click", ".gotoCalendar", function () {
            $("#calendar-checkboxes").empty();

            rogerthat.service.data.solutionCalendars.sort(function (calendar1, calendar2) {
                return smartSort(calendar1.name, calendar2.name);
            });

            $.each(rogerthat.service.data.solutionCalendars, function (i, calendar) {
                var input = $('<input class="custom" type="checkbox">');
                input.prop("name", "calendar-checkbox-" + calendar.id);
                input.prop("id", "calendar-checkbox-" + calendar.id);

                var disabledFilter = $.inArray(calendar.id, rogerthat.user.data.calendar.disabled);
                input.prop('checked', 0 > disabledFilter);
                input.attr("calendar-id", calendar.id);
                $("#calendar-checkboxes").append(input);

                var label = $('<label></label>');
                label.text(calendar.name);
                label.prop("for", "calendar-checkbox-" + calendar.id);
                label.attr("calendar-id", calendar.id);
                $("#calendar-checkboxes").append(label);
            });
            $('#calendars').trigger('create');
        });

        $(document).on("click", ".calendar-save", function () {
            var disabled = [];
            $('#calendar-checkboxes').find('input[type=checkbox]:not(:checked)').each(function () {
                disabled.push(parseInt($(this).attr("calendar-id")));
            });

            rogerthat.user.data.calendar.disabled = disabled;
            rogerthat.user.put();
            loadEvents();
        });

        $(document).on("click", ".gotoBroadcast", function () {
            $("#calendar-radiobuttons").empty();

            var adminCalendars = getAdminCalendars();

            var calendars = rogerthat.service.data.solutionCalendars.filter(function (calendar, i) {
                return $.inArray(calendar.id, adminCalendars) >= 0;
            });

            calendars.sort(function (calendar1, calendar2) {
                return smartSort(calendar1.name, calendar2.name);
            });

            $.each(calendars, function (i, calendar) {
                var input = $('<input class="custom" type="radio">');
                input.prop("name", "radio-choice-broadcast");
                input.prop("id", "radio-choice-" + calendar.id);

                input.prop('checked', i == 0);
                input.attr("calendar-id", calendar.id);
                $("#calendar-radiobuttons").append(input);

                var label = $('<label></label>');
                label.text(calendar.name);
                label.prop("for", "radio-choice-" + calendar.id);
                label.attr("calendar-id", calendar.id);
                $("#calendar-radiobuttons").append(label);
            });

            $('#broadcast').trigger('create');
        });

        $(document).on("click", ".broadcast-send", function () {
            var calendarId = $('input[name=radio-choice-broadcast]:checked').attr("calendar-id");
            var messageText = $("#broadcast-message").val();
            $("#broadcast-message").val("");

            var broadcastParams = {
                'calendarId': calendarId,
                'message': messageText
            };
            var paramsss = JSON.stringify(broadcastParams);
            rogerthat.api.call("solutions.calendar.broadcast", paramsss, "");
        });

        var eventGuestsClicked = function (status) {
            $.mobile.navigate("#guests", {transition: "slide"});
            var event = $("#detail").data("event");
            resetGuestDetails(status);

            if (guestsDict[event.id].include_details === 0) {
                var participantsParams = {
                    'eventId': event.id,
                    'includeDetails': 1
                };

                var paramsss = JSON.stringify(participantsParams);
                rogerthat.api.call("solutions.events.guests", paramsss, "" + status);
            } else {
                loadGuestsDetails(event.id, status);
            }
        };

        $(document).on("click", ".event-detail-guests-detail-going", function () {
            eventGuestsClicked(1);
        });

        $(document).on("click", ".event-detail-guests-detail-maybe", function () {
            eventGuestsClicked(2);
        });

        $(document).on("click", ".event-detail-guests-detail-not-going", function () {
            eventGuestsClicked(3);
        });

        $(document).on("pagecontainershow", function () {
            var activePage = $.mobile.pageContainer.pagecontainer("getActivePage");
            var activePageId = activePage[0].id;

            switch (activePageId) {
                case 'guests':
                    var event = $("#detail").data("event");
                    if (guestsDict[event.id].include_details == 0) {
                        $.mobile.loading('show', {
                            text: EventsTranslations.LOADING_GUESTS,
                            textVisible: true,
                            theme: 'a',
                            html: ""
                        });
                    }
                default:
                    console.log("PAGE: " + activePageId);
                    break;
            }
        });
    }

    function parseDateToEventDateTime(d) {
        var momentTrans = moment(d).format("LLLL");
        return momentTrans;
    }

    function parseDateToEventDate(d) {
        var momentTrans = moment(d).format("LL");
        return momentTrans;
    }

    function parseDateToEventDateFromTill(from, until) {
        var f = moment(from).format("LT");
        var t = moment(until).format("LT");
        return f + " - " + t;
    }

    function htmlize(value) {
        return $("<div></div>").text(value).html().replace(/\n/g, "<br>");
    }

    function loadGuests(eventId) {
        var r = guestsDict[eventId];

        $('input[name="radio-choice-guests"]').checkboxradio();

        $('input[name="radio-choice-guests"][value="1"]').prop('checked', false).checkboxradio("refresh");
        $('input[name="radio-choice-guests"][value="2"]').prop('checked', false).checkboxradio("refresh");
        $('input[name="radio-choice-guests"][value="3"]').prop('checked', false).checkboxradio("refresh");
        if (r.your_status) {
            $('input[name="radio-choice-guests"][value="' + r.your_status + '"]').prop('checked', true).checkboxradio("refresh");
            if(r.your_status == 1) {
                $('#event-detail-calendar').show();
            } else {
                $('#event-detail-calendar').hide();
            }
        } else {
            $('#event-detail-calendar').hide();
        }
        $("#event-detail-guests-count-going").text(r.guests_count_going);
        $("#event-detail-guests-count-maybe").text(r.guests_count_maybe);
        $("#event-detail-guests-count-not-going").text(r.guests_count_not_going);

        $("#detail .event-detail-guests-loading").hide();
        $("#detail .event-detail-guests").show();

        $(".event-detail-guests .ui-controlgroup-controls").css("width", "100%");
        $(".event-detail-guests .ui-radio.ui-mini").css("width", "33%").css("text-align", "center");
    }

    function resetGuestDetails(status) {
        $("#guests-tabs-going ul").empty();
        $("#guests-tabs-maybe ul").empty();
        $("#guests-tabs-not-going ul").empty();

        if (status == 1) {
            $('#guests-tab-going').addClass('ui-btn-active');
            $('#guests-tab-maybe').removeClass('ui-btn-active');
            $('#guests-tab-not-going').removeClass('ui-btn-active');
        } else if (status == 2) {
            $('#guests-tab-going').removeClass('ui-btn-active');
            $('#guests-tab-maybe').addClass('ui-btn-active');
            $('#guests-tab-not-going').removeClass('ui-btn-active');
        } else if (status == 3) {
            $('#guests-tab-going').removeClass('ui-btn-active');
            $('#guests-tab-maybe').removeClass('ui-btn-active');
            $('#guests-tab-not-going').addClass('ui-btn-active');
        }
    }

    function loadGuestsDetails(eventId, status) {
        $.mobile.loading('hide');
        var r = guestsDict[eventId];

        var listGoing = $("#guests-tabs-going ul");
        var listMaybe = $("#guests-tabs-maybe ul");
        var listNotGoing = $("#guests-tabs-not-going ul");

        $.each(r.guests, function (i, guest) {
            var guestItem = createGuestDetailListItem(guest);
            if (guest.status == 1) {
                listGoing.append(guestItem);
            } else if (guest.status == 2) {
                listMaybe.append(guestItem);
            } else if (guest.status == 3) {
                listNotGoing.append(guestItem);
            }
        });
        if (status == 1) {
            $("#guests-tabs").tabs("option", "active", 0);
        } else if (status == 2) {
            $("#guests-tabs").tabs("option", "active", 1);
        } else if (status == 3) {
            $("#guests-tabs").tabs("option", "active", 2);
        }
    }

    function loadEvents() {
        if (rogerthat.service.data.solutionCalendars === undefined)
            return;
        
        if (rogerthat.user.data.calendar.disabled === undefined) {
        	rogerthat.user.data.calendar.disabled = [];
        }

        if (rogerthat.service.data.solutionCalendars.length > 1) {
            $("#events-footer").show();
        } else {
            $("#events-footer").hide();
        }

        var now = (new Date().getTime()) / 1000;
        var checkdate = now - DAY;
        events = rogerthat.service.data.solutionEvents.filter(function (event, i) {
            if ($.inArray(event.id, removedEvents) >= 0) {
                return false;
            }

            var isCalendarDisabled = $.inArray(event.calendar_id, rogerthat.user.data.calendar.disabled) > -1;
            return !isCalendarDisabled;
        });

        calendarsDict = {};
        $.each(rogerthat.service.data.solutionCalendars, function (i, calendar) {
            calendarsDict[calendar.id] = calendar;
        });

        var adminCalendars = getAdminCalendars();
        if (adminCalendars.length === 0) {
            $("#broadcast-to-calendar").hide();
        } else {
            $("#broadcast-to-calendar").show();
        }

        var eventsListview = $("#events-listview");
        eventsListview.empty();
        if (events.length === 0) {
            $("#events-empty").show();
            return;
        }
        $("#events-empty").hide();

        var colorSchemeTag = $("meta[property='rt:style:color-scheme']")[0];
        var colorscheme = "light";
        if (colorSchemeTag !== undefined) {
            colorscheme = colorSchemeTag.content;
        }
        console.log("Colorscheme: " + colorscheme);

        var eventsPerDay = {};
        var days = [];
        eventsDict = {};
        $.each(events, function (i, event) {
            var upcomingEvents = getUpcomingStartAndEndDates(event, now, true, true);
            for(var i=0; i < upcomingEvents.length; i++) {
                var eventDate = toDateObject(upcomingEvents[i].start);
                var eventDateEnd = toDateObject(upcomingEvents[i].end);
                var dayDate = Date.parse(eventDate.toDateString());
                if (!eventsPerDay[dayDate]) {
                    eventsPerDay[dayDate] = [];
                }

                var eventCopy = Object.assign({}, event);
                eventCopy.start_date = eventDate;
                eventCopy.end_date = eventDateEnd;
                if(!eventsDict[eventCopy.id]) {
                    eventsDict[eventCopy.id] = {};
                }
                eventsDict[eventCopy.id][eventDate] = eventCopy;

                eventsPerDay[dayDate].push({
                    "event":  event,
                    "date": eventDate,
                    "time": parseDateToEventDateFromTill(eventDate, eventDateEnd),
                    "upcomingEvents": upcomingEvents
                });
            }
        });

        var sortedEvents = new Map();
        Object.keys(eventsPerDay).sort().map(function(date) {
            sortedEvents[date] = eventsPerDay[date];
        });

        $.each(sortedEvents, function(dayDate, events) {
            days.push({
                "date": parseDateToEventDate(new Date(parseInt(dayDate))),
                "events": events
            });
        });

        var html = $.tmpl(eventsTemplate, {
            days: days
        });
        eventsListview.append(html);
    }

    function onReceivedApiResult(method, result, error, tag) {
        console.log("onReceivedApiResult");
        console.log("method: " + method);
        console.log("result: " + result);
        console.log("error: " + error);

        if (method == "solutions.events.guests") {
            if (result) {
                var r = JSON.parse(result);
                guestsDict[r.event_id] = r;
                var event = $("#detail").data("event");
                if (r.include_details == 0) {
                    if (event && event.id == r.event_id) {
                        loadGuests(r.event_id);
                    }
                } else {
                    r.guests.sort(function (guest1, guest2) {
                        return smartSort(guest1.name, guest2.name);
                    });
                    if (event && event.id == r.event_id) {
                        loadGuestsDetails(r.event_id, parseInt(tag));
                    }
                }
            }
        }
    }
})();

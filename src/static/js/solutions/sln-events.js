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

$(function() {
    var GOOGLE_CALENDAR_CLIENT_ID = '17301441312-m3igq429ouf8rnch73ennqu2gqqbkg7d.apps.googleusercontent.com';
    var GOOGLE_CALENDAR_SCOPES = [ "https://www.googleapis.com/auth/calendar.readonly", "email" ];
    var DEBUG = window.location.hostname.match(/^10\.|^192\.168|^localhost|^rt.dev/) ? true : false;

    var CALENDAR_ADMIN_TEMPLATE = '{{each admins}}'
            + ' <li>${$value.label} <a user_key="${$value.key}" href="#" action="delete_calendar_admin">'
            + CommonTranslations.DELETE + '</a></li>' + '{{/each}}';

    var ADD_CALENDAR_ADMIN_TEMPLATE = '<div class="add-calendar-admin-modal modal hide fade" tabindex="-1" role="dialog" aria-labelledby="myModalLabel" aria-hidden="true">'
            + '    <div class="modal-header">'
            + '        <button type="button" class="close" data-dismiss="modal" aria-hidden="true">&times;</button>'
            + '        <h3 id="myModalLabel">${header}</h3>'
            + '    </div>'
            + '    <div class="modal-body" style="overflow-y: visible;">'
            + '        <input id="calendar_admin" type="text" style="width: 514px" placeholder="${placeholder}" value="${value}" />'
            + '    </div>'
            + '    <div class="modal-footer">'
            + '        <button action="cancel" class="btn" data-dismiss="modal" aria-hidden="true">${cancelBtn}</button>'
            + '        <button action="submit" class="btn btn-primary">${submitBtn}</button>' //
            + '    </div>' //
            + '</div>';

    var TMPL_SET_CALENDAR_BROADCAST_ENABLED = '<div class="btn-group">'
            + '      <button class="btn btn-success" id="calendarBroadcastEnabled">'
            + CommonTranslations.BROADCAST_ENABLED + '</button>'
            + '      <button class="btn" id="calendarBroadcastDisabled">&nbsp;</button>' + '</div>';

    var DEFAULT_START_EPOCH = 20 * 3600;
    var DEFAULT_UNTIL_EPOCH = 4 * 3600;

    var currentCalendarId = null;
    var currentSettingsCalendarId = null;
    var currentSettingsCalendarModal = null;
    var currentGoogleAuthenticateWindow = null;
    var calendarsIds = null;
    var calendarsMap = null;
    var calendarsArray = null;

    var to_epoch = function(textField) {
        return Math.floor(textField.data('datepicker').date.valueOf() / 1000);
    };

    var eventStartChanged = function(e) {
        var div = $(this).parent().parent();
        var dateKey = div.attr("date_key");
        var d = div.data("date");
        d.start = e.time.hours * 3600 + e.time.minutes * 60;
        div.data("date", d);
    };

    var eventUntilChanged = function(e) {
        var div = $(this).parent().parent();
        var dateKey = div.attr("date_key");
        var d = div.data("date");
        d.end = e.time.hours * 3600 + e.time.minutes * 60;
        div.data("date", d);
    };

    var loadCalendars = function() {
        sln.call({
            url : "/common/calendar/load",
            type : "GET",
            success : function(data) {
                calendarsArray = data;
                calendarsMap = {};
                calendarsIds = [];

                calendarsArray.sort(function(calendar1, calendar2) {
                    return sln.smartSort(calendar1.name, calendar2.name);
                });

                $.each(data, function(i, calendar) {
                    calendar.loading = false;
                    calendarsMap[calendar.id] = calendar;
                    calendarsIds.push(calendar.id);
                });
                renderEvents();
                renderCalendarSettings();
            },
            error : sln.showAjaxError
        });
    };

    var loadUitId = function() {
        sln.call({
            url : "/common/events/uit/actor/load",
            type : "GET",
            success : function(data) {
                if (data) {
                    $('.sln-set-events-uit-actor input').val(data);
                }
            },
            error : sln.showAjaxError
        });
    };

    var putUitId = function() {
        sln.showProcessing(CommonTranslations.SAVING_DOT_DOT_DOT);
        sln.call({
            url : "/common/events/uit/actor/put",
            type : "POST",
            data : {
                data : JSON.stringify({
                    uit_id : $('.sln-set-events-uit-actor input').val()
                })
            },
            success : function(data) {
                sln.hideProcessing();
            },
            error : sln.showAjaxError
        });
    };

    var addEvent = function() {
        var calendarId = parseInt($(this).attr("calendar_id"));

        var html = $.tmpl(templates.events_add, {
            header : CommonTranslations.EVENT_ADD,
            cancelBtn : CommonTranslations.CANCEL,
            submitBtn : CommonTranslations.SAVE,
            CommonTranslations : CommonTranslations
        });

        var dates = [ {
            "key" : sln.uuid(),
            "date" : sln.today(),
            "start" : DEFAULT_START_EPOCH,
            "end" : DEFAULT_UNTIL_EPOCH
        } ];

        var dates_html = $.tmpl(templates.events_add_dates, {
            dates : dates,
            CommonTranslations : CommonTranslations
        });

        $(".dates", html).html(dates_html);
        $('div[date_key="' + dates[0].key + '"] .date', html).datepicker({
            format : sln.getLocalDateFormat()
        }).datepicker('setValue', dates[0].date);

        $('div[date_key="' + dates[0].key + '"] .eventTimeStart', html).timepicker({
            defaultTime : "20:00",
            showMeridian : false
        });

        $('div[date_key="' + dates[0].key + '"] .eventTimeEnd', html).timepicker({
            defaultTime : "04:00",
            showMeridian : false
        });

        $('div[date_key="' + dates[0].key + '"]', html).data("date", dates[0]);

        $('.eventTimeStart', html).on('changeTime.timepicker', eventStartChanged);
        $('.eventTimeEnd', html).on('changeTime.timepicker', eventUntilChanged);

        $('#existingEventPicture', html).hide();

        var modal = sln.createModal(html);

        $('button[action="date_add"]', modal).click(function() {
            addNewEventDate(html);
        });

        $('button[action="delete"]', modal).click(function() {
            var dateKey = $(this).attr("date_key");
            $('div[date_key="' + dateKey + '"]').remove();
        });

        $('button[action="submit"]', modal).click(function() {
            saveEvent(calendarId, null, modal);
        });
    };

    var addNewEventDate = function(html) {
        var d = sln.today();
        d.setDate(d.getDate() + $(".dates > div", html).length);
        var dates = [ {
            "key" : sln.uuid(),
            "date" : d,
            "start" : DEFAULT_START_EPOCH,
            "end" : DEFAULT_UNTIL_EPOCH
        } ];

        var dates_html = $.tmpl(templates.events_add_dates, {
            dates : dates,
            CommonTranslations : CommonTranslations
        });

        $('button[action="delete"]', dates_html).click(function() {
            var dateKey = $(this).attr("date_key");
            $('div[date_key="' + dateKey + '"]').remove();
        });

        $('.date', dates_html).datepicker({
            format : sln.getLocalDateFormat()
        }).datepicker('setValue', dates[0].date);

        $('.eventTimeStart', dates_html).timepicker({
            defaultTime : "20:00",
            showMeridian : false
        });

        $('.eventTimeEnd', dates_html).timepicker({
            defaultTime : "04:00",
            showMeridian : false
        });

        $('.eventTimeStart', dates_html).on('changeTime.timepicker', eventStartChanged);
        $('.eventTimeEnd', dates_html).on('changeTime.timepicker', eventUntilChanged);

        $(".dates", html).append(dates_html);
        $('div[date_key="' + dates[0].key + '"]', html).data("date", dates[0]);
    };

    var saveEvent = function(calendarId, id, modal) {
        sln.showProcessing(CommonTranslations.SAVING_DOT_DOT_DOT);

        var startDates = [];
        var endDates = []

        $('.dates > div', modal).each(function() {
            var d = $(this).data("date");
            var dateEpoch = to_epoch($(".eventDate", $(this)));
            var selectDate = new Date((dateEpoch + d.start) * 1000);
            startDates.push({
                year : selectDate.getFullYear(),
                month : selectDate.getMonth() + 1,
                day : selectDate.getDate(),
                hour : selectDate.getHours(),
                minute : selectDate.getMinutes()
            });
            endDates.push(d.end);
        });

        // Resize file on the client
        var picture = null;
        var new_picture = false;
        var post = function() {
            sln.call({
                url : "/common/events/put",
                type : "POST",
                data : {
                    data : JSON.stringify({
                        event : {
                            id : id,
                            calendar_id : calendarId,
                            title : $("#eventTitle").val(),
                            place : $("#eventPlace").val(),
                            organizer : $("#eventOrganizer").val(),
                            description : $("#eventDescription").val(),
                            external_link : $("#eventUrl").val(),
                            start_dates : startDates,
                            end_dates : endDates,
                            picture : picture,
                            new_picture : new_picture
                        }
                    })
                },
                success : function(data) {
                    sln.hideProcessing();
                    if (!data.success) {
                        sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                        return;
                    }
                    loadCalendars();
                    modal.modal('hide');
                },
                error : sln.showAjaxError
            });
        };

        var eventPictureElement = document.getElementById('eventPicture');
        if (eventPictureElement.files.length > 0) {
            var file = eventPictureElement.files[0];

            var canvas = document.createElement("canvas");
            var ctx = canvas.getContext("2d");
            var reader = new FileReader();
            reader.onload = function(e) {
                var img = new Image();
                img.onload = function() {
                    var MAX_WIDTH = 640;
                    var width = img.width;
                    var height = img.height;

                    height *= MAX_WIDTH / width;
                    width = MAX_WIDTH;

                    canvas.width = width;
                    canvas.height = height;

                    ctx.drawImage(img, 0, 0, width, height);
                    picture = canvas.toDataURL("image/png");
                    new_picture = true;
                    post();
                }
                img.src = e.target.result;
            };
            reader.readAsDataURL(file);
        } else {
            var existingPicture = $("#existingEventPicture img").attr('src');
            if (existingPicture)
                picture = existingPicture;
            post();
        }
    };

    var editEvent = function() {
        var eventId = $(this).attr("event_id");
        var event = $('button[action="editEvent"][event_id="' + eventId + '"]', html).data("event");

        var picture = $('img.eventPicture', $(this).closest('tr'));
        var html = $.tmpl(templates.events_add, {
            header : CommonTranslations.EVENT_EDIT,
            cancelBtn : CommonTranslations.CANCEL,
            submitBtn : CommonTranslations.SAVE,
            CommonTranslations : CommonTranslations
        });

        var dates = [];
        $.each(event.start_dates, function(i, sd) {
            var startDate = new Date(sd.year, sd.month - 1, sd.day, sd.hour, sd.minute);
            var startDateOnly = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate());
            dates.push({
                "key" : sln.uuid(),
                "date" : startDateOnly,
                "start" : parseInt(startDate.getHours() * 3600 + startDate.getMinutes() * 60),
                "end" : event.end_dates[i]
            })
        });

        var dates_html = $.tmpl(templates.events_add_dates, {
            dates : dates,
            CommonTranslations : CommonTranslations
        });

        $(".dates", html).html(dates_html);

        if (picture.length > 0) {
            $("#existingEventPicture img", html).attr('src', picture.attr('src'));
            $("#existingEventPicture button", html).click(function() {
                $("#existingEventPicture img", html).attr('src', '');
                $("#existingEventPicture", html).hide();
            });
            $('#eventPicture', html).change(function() {
                $('#existingEventPicture img', html).attr('src', '');
                $('#existingEventPicture', html).hide();
            });
        } else {
            $("#existingEventPicture", html).hide();
        }

        $('.modal-body #eventTitle', html).val(event.title);
        $('.modal-body #eventPlace', html).val(event.place);
        $('.modal-body #eventOrganizer', html).val(event.organizer);
        $('.modal-body #eventDescription', html).val(event.description);
        $('.modal-body #eventUrl', html).val(event.external_link);

        $('.eventTimeStart', html).timepicker({
            defaultTime : "20:00",
            showMeridian : false
        });

        $('.eventTimeEnd', html).timepicker({
            defaultTime : "04:00",
            showMeridian : false
        });

        $.each(dates, function(i, d) {
            $('div[date_key="' + d.key + '"]', html).data("date", d);
            $('div[date_key="' + d.key + '"] .eventDate', html).datepicker({
                format : sln.getLocalDateFormat()
            }).datepicker('setValue', d.date);

            $('div[date_key="' + d.key + '"] .eventTimeStart', html).timepicker('setTime', sln.intToTime(d.start));
            $('div[date_key="' + d.key + '"] .eventTimeEnd', html).timepicker('setTime', sln.intToTime(d.end));
        });

        $('.eventTimeStart', html).on('changeTime.timepicker', eventStartChanged);
        $('.eventTimeEnd', html).on('changeTime.timepicker', eventUntilChanged);

        var modal = sln.createModal(html, function() {
            $("#itemName", modal).focus();
        });

        $('button[action="date_add"]', modal).click(function() {
            addNewEventDate(html);
        });

        $('button[action="delete"]', modal).click(function() {
            var dateKey = $(this).attr("date_key");
            $('div[date_key="' + dateKey + '"]').remove();
        });

        $('button[action="submit"]', modal).click(function() {
            saveEvent(event.calendar_id, event.id, modal);
        });
    };

    var guestsEvent = function() {
        var eventId = parseInt($(this).attr("event_id"));
        var html = $.tmpl(templates.events_guests_modal, {
            header : CommonTranslations.GUESTS,
            cancelBtn : CommonTranslations.CLOSE,
            CommonTranslations : CommonTranslations
        });
        var modal = sln.createModal(html);
        $("li a", modal).click(function() {
            $("li", modal).removeClass("active");
            var li = $(this).parent().addClass("active");
            var s = li.attr("section");
            $("section", modal).hide()
            $("section#" + s, modal).show();
        });

        sln.call({
            url : "/common/events/guests",
            type : "POST",
            data : {
                data : JSON.stringify({
                    event_id : eventId
                })
            },
            success : function(guests) {
                var guests_going = sln.filter(guests, function(guest, i) {
                    return guest.status == 1;
                });
                var guests_maybe = sln.filter(guests, function(guest, i) {
                    return guest.status == 2;
                });
                var guests_not_going = sln.filter(guests, function(guest, i) {
                    return guest.status == 3;
                });

                var html_guests_going = $.tmpl(templates.events_guests_table, {
                    guests : guests_going
                });
                $("#section_event_guests_going tbody", modal).html(html_guests_going);
                $("#event_guests_count_going", modal).text(guests_going.length);

                var html_guests_maybe = $.tmpl(templates.events_guests_table, {
                    guests : guests_maybe
                });
                $("#section_event_guests_maybe tbody", modal).html(html_guests_maybe);
                $("#event_guests_count_maybe", modal).text(guests_maybe.length);

                var html_guests_not_going = $.tmpl(templates.events_guests_table, {
                    guests : guests_not_going
                });
                $("#section_event_guests_not_going tbody", modal).html(html_guests_not_going);
                $("#event_guests_count_not_going", modal).text(guests_not_going.length);
            },
            error : sln.showAjaxError
        });
    };

    var deleteEvent = function() {
        var eventId = $(this).attr("event_id");
        sln.call({
            url : "/common/events/delete",
            type : "POST",
            data : {
                data : JSON.stringify({
                    event_id : parseInt(eventId)
                })
            },
            success : function(data) {
                if (!data.success) {
                    sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                    return;
                }
                loadCalendars();
            },
            error : sln.showAjaxError
        });
    };

    var getNextStartAndEndTime = function(event, now) {
        for ( var i in event.start_dates) {
            var startDate = event.start_dates[i];
            if (now < (new Date(startDate.year, startDate.month - 1, startDate.day, startDate.hour, startDate.minute)
                    .getTime() / 1000)) {
                return {
                    "start" : startDate,
                    "end" : event.end_dates[i]
                };
            }
        }
        return {
            "start" : event.start_dates[event.start_dates.length - 1],
            "end" : event.end_dates[event.end_dates.length - 1]
        };
    };

    var getUpcommingStartAndEndDates = function(event, now) {
        var upcomming = [];
        for ( var i in event.start_dates) {
            var startDate = event.start_dates[i];
            if (now < (new Date(startDate.year, startDate.month - 1, startDate.day, startDate.hour, startDate.minute)
                    .getTime() / 1000)) {
                upcomming.push({
                    "start" : startDate,
                    "end" : event.end_dates[i]
                });
            }
        }
        if (upcomming.length == 0)
            return [ {
                "start" : event.start_dates[event.start_dates.length - 1],
                "end" : event.end_dates[event.end_dates.length - 1]
            } ];
        return upcomming;
    };

    var renderEvents = function() {
        var html = $.tmpl(templates.events, {
            calendars : calendarsArray,
            user_email : service_user_email,
            CommonTranslations : CommonTranslations
        });
        $("#events #calendars").empty().append(html);

        $.each(calendarsArray, function(i, calendar) {
            renderEventsForCalendar(calendar.id);
        });

        if (currentCalendarId !== null && ($("#" + currentCalendarId).length > 0)) {
            var activeSection = "section_calendar_" + calendarsIds[0];
            $("#events #calendars li[section=" + activeSection + "]").removeClass("active");
            $("#" + activeSection).css("display", 'none');

            $("#events #calendars li[section=" + currentCalendarId + "]").addClass("active");
            $("#" + currentCalendarId).css("display", 'block');
        } else {
            var activeSection = "section_calendar_" + calendarsIds[0];
            $("#events #calendars li[section=" + activeSection + "]").addClass("active");
            $("#" + activeSection).css("display", 'block');
            currentCalendarId = activeSection;
        }

        $("#calendars .addevent").click(addEvent);
        $("#events li a").click(calendarsTabPress);
    };

    var renderEventsForCalendar = function(calendarId) {
        var calendar = calendarsMap[calendarId];
        var now = (new Date().getTime()) / 1000;
        calendar.events.sort(function(a, b) {
            var rA = getNextStartAndEndTime(a, now);
            var dA = new Date(rA.start.year, rA.start.month - 1, rA.start.day, rA.start.hour, rA.start.minute);
            var rB = getNextStartAndEndTime(b, now);
            var dB = new Date(rB.start.year, rB.start.month - 1, rB.start.day, rB.start.hour, rB.start.minute);
            return dA - dB;
        });

        $.each(calendar.events, function(i, event) {
            var upcommingEvents = getUpcommingStartAndEndDates(event, now);
            var eventDate = new Date(upcommingEvents[0].start.year, upcommingEvents[0].start.month - 1,
                    upcommingEvents[0].start.day, upcommingEvents[0].start.hour, upcommingEvents[0].start.minute);
            event.startEpoch = eventDate.getTime();
            event.end = upcommingEvents[0].end;
            if (upcommingEvents.length == 1) {
                event.date = sln.parseDateToEventDateTime(eventDate);
            } else {
                event.date = "";
                $.each(upcommingEvents, function(ui, upcomming_event) {
                    var upcommingEventDate = new Date(upcomming_event.start.year, upcomming_event.start.month - 1,
                            upcomming_event.start.day, upcomming_event.start.hour, upcomming_event.start.minute);
                    event.date += sln.parseDateToEventDateTime(upcommingEventDate) + "<br>";
                });
            }
            event.htmlDescription = sln.htmlize(event.description);
        });

        var html = $.tmpl(templates.events_events, {
            events : calendar.events,
            user_email : service_user_email,
            CommonTranslations : CommonTranslations
        });

        $("#events #calendars #section_calendar_" + calendarId + " table tbody").empty().append(html);
        $("#events #calendars #section_calendar_" + calendarId + " .load-more").toggle(calendar.has_more);

        $.each(calendar.events, function(i, event) {
            if (event.can_edit) {
                $('button[action="editEvent"][event_id="' + event.id + '"]', html).data("event", event);
            }
        });

        $('#calendars #section_calendar_' + calendarId + ' button[action="editEvent"]').click(editEvent);
        $('#calendars #section_calendar_' + calendarId + ' button[action="guestsEvent"]').click(guestsEvent);
        $('#calendars #section_calendar_' + calendarId + ' button[action="deleteEvent"]').click(deleteEvent);
    };

    var renderCalendarSettings = function() {
        var menuHtmlElement = $("#section_settings_agenda_calendars tbody");
        menuHtmlElement.empty();

        var html = $.tmpl(templates.events_settings, {
            solution : SOLUTION,
            calendars : calendarsArray,
            user_email : service_user_email,
            CommonTranslations : CommonTranslations
        });

        menuHtmlElement.append(html);
        $('#section_settings_agenda_calendars tbody button[action="editCalendar"]').click(editCalendar);
        $('#section_settings_agenda_calendars tbody button[action="adminCalendar"]').click(function() {
            renderCalendarSettingsDetail(parseInt($(this).attr("calendar_id")));
        });
        $('#section_settings_agenda_calendars tbody button[action="deleteCalendar"]').click(deleteCalendar);

        if (currentSettingsCalendarId) {
            loadCalendarAdmins();
            loadGoogleCalendarStatus();
        }
    };

    var addCalendar = function() {
        var calendarId = null;
        sln.input(function(value) {
            saveCalendar(calendarId, value, false);
        }, CommonTranslations.CREATE_NEW_CALENDAR, CommonTranslations.ADD, CommonTranslations.ENTER_DOT_DOT_DOT);
    };

    var editCalendar = function() {
        var calendarId = parseInt($(this).attr("calendar_id"));
        var calendar = calendarsMap[calendarId];
        sln.input(function(value) {
            saveCalendar(calendarId, value, calendar.broadcast_enabled);
        }, CommonTranslations.EDIT, CommonTranslations.SAVE, CommonTranslations.ENTER_DOT_DOT_DOT, calendar.name);
    };

    var loadCalendarAdmins = function() {
        var calendar = calendarsMap[currentSettingsCalendarId];
        var calendarAdmins = $("#calendar_admins", currentSettingsCalendarModal);
        var html_admins = $.tmpl(CALENDAR_ADMIN_TEMPLATE, {
            admins : calendar.admins
        });
        calendarAdmins.empty().append(html_admins);
        $('#calendar_admins a[action="delete_calendar_admin"]', currentSettingsCalendarModal).click(function() {
            var userKey = $(this).attr("user_key");
            sln.call({
                url : "/common/calendar/admin/delete",
                type : "POST",
                data : {
                    data : JSON.stringify({
                        calendar_id : currentSettingsCalendarId,
                        key : userKey
                    })
                },
                success : function(data) {
                    if (!data.success) {
                        return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                    }
                    loadCalendars();
                },
                error : sln.showAjaxError
            });
        });
    };

    var renderCalendarSettingsDetail = function(calendarId) {
        currentSettingsCalendarId = calendarId;
        var calendar = calendarsMap[calendarId];

        var html = $.tmpl(templates.events_calendar_settings, {
            header : CommonTranslations.SETTINGS,
            cancelBtn : CommonTranslations.CLOSE,
            CommonTranslations : CommonTranslations,
            calendar : calendar
        });

        $("#add_calendar_admin", html).click(function() {
            var calendarSettingsAdminSearch = {};
            var html_add_admin = $.tmpl(ADD_CALENDAR_ADMIN_TEMPLATE, {
                header : CommonTranslations.CALENDAR_ADMIN_ADD,
                cancelBtn : CommonTranslations.CANCEL,
                submitBtn : CommonTranslations.ADD,
                placeholder : CommonTranslations.ENTER_NAME_OR_EMAIL,
                value : ""
            });
            var modal_add_admin = sln.createModal(html_add_admin, function(modal) {
                $('input', modal_add_admin).focus();
            });
            $('button[action="submit"]', modal_add_admin).click(function() {
                var key = $(this).attr("user_key");
                sln.call({
                    url : "/common/calendar/admin/add",
                    type : "POST",
                    data : {
                        data : JSON.stringify({
                            calendar_id : calendarId,
                            key : key
                        })
                    },
                    success : function(data) {
                        if (!data.success) {
                            return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                        }
                        loadCalendars();
                    },
                    error : sln.showAjaxError
                });

                modal_add_admin.modal('hide');
            });

            $('button[action="submit"]', modal_add_admin).hide();
            $('#calendar_admin', html_add_admin).typeahead({
                source : function(query, process) {
                    $('button[action="submit"]', modal_add_admin).hide();
                    sln.call({
                        url : "/common/users/search",
                        type : "POST",
                        data : {
                            data : JSON.stringify({
                                name_or_email_term : query
                            })
                        },
                        success : function(data) {
                            var usersKeys = [];
                            calendarSettingsAdminSearch = {};
                            $.each(data, function(i, user) {
                                var userKey = user.email + ":" + user.app_id;
                                usersKeys.push(userKey);

                                calendarSettingsAdminSearch[userKey] = {
                                    avatar_url : user.avatar_url,
                                    label : user.name + ' (' + user.email + ')',
                                    sublabel : user.app_id
                                };
                            });
                            process(usersKeys);
                        },
                        error : sln.showAjaxError
                    });
                },
                matcher : function() {
                    return true;
                },
                highlighter : function(key) {
                    var p = calendarSettingsAdminSearch[key];

                    var typeahead_wrapper = $('<div class="typeahead_wrapper"></div>');
                    var typeahead_photo = $('<img class="typeahead_photo" src="" />').attr("src", p.avatar_url);
                    typeahead_wrapper.append(typeahead_photo);
                    var typeahead_labels = $('<div class="typeahead_labels"></div>');
                    var typeahead_primary = $('<div class="typeahead_primary"></div>').text(p.label);
                    typeahead_labels.append(typeahead_primary);
                    var typeahead_secondary = $('<div class="typeahead_secondary"></div>').text(p.sublabel);
                    typeahead_labels.append(typeahead_secondary);
                    typeahead_wrapper.append(typeahead_labels);

                    return typeahead_wrapper;
                },
                updater : function(key) {
                    var p = calendarSettingsAdminSearch[key];
                    $('button[action="submit"]', modal_add_admin).attr("user_key", key);
                    $('button[action="submit"]', modal_add_admin).show();
                    return p.label;
                }
            });
        });

        var calendarBroadcastEnabled = calendar.broadcast_enabled;

        var setCalendarBroadcastVisible = function() {
            if (calendarBroadcastEnabled) {
                $('#calendarBroadcastEnabled', html).addClass("btn-success").text(CommonTranslations.BROADCAST_ENABLED);
                $('#calendarBroadcastDisabled', html).removeClass("btn-danger").html('&nbsp;');
            } else {
                $('#calendarBroadcastEnabled', html).removeClass("btn-success").html('&nbsp;');
                $('#calendarBroadcastDisabled', html).addClass("btn-danger")
                        .text(CommonTranslations.BROADCAST_DISABLED);
            }
        };
        $(".sln-set-calendar-broadcast", html).html(TMPL_SET_CALENDAR_BROADCAST_ENABLED);

        $('#calendarBroadcastEnabled, #calendarBroadcastDisabled', html).click(function() {
            calendarBroadcastEnabled = !calendarBroadcastEnabled;
            setCalendarBroadcastVisible();
            saveCalendar(calendarId, calendar.name, calendarBroadcastEnabled);
        });

        setCalendarBroadcastVisible();
        var modal = sln.createModal(html);

        modal.on('hidden', function() {
            currentSettingsCalendarId = null;
            currentSettingsCalendarModal = null;
        });

        currentSettingsCalendarModal = modal;
        loadCalendarAdmins();

        $("#authorize-google-calendar", currentSettingsCalendarModal).click(function() {
            handleAuthClick();
        });

        $("#save-google-calendar", currentSettingsCalendarModal).click(function() {
            if ($(this).prop("disabled")) {
                return;
            }
            $(this).prop("disabled", true);
            var googleCalendars = [];
            $('#google-calendars input:checked[type="checkbox"]', currentSettingsCalendarModal).each(function() {
                var googleCalendar = $(this).data("calendar");
                googleCalendars.push({
                    key : googleCalendar.key,
                    label : googleCalendar.label
                });
            });
            sln.call({
                url : "/common/calendar/import/google/put",
                type : "POST",
                data : {
                    data : JSON.stringify({
                        calendar_id : currentSettingsCalendarId,
                        google_calendars : googleCalendars
                    })
                },
                success : function(data) {
                    if (!data.success) {
                        return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                    }
                    currentSettingsCalendarModal.modal('hide');
                    loadCalendars();
                },
                error : sln.showAjaxError
            });
        });

        $(".hideAutoImport", currentSettingsCalendarModal).click(function() {
            $("#save-google-calendar", currentSettingsCalendarModal).hide();
        });

        $(".showAutoImport", currentSettingsCalendarModal).click(function() {
            loadGoogleCalendarStatus();
        });

        $(document).on('focusin', function(e) {
            if ($(e.target).closest(".add-calendar-admin-modal").length) {
                e.stopImmediatePropagation();
            }
        });
    };

    var deleteCalendar = function() {
        var calendarId = parseInt($(this).attr("calendar_id"));
        var calendar = calendarsMap[calendarId];
        if (calendar.events.length > 0) {
            sln.alert(sln.htmlize(CommonTranslations.CALENDAR_REMOVE_FAILED_HAS_EVENTS), null,
                    CommonTranslations.REMOVE_FAILED);

        } else {
            sln.call({
                url : "/common/calendar/delete",
                type : "POST",
                data : {
                    data : JSON.stringify({
                        calendar_id : calendarId
                    })
                },
                success : function(data) {
                    if (!data.success) {
                        sln.alert(sln.htmlize(data.errormsg), null, CommonTranslations.ERROR);
                        return;
                    }
                    loadCalendars();
                },
                error : sln.showAjaxError
            });
        }

    };

    var saveCalendar = function(calendarId, calendarName, broadcast_enabled) {
        sln.call({
            url : "/common/calendar/save",
            type : "POST",
            data : {
                data : JSON.stringify({
                    calendar : {
                        id : calendarId,
                        name : calendarName,
                        events : [],
                        broadcast_enabled : broadcast_enabled
                    }
                })
            },
            success : function(data) {
                if (!data.success) {
                    sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                    return;
                }
                loadCalendars();
            },
            error : sln.showAjaxError
        });
    };

    var channelUpdates = function(data) {
        if (data.type == 'solutions.common.settings.timezoneChanged') {
            loadCalendars();
        } else if (data.type == 'solutions.common.calendar.update') {
            loadCalendars();
        } else if (data.type == 'solutions.common.calendar.google.callback') {
            if (currentSettingsCalendarId == data.calendar_id) {
                currentGoogleAuthenticateWindow.close();
                loadGoogleCalendarStatus();
            }
        }
    };

    sln.registerMsgCallback(channelUpdates);

    loadCalendars();

    if (MODULES.indexOf('city_app') === -1) {
        $('.sln-set-events-uit-actor p').html(sln.htmlize(CommonTranslations.EVENTS_UIT_ACTOR));
        $('.sln-set-events-uit-actor').show();
        loadUitId();
        sln.configureDelayedInput($('.sln-set-events-uit-actor input'), putUitId);
    }

    var calendarsTabPress = function() {
        $("#events li").removeClass("active");
        var li = $(this).parent().addClass("active");
        currentCalendarId = li.attr("section");
        $("#events section").hide()
        $("#events section#" + currentCalendarId).show();
    };

    $("#section_settings_agenda .add-calendar").click(addCalendar);

    function handleAuthClick() {
        sln.call({
            url : "/common/calendar/google/authenticate/url",
            type : "GET",
            data : {
                calendar_id : currentSettingsCalendarId
            },
            success : function(data) {
                currentGoogleAuthenticateWindow = window.open(data, "", "width=600, height=400");
            },
            error : sln.showAjaxError
        });
    };

    function loadGoogleCalendarStatus() {
        $("#google-calendars-loading", currentSettingsCalendarModal).show();
        $("#authorize-google-calendar", currentSettingsCalendarModal).hide();
        $("#save-google-calendar", currentSettingsCalendarModal).hide();
        $("#google-calendars-none", currentSettingsCalendarModal).hide();
        sln.call({
            url : "/common/calendar/google/load",
            type : "get",
            data : {
                calendar_id : currentSettingsCalendarId
            },
            success : function(data) {
                $("#google-calendars-loading", currentSettingsCalendarModal).hide();
                if (data.enabled) {
                    $("#authorize-google-calendar", currentSettingsCalendarModal).hide();
                    if (data.calendars.length > 0) {
                        $("#save-google-calendar", currentSettingsCalendarModal).show();
                        $("#google-calendars", currentSettingsCalendarModal).show();
                        data.calendars.sort(function(calendar1, calendar2) {
                            return sln.smartSort(calendar1.label, calendar2.label);
                        });
                        var table = $("#google-calendars", currentSettingsCalendarModal);
                        table.empty();

                        for (i = 0; i < data.calendars.length; i++) {
                            var googleCalendar = data.calendars[i];
                            var tr = $('<tr></tr>');
                            var td_1 = $('<td class="google_calendar"></td>');
                            td_1.text(googleCalendar.label);
                            tr.append(td_1);
                            var td_2 = $('<td style="width: 15px;"></td>');
                            var checkbox = $('<input type="checkbox">');
                            checkbox.val(googleCalendar.key);
                            checkbox.data("calendar", googleCalendar);
                            checkbox.prop('checked', googleCalendar.enabled);
                            td_2.append(checkbox);
                            tr.append(td_2);
                            table.append(tr);
                        }

                        $(".google_calendar", table).click(function(event) {
                            event.stopPropagation();
                            event.preventDefault();
                            var cb = $(this).parent().find("input");
                            cb.prop("checked", !cb.prop("checked"));
                        });
                    } else {
                        $("#google-calendars-none", currentSettingsCalendarModal).show();
                    }
                } else {
                    $("#authorize-google-calendar", currentSettingsCalendarModal).show();
                }
            }
        });
    };

    var eventsMenuItem = $('#topmenu').find('li[menu=events]');
    var calendarsOverview = $("#calendars");

    var validateLoadMore = function() {
        var id_ = calendarsOverview.find(".nav li.active").attr("section");
        if (id_ === undefined) {
            return;
        }
        var calendarId = parseInt(id_.replace("section_calendar_", ""));
        if (calendarsMap[calendarId] === undefined) {
            return;
        }
        var calendarIsOpen = eventsMenuItem.hasClass('active');

        if (calendarIsOpen && sln.isOnScreen($("#" + id_).find("table tr:last"))) {
            if (calendarsMap[calendarId].has_more && calendarsMap[calendarId].loading === false) {
                calendarsMap[calendarId].loading = true;
                sln.call({
                    url : "/common/calendar/load/more",
                    type : "get",
                    data : {
                        calendar_id : calendarId,
                        cursor : calendarsMap[calendarId].cursor
                    },
                    success : function(data) {
                        calendarsMap[calendarId].cursor = data.cursor;
                        calendarsMap[calendarId].has_more = data.has_more;
                        calendarsMap[calendarId].loading = false;
                        for (i = 0; i < data.events.length; i++) {
                            calendarsMap[calendarId].events.push(data.events[i]);
                        }
                        renderEventsForCalendar(calendarId);
                        validateLoadMore();
                    }
                });
            }
        }
    };

    $(window).scroll(function() {
        validateLoadMore();
    });
});

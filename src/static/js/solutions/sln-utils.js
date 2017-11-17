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

String.prototype.capitalize = function() {
    return this.charAt(0).toUpperCase() + this.slice(1);
};

// Some ES2015 shims
if (!String.prototype.startsWith) {
    String.prototype.startsWith = function (searchString, position) {
        position = position || 0;
        return this.substr(position, searchString.length) === searchString;
    };
}
if (!Object.values) {
    Object.values = (function (obj) {
        return Object.keys(obj).map(function (key) {
            return obj[key];
        });
    });
}
if (!String.prototype.includes) {
    String.prototype.includes = function (search, start) {
        if (typeof start !== 'number') {
            start = 0;
        }

        if (start + search.length > this.length) {
            return false;
        } else {
            return this.indexOf(search, start) !== -1;
        }
    };
}
if (!Array.prototype.includes) {
    Array.prototype.includes = function (searchElement /*, fromIndex*/) {
        'use strict';
        if (this == null) {
            throw new TypeError('Array.prototype.includes called on null or undefined');
        }

        var O = Object(this);
        var len = parseInt(O.length, 10) || 0;
        if (len === 0) {
            return false;
        }
        var n = parseInt(arguments[1], 10) || 0;
        var k;
        if (n >= 0) {
            k = n;
        } else {
            k = len + n;
            if (k < 0) {
                k = 0;
            }
        }
        var currentElement;
        while (k < len) {
            currentElement = O[k];
            if (searchElement === currentElement ||
                (searchElement !== searchElement && currentElement !== currentElement)) { // NaN !== NaN
                return true;
            }
            k++;
        }
        return false;
    };
}
var SLN_CONSTS = {
    LOG_ERROR_URL: "/unauthenticated/mobi/logging/web_error",
    PROCESSING_TIMEOUT: 400
};

var sln;

var TMPL_LOADING_SPINNER = '<svg class="circular" style="margin:0 auto; left: 0;right: 0;">'
    + '<circle class="path" cx="50" cy="50" r="20" fill="none" stroke-width="3" stroke-miterlimit="10" />'
    + '</svg>';

var TMPL_ALERT = '<div class="modal hide fade" tabindex="-1" role="dialog" aria-labelledby="myModalLabel" aria-hidden="true">'
    + '    <div class="modal-header">'
    + '        <button type="button" class="close" data-dismiss="modal" aria-hidden="true">&times;</button>'
    + '        <h3 id="myModalLabel">${header}</h3>'
    + '    </div>'
    + '    <div class="modal-body">'
    + '        <p>{{html body}}</p>'
    + '    </div>'
    + '    <div class="modal-footer">'
    + '        <button class="btn" data-dismiss="modal" aria-hidden="true">${closeBtn}</button>' //
    + '    </div>'
    + '</div>';

var TMPL_INPUTBOX = '<div class="modal hide fade" tabindex="-1" role="dialog" aria-labelledby="myModalLabel" aria-hidden="true">'
    + '    <div class="modal-header">'
    + '        <button type="button" class="close" data-dismiss="modal" aria-hidden="true">&times;</button>'
    + '        <h3 id="myModalLabel">${header}</h3>'
    + '        <h5>{{html subHeader}}</h5>'
    + '    </div>'
    + '    <div class="modal-body">'
    + '        <p class="modal-body-body"></p>'
    + '        <div class="control-group" id="input_group">'
    + '            <textarea class="modal-body-message" style="width: 514px" rows="5" {{if required}}required{{/if}} {{if placeholder}}placeholder="${placeholder}"{{/if}}></textarea>'
    + '            {{if checkboxLabel}}'
    + '            <div class="checkbox"><label><input type="checkbox" name="extra-checkbox" style="display: none;"/>${checkboxLabel}</label></div>'
    + '            {{/if}}'
    + '        </div>'
    + '    </div>'
    + '    <div class="modal-footer">'
    + '        <button action="cancel" class="btn" data-dismiss="modal" aria-hidden="true">${cancelBtn}</button>'
    + '        <button action="submit" class="btn btn-primary">${submitBtn}</button>' //
    + '        <button action="submit-2" class="btn btn-primary" style="display: none;">${submit2Btn}</button>' //
    + '    </div>'
    + '</div>';

var TMPL_INPUT = '<div class="modal hide fade" tabindex="-1" role="dialog" aria-labelledby="myModalLabel" aria-hidden="true">'
    + '    <div class="modal-header">'
    + '        <button type="button" class="close" data-dismiss="modal" aria-hidden="true">&times;</button>'
    + '        <h3 id="myModalLabel">${header}</h3>'
    + '    </div>'
    + '    <div class="modal-body">'
    + '        <input id="categoryname" type="{{if inputType}}${inputType}{{else}}text{{/if}}" style="width: 514px" placeholder="${placeholder}" value="${value}" />'
    + '    </div>'
    + '    <div class="modal-footer">'
    + '        <button action="cancel" class="btn" data-dismiss="modal" aria-hidden="true">${cancelBtn}</button>'
    + '        <button action="submit" class="btn btn-primary">${submitBtn}</button>' //
    + '    </div>'
    + '</div>';

var TMPL_CONFIRM = '<div class="modal hide fade" tabindex="-1" role="dialog" aria-labelledby="myModalLabel" aria-hidden="true">'
    + '    <div class="modal-header">'
    + '        <button type="button" class="close" data-dismiss="modal" aria-hidden="true">&times;</button>'
    + '        <h3 id="myModalLabel">${header}</h3>'
    + '    </div>'
    + '    <div class="modal-body">'
    + '        <p>{{html body}}</p>'
    + '    </div>'
    + '    <div class="modal-footer">'
    + '        {{if showRemember}}<label class="checkbox pull-left"><input id="remember_choice" type="checkbox">${remember_my_choice}</label>{{/if}}'
    + '        <button action="cancel" class="btn" data-dismiss="modal" aria-hidden="true">${cancelBtn}</button>'
    + '        <button action="submit" class="btn btn-primary">${submitBtn}</button>' //
    + '    </div>'
    + '</div>';

var TMPL_PROCESSING = '<div class="modal hide fade" tabindex="-1" role="dialog" aria-labelledby="myModalLabel" aria-hidden="true">'
    + '    <div class="modal-header">'
    + '        <h3 id="myModalLabel">${header}</h3>'
    + '    </div>'
    + '    <div class="modal-body">'
    + '        <div class="progress progress-striped active"><div class="bar" style="width: 100%;"></div></div>'
    + '    </div>'
    + '</div>';

if("1.10.0" != jQuery.fn.jquery) {
    throw Error("This monkey-patched code should be updated when using a jquery version other than 1.10.0");
}

// Modify jQuery so it automatically logs errors to the server
var origDispatchFunc = jQuery.event.dispatch;
jQuery.event.dispatch = function(event) {
    try {
        return origDispatchFunc.apply(this, arguments);
    } catch(err) {
        sln.logError("Caught exception in '" + event.type + "' handler of " + event.target, err);
        throw err;
    }
};


var supportsColorInput = (function() {
    var inputElem = document.createElement('input'), bool, docElement = document.documentElement, smile = ':)';

    inputElem.setAttribute('type', 'color');
    bool = inputElem.type !== 'text';

    // We first check to see if the type we give it sticks..
    // If the type does, we feed it a textual value, which shouldn't be valid.
    // If the value doesn't stick, we know there's input sanitization which infers a custom UI
    if(bool) {

        inputElem.value = smile;
        inputElem.style.cssText = 'position:absolute;visibility:hidden;';

        // chuck into DOM and force reflow for Opera bug in 11.00
        // github.com/Modernizr/Modernizr/issues#issue/159
        docElement.appendChild(inputElem);
        bool = inputElem.value != smile;
        docElement.removeChild(inputElem);
    }

    return bool;
})();


// jQuery no-double-tap-zoom plugin

// Triple-licensed: Public Domain, MIT and WTFPL license - share and enjoy!

(function($) {
    $.fn.nodoubletapzoom = function() {
        $(this)
            .bind(
                'touchstart',
                function preventZoom(e) {
                    var t2 = e.timeStamp, t1 = $(this).data('lastTouch') || t2, dt = t2 - t1, fingers = e.originalEvent.touches.length;
                    $(this).data('lastTouch', t2);
                    if(!dt || dt > 500 || fingers > 1)
                        return; // not double-tap

                    e.preventDefault(); // double tap - prevent the zoom
                    // also synthesize click events we just swallowed up
                    $(this).trigger('click').trigger('click');
                });
    };
})(jQuery);

var createLib = function() {
    return {
        processingTimeout: null,
        resize_header: function() {
            var navbar_height = $("div.navbar.navbar-fixed-top").height() + 5;
            $("#push-down").css('height', navbar_height + 'px');
        },
        day: 24 * 3600,
        timezoneOffset: function(utcTimestamp) {
            return 60 * new Date(utcTimestamp * 1000).getTimezoneOffset()
        },
        handleTimezone: function(utcTimestamp) {
            return utcTimestamp - sln.timezoneOffset(utcTimestamp);
        },
        nowUTC: function() {
            return Math.floor(new Date().getTime() / 1000);
        },
        today: function() {
            var now = new Date();
            return new Date(now.getFullYear(), now.getMonth(), now.getDate());
        },
        format: function(date) {
            var date_format = sln.getLocalDateFormat() + " h:m";
            return date_format.replace("yyyy", date.getFullYear()).replace("mm",
                sln.padLeft((date.getMonth() + 1), 2, '0')).replace("dd", sln.padLeft(date.getDate(), 2, '0'))
                .replace("h", sln.padLeft(date.getHours(), 2, '0')).replace("m",
                    sln.padLeft(date.getMinutes(), 2, '0'));
        },
        formatDate: function(timestamp, time, includeSeconds, showTimeWhenToday, showDay) {
            if(includeSeconds == undefined)
                includeSeconds = true;
            if(showTimeWhenToday == undefined)
                showTimeWhenToday = true;
            if(showDay == undefined)
                showDay = false;
            var now = sln.nowUTC();

            if(showTimeWhenToday && sln.isSameDay(now, timestamp)) {
                return sln.intToTime(sln.handleTimezone(timestamp) % sln.day, time && includeSeconds);
            }

            var date = new Date(timestamp * 1000);
            var r = '';
            if(showDay) {
                r += WEEK_DAYS[date.getDay()] + ' ';
            }
            if(sln.isSameYear(now, timestamp)) {
                return r + MONTHS_SHORT[date.getMonth()] + ' ' + date.getDate()
                    + (time ? " " + sln.intToTime(sln.handleTimezone(timestamp) % sln.day, includeSeconds) : "");
            }
            return r + MONTHS_SHORT[date.getMonth()] + ' ' + date.getDate() + " " + date.getFullYear()
                + (time ? " " + sln.intToTime(sln.handleTimezone(timestamp) % sln.day, includeSeconds) : "");
        },
        formatUTCDate: function(timestamp, time, includeSeconds, showTimeWhenToday, showDay) {
            if(includeSeconds == undefined)
                includeSeconds = true;
            if(showTimeWhenToday == undefined)
                showTimeWhenToday = true;
            if(showDay == undefined)
                showDay = false;
            var now = sln.nowUTC();

            if(showTimeWhenToday && sln.isSameDay(now, timestamp)) {
                return sln.intToTime(timestamp % sln.day, time && includeSeconds);
            }

            var date = new Date(timestamp * 1000);
            var r = '';
            if(showDay) {
                r += WEEK_DAYS[date.getUTCDay()] + ' ';
            }
            if(sln.isSameYear(now, timestamp)) {
                return r + MONTHS_SHORT[date.getUTCMonth()] + ' ' + date.getUTCDate()
                    + (time ? " " + sln.intToTime(timestamp % sln.day, includeSeconds) : "");
            }
            return r + MONTHS_SHORT[date.getUTCMonth()] + ' ' + date.getUTCDate() + " " + date.getUTCFullYear()
                + (time ? " " + sln.intToTime(timestamp % sln.day, includeSeconds) : "");
        },
        toWireFormat: function(date) {
            // used with the input with type date
            // to set the value, it must be in wire format yyyy-mm-dd
            if (typeof date === 'number') {
                date = new Date(date * 1000);
            }
            dateStr = '' + date.getFullYear();
            dateStr += '-' + sln.padLeft(date.getMonth() + 1, 2, '0');
            dateStr += '-' + sln.padLeft(date.getDate(), 2, '0');
            return dateStr;
        },
        utcDate: function(timestamp) {
            var date = new Date(timestamp * 1000);
            return new Date(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), date.getUTCHours(), date.getUTCMinutes());
        },
        isSameDay: function(timestamp1, timestamp2) {
            return Math.floor(timestamp1 / sln.day) === Math.floor(timestamp2 / sln.day);
        },
        isSameYear: function(timestamp1, timestamp2) {
            return new Date(timestamp1 * 1000).getFullYear() === new Date(timestamp2 * 1000).getFullYear();
        },
        intToTime: function(timestamp, includeSeconds) {
            var stub = function(number) {
                var string = '' + number;
                if(string.length == 1)
                    return '0' + string;
                return string;
            };
            var hours = Math.floor(timestamp / 3600);
            var minutes = Math.floor((timestamp % 3600) / 60);
            if(includeSeconds) {
                var seconds = Math.floor((timestamp % 3600) % 60);
                return stub(hours) + ':' + stub(minutes) + ':' + stub(seconds);
            } else {
                return stub(hours) + ':' + stub(minutes);
            }
        },
        intToHumanTime: function(timestamp) {
            var hours = Math.floor(timestamp / 3600);
            var minutes = Math.floor((timestamp % 3600) / 60);
            var seconds = Math.floor((timestamp % 3600) % 60);
            if(hours > 0) {
                return hours + 'h ' + minutes + 'm ' + seconds + 's';
            } else if(minutes > 0) {
                return minutes + 'm ' + seconds + 's';
            } else {
                return seconds + 's';
            }
        },
        uuid: function() {
            var S4 = function() {
                return (((1 + Math.random()) * 0x10000) | 0).toString(16).substring(1);
            };
            return (S4() + S4() + "-" + S4() + "-" + S4() + "-" + S4() + "-" + S4() + S4() + S4());
        },
        capitalize: function(s) {
            return s.charAt(0).toUpperCase() + s.substring(1);
        },
        caseInsensitiveStringSort: function(a, b) {
            var lowerCaseA = a.toLowerCase();
            var lowerCaseB = b.toLowerCase();
            if(lowerCaseA < lowerCaseB)
                return -1;
            if(lowerCaseA > lowerCaseB)
                return 1;
            return 0;
        },
        smartSort: function(a, b) {
            a = a.replace(',', '');
            b = b.replace(',', '');
            var wordsA = a.split(' ');
            var wordsB = b.split(' ');
            for(var i = 0; i < Math.min(wordsA.length, wordsB.length); i++) {
                var wordA = wordsA[i];
                var wordB = wordsB[i];
                var numberA = parseFloat(wordA);
                var numberB = parseFloat(wordB);
                var aStartsWithNumber = !isNaN(numberA);
                var bStartsWithNumber = !isNaN(numberB);
                var aIsNumber = aStartsWithNumber && !isNaN(wordA) && isFinite(wordA);
                var bIsNumber = bStartsWithNumber && !isNaN(wordB) && isFinite(wordB);

                if(aStartsWithNumber && bStartsWithNumber) {
                    // wordA and wordB both start with a number
                    if(numberA == numberB) {
                        if(aIsNumber && bIsNumber)
                            continue;

                        // wordA or wordB starts with a number, but contains a non-numeric char as well
                        if(aIsNumber) {
                            return -1;
                        } else if(bIsNumber) {
                            return 1;
                        } else {
                            // Falling through to string cmp
                        }
                    } else {
                        return numberA - numberB;
                    }
                } else if(aIsNumber) {
                    // only wordA is a number
                    return -1;
                } else if(bIsNumber) {
                    // only wordB is a number
                    return 1;
                }
                // wordA and wordB are both non-numeric strings
                var cmp = sln.caseInsensitiveStringSort(wordA, wordB);
                if(cmp == 0)
                    continue;
                return cmp;
            }
            // if we reach this point, then a and b are equal until
            // Math.min(wordsA.length, wordsB.length)
            // the string with the fewest words is smaller than the other string
            return wordsA.length - wordsB.length;
        },
        filter: function(array, callback) {
            var result = [];
            for(var index in array) {
                if(callback(array[index], index)) {
                    result.push(array[index]);
                }
            }
            return result;
        },
        isNumber: function(n) {
            return !isNaN(n) && !isNaN(parseFloat(n)) && isFinite(n);
        },
        htmlize: function(value) {
            return $("<div></div>").text(value).html().replace(/\n/g, "<br>");
        },
        createModal: function(html, onShown, options) {
            var defaultOptions = {
                backdrop: true,
                keyboard: true,
                show: false
            };
            if(options) {
                $.each(defaultOptions, function(k, v) {
                    if(options[k] === undefined) {
                        options[k] = v;
                    }
                });
            } else {
                options = defaultOptions;
            }

            var modal = $(html).modal(options).on('hidden', function() {
                modal.remove(); // remove from DOM
            });

            if(onShown) {
                modal.on('shown', function() {
                    onShown(modal);
                });
            }
            modal.modal('show');
            return modal;
        },
        getLocalDateFormat: function() {
            var date = new Date(2013, 10, 18);
            var format = date.toLocaleDateString();
            return format.replace('2013', 'yyyy').replace('11', 'mm').replace('18', 'dd');
        },
        padLeft: function(string, length, char) {
            string = string + '';
            while(string.length < length) {
                string = char + string;
            }
            return string;
        },
        _processingModal: null,
        showProcessing: function(title) {
            sln.processingTimeout = setTimeout(function() {
                if(sln._processingModal)
                    return;
                var html = $.tmpl(TMPL_PROCESSING, {
                    header: title
                });
                sln._processingModal = sln.createModal(html, null, {
                    backdrop: "static",
                    keyboard: false
                });
            }, SLN_CONSTS.PROCESSING_TIMEOUT);
        },
        hideProcessing: function() {
            clearTimeout(sln.processingTimeout);
            if(!sln._processingModal)
                return;
            sln._processingModal.modal('hide');
            sln._processingModal = null;
        },
        confirm: function(message, onConfirm, onCancel, positiveCaption, negativeCaption, title, closeCheck, showRemember) {
            var html = $.tmpl(TMPL_CONFIRM, {
                body: message,
                header: title || CommonTranslations.CONFIRM,
                cancelBtn: negativeCaption || CommonTranslations.NO,
                submitBtn: positiveCaption || CommonTranslations.YES,
                showRemember: showRemember,
                remember_my_choice: CommonTranslations.remember_my_choice,
            });
            var modal = sln.createModal(html);

            function rememberChoice() {
                return showRemember && $('#remember_choice', modal).is(':checked');
            }

            $('button[action="submit"]', modal).click(function() {
                if(onConfirm)
                    onConfirm(rememberChoice());
                if(!closeCheck || closeCheck()) {
                    modal.modal('hide');
                }
            });
            $('button[action="cancel"]', modal).click(function() {
                if(onCancel)
                    onCancel(rememberChoice());
                modal.modal('hide');
            });
        },
        inputBox : function(onSubmit, title, submitBtnCaption, subTitle, message, body, checkboxLabel, required, placeholder) {
            var html = $.tmpl(TMPL_INPUTBOX, {
                header : title || CommonTranslations.INPUT,
                subHeader : subTitle || "",
                cancelBtn : CommonTranslations.CANCEL,
                submitBtn : submitBtnCaption || CommonTranslations.SUBMIT,
                checkboxLabel : checkboxLabel,
                required: required,
                placeholder: placeholder
            });
            $(".modal-body-message", html).val(message || "");
            $(".modal-body-body", html).html(body || "");

            var inputText, validated = false;
            var modal = sln.createModal(html, function(modal) {
                inputText = $('textarea', modal);
                inputText.focus();
                if(required) {
                    function validateInput() {
                        var control_group = $('#input_group', modal);
                        validated = sln.validate(control_group, inputText, T('required'));
                    }
                    validated = message && message.trim() !== '';
                    inputText.bind('input propertychange', validateInput);
                }
            });

            var btn = 1; // 1: message, 2: no message
            if (checkboxLabel) {
                var checkbox = $('input[name=extra-checkbox]', modal);
                checkbox.show();
                checkbox.change(function() {
                    // hide/show textbox,
                    if ($(this).prop('checked')){
                        $('.modal-body-message', modal).slideUp();
                        btn = 2;
                    }else{
                        $('.modal-body-message', modal).slideDown();
                        btn = 1;
                    }
                });
            }

            $('button[action="submit"]', modal).click(function() {
                if(required && !validated)
                    return;

                var close = onSubmit(inputText.val(), btn) !== false;
                if(close)
                    modal.modal('hide');
            });
        },
        input: function(onSubmit, title, submitBtnCaption, placeholder, initialValue, inputType) {
            var html = $.tmpl(TMPL_INPUT, {
                header: title || CommonTranslations.INPUT,
                cancelBtn: CommonTranslations.CANCEL,
                submitBtn: submitBtnCaption || CommonTranslations.SUBMIT,
                placeholder: placeholder,
                value: initialValue,
                inputType: inputType
            });
            var modal = sln.createModal(html, function(modal) {
                $('input', modal).focus().keyup(function(e) {
                    if(e.keyCode == 13) {
                        $('button[action="submit"]', modal).click();
                    }
                });
            });
            $('button[action="submit"]', modal).click(function() {
                var close = onSubmit($("input", modal).val()) !== false;
                if(close)
                    modal.modal('hide');
            });
        },
        userSearch: function(input, searchDict, userSelectedCallback, typingCallback) {
            input.typeahead({
                source : function(query, process) {
                    if(typingCallback) {
                        typingCallback(query);
                    }
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
                            searchDict = {};
                            $.each(data, function(i, user) {
                                var userKey = user.email + ":" + user.app_id;
                                usersKeys.push(userKey);

                                searchDict[userKey] = {
                                    avatar_url : user.avatar_url,
                                    label : user.name + ' (' + user.email + ')',
                                    sublabel: user.app_id
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
                    var p = searchDict[key];

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
                    var p = searchDict[key];
                    userSelectedCallback(key);
                    return p.label;
                }
            });
        },
        alert: function(message, onClose, title, timeout) {
            var html = $.tmpl(TMPL_ALERT, {
                header: title || CommonTranslations.ALERT,
                body: message,
                closeBtn: CommonTranslations.CLOSE
            });
            var modal = sln.createModal(html);
            var closed = false;
            var close = function() {
                if(!closed) {
                    closed = true;
                    onClose();
                }
            };
            if(onClose) {
                modal.on('hidden', close);
            }
            if(timeout) {
                window.setTimeout(function() {
                    if(!closed)
                        modal.modal('hide');
                }, timeout);
            }
        },
        showAjaxError: function(XMLHttpRequest, textStatus, errorThrown) {
            sln.hideProcessing();
            sln.alert(CommonTranslations.AJAX_ERROR_MESSAGE);
        },
        logError: function(description, err) {
            var stack_trace = '';
            try {
                stack_trace = (err && err instanceof Error) ? err + '\n' + printStackTrace({
                    guess: true,
                    e: err
                }).join('\n') : err;
            } catch(err) {
                stack_trace = 'Failed to print stack trace! \nOriginal error: ' + description;
            }
            console.log(description + (stack_trace ? ('\n' + stack_trace) : ''));
            $.ajax({
                hideProcessing: true,
                url: SLN_CONSTS.LOG_ERROR_URL,
                contentType: "application/json; charset=utf-8",
                type: "POST",
                data: JSON.stringify({
                    description: description,
                    errorMessage: stack_trace,
                    timestamp: sln.nowUTC(),
                    user_agent: navigator.userAgent
                }),
                success: function(data, textStatus, XMLHttpRequest) {
                },
                error: function(XMLHttpRequest, textStatus, errorThrown) {
                }
            });
        },
        _message_callbacks: [],
        registerMsgCallback: function(f) {
            sln._message_callbacks.push(f);
        },
        unregisterMsgCallback: function(f) {
            var i = sln._message_callbacks.indexOf(f);
            if(i > -1) {
                sln._message_callbacks.splice(i, 1);
            }
        },
        broadcast: function(data) {
            $.each(sln._message_callbacks, function(i, callback) {
                try {
                    callback(data);
                } catch(err) {
                    sln.logError('Caught exception in sln.broadcast', err);
                    sln.showAjaxError(null, null, err);
                }
            });
        },
        _on_message: function(msg) {
            console.log("--------- channel ---------\n", msg.data);
            var process = function(raw_data) {
                var data = JSON.parse(raw_data);
                if($.isArray(data)) {
                    $.each(data, function(i, d) {
                        sln.broadcast(d);
                    });
                } else {
                    sln.broadcast(data);
                }
            };
            process(msg.data);
        },
        runChannel: function(token) {
            var onOpen = function() {
                sln.broadcast({
                    type: "rogerthat.system.channel_connected"
                });
            };
            var onClose = function() {
                sln.alert(CommonTranslations.CHANNEL_DISCONNECTED_RELOAD_BROWSER, function() {
                    window.location.reload();
                }, CommonTranslations.WARNING);
            };

            var channel = new FirebaseChannel(firebaseConfig,
                                              serviceIdentity,
                                              token || firebaseToken,
                                              'channels',
                                              [userChannelId, sessionChannelId],
                                              onOpen,
                                              sln._on_message,
                                              onClose);
            channel.connect();
        },
        map: function(array, callback) {
            var result = [];
            for(var index in array) {
                result.push(callback(array[index]));
            }
            return result;
        },
        validate: function(controlGroup, field, errorMessage, valfunc) {
            function ft() {
                var value = field.val().trim();
                field.unbind("focusout").val(field.val());
                controlGroup.find('.help-inline').remove();
                var originalPlaceholder = field.attr('placeholder');
                if(valfunc ? !valfunc(value) : (!value)) {
                    controlGroup.addClass("error").append('<span class="help-inline">' + errorMessage + '</span>');
                    field.attr('placeholder', errorMessage);
                    field.focusout(ft);
                    return false;
                } else {
                    controlGroup.removeClass("error");
                    field.attr("placeholder", originalPlaceholder);
                    return true;
                }
            }
            return ft();
        },
        configureDelayedInput: function(input, callback, label, check_value, timeout, unbind) {
            if(timeout == undefined)
                timeout = 2000;
            if(check_value == undefined)
                check_value = true;
            if(input.size() === 0)
                return;
            var label_text = label ? label.text() : null;
            var lastKeyStroke = 0;
            var originalValue = input.val();
            var event_handler = function() {
                lastKeyStroke = new Date().getTime();
                if(label) {
                    label.text(label_text + CommonTranslations.PARSING_DOT_DOT_DOT);
                }
                window.setTimeout(function() {
                    var now = new Date().getTime();
                    var value = input.val();
                    if(label)
                        label.text(label_text);
                    if(now - lastKeyStroke >= timeout && (!check_value || value != originalValue)) {
                        lastKeyStroke = now;
                        callback(value);
                        originalValue = value;
                    }
                }, timeout);
            };
            var tagName = input.prop('tagName');
            var inputType = input.attr('type') ? input.attr('type').toLowerCase() : '';
            var editableInputTypes = ['text', 'search', 'email', 'tel', 'url', 'number'];
            if(unbind) {
                // unbind keyup, paste, change... event types
                input.unbind();
            }
            if((tagName === "INPUT" && (editableInputTypes.indexOf(inputType) !== -1)) || tagName === "TEXTAREA") {
                input.keyup(event_handler);
                input.bind('paste', event_handler);
            } else if (tagName === "SELECT" || tagName === 'INPUT' && inputType === 'number') {
                input.change(event_handler);
            } else {
                sln.alert("This input " + tagName + " " + inputType + " is not supported!");
                return;
            }
            input.data('updateVal', function(value) {
                input.val(value);
                originalValue = value;
            });
        },
        parseToEventDateTime: function(epoch) {
            return sln.parseDateToEventDateTime(new Date(epoch));
        },
        parseDateToEventDateTime: function(d) {
            return WEEK_DAYS[d.getDay()] + ", " + MONTHS[d.getMonth()] + " " + d.getDate() + ", " + d.getFullYear()
                + ", " + CommonTranslations.STARTING_AT + ": " + sln.padLeft(d.getHours(), 2, "0") + ":"
                + sln.padLeft(d.getMinutes(), 2, "0");
        },
        parseDateToDateTime: function(d) {
            return WEEK_DAYS[d.getDay()] + ", " + MONTHS[d.getMonth()] + " " + d.getDate() + ", " + d.getFullYear()
                + " " + sln.padLeft(d.getHours(), 2, "0") + ":" + sln.padLeft(d.getMinutes(), 2, "0");
        },
        _InboxCallbackListener: undefined,
        _InboxActionResults: [],
        _InboxActionListeners: {},
        _InboxActionRequests: {},
        registerInboxCallbackListener: function(listener) {
            sln._InboxCallbackListener = listener;

            var results = sln._InboxActionResults;
            if(results) {
                $.each(results, function(i, result) {
                    listener(result.chatId, result.actions);
                });
                results = [];
            }
        },
        setInboxActions: function(chatId, actions) {
            var listener = sln._InboxCallbackListener;
            if(listener)
                listener(chatId, actions);
            else {
                sln._InboxActionResults.push({
                    chatId: chatId,
                    actions: actions
                });
            }
        },
        getInboxActions: function(type, chatId) {
            var listener = sln._InboxActionListeners[type];
            if(listener)
                listener(chatId);
            else {
                var requests = sln._InboxActionRequests[type];
                if(!requests)
                    sln._InboxActionRequests[type] = [];
                sln._InboxActionRequests[type].push({
                    chatId: chatId
                });
            }
        },
        registerInboxActionListener: function(type, listener) {
            sln._InboxActionListeners[type] = listener;
            var requests = sln._InboxActionRequests[type];
            if(requests) {
                $.each(requests, function(i, request) {
                    sln.getInboxActions(type, request.chatId);
                });
                requests = [];
            }
        },
        call : function(options) {
            var method = options.type || options.method;
            if (!method)
                method = "GET";
            method = method.toUpperCase();
            if (options.data && options.data.data) {
                options.data = options.data.data;
            }
            if (method === 'POST' && options.data && typeof(options.data) !== 'string') {
                options.data = JSON.stringify(options.data);
            }
            if (options.showProcessing)
                sln.showProcessing();
            var success = options.success;
            var error = options.error;
            options.success = function(data, textStatus, XMLHttpRequest) {
                if(options.showProcessing)
                    sln.hideProcessing();
                try {
                    if(success)
                        success(data, textStatus, XMLHttpRequest);
                } catch(err) {
                    sln.logError('Caught exception in success handler of ' + options.url, err);
                }
            }, options.error = function(XMLHttpRequest, textStatus, errorThrown) {
                if(options.showProcessing)
                    sln.hideProcessing();
                if(error) {
                    try {
                        error(XMLHttpRequest, textStatus, errorThrown);
                    } catch(err) {
                        sln.logError('Caught exception in error handler of ' + options.url, err);
                    }
                } else {
                    sln.showAjaxError(XMLHttpRequest, textStatus, errorThrown);
                }
            };
            if (!options.contentType) {
                options.contentType = "application/json; charset=utf-8";
            }
            return $.ajax(options);
        },
        fixColorPicker: function(colorInput, colorPickerInput, callback) {
            if(!supportsColorInput) {
                var colorToSet = colorInput.val();
                if(!colorInput.parent().hasClass('colorpicker-element')) {
                    colorPickerInput.hide();
                    var newColorPicker = colorInput.clone();
                    var newElem = $('<div/>').addClass('input-append')
                        .append(newColorPicker)
                        .append($('<span class="add-on"></span>'));
                    colorInput.replaceWith(newElem);
                    newElem.colorpicker({format: 'hex'}).on('changeColor.colorpicker', callback);
                    newElem.colorpicker('setValue', colorToSet);
                } else {
                    var newElem = colorInput.parent();
                    newElem.colorpicker('setValue', colorToSet);
                }
            }
        },
        isFlagSet: function (value, flag) {
            return !!(value & flag);
        },
        formatHtml: function (s) {
            if (!s) {
                s = '';
            }
            return s.replace(/\t/g, '&nbsp;&nbsp;').replace(/\n/g, '<br />');
        },
        showBrowserNotSupported: function () {
            sln.alert(CommonTranslations.browser_does_not_support_function
                .replace('%(url)s', '<a href="http://browsehappy.com/" target="_blank">http://browsehappy.com/</a>'));
        },
        isOnScreen: function(element) {
            var curPos = element.offset();
            if (curPos === undefined) {
                return false;
            }
            var curTop = curPos.top;
            var screenHeight = $(window).scrollTop() + $(window).height();
            return (curTop < screenHeight);
        },
        readFile: function readFile(input, targetElement, type, callback) {
            if (input.files && input.files[0]) {
                var reader = new FileReader();

                reader.onload = function (e) {
                    targetElement.attr('src', reader.result);
                    callback();
                };
                if (type === 'dataURL') {
                    reader.readAsDataURL(input.files[0]);
                } else {
                    throw Error('Unknown file reader type', type);
                }
            } else {
                sln.showBrowserNotSupported();
            }
        },
        readFileData: function readFileData(input, callback) {
            if (input.files && input.files[0]) {
                var reader = new FileReader();

                reader.onload = function (e) {
                    var base64Date = reader.result.split(';base64,').pop();
                    callback(base64Date);
                };
                reader.readAsDataURL(input.files[0]);
            } else {
                sln.showBrowserNotSupported();
            }
        },
        debounce: function debounce(func, wait, immediate) {
            var timeout;
            return function () {
                var context = this, args = arguments;
                var later = function () {
                    timeout = null;
                    if (!immediate) func.apply(context, args);
                };
                var callNow = immediate && !timeout;
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
                if (callNow) func.apply(context, args);
            };
        }
    };
};

$(document).ready(function() {
    sln = createLib();
    sln.registerMsgCallback(function(data) {
        if(data.type == 'rogerthat.system.logout') {
            window.location.assign(window.location.origin + '/ourcityapp');
        } else if(data.type == 'rogerthat.system.dologout') {
            $.ajax({
                hideProcessing: true,
                url: "/logout?continue=ourcityapp",
                type: "GET",
                success: function(data, textStatus, XMLHttpRequest) {
                    window.location.reload();
                },
                error: function(XMLHttpRequest, textStatus, errorThrown) {
                    window.location.reload();
                }
            });
        }
    });

    window.onerror = function(msg, url, line, column, error) {
        var stack_trace = '';
        if(column) {
            column = ':' + column;
        }
        if(error) {
            stack_trace = '\n' + printStackTrace({
                    guess: true,
                    e: error
                }).join('\n');
        }
        var errorMsg = msg + '\n in ' + url + ' at line ' + line + column + stack_trace;
        $.ajax({
            hideProcessing: true,
            url: SLN_CONSTS.LOG_ERROR_URL,
            type: "POST",
            data: {
                data: JSON.stringify({
                    description: 'Caught exception in global scope: ' + msg,
                    errorMessage: errorMsg,
                    timestamp: sln.nowUTC(),
                    user_agent: navigator.userAgent
                })
            },
            success: function(data, textStatus, XMLHttpRequest) {
            },
            error: function(XMLHttpRequest, textStatus, errorThrown) {
            }
        });
    };

    // Monkey patch bootstrap dialogs to allow stacking modals without throwing RangeErrors all over the place
    if ($.fn.modal) {
        $.fn.modal.Constructor.prototype.enforceFocus = function () {
        };
    };
});

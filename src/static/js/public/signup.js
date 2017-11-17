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

var signupCallback;

$(function() {
    'use strict';

    var TMPL_ORG_TYPE = '<div class="radio">'
        + '<label><input type="radio" name="organization_type" value="${value}" {{if checked}}checked{{/if}}>${label}</label>'
        + '</div>';

    var formElem = $('#signup_form')[0];
    var tabs = [];
    var currentStep = 0;
    var orgTypesCache = {};

    $('form').submit(function(event){
      event.preventDefault();
    });

    init();

    function init() {
        $('#signup').click(signup);
        $('#next').click(nextStep);
        $('#back').click(previousStep);

        $('#app').change(customerSelected);
        $('select').change(validateInput);
        $('input[type!=checkbox][type!=radio]').each(function() {
            var input = this;
            sln.configureDelayedInput($(input), function() {
                validateInput(input);
            }, null, false, 1000);
        });
        var vatInput = $('#enterprise_vat');
        sln.configureDelayedInput(vatInput, function() {
            validateVat(vatInput);
        }, null, false, 3000, true);

        for(var i = 0; i <= 3; i++) {
            tabs.push($('#tab' + i));
        }
    }

    function setEditableOrganizationTypes(types) {
        $('#organization_types div[class=radio]').remove();
        $('#organization_types').show();

        var selectFirstType = true;
        $.each(types, function(type, label) {
            $('#organization_types > div[class=controls]').append(
                $.tmpl(TMPL_ORG_TYPE, {
                    value: type,
                    label: label,
                    checked: selectFirstType
                })
            );
            selectFirstType = false;
        });
    }

    function customerSelected() {
        var customerId = $('#app option:selected').attr('customer_id');
        if(customerId) {
            $('#signup_form').attr('customer', customerId);

            // get editable organization types
            if(orgTypesCache[customerId]) {
                setEditableOrganizationTypes(orgTypesCache[customerId]);
            } else {
                $('#next').attr('disabled', true);
                sln.call({
                    url: '/unauthenticated/osa/customer/org/types',
                    type: 'GET',
                    data: {
                        customer_id: parseInt(customerId)
                    },
                    success: function(data) {
                        setEditableOrganizationTypes(data);
                        orgTypesCache[customerId] = data;
                        $('#next').attr('disabled', false);
                    },
                    error: function() {
                        $('#next').attr('disabled', false);
                        sln.showAjaxError();
                    }
                });
            }
        } else {
            $('#organization_types').hide();
        }
    }

    function fillInput(inputId, value) {
        var input = $('#' + inputId);
        if (!input.val().trim()) {
            input.val(value);
        }
    }

    function copyInput(inputIdFrom, inputIdTo) {
        var value = $('#' + inputIdFrom).val();
        fillInput(inputIdTo, value);
    }

    function clearErrors(input) {
        input.next('p[class=text-error], [class=text-warning]').remove();
    }

    function validateVat(input) {
        var vat = input.val().replace(/\s/g,'');
        if(!vat) {
            // clear any prev errors/warnings
            clearErrors(input);
            return;
        }

        var country = $('#app option:selected').attr('country');
        if(isDigit(vat[0])) {
            vat = country + vat;
        }

        $('#next').attr('disabled', true);
        sln.call({
            url: '/unauthenticated/osa/company/info',
            type: 'get',
            data: {
                vat: vat,
                country: country
            },
            success: function(data) {
                var errorMessage, warningMessage;
                if(data.errormsg && !data.vat) {
                    errorMessage = SignupTranslations.VAT_INVALID;
                } else if(data.errormsg && data.vat) {
                    // vat format is valid, but it's unknown
                    warningMessage = SignupTranslations.VAT_UNKNOWN;
                } else if(data.country.toUpperCase() !== country) {
                    errorMessage = SignupTranslations.VAT_INCORRECT_COUNTRY;
                } else {
                    fillInput('enterprise_name', data.name);
                    fillInput('enterprise_address1', data.address1 + (data.address2 ? ', ' + data.address2 : ''));
                    fillInput('enterprise_zip_code', data.zip_code);
                    fillInput('enterprise_city', data.city);
                }

                if(data.vat) {
                    $('#enterprise_vat').val(data.vat);
                }

                $('#next').attr('disabled', false);
                clearErrors(input);
                if(errorMessage) {
                    $('<p class="text-error">' + errorMessage + '</p>').insertAfter(input);
                } else if(warningMessage) {
                    $('<p class="text-warning">' + warningMessage + '</p>').insertAfter(input);
                }
            },
            error: function() {
                $('#next').attr('disabled', false);
                sln.showAjaxError()
            }
        });
    }

    function gatherFromInputs(divName) {
        var result = {};

        $('#' + divName + ' input').each(function(i, el) {
            var fieldName = $(el).attr('id').replace(divName + '_', '');
            result[fieldName] = $(el).val().trim();
        });

        return result;
    }

    function getSignupDetails(recaptchaToken) {
        var args = {};

        args.city_customer_id = parseInt($('#signup_form').attr('customer'));
        args.company = gatherFromInputs('enterprise');
        args.company.organization_type = parseInt($('input[name=organization_type]:checked').val());
        args.customer = gatherFromInputs('contact');
        args.customer.language = getBrowserLanguage();
        args.recaptcha_token = recaptchaToken;

        return args;
    }

    function signup() {
        // validate first
        nextStep();
        if(formElem.checkValidity()) {
            grecaptcha.execute();
        }
    }

    signupCallback = function(recaptchaToken) {
        sln.showProcessing(CommonTranslations.SUBMITTING_DOT_DOT_DOT);
        sln.call({
            url: '/unauthenticated/osa/customer/signup',
            type: 'POST',
            data: getSignupDetails(recaptchaToken),
            success: function(result) {
                sln.hideProcessing();
                if(!result.success) {
                    var message = SignupTranslations[result.errormsg.toUpperCase()] || result.errormsg;
                    sln.alert(message, null, CommonTranslations.ERROR);
                } else {
                    var email = gatherFromInputs('contact').user_email;
                    $('#signup_note').removeClass('white-text').parent().addClass('white-box');
                    $('#signup_note').html(SignupTranslations.SIGNUP_SUCCCESS);
                    $('#signup_box').hide();
                    $('#go_back').show();
                }
            },
            error: sln.showAjaxError
        });

        grecaptcha.reset();
    };

    function getCurrentTab() {
        return  tabs[currentStep];
    }

    function isLastStep() {
        return currentStep >= tabs.length - 1;
    }

    function isFirstStep() {
        return currentStep <= 0;
    }

    function nextStep() {
        if(currentStep === 2) {
            var vatError = $('#enterprise_vat').next('p[class=text-error]');
            if(vatError.length) {
                return;
            }
        }

        if(!validateInputs(getCurrentTab()) || isLastStep()) {
            return;
        }

        if(isFirstStep()) {
            // redirect to the signup page if the user already in/have an app
            if($('input[name=already_in_app]:checked').val() === 'yes') {
                window.location = '/customers/signin';
                return;
            }
        }

        stepChanged(currentStep + 1);
    }

    function previousStep() {
        if(isFirstStep()) {
            return;
        }

        stepChanged(currentStep - 1);
    }

    function stepChanged(step) {
        getCurrentTab().hide();
        currentStep = step;
        getCurrentTab().show();
        getCurrentTab().find('input').first().focus();
        showHideButtons();

        /* refill some info from the previous one */
        if(currentStep === 2) {
            var city = $('#app option:selected').attr('city');
            fillInput('enterprise_city', city);
            fillInput('contact_city', city)
        }

        if(currentStep === 3) {
            copyInput('enterprise_user_email', 'contact_user_email');
            copyInput('enterprise_telephone', 'contact_telephone');
        }
    }

    function showHideButtons() {
        if(isLastStep()) {
            $('#signup').show();
            $('#next').hide();
        } else {
            $('#signup').hide();
            $('#next').show();
        }

        if(isFirstStep()) {
            $('#back').hide();
        } else {
            $('#back').show();
        }
    }

    $(window).keydown(function(event) {
        // if enter is pressed and is not the last step
        // then go the next step
        if(event.keyCode == 13) {
            if(!isLastStep()) {
                event.preventDefault();
                nextStep();
            } else {
                signup();
            }
        }
    });

});

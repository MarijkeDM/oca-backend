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

var loyaltyExports = [];
var loyaltyExportsCursor;
var voucherExports = [];
var voucherExportsCursor;
var HAS_LOYALTY = MODULES.indexOf('loyalty') !== -1;
var HAS_CITY_WIDE_LOTTERY = MODULES.indexOf('hidden_city_wide_lottery') !== -1;
var LOYALTY_TYPE_REVENUE_DISCOUNT = 1;
var LOYALTY_TYPE_LOTTERY = 2;
var LOYALTY_TYPE_STAMPS = 3;
var LOYALTY_TYPE_CITY_WIDE_LOTTERY = 4;
var currentLoyaltyType = -1;

$(function() {
    "use strict";
    var loyaltySlideAddModal = null;

    var loadLoyaltyScansCount = 0;
    var hasMore = false;
    var cursor = null;
    var loading = true;
    var customers = [];
    var lotteryDict = {};
    var _loyaltySettings = null;
    init();

    function init() {
        modules.loyalty = {
            requestLoyaltyDevice: requestLoyaltyDevice
        };
    }

    // Do not bother initializing all the following functions if the customer does not have a loyalty device
    if (!(HAS_LOYALTY || HAS_CITY_WIDE_LOTTERY)) {
        $('#loyalty_request_device').click(requestLoyaltyDeviceClicked);
        return;
    }

    function requestLoyaltyDevice(source, callback) {
        sln.call({
            url: '/common/loyalty/request_device',
            data: {
                source: source
            },
            success: function () {
                if (callback) {
                    callback(true);
                }
            },
            error: function () {
                if (callback) {
                    callback(false);
                }
            }
        });
    }

    function requestLoyaltyDeviceClicked() {
        var btn = $('#loyalty_request_device');
        if (btn.attr('disabled')) {
            return;
        }
        btn.attr('disabled', true);
        requestLoyaltyDevice('Loyalty tab (dashboard)', function (success) {
            if (success) {
                sln.alert(CommonTranslations.loyalty_device_requested, null, CommonTranslations.SUCCESS);
            } else {
                btn.attr('disabled', false);
            }
        });
    }

    var loadCustomerPoints = function(loyalty_type) {
        if (isLoyaltyTablet)
            return;
        loading = true;
        var url = "/common/loyalty/customer_points/load";
        var params = {loyalty_type: loyalty_type, cursor: cursor};
        if (HAS_CITY_WIDE_LOTTERY) {
            url = "/common/city_wide_lottery/customer_points/load";
            params.city_app_id = CITY_APP_ID;
        }
        sln.call({
            url : url,
            type : "GET",
            data : params,
            success : function(data) {
                _loyaltySettings = data.loyalty_settings;
                if (!cursor) {
                    customers = [];
                }
                $.each(data.customers, function(i, o) {
                    customers.push(o);
                });

                var data_ = {};
                data_.count = 0;
                data_.days_epoch = [];
                data_.days = [];

                var visits = {};
                $.each(customers, function(i, o) {
                    var userKey = o.user_details.email  + ":" + o.user_details.app_id;

                    $.each(o.visits, function(i, v) {
                        if (visits[v.timestamp_day] == undefined) {
                            visits[v.timestamp_day] = [];
                            data_.days_epoch.push(v.timestamp_day);
                        }
                        v.user_key = userKey;
                        v.user_details = o.user_details;
                        v.timestamp_day_str = sln.formatDate(v.timestamp_day, false, false, false, true);
                        v.timestamp_str = sln.intToTime(sln.handleTimezone(v.timestamp) % sln.day, false);
                        if (data.loyalty_type == LOYALTY_TYPE_REVENUE_DISCOUNT) {
                            v.discount = parseInt(v.value_number * data.loyalty_settings.x_discount /100);
                        }
                        visits[v.timestamp_day].push(v);
                        data_.count += 1;
                    });
                });

                data_.days_epoch = data_.days_epoch.sort(function(a, b) {
                    return b - a;
                });

                $.each(data_.days_epoch, function(i, day) {
                    var visits_on_day = visits[day].sort(function(a, b) {
                        return a.timestamp - b.timestamp;
                    });
                    var day_ = {};
                    day_.count = 0;
                    day_.timestamp_day_str = visits_on_day[0].timestamp_day_str;
                    day_.visits = [];
                    $.each(visits_on_day, function(i, visit) {
                        visit.text_1 = CommonTranslations.NAME_AT_TIME.replace('%(name)s', visit.user_details.name).replace('%(time)s', visit.timestamp_str);

                        day_.visits.push(visit);
                        day_.count += 1;
                    });
                    data_.days.push(day_);
                });

                var container = $("#customer_loyalty_visits");
                container.empty();

                if (data.loyalty_type == LOYALTY_TYPE_REVENUE_DISCOUNT) {
                    var html = $.tmpl(templates.loyalty_customer_visit, {
                        loyalty_type : LOYALTY_TYPE_REVENUE_DISCOUNT,
                        data : data_,
                        CommonTranslations : CommonTranslations
                    });
                    container.append(html);
                } else if (data.loyalty_type == LOYALTY_TYPE_LOTTERY || data.loyalty_type == LOYALTY_TYPE_CITY_WIDE_LOTTERY) {
                    var html = $.tmpl(templates.loyalty_customer_visit, {
                        loyalty_type : LOYALTY_TYPE_LOTTERY,
                        data : data_,
                        CommonTranslations : CommonTranslations
                    });
                    container.append(html);
                } else if (data.loyalty_type == LOYALTY_TYPE_STAMPS) {
                    var html = $.tmpl(templates.loyalty_customer_visit, {
                        loyalty_type : LOYALTY_TYPE_STAMPS,
                        data : data_,
                        CommonTranslations : CommonTranslations
                    });
                    container.append(html);
                } else {
                    console.log("Unknown loyalty type");
                    return;
                }

                $("#loyalty .loyalty_filter_show_" + data.loyalty_type).show();
                $("#loyalty .loyalty_filter_hide_" + data.loyalty_type).hide();
                cursor = data.cursor;
                hasMore = data.has_more;
                loading = false;

                validateLoadMore();
            },
            error : sln.showAjaxError
        });
    };

    var channelUpdates = function(data) {
        if (data.type == 'solutions.common.loyalty.slides.update') {
            loadLoyaltySlides();
        } else if (data.type == 'solutions.common.loyalty.settings.update') {
            loadLoyaltySettings();
        } else if (data.type == "solutions.common.loyalty.slide.post_result") {
            sln.hideProcessing();
            if (data.error != null) {
                sln.alert(data.error);
            } else {
                if (loyaltySlideAddModal != null) {
                    loyaltySlideAddModal.modal("hide");
                }
                loadLoyaltySlides();
            }
        } else if (data.type == "solutions.common.loyalty.scan.update") {
            loadLoyaltyScans();
        } else if (data.type == "solutions.common.loyalty.lottery.update") {
            loadLotteryInfo();
        } else if(data.type == "solutions.common.postal_code.update") {
            if(data.deleted) {
                removePostalCodeRow(data.code);
            } else {
                addPostalCodeRow(data.code);
            }
        } else if (data.type == "solutions.common.loyalty.points.update") {
            if (currentLoyaltyType > 0) {
                cursor = null;
                loadCustomerPoints(currentLoyaltyType);
                loadLoyaltyScans();
            }
        }
    };

    var loadLoyaltySlides = function() {
        if (isLoyaltyTablet)
            return;

        sln.call({
            url : "/common/loyalty/slides/load",
            type : "GET",
            success : function(data) {
                var slides = $("#loyalty-slides tbody");
                var html = $.tmpl(templates.loyalty_slides, {
                    slides : data,
                    CommonTranslations : CommonTranslations
                });
                slides.empty().append(html);

                $.each(data, function(i, o) {
                    $("#" + o.id).data("slide", o);
                });

                $('#loyalty-slides button[action="update"]').click(slideUpdatePressed);
                $('#loyalty-slides button[action="delete"]').click(slideDeletePressed);
            },
            error : sln.showAjaxError
        });
    };

    var loadLoyaltySettings = function() {
        if (isLoyaltyTablet)
            return;

        sln.call({
            url : "/common/loyalty/settings/load",
            type : "GET",
            success : function(data) {
                if (data) {
                    if (currentLoyaltyType > 0 && currentLoyaltyType != data.loyalty_type) {
                        cursor = null;
                        loadCustomerPoints(data.loyalty_type);
                        if (data.loyalty_type == LOYALTY_TYPE_LOTTERY || data.loyalty_type == LOYALTY_TYPE_CITY_WIDE_LOTTERY)  {
                            loadLotteryInfo();
                        }
                    }
                    if (currentLoyaltyType < 0 && data.loyalty_type == LOYALTY_TYPE_LOTTERY || data.loyalty_type == LOYALTY_TYPE_CITY_WIDE_LOTTERY) {
                        loadLotteryInfo();
                    }
                    if (currentLoyaltyType < 0) {
                        loadCustomerPoints(null);
                    }
                    currentLoyaltyType = data.loyalty_type;
                    $("#section_settings_loyalty #loyalty-type").val(data.loyalty_type);
                    $("#section_settings_loyalty .loyalty-type-1").hide();
                    $("#section_settings_loyalty .loyalty-type-2").hide();
                    $("#section_settings_loyalty .loyalty-type-3").hide();
                    $("#section_settings_loyalty #loyalty-website").val(data.loyalty_website ? data.loyalty_website : "");
                    $("#section_settings_loyalty #loyalty-website").attr("correctUrl", data.loyalty_website ? data.loyalty_website : "");


                    if (data.loyalty_type == LOYALTY_TYPE_REVENUE_DISCOUNT) {
                        $("#section_settings_loyalty #revenue-discount-visits").val(data.loyalty_settings.x_visits);
                        $("#section_settings_loyalty #revenue-discount-discount").val(data.loyalty_settings.x_discount);
                        $("#section_settings_loyalty .loyalty-type-1").show();
                        if (loadLoyaltyScansCount > 0) {
                            $(".sln-loyalty-scans").show();
                        }
                    }  else if (data.loyalty_type == LOYALTY_TYPE_CITY_WIDE_LOTTERY && HAS_LOYALTY) {
                    	$('#topmenu').find('li[menu="loyalty"]').hide();
                    } else if (data.loyalty_type == LOYALTY_TYPE_LOTTERY || data.loyalty_type == LOYALTY_TYPE_CITY_WIDE_LOTTERY) {
                        $("#section_settings_loyalty .loyalty-type-2").show();
                        $(".sln-loyalty-scans").hide();
                    } else if (data.loyalty_type == LOYALTY_TYPE_STAMPS) {
                        $("#section_settings_loyalty #stamps-count").val(data.loyalty_settings.x_stamps);
                        $("#section_settings_loyalty #stamps-type").val(data.loyalty_settings.stamps_type);
                        $("#section_settings_loyalty #stamps-winnings").val(data.loyalty_settings.stamps_winnings);
                        $("#section_settings_loyalty #stamps-auto-redeem").prop('checked', data.loyalty_settings.stamps_auto_redeem);
                        $("#section_settings_loyalty .loyalty-type-3").show();
                        if (loadLoyaltyScansCount > 0) {
                            $(".sln-loyalty-scans").show();
                        }
                    } else {
                        console.log("ERROR: Unknown loyalty type");
                        $(".sln-loyalty-scans").hide();
                    }

                    $("#section_settings_loyalty .loyalty-admin-qr a").attr("href", data.image_uri + "?download=true");
                    $("#section_settings_loyalty .loyalty-admin-qr img").attr("src", data.image_uri);

                    var loyaltyAdmins = $("#loyalty-admins tbody");
                    var html = $.tmpl(templates.loyalty_tablets, {
                        admins : data.admins,
                        names : data.names,
                        functions : data.functions,
                        CommonTranslations : CommonTranslations
                    });
                    loyaltyAdmins.empty().append(html);

                    if (data.admins.length) {
                        $("#loyalty-admins").show();
                        $('#no-loyalty-admins').hide();
                    } else {
                        $("#loyalty-admins").hide();
                        $('#no-loyalty-admins').show();
                    }

                    $('button[action="update"]', html).click(function() {
                        var tr = $(this).closest('tr');
                        var userKey = tr.attr("user_key");
                        var functions = tr.attr("functions");
                        var tabletName = tr.attr("tablet_name");
                        var html = $.tmpl(templates.loyalty_tablet_modal, {
                            CommonTranslations : CommonTranslations
                        });

                        var modal = sln.createModal(html);
                        $('#tabletModalInput', modal).val(tabletName);

                        $('.checkbox input', modal).each(function(index) {
                            var value = $(this).val();
                            $(this)[0].checked = (functions & value) == value;
                        });

                        $('button[action="submit"]', modal).click(function() {
                            var functions = 0
                            $('input:checked[type="checkbox"]', modal).each(function() {
                                functions = functions | Number($(this).val());
                            });

                            sln.call({
                                url : "/common/loyalty/settings/admin/update",
                                type : "POST",
                                data : {
                                    data : JSON.stringify({
                                        admin_app_user_email : userKey,
                                        admin_name : $('#tabletModalInput', modal).val(),
                                        admin_functions : functions
                                    })
                                },
                                success : function(data) {
                                    if (!data.success) {
                                        return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                                    }
                                    loadLoyaltySettings();
                                },
                                error : sln.showAjaxError
                            });
                            modal.modal('hide');
                        });
                    });

                    $('button[action="delete"]', html).click(function() {
                        var tr = $(this).closest('tr');
                        var userKey = tr.attr("user_key");
                        sln.confirm(CommonTranslations.DELETE_ADMIN_CONFIRMATION, function() {
                            sln.call({
                                url : "/common/loyalty/settings/admin/delete",
                                type : "POST",
                                data : {
                                    data : JSON.stringify({
                                        admin_app_user_email : userKey
                                    })
                                },
                                success : function(data) {
                                    if (!data.success) {
                                        return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                                    }
                                    loadLoyaltySettings();
                                },
                                error : sln.showAjaxError
                            });
                        }, null, null, null, CommonTranslations.DELETE);
                    });
                } else {
                    sln.alert(CommonTranslations.ERROR_OCCURED_UNKNOWN, null, CommonTranslations.ERROR);
                }
            },
            error : sln.showAjaxError
        });
    };

    var putLoyaltySettings = function() {
        var loyaltyType = parseInt($("#section_settings_loyalty #loyalty-type").val());
        var loyaltySettings = {};
        loyaltySettings["loyalty_type"] = loyaltyType;
        var errorlist = [];
        var loyalty_website = $("#section_settings_loyalty #loyalty-website").attr("correctUrl");
        $("#section_settings_loyalty #loyalty-website").val(loyalty_website);

        if (loyaltyType == LOYALTY_TYPE_REVENUE_DISCOUNT) {
            var x_visits = $("#section_settings_loyalty #revenue-discount-visits").val();
            var x_discount = $("#section_settings_loyalty #revenue-discount-discount").val();

            var x_visits_f = parseInt(x_visits);
            var x_discount_f = parseInt(x_discount);

            if (isNaN(x_visits_f)) {
                errorlist.push("<li>" + CommonTranslations.VISITS_IS_AN_INVALID_NUMBER + "</li>");
            }
            if (isNaN(x_discount_f)) {
                errorlist.push("<li>" + CommonTranslations.DISCOUNT_IS_AN_INVALID_NUMBER + "</li>");
            }
            if (errorlist.length > 0) {
                errorlist.splice(0, 0, "<ul>");
                errorlist.push("</ul>");
                sln.alert(errorlist.join(""), null, CommonTranslations.ERROR);
                return;
            }
            if (x_visits_f < 1) {
                sln.alert(CommonTranslations.VISITS_NEEDS_TO_BE_AT_LEAST_1, null, CommonTranslations.ERROR);
                return;
            }

            if (x_discount_f < 1) {
                sln.alert(CommonTranslations.DISCOUNT_NEEDS_TO_BE_BETWEEN_0_AND_100, null, CommonTranslations.ERROR);
                return;
            }

            if (x_discount_f > 100) {
                sln.alert(CommonTranslations.DISCOUNT_NEEDS_TO_BE_BETWEEN_0_AND_100, null, CommonTranslations.ERROR);
                return;
            }
            loyaltySettings["x_visits"] = x_visits_f;
            loyaltySettings["x_discount"] = x_discount_f;
        } else if (loyaltyType == LOYALTY_TYPE_LOTTERY || loyaltyType == LOYALTY_TYPE_CITY_WIDE_LOTTERY) {
        } else if (loyaltyType == LOYALTY_TYPE_STAMPS) {
            var x_stamps = $("#section_settings_loyalty #stamps-count").val();
            var stamps_type = parseInt($("#section_settings_loyalty #stamps-type").val());
            var x_stamps_f = parseInt(x_stamps);

            if (isNaN(x_stamps_f)) {
                errorlist.push("<li>" + CommonTranslations.NUMBER_OF_STAMPS_IS_AN_INVALID_NUMBER + "</li>");
            }
            if (errorlist.length > 0) {
                errorlist.splice(0, 0, "<ul>");
                errorlist.push("</ul>");
                sln.alert(errorlist.join(""), null, CommonTranslations.ERROR);
                return;
            }

            if (x_stamps_f < 1) {
                sln.alert(CommonTranslations.NUMBER_OF_STAMPS_NEEDS_TO_BE_AT_LEAST_1, null, CommonTranslations.ERROR);
                return;
            }

            loyaltySettings["x_stamps"] = x_stamps_f;
            loyaltySettings["stamps_type"] = stamps_type;
            loyaltySettings["stamps_winnings"] = $("#section_settings_loyalty #stamps-winnings").val();
            loyaltySettings["stamps_auto_redeem"] = $("#section_settings_loyalty #stamps-auto-redeem").prop('checked');
        } else {
            sln.alert(CommonTranslations.ERROR_OCCURED_UNKNOWN, null, CommonTranslations.ERROR);
            return;
        }
        sln.showProcessing(CommonTranslations.SAVING_DOT_DOT_DOT);
        sln.call({
            url : "/common/loyalty/settings/put",
            type : "POST",
            data : {
                data : JSON.stringify({
                    loyalty_type : loyaltyType,
                    loyalty_settings : loyaltySettings,
                    loyalty_website : loyalty_website
                })
            },
            success : function(data) {
                sln.hideProcessing();
                if (!data.success) {
                    return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                }
            },
            error : sln.showAjaxError
        });
    };

    var showPutSlideModal = function(slideId) {
        var slide = null;
        if (slideId != null) {
            slide = $("#" + slideId).data("slide");
        }
        var upload_url = '/common/loyalty/slide/upload';

        var html = $.tmpl(templates.loyalty_slide_add, {
            header : slide != null ? CommonTranslations.UPDATE : CommonTranslations.ADD,
            cancelBtn : CommonTranslations.CANCEL,
            submitBtn : CommonTranslations.SAVE,
            CommonTranslations : CommonTranslations
        });

        $("#slide_form", html).attr("action", upload_url);
        if (slide == null) {
            $("#slide_id", html).val("");
            $("#slide_name", html).val("");
            $("#slide_time", html).val(10);
        } else {
            $("#slide_id", html).val(slide.id);
            $("#slide_name", html).val(slide.name);
            $("#slide_time", html).val(slide.time);
        }

        loyaltySlideAddModal = sln.createModal(html);

        $('button[action="submit"]', loyaltySlideAddModal).click(function() {
            var slideFile = document.getElementById('slide_file', html);
            if (slideFile.files.length > 0 || slide != null) {
            	if (slideFile.files.length > 0) {
            		if (slideFile.files[0].size > (20 * 1024 * 1024)) {
            			sln.alert(CommonTranslations.PICTURE_SIZE_TOO_LARGE_20MB, null, CommonTranslations.ERROR);
            			return;
            		}
            	}

                sln.showProcessing(CommonTranslations.UPLOADING_TAKE_A_FEW_SECONDS);
                $("#slide_form", html).submit();
            } else {
                sln.alert(CommonTranslations.PLEASE_SELECT_A_PICTURE, null, CommonTranslations.ERROR);
            }
        });
    };

    $("#saveLoyaltySettings").click(function() {
        putLoyaltySettings();
    });

    $(".add-loyalty-slide").click(function() {
        showPutSlideModal(null);
    });

    $("#loyalty-type").change(function() {
        sln.showProcessing(CommonTranslations.LOADING_DOT_DOT_DOT);

        sln.call({
            url : "/common/loyalty/settings/load_specific",
            type : "GET",
            data : {loyalty_type: $("#loyalty-type").val()},
            success : function(data) {
                sln.hideProcessing();
                if (data) {
                	if (data.loyalty_type == LOYALTY_TYPE_CITY_WIDE_LOTTERY && HAS_LOYALTY) {
                		$('#topmenu').find('li[menu="loyalty"]').hide();
                	} else {
                    	$('#topmenu').find('li[menu="loyalty"]').show();
                	}

                    currentLoyaltyType = data.loyalty_type;
                    $("#section_settings_loyalty #loyalty-type").val(data.loyalty_type);
                    $("#section_settings_loyalty .loyalty-type-1").hide();
                    $("#section_settings_loyalty .loyalty-type-2").hide();
                    $("#section_settings_loyalty .loyalty-type-3").hide();
                    $('.sln-loyalty-badge').text('');
                    if (data.loyalty_type == LOYALTY_TYPE_REVENUE_DISCOUNT) {
                        $("#section_settings_loyalty #revenue-discount-visits").val(data.loyalty_settings.x_visits);
                        $("#section_settings_loyalty #revenue-discount-discount").val(data.loyalty_settings.x_discount);
                        $("#section_settings_loyalty .loyalty-type-1").show();
                        loadLoyaltyScans();
                    } else if (data.loyalty_type == LOYALTY_TYPE_CITY_WIDE_LOTTERY && HAS_LOYALTY) {
                    } else if (data.loyalty_type == LOYALTY_TYPE_LOTTERY || data.loyalty_type == LOYALTY_TYPE_CITY_WIDE_LOTTERY) {
                        $("#section_settings_loyalty .loyalty-type-2").show();
                        $(".sln-loyalty-scans").hide();
                        loadLotteryInfo();
                    } else if (data.loyalty_type == LOYALTY_TYPE_STAMPS) {
                        $("#section_settings_loyalty #stamps-count").val(data.loyalty_settings.x_stamps);
                        $("#section_settings_loyalty #stamps-type").val(data.loyalty_settings.stamps_type);
                        $("#section_settings_loyalty #stamps-winnings").val(data.loyalty_settings.stamps_winnings);
                        $("#section_settings_loyalty #stamps-auto-redeem").prop('checked', data.loyalty_settings.stamps_auto_redeem);
                        $("#section_settings_loyalty .loyalty-type-3").show();
                        loadLoyaltyScans();
                    } else {
                        console.log("ERROR: Unknown loyalty type");
                        $(".sln-loyalty-scans").hide();
                    }

                } else {
                    sln.alert(CommonTranslations.ERROR_OCCURED_UNKNOWN, null, CommonTranslations.ERROR);
                }
            },
            error : sln.showAjaxError
        });
        cursor = null;
        loadCustomerPoints($("#loyalty-type").val());
    });

    sln.configureDelayedInput($('#loyalty-website'), function() {
        $('#loyalty-website').removeClass("success");
        $('#loyalty-website').removeClass("error");
        $("#loyalty-website-error").hide();
        $("#loyalty-website-validating").show();

        sln.call({
            url : "/common/broadcast/validate/url",
            type : "POST",
            data : {
                data : JSON.stringify({
                    url : $('#loyalty-website').val(),
                    allow_empty : true
                })
            },
            success : function(data) {
                $("#loyalty-website-validating").hide();
                $('#loyalty-website').val(data.url);
                if (!data.success) {
                    $("#loyalty-website-error").show();
                    $("#loyalty-website-error-msg").html(sln.htmlize(data.errormsg));
                    $('#loyalty-website').addClass("error");
                    return;
                }
                $('#loyalty-website').addClass("success");
                $('#loyalty-website').attr("correctUrl", data.url);
            },
            error : sln.showAjaxError
        });
    });

    var slideUpdatePressed = function() {
        var slideId = parseInt($(this).attr("slide_id"));
        showPutSlideModal(slideId);
    };

    var slideDeletePressed = function() {
        var slideId = parseInt($(this).attr("slide_id"));
        sln.confirm(CommonTranslations.DELETE_SLIDE_CONFIRM, function() {
            sln.call({
                url : "/common/loyalty/slides/delete",
                type : "POST",
                data : {
                    data : JSON.stringify({
                        slide_id : slideId
                    })
                },
                success : function(data) {
                    if (!data.success) {
                        return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                    }
                    $('#section_settings_loyalty tr[slide_id="' + slideId + '"]').fadeOut('slow', function() {
                        $(this).remove();
                    });
                },
                error : sln.showAjaxError
            });
        }, null, null, null, CommonTranslations.DELETE);
    };

    var loadLoyaltyScans = function() {
        sln.call({
            url : "/common/loyalty/scans/load",
            type : "GET",
            success : function(data) {
                loadLoyaltyScansCount = data.length;
                if (data.length == 0) {
                    $(".sln-loyalty-scans").hide();
                    return;
                }
                if (currentLoyaltyType == LOYALTY_TYPE_REVENUE_DISCOUNT) {
                    $(".sln-loyalty-scans").show();
                    $(".sln-loyalty-scans-1").show();
                    $(".sln-loyalty-scans-3").hide();
                } else if (currentLoyaltyType == LOYALTY_TYPE_STAMPS) {
                    $(".sln-loyalty-scans").show();
                    $(".sln-loyalty-scans-1").hide();
                    $(".sln-loyalty-scans-3").show();
                } else {
                    $(".sln-loyalty-scans").hide();
                }

                var d = $(".sln-loyalty-scans tbody");
                d.empty();

                var html = $.tmpl(templates.loyalty_scans, {
                    data : data,
                    CommonTranslations : CommonTranslations
                });
                d.empty().append(html);

                $.each(data, function(i, o) {
                   var c = $('tr[key="' + o.key + '"]', d);
                   var addEnabled = false;

                    if (currentLoyaltyType == LOYALTY_TYPE_REVENUE_DISCOUNT) {
                       addEnabled = o.points.visit_count < o.loyalty_settings.x_visits;
                   } else if (currentLoyaltyType == LOYALTY_TYPE_STAMPS) {
                       addEnabled = o.points.total_spent < o.loyalty_settings.x_stamps;
                   } else {
                       $('button[action="add"]', c).attr("disabled", "disabled");
                       $('button[action="redeem"]', c).attr("disabled", "disabled");
                       return;
                   }

                    if (addEnabled) {
                       $('button[action="redeem"]', c).attr("disabled", "disabled");
                       $('button[action="add"]', c).click(function() {
                           sln.input(function(value) {
                               var value_f;
                               if (currentLoyaltyType == LOYALTY_TYPE_REVENUE_DISCOUNT) {
                                   value_f = parseFloat(value.replace(",", "."));
                               } else if (currentLoyaltyType == LOYALTY_TYPE_STAMPS) {
                                   value_f = parseInt(value);
                               }

                               var errorlist = [];
                               if (isNaN(value_f)) {
                                   if (currentLoyaltyType == LOYALTY_TYPE_REVENUE_DISCOUNT) {
                                       errorlist.push("<li>" + CommonTranslations.PRICE_IS_AN_INVALID_NUMBER + "</li>");
                                   } else if (currentLoyaltyType == LOYALTY_TYPE_STAMPS) {
                                       errorlist.push("<li>" + CommonTranslations.NUMBER_OF_STAMPS_IS_AN_INVALID_NUMBER + "</li>");
                                   }
                               }

                               if (errorlist.length > 0) {
                                   errorlist.splice(0, 0, "<ul>");
                                   errorlist.push("</ul>");
                                   sln.alert(errorlist.join(""), null, CommonTranslations.ERROR);
                                   return;
                               }
                               if (currentLoyaltyType == LOYALTY_TYPE_REVENUE_DISCOUNT) {
                                   value_f = value_f * 100;
                               }

                               sln.call({
                                   url : "/common/loyalty/scans/add",
                                   type : "POST",
                                   data : {
                                       data : JSON.stringify({
                                           key : o.key,
                                           loyalty_type : currentLoyaltyType,
                                           value : value_f
                                       })
                                   },
                                   success : function(data) {
                                       if (!data.success) {
                                           return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                                       }
                                       loadLoyaltyScans();
                                   },
                                   error : sln.showAjaxError
                               });

                           }, CommonTranslations.ADD, CommonTranslations.ADD, CommonTranslations.ENTER_DOT_DOT_DOT);
                       });
                   } else {
                       $('button[action="add"]', c).attr("disabled", "disabled");
                       $('button[action="redeem"]', c).click(function() {

                           var showRedeemConfirmation = function(value_) {
                               sln.confirm(CommonTranslations.REDEEM_CONFIRMATION, function() {
                                   sln.call({
                                       url : "/common/loyalty/scans/redeem",
                                       type : "POST",
                                       data : {
                                           data : JSON.stringify({
                                               key : o.key,
                                               loyalty_type : currentLoyaltyType,
                                               value : value_
                                           })
                                       },
                                       success : function(data) {
                                           if (!data.success) {
                                               return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                                           }
                                           loadLoyaltyScans();
                                       },
                                       error : sln.showAjaxError
                                   });
                               }, null, null, null, CommonTranslations.REDEEM);
                           };

                           var value = 1;
                           if (currentLoyaltyType == LOYALTY_TYPE_STAMPS) {
                               value = parseInt(o.points.total_spent / o.loyalty_settings.x_stamps);
                           }

                           if (value == 1) {
                               showRedeemConfirmation(value);
                           } else {
                               var html = $.tmpl(templates.loyalty_scans_redeem_stamps_modal, {
                                   CommonTranslations : CommonTranslations
                               });

                               $("#redeem-stamps-count", html).keyup(redeem_stamps_count_keyup(html, value));
                               $("#redeem-stamps-plus", html).click(redeem_stamps_plus_click(html, value));
                               $("#redeem-stamps-min", html).click(redeem_stamps_min_click(html, value));
                               redeem_stamps_visibility_update(html, value);
                               var modal = sln.createModal(html);

                               $('button[action="submit"]', modal).click(function() {
                                   var count = parseInt($("#redeem-stamps-count", html).val());
                                   modal.modal('hide');
                                   showRedeemConfirmation(count);
                               });
                           }
                       });
                   }
                });
            },
            error : sln.showAjaxError
        });
    };

    var redeem_stamps_visibility_update = function(html, max) {
        var elem = $("#redeem-stamps-count", html);
        var current = parseInt(elem.val());
        if (current >= max) {
            $("#redeem-stamps-plus", html).prop("disabled", true);
            $("#redeem-stamps-min", html).prop("disabled", false);
        } else if (current <= 1) {
            $("#redeem-stamps-min", html).prop("disabled", true);
            $("#redeem-stamps-plus", html).prop("disabled", false);
        } else {
            $("#redeem-stamps-plus", html).prop("disabled", false);
            $("#redeem-stamps-min", html).prop("disabled", false);
        }
    };

    var redeem_stamps_count_keyup = function(html, max) {
        return function(e) {
            if (/\D/g.test($(this).val())) {
                $(this).val($(this).val().replace(/\D/g, ''));
            }
            if (!$(this).val()) {
                $(this).val('1');
            } else {
                var current = parseInt($(this).val());
                if (current <= 1) {
                    $(this).val(1);
                } else if (current >= max) {
                    $(this).val(max);
                }
            }
            redeem_stamps_visibility_update(html, max);
        };
    };
    var redeem_stamps_plus_click = function(html, max) {
        return function(e) {
            var elem = $("#redeem-stamps-count", html);
            var current = parseInt(elem.val());
            if (current >= max) {
                elem.val(max);
            } else {
                elem.val(current + 1);
            }
            redeem_stamps_visibility_update(html, max);
        };
    };
    var redeem_stamps_min_click = function(html, max) {
        return function(e) {
            var elem = $("#redeem-stamps-count", html);
            var current = parseInt(elem.val());
            if (current > 1)
                elem.val(current - 1);
            redeem_stamps_visibility_update(html, max);
        };
    };

    var to_epoch = function(textField) {
        return Math.floor(textField.data('datepicker').date.valueOf() / 1000);
    };

    var loyaltyLotteryTimeChanged = function(e) {
        var div = $(this).parent().parent().parent();
        var d = div.data("date");
        d.start = e.time.hours * 3600 + e.time.minutes * 60;
        div.data("date", d);
    };

    var loadLotteryInfo = function() {
        $('.sln-loyalty-badge').text('');
        $('#loyalty .add-lottery-required').hide();
        var url = "/common/loyalty/lottery/load";
        var params = {};
        if (HAS_CITY_WIDE_LOTTERY) {
            url = "/common/city_wide_lottery/load";
            params.city_app_id = CITY_APP_ID
        }
        sln.call({
            url : url,
            type : "GET",
            data : params,
            success : function(data) {
                sln.hideProcessing();
                var pendingLotteryKey = null;
                if (data.length != 0) {
                    $('#loyalty #lottery-history').show();
                    data = data.sort(function(a, b) {
                        return a.end_timestamp - b.end_timestamp;
                    });
                    var lotteryPending = [];
                    var lotteryHistory = [];
                    $.each(data, function(i, lottery) {
                        if (!lottery.winners[0] && pendingLotteryKey == null) {
                            pendingLotteryKey = lottery.key;
                        }
                    });
                    $.each(data, function(i, lottery) {
                        lottery.end_timestamp_str = sln.formatDate(lottery.end_timestamp, true, false, false);
                        lottery.winnings_html = sln.htmlize(lottery.winnings);
                        lottery.pending_lottery = pendingLotteryKey === lottery.key ? true : false;
                        lotteryDict[lottery.key] = lottery;
                        if (lottery.claimed && lottery.redeemed) {
                            lotteryHistory.push(lottery);
                        } else {
                            lotteryPending.push(lottery);
                        }
                    });

                    $('#loyalty #lottery-history-pending').empty();
                    $('#loyalty #lottery-history').find('.nav').find('li[section="lottery-history-pending"] span').text(lotteryPending.length || '');
                    if (lotteryPending.length != 0) {
                        var html = $.tmpl(templates.loyalty_lottery_history, {
                            data : lotteryPending,
                            CommonTranslations : CommonTranslations,
                            sln : sln
                        });
                        $('#loyalty #lottery-history-pending').append(html);
                    }

                    $('#loyalty #lottery-history-history').empty();
                    $('#loyalty #lottery-history').find('.nav').find('li[section="lottery-history-history"] span').text(lotteryHistory.length || '');
                    if (lotteryHistory.length != 0) {
                        var html = $.tmpl(templates.loyalty_lottery_history, {
                            data : lotteryHistory,
                            CommonTranslations : CommonTranslations
                        });
                        $('#loyalty #lottery-history-history').append(html);
                    }
                }

                if (pendingLotteryKey == null) {
                    $('.sln-loyalty-badge').text('!');
                    $('#loyalty .add-lottery-required').show();
                }
            },
            error : sln.showAjaxError
        });
    };

    var showEditLotteryModal = function(key) {
        var html = $.tmpl(templates.loyalty_lottery_add_modal, {
            CommonTranslations : CommonTranslations
        });

        var d = {};
        if (key) {
            var lottery = lotteryDict[key];
            d.date = sln.utcDate(lottery.end_timestamp - (lottery.end_timestamp % sln.day));
            d.start = lottery.end_timestamp % sln.day;
            $('#lottery-winnings', html).val(lottery.winnings);
            $('#lottery-x-winners-val', html).val(lottery.x_winners);
        } else {
            d.date = sln.today();
            d.start = 20 * 3600;
        }

        $(html).data("date", d);

        $('#lottery-date', html).datepicker({
            format : sln.getLocalDateFormat()
        }).datepicker('setValue', d.date);

        $('#lottery-time', html).timepicker({
            defaultTime : sln.intToTime(d.start, false),
            showMeridian : false
        });

        $('#lottery-time', html).on('changeTime.timepicker', loyaltyLotteryTimeChanged);
        if (HAS_CITY_WIDE_LOTTERY) {
            $('#lottery-x-winners', html).show();

            $('#lottery-x-winners-plus', html).click(function() {
                var elem = $('#lottery-x-winners-val', html);
                elem.val(parseInt(elem.val()) + 1);
            });

            $('#lottery-x-winners-min', html).click(function() {
                var elem = $('#lottery-x-winners-val', html);
                var current = parseInt(elem.val());
                if (current > 1)
                    elem.val(current - 1);
            });
        }
        var modal = sln.createModal(html);

        $('button[action="submit"]', modal).click(function() {
            var errorlist = [];
            var winnings = $('#lottery-winnings', modal).val();

            if (!winnings) {
                errorlist.push("<li>" + CommonTranslations.PLEASE_ENTER_THE_WINNINGS + "</li>");
            }

            var d = $(html).data("date");
            var dateEpoch = to_epoch($('#lottery-date', html));
            var selectDate = new Date((dateEpoch + d.start) * 1000);

            var nowDate = new Date();

            if((Date.parse(nowDate) + (24 * 3600 * 1000)) >= Date.parse(selectDate)){
                errorlist.push("<li>" + CommonTranslations.END_DATE_24H_IN_FUTURE + "</li>");
            }

            if (errorlist.length > 0) {
                errorlist.splice(0, 0, "<ul>");
                errorlist.push("</ul>");
                sln.alert(errorlist.join(""), null, CommonTranslations.ERROR);
                return;
            }
            sln.showProcessing(CommonTranslations.LOADING_DOT_DOT_DOT);
            var url;
            var params = {
                winnings : winnings,
                date : {
                    year : selectDate.getFullYear(),
                    month : selectDate.getMonth() + 1,
                    day : selectDate.getDate(),
                    hour : selectDate.getHours(),
                    minute : selectDate.getMinutes()
                },
            };
            if (key) {
                params.key = key;
                if (HAS_CITY_WIDE_LOTTERY) {
                    url = "/common/city_wide_lottery/edit";
                    params.x_winners = parseInt($('#lottery-x-winners-val', html).val());
                } else {
                    url = "/common/loyalty/lottery/edit";
                }
            } else {
                if (HAS_CITY_WIDE_LOTTERY) {
                    url = "/common/city_wide_lottery/add";
                    params.city_app_id = CITY_APP_ID
                    params.x_winners = parseInt($('#lottery-x-winners-val', html).val());
                } else {
                    url = "/common/loyalty/lottery/add";
                }
            }

            sln.call({
                url : url,
                type : "POST",
                data : {
                    data : JSON.stringify(params)
                },
                success : function(data) {
                    if (!data.success) {
                        sln.hideProcessing();
                        return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                    }
                    loadLotteryInfo();
                },
                error : sln.showAjaxError
            });
            modal.modal('hide');
        });
    };

    $('#loyalty #loyalty_add_lottery').click(function() {
        showEditLotteryModal(null);
    });

    $(document).on("touchend click", ".lottery-edit", function(event) {
        var key = $(this).attr("key");
        showEditLotteryModal(key);
    });

    $(document).on("touchend click", ".lottery-delete", function(event) {
        var key = $(this).attr("key");
        sln.showProcessing(CommonTranslations.LOADING_DOT_DOT_DOT);
        var url = HAS_CITY_WIDE_LOTTERY ? "/common/city_wide_lottery/delete" : "/common/loyalty/lottery/delete";
        sln.call({
            url :  url,
            type : "POST",
            data : {
                data : JSON.stringify({key: key})
            },
            success : function(data) {
                sln.hideProcessing();
                if (!data.success) {
                    return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                }
                loadLotteryInfo();
            },
            error : sln.showAjaxError
        });
    });

    $(document).on("touchend click", ".lottery-winner-close", function(event) {
        var key = $(this).attr("key");
        var url = HAS_CITY_WIDE_LOTTERY ? "/common/city_wide_lottery/close" : "/common/loyalty/lottery/close";
        sln.call({
            url : url,
            type : "POST",
            data : {
                data : JSON.stringify({
                    key: key
                })
            },
            success : function(data) {
                if (!data.success) {
                    sln.hideProcessing();
                    return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                }
                loadLotteryInfo();
            },
            error : sln.showAjaxError
        });
    });

    $(document).on("touchend click", ".customer-visits-detail", function(event) {
        event.stopPropagation();
        event.preventDefault();
        var email = $(this).attr("email");
        var appId = $(this).attr("app_id");
        sln.showProcessing(CommonTranslations.LOADING_DOT_DOT_DOT);
        var modal = null;
        var html = null;
        var inEditingMode = false;
        var loadVisitsDetail = function() {
            var url = "/common/loyalty/customer_points/detail";
            var params = {loyalty_type: currentLoyaltyType, email: email, app_id: appId};
            if (HAS_CITY_WIDE_LOTTERY) {
                url = "/common/city_wide_lottery/customer_points/detail";
                params.city_app_id = CITY_APP_ID
            }
            sln.call({
                url : url,
                type : "GET",
                data : params,
                success : function(data) {
                    sln.hideProcessing();
                    data.visits = data.visits.sort(function(a, b) {
                        return a.timestamp - b.timestamp;
                    });
                    var discount = 0;
                    var valueNumber = 0;
                    var visitCount = data.visits.length;
                    $.each(data.visits, function(i, visit) {
                        visit.timestamp_str = sln.formatDate(visit.timestamp, true, true, false, true);
                        valueNumber += visit.value_number;
                        if (currentLoyaltyType == LOYALTY_TYPE_REVENUE_DISCOUNT) {
                            visit.discount = parseInt(visit.value_number * _loyaltySettings.x_discount /100);
                            discount += visit.discount;
                        }
                    });

                    if (html == null) {
                        html = $.tmpl(templates.loyalty_customer_visits_detail_modal, {
                            CommonTranslations : CommonTranslations,
                            show_abuse : HAS_LOYALTY
                        });
                    }

                    var html_content = $.tmpl(templates.loyalty_customer_visits_detail, {
                        CommonTranslations : CommonTranslations,
                        user_details : data.user_details,
                        loyalty_type : currentLoyaltyType,
                        visits : data.visits,
                        discount : discount,
                        value_number : valueNumber,
                        visit_count : visitCount
                    });

                    $('tbody', html).empty().append(html_content);

                    $('.visit-action-trash', html).click(function() {
                        var key = $(this).attr("visit_key");

                        sln.confirm(CommonTranslations.MENU_CATEGORY_ITEM_DELETE_CONFIRMATION, function() {
                            sln.call({
                                url : "/common/loyalty/visit/delete",
                                type : "POST",
                                data : {
                                    data : JSON.stringify({
                                        key : key
                                    })
                                },
                                success : function(data) {
                                    if (!data.success) {
                                        return sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                                    }
                                    loadVisitsDetail();
                                },
                                error : sln.showAjaxError
                            });
                        }, null, null, null, CommonTranslations.DELETE);
                    });


                    if (currentLoyaltyType == LOYALTY_TYPE_LOTTERY || currentLoyaltyType == LOYALTY_TYPE_CITY_WIDE_LOTTERY) {
                        var url = "/common/loyalty/lottery/chance";
                        var params = {email: email, app_id: appId}
                        if (HAS_CITY_WIDE_LOTTERY) {
                            url = "/common/city_wide_lottery/chance";
                            params.city_app_id = CITY_APP_ID
                        }
                        sln.call({
                            url : url,
                            type : "GET",
                            data : params,
                            success : function(data) {
                                $(".lottery-chance", html).html(sln.htmlize(CommonTranslations.LOTTERY_TEXT_DISCOUNT.replace("%%", "%").replace("%(count)s", data.my_visits).replace("%(chance)s", (data.chance).toFixed(2))));
                            },
                            error : sln.showAjaxError
                        });
                    }

                    if (modal == null) {
                        modal = sln.createModal(html);

                        var t = $('a[data-toggle="tooltip"]', modal).tooltip();
                        t.on('show', function(e) {
                            e.stopPropagation();
                        }).on('hide', function(e) {
                            e.stopPropagation();
                        }).on('hidden', function(e) {
                            e.stopPropagation();
                        });

                        $('button[action="abuse"]', html).click(function() {
                            inEditingMode = true;
                            updateEditingMode();
                        });

                        $('button[action="done"]', html).click(function() {
                            inEditingMode = false;
                            updateEditingMode();
                        });
                    }
                    updateEditingMode();
                },
                error : sln.showAjaxError
            });
        };

        var updateEditingMode = function() {
            if (inEditingMode) {
                $(".visit-abuse", html).show();
                $('button[action="abuse"]', html).hide();
                $('button[action="done"]', html).show();
            } else {
                $(".visit-abuse", html).hide();
                $('button[action="abuse"]', html).show();
                $('button[action="done"]', html).hide();
            }
        };

        loadVisitsDetail();
    });

    var loyaltyMenuItem = $('#topmenu').find('li[menu=loyalty]');

    var validateLoadMore = function() {
        var id_ = $("#customer_loyalty_visits").find("div:last");

        var loyaltyIsOpen = loyaltyMenuItem.hasClass('active');
        if (loyaltyIsOpen && sln.isOnScreen(id_)) {
            if(hasMore && loading == false) {
                loadCustomerPoints(currentLoyaltyType);
            }
        }
    };

    $(window).scroll(function() {
        validateLoadMore();
    });

    sln.registerMsgCallback(channelUpdates);

    $("#lottery-history").find(".nav li a").on("click", function () {
        $("#lottery-history").find(".nav li").removeClass("active");
        var li = $(this).parent().addClass("active");
        $("#lottery-history").find("section").hide();
        $("#lottery-history").find("section#" + li.attr("section")).show();
    });


    loadLoyaltySlides();
    loadLoyaltySettings();
    if (HAS_LOYALTY) {
        loadLoyaltyScans();
    }

    function addPostalCodeRow(code) {
        $('#postal_codes > tbody').append(
            '<tr><td>' + code + '</td><td><button class="remove-postal-code btn btn-warning">'
            + CommonTranslations.DELETE + '</button></td></tr>'
        );
    }

    function removePostalCodeRow(code_or_row) {
        if (typeof code_or_row === 'string') {
            $('#postal_codes td:contains(' + code_or_row + ')').parent().remove();
        } else {
            // the row itself
            code_or_row.remove();
        }
    }

    function loadPostalCodes() {
        sln.call({
            url: '/common/city/postal_codes',
            type: 'get',
            data: {
                app_id: CITY_APP_ID
            },
            success: function(codes) {
                $.each(codes, function(i, code) {
                    addPostalCodeRow(code);
                });
            }
        });
    }

    function addOrRemovePostalCode(code, remove) {
        var operation = 'add';
        if (remove) {
            operation = 'remove'
        }
        sln.showProcessing();
        sln.call({
            url: '/common/city/postal_codes/' + operation,
            type: 'post',
            data: {
                app_id: CITY_APP_ID,
                postal_code: code
            },
            success: function(result) {
                sln.hideProcessing();
                if (!result.success) {
                    sln.alert(result.errormsg, null, CommonTranslations.ERROR);
                }
                // will be added or removed by the channel update
            },
            error: sln.showAjaxError
        });
    }

    function addPostalCode() {
        sln.input(function(code) {
           addOrRemovePostalCode(code, false)
        }, CommonTranslations.postal_code, CommonTranslations.ADD);
    }

    function removePostalCode() {
        var row = $(this).parent().parent();
        var code = $('td:first-child', row).text();
        addOrRemovePostalCode(code, true)
    }

    loadPostalCodes();
    $('.add-postal-code').on('click', addPostalCode);
    // remove button will be added later
    $('body').on('click', '.remove-postal-code', removePostalCode);

});

function loadLoyaltyExportList() {
    renderLoyaltyExportList(false);
    if (!loyaltyExports.length) {
        $('#loyalty-export-list').html(TMPL_LOADING_SPINNER);
        sln.call({
            url: '/common/loyalty/export/list',
            success: function (data) {
                loyaltyExports = data.list;
                loyaltyExportsCursor = data.cursor;
                renderLoyaltyExportList(data.list.length === 10);
            },
            error: function () {
                window.location.hash = '#/loyalty';
            }
        });
    }
}

function renderLoyaltyExportList(hasMore) {
    var html = $.tmpl(templates['loyalty_export'], {
    	exports: loyaltyExports,
        t: CommonTranslations
    });
    $('#loyalty_export').show();
    $('#loyalty-export-list').html(html)
    $('#loyalty_lottery, #customer_loyalty_visits, #loyalty_export_btn').hide();
    $('#load-more-loyalty-exports').toggle(hasMore).unbind('click').click(loadMoreLoyaltyExports);
}

function loadMoreLoyaltyExports() {
    sln.call({
        url: '/common/loyalty/export/list',
        data: {
            cursor: loyaltyExportsCursor
        },
        success: function (data) {
            loyaltyExportsCursor = data.cursor;
            loyaltyExports.push.apply(loyaltyExports, data.list);
            renderLoyaltyExportList(data.list.length === 10);
        }
    });
}

function loadVoucherExportList() {
	renderVoucherExportList(false);
	if (!voucherExports.length) {
        $('#voucher-export-list').html(TMPL_LOADING_SPINNER);
        sln.call({
            url: '/common/vouchers/export/list',
            success: function (data) {
            	voucherExports = data.list;
            	voucherExportsCursor = data.cursor;
            	renderVoucherExportList(data.list.length === 10);
            },
            error: function () {
                window.location.hash = '#/loyalty';
            }
        });
    }
}

function renderVoucherExportList(hasMore) {
	if (voucherExports.length == 0) {
		$("#loyalty_export_vouchers").hide();
	} else {
		$("#loyalty_export_vouchers").show();
		var html = $.tmpl(templates['voucher_export'], {
			exports: voucherExports,
			t: CommonTranslations
		});
		$('#voucher-export-list').html(html);
		$('#load-more-voucher-exports').toggle(hasMore).unbind('click').click(loadMoreVoucherExports);
	}
}

function loadMoreVoucherExports() {
	sln.call({
        url: '/common/vouchers/export/list',
        data: {
            cursor: voucherExportsCursor
        },
        success: function (data) {
        	voucherExportsCursor = data.cursor;
        	voucherExports.push.apply(voucherExports, data.list);
        	renderVoucherExportList(data.list.length === 10);
        }
    });
}

function renderLoyaltyPage() {
    $('#loyalty_export').hide();
    if (HAS_LOYALTY || HAS_CITY_WIDE_LOTTERY) {
    	$('#loyalty_order_now').hide();
        if (HAS_LOYALTY) {
            $('#customer_loyalty_visits, #loyalty_export_btn').show();
        } else if (HAS_CITY_WIDE_LOTTERY) {
            $('#customer_loyalty_visits').show();
        }
        if (currentLoyaltyType > 0 && currentLoyaltyType == LOYALTY_TYPE_LOTTERY || currentLoyaltyType == LOYALTY_TYPE_CITY_WIDE_LOTTERY) {
            $('#loyalty_lottery').show();
        }
    }else {
        $('#loyalty_order_now').show();
    }
}

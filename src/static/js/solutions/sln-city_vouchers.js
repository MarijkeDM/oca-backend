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
    // should create a widget for the data list with auto loading on scroll?
    var voucherBackup = {
        has_more: false,
        prev_cursor: null
    };
    var qrCodeExportBackup = {};
    var exportBackup = {};

    var renderVouchers = function() {
        var html = $.tmpl(templates['city_vouchers/city_vouchers_list'], {
            vouchers : voucherBackup.vouchers,
            CommonTranslations : CommonTranslations
        });

        $("#city_vouchers #city_vouchers-search table tbody").empty().append(html);
        if (voucherBackup.vouchers.length == 0) {
            $("#city_vouchers #city_vouchers-search table tbody").hide();
        } else {
            $("#city_vouchers #city_vouchers-search table tbody").show();
        }
        $("#city_vouchers #city_vouchers-search .load-more").toggle(voucherBackup.has_more);
        $('#city_vouchers #city_vouchers-search button[action="voucherHistory"]').click(voucherHistory);
    };

    var loadSearchVouchers = function(cursor) {
        if (cursor == null) {
            voucherBackup.cursor = null;
            voucherBackup.has_more = false;
            voucherBackup.vouchers = [];
            voucherBackup.loading = true;
        }

        if(voucherBackup.cursor && voucherBackup.cursor === voucherBackup.prev_cursor) {
            return;
        } else {
            voucherBackup.prev_cursor = cursor;
        }
        var params = {
            app_id: CITY_APP_ID,
            search_string: voucherBackup.query,
            cursor: voucherBackup.cursor
        };
        sln.call({
            url : "/common/city/vouchers/search",
            type : "get",
            data : params,
            success : function(data) {
                voucherBackup.cursor = data.cursor;
                voucherBackup.has_more = data.has_more;
                voucherBackup.loading = false;
                $.each(data.vouchers, function(i, voucher) {
                    voucher.expiration_date = sln.formatDate(voucher.expiration_date, false, false, false);
                });
                voucherBackup.vouchers.push.apply(voucherBackup.vouchers, data.vouchers);
                $("#city_vouchers-search_results").show();
                renderVouchers();
                validateLoadMore();
            }
        });
    };

    var clearSearchResults = function() {
        voucherBackup.vouchers = [];
        renderVouchers();
    };

    sln.configureDelayedInput($('#city_vouchers-search_input'), function(query) {
        if (query) {
            voucherBackup.query = query;
            loadSearchVouchers(null);
        } else {
            clearSearchResults();
        }
    });

    var renderQRCodesExport = function() {
        $.each(qrCodeExportBackup.data, function(i, qrcode_export) {
            qrcode_export.date = sln.formatDate(qrcode_export.created, true, false, false);
        });

        var html = $.tmpl(templates['city_vouchers/city_vouchers_qrcode_export_list'], {
            data : qrCodeExportBackup.data,
            CommonTranslations : CommonTranslations
        });

        $("#city_vouchers #city_vouchers-qrcode_export table tbody").empty().append(html);
        if (qrCodeExportBackup.data.length == 0) {
            $("#city_vouchers #city_vouchers-qrcode_export table tbody").hide();
        } else {
            $("#city_vouchers #city_vouchers-qrcode_export table tbody").show();
        }
        $("#city_vouchers #city_vouchers-qrcode_export .load-more").toggle(qrCodeExportBackup.has_more);
    };

    var loadQRCodeExports = function(cursor) {
        if (cursor == null) {
            qrCodeExportBackup.cursor = null;
            qrCodeExportBackup.has_more = false;
            qrCodeExportBackup.data = [];
            qrCodeExportBackup.loading = true;
        }
        var params = {app_id: CITY_APP_ID, cursor: qrCodeExportBackup.cursor};
        sln.call({
            url : "/common/city/vouchers/qrcode_export/load",
            type : "get",
            data : params,
            success : function(data) {
                qrCodeExportBackup.cursor = data.cursor;
                qrCodeExportBackup.has_more = data.has_more;
                qrCodeExportBackup.loading = false;
                qrCodeExportBackup.data.push.apply(qrCodeExportBackup.data, data.data);
                renderQRCodesExport();
                validateLoadMore();
            }
        });
    };

    var renderExport = function() {
    	var html = $.tmpl(templates['city_vouchers/city_vouchers_export_list'], {
            exports: exportBackup.data,
            app_id : CITY_APP_ID,
            t: CommonTranslations
        });
        $('#city_vouchers-export_data').html(html).show();
        $("#city_vouchers #city_vouchers-export .load-more").toggle(exportBackup.has_more);
    };

    var loadExports = function(cursor) {
    	if (cursor == null) {
            exportBackup.cursor = null;
            exportBackup.has_more = false;
            exportBackup.data = [];
            exportBackup.loading = true;
        }
        var params = {app_id: CITY_APP_ID, cursor: exportBackup.cursor};
        sln.call({
            url : "/common/city/vouchers/export/load",
            type : "get",
            data : params,
            success : function(data) {
            	exportBackup.cursor = data.cursor;
            	exportBackup.has_more = data.has_more;
            	exportBackup.loading = false;
            	exportBackup.data.push.apply(exportBackup.data, data.data);
                renderExport();
                validateLoadMore();
            }
        });
    };

    $(".addqrcodes").click(function() {
        sln.showProcessing(CommonTranslations.SAVING_DOT_DOT_DOT);
        sln.call({
            url : "/common/city/vouchers/qrcode_export/put",
            type : "POST",
            data : {
                data : JSON.stringify({
                    app_id : CITY_APP_ID,
                })
            },
            success : function(data) {
                sln.hideProcessing();
                if (!data.success) {
                    sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                    return;
                }
                loadQRCodeExports(null);
            },
            error : sln.showAjaxError
        });
    });

    var voucherHistory = function() {
        var voucher_id = parseInt($(this).attr("voucher_id"));
        var params = {app_id: CITY_APP_ID, voucher_id: voucher_id};
        sln.call({
            url : "/common/city/vouchers/transactions/load",
            type : "get",
            data : params,
            success : function(data) {
            	data.amount = CURRENCY + " " + ((data.value - data.redeemed_value) / 100).toFixed(2);

                $.each(data.transactions, function(i, transaction) {
                    transaction.date = sln.formatDate(transaction.created, true, false, false);
                    transaction.amount = "";
                    if (transaction.action == 2 || transaction.action == 3) {
                    	transaction.amount = CURRENCY + " " + (transaction.value / 100).toFixed(2);
                    }
                });
                var html = $.tmpl(templates['city_vouchers/city_vouchers_transactions'], {
                    header : CommonTranslations.HISTORY,
                    cancelBtn : CommonTranslations.CANCEL,
                    CommonTranslations: CommonTranslations,
                    voucher : data
                });
                var modal = sln.createModal(html);
            }
        });
    };

    $(document).on('input', '#vouchers_validity', function() {
        var disabled = !$(this).val().trim();
        $('#save_vouchers_validity').attr('disabled', disabled);
    });

    var saveVouchersValidity = function(unlimited) {
        var validity;
        if (unlimited) {
            validity = null;
        } else {
            validity = parseInt($('#vouchers_validity').val());
        }
        sln.call({
            url: '/common/vouchers/validity/put',
            type: 'post',
            showProcessing: true,
            data: {
                app_id: CITY_APP_ID,
                validity: validity
            },
            success: function(result) {
                if(!result.success) {
                    sln.alert(CommonTranslations[result.errormsg]);
                }
            },
            error: sln.showAjaxError
        });
    };
    $(document).on('click', '#save_vouchers_validity', function() {
        saveVouchersValidity(false);
    });

    var checkVouchersValdity = function() {
        var unlimited = $('#vouchers_validity_unlimited').is(':checked');
        $('#vouchers_validity').attr('disabled', unlimited);
        $('#save_vouchers_validity').attr('disabled', unlimited);
        saveVouchersValidity(unlimited);
    };
    $(document).on('click', '#vouchers_validity_unlimited', checkVouchersValdity);

    var cityVouchersMenuItem = $('#topmenu').find('li[menu=city_vouchers]');
    var validateLoadMore = function() {
        if (!cityVouchersMenuItem.hasClass('active')) {
            return;
        }

        var id_ = $("#city_vouchers-tab").find(".nav li.active").attr("section");
        if(id_ === "city_vouchers-search") {
            if (!sln.isOnScreen($("#city_vouchers #city_vouchers-search").find("table tr:last"))) {
                return;
            }
            if (voucherBackup.has_more && voucherBackup.loading === false) {
                loadSearchVouchers(voucherBackup.cursor);
            }
        } else if (id_ === "city_vouchers-qrcode_export"){
            if (!sln.isOnScreen($("#city_vouchers #city_vouchers-qrcode_export").find("table tr:last"))) {
                return;
            }
            if (qrCodeExportBackup.has_more && qrCodeExportBackup.loading === false) {
                loadQRCodeExports(qrCodeExportBackup.cursor);
            }
        } else {
        	if (!sln.isOnScreen($("#city_vouchers #city_vouchers-export").find("table tr:last"))) {
                return;
            }
            if (exportBackup.has_more && exportBackup.loading === false) {
                loadExports(exportBackup.cursor);
            }
        }
    };

    $(window).scroll(function() {
        validateLoadMore();
    });

    loadQRCodeExports(null);
    loadExports(null);

    $("#city_vouchers-tab").find(".nav li a").on("click", function () {
        $("#city_vouchers-tab").find(".nav li").removeClass("active");
        var li = $(this).parent().addClass("active");
        $("#city_vouchers-tab").find("section").hide();
        $("#city_vouchers-tab").find("section#" + li.attr("section")).show();
    });

    var channelUpdates = function(data) {
        if (data.type == 'solutions.common.city.vouchers.qrcode_export.updated') {
            loadQRCodeExports(null);
        }
    };

    sln.registerMsgCallback(channelUpdates);
});

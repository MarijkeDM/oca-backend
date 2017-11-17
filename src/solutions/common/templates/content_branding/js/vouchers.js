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

var hidePinActivateVoucherPopupOverlay = function(callback) {
    console.log("hidePinActivateVoucherPopupOverlay");
    if (callback != undefined) {
        $("#main #pin-activate-voucher-popup").on( "popupafterclose", function() {
            $("#main #pin-activate-voucher-popup").off( "popupafterclose");
            setTimeout(callback, 10);
        });
    }
    $("#main #pin-activate-voucher-popup").popup("close");  // needs to be double for first close
    if (shouldDoubleClose)
        $("#main #pin-activate-voucher-popup").popup("close");
};

var showPinActivateVoucherPopupOverlay = function() {
	console.log("showActivateVoucherPopupOverlay");
    var pinPopup = $("#main #pin-activate-voucher-popup");
    pinPopup.find('.calculator .screen').text('');
    pinPopup.find('.calculator .screen').data('pin', "");
    pinPopup.popup("open", {positionTo: 'window'});
};

var hideActivateVoucherPopupOverlay = function(callback) {
    console.log("hideActivateVoucherPopupOverlay");
    if (callback != undefined) {
        $("#main #activate-voucher-popup").on( "popupafterclose", function() {
            $("#main #activate-voucher-popup").off( "popupafterclose");
            setTimeout(callback, 10);
        });
    }
    $("#main #activate-voucher-popup").popup("close");  // needs to be double for first close
    if (shouldDoubleClose)
        $("#main #activate-voucher-popup").popup("close");
};

var showActivateVoucherPopupOverlay = function() {
	console.log("showActivateVoucherPopupOverlay");
    var activatePopup = $("#main #activate-voucher-popup");
    activatePopup.find(".uid").text("(" + currentScannedInfo.uid + ")");

    activatePopup.find("#av-value").val("");
    activatePopup.find("#av-internal-account").val("");
    activatePopup.find("#av-cost-center").val("");
    activatePopup.find(".error_msg").hide();

    activatePopup.popup("open", {positionTo: 'window'});
};

var hideRedeemVoucherPopupOverlay = function(callback) {
    console.log("hideRedeemVoucherPopupOverlay");
    if (callback != undefined) {
        $("#main #redeem-voucher-popup").on( "popupafterclose", function() {
            $("#main #redeem-voucher-popup").off( "popupafterclose");
            setTimeout(callback, 10);
        });
    }
    $("#main #redeem-voucher-popup").popup("close");  // needs to be double for first close
    if (shouldDoubleClose)
        $("#main #redeem-voucher-popup").popup("close");
};

var showRedeemVoucherPopupOverlay = function() {
    console.log("showRedeemVoucherPopupOverlay");
    var redeemPopup = $("#main #redeem-voucher-popup");
    redeemPopup.find(".uid").text("(" + currentScannedInfo.uid + ")");

	var valueLeft = currentScannedInfo.value - currentScannedInfo.redeemed_value;
	if (valueLeft > 0) {
		$('#redeem-voucher-popup .calculator').show()
		$('#redeem-voucher-popup button[redeemAction="submit"]').show();
	} else {
		$('#redeem-voucher-popup .calculator').hide()
		$('#redeem-voucher-popup button[redeemAction="submit"]').hide();
	}
	redeemPopup.find(".price_left").text(Translations.REMAINING_VALUE + ": " + rogerthat.service.data.currency + " " + (valueLeft / 100).toFixed(2));
	calculatorDecimalAdded = false;
	redeemPopup.find('.calculator .screen').text('');
	redeemPopup.find(".error_msg").hide();

    redeemPopup.popup("open", {positionTo: 'window'});
};

var hideConfirmRedeemVoucherPopupOverlay = function(callback) {
    console.log("hideConfirmRedeemVoucherPopupOverlay");
    if (callback != undefined) {
        $("#main #confirm-redeem-voucher-popup").on( "popupafterclose", function() {
            $("#main #confirm-redeem-voucher-popup").off( "popupafterclose");
            setTimeout(callback, 10);
        });
    }
    $("#main #confirm-redeem-voucher-popup").popup("close");  // needs to be double for first close
    if (shouldDoubleClose)
        $("#main #confirm-redeem-voucher-popup").popup("close");
};

var showConfirmRedeemVoucherPopupOverlay = function() {
    console.log("showConfirmRedeemVoucherPopupOverlay");
    var redeemPopup = $("#main #confirm-redeem-voucher-popup");
    redeemPopup.find(".uid").text("(" + currentScannedInfo.uid + ")");
    redeemPopup.find(".confirm_text").text(Translations.PRICE + ": " + (currentScannedInfo.value / 100).toFixed(2));

    redeemPopup.popup("open", {positionTo: 'window'});
};

$(document).on("touchend click", ".closePinActivateVoucherPopup", function(event) {
    event.stopPropagation();
    event.preventDefault();

    var selected = $(this).attr("pinAction");
    if (selected == "submit") {
    	var pin = $('#main #pin-activate-voucher-popup .calculator .screen').data("pin");

    	solutionsVoucherPinActivateGuid = rogerthat.util.uuid();
        var tag = solutionsVoucherPinActivateGuid;
        rogerthat.api.call("solutions.voucher.activate.pin",
        		JSON.stringify({
        			'timestamp': Math.floor(Date.now() / 1000),
        			'app_id': currentScannedInfo.app_id,
        			'voucher_id': currentScannedInfo.voucher_id,
       			 	'pin': pin
        		}),
        		tag);

        hidePinActivateVoucherPopupOverlay();
        showLoading(Translations.VALIDATING);

        setTimeout(function(){
            if (tag == solutionsVoucherPinActivateGuid) {
                console.log("solutions.voucher.activate.pin timeout");
                solutionsVoucherPinActivateGuid = null;
                hideLoading();
                showErrorPopupOverlay(Translations.INTERNET_SLOW_RETRY);
            }
        }, 15000);

    } else {
    	hidePinActivateVoucherPopupOverlay(startScanningForQRCode);
    }
});

$(document).on("touchend click", "#main #pin-activate-voucher-popup .calculator span", function(event) {
    event.stopPropagation();
    event.preventDefault();

    var btnVal = this.innerHTML;
    var input = $('#main #pin-activate-voucher-popup .calculator .screen');
    if(btnVal == 'C') {
        input.text('');
        input.data("pin", "");
    } else {
    	if (input.text().length < 4) {
    		var pin = input.data("pin");
    		input.data("pin", pin + btnVal)
    		input.text(input.text() + "*");
    	}
    }
});

$(document).on("touchend click", ".closeActivateVoucherPopup", function(event) {
    event.stopPropagation();
    event.preventDefault();

    var selected = $(this).attr("activateAction");
    console.log("closeActivateVoucherPopup selected: " + selected);
    if (selected == "submit") {
    	var activatePopup = $("#main #activate-voucher-popup");

    	var avInternalAccount = activatePopup.find('#av-internal-account');
    	if (avInternalAccount.val().trim() == "") {
    		activatePopup.find(".error_msg").text(Translations.REQUIRED_FIELDS_MISSING);
    		activatePopup.find(".error_msg").show();
            return;
    	}

    	var avCostCenter = activatePopup.find('#av-cost-center');
    	if (avCostCenter.val().trim() == "") {
    		activatePopup.find(".error_msg").text(Translations.REQUIRED_FIELDS_MISSING);
    		activatePopup.find(".error_msg").show();
            return;
    	}

    	var avValue = activatePopup.find('#av-value');
    	var priceFloat = parseFloat(avValue.val());
        if(isNaN(priceFloat)) {
        	activatePopup.find(".error_msg").text(Translations.PRICE_IS_NOT_A_NUMBER);
            activatePopup.find(".error_msg").show();
            return;
        }

        voucherActivationData = {
            voucher_scan: $.extend({}, currentScannedInfo),
            internal_account: avInternalAccount.val().trim(),
            cost_center: avCostCenter.val().trim(),
            amount: Math.round(priceFloat * 100)
        }

        hideActivateVoucherPopupOverlay(function() {
            showPopup('link-voucher-to-user');
        });

    } else {
    	hideActivateVoucherPopupOverlay(startScanningForQRCode);
    }
});

$(document).on('touched click', '#main #link-voucher-to-user .closeLinkVoucherPopup', function(event) {
    event.stopPropagation();
    event.preventDefault();

    var selected = $(this).attr("linkAction");
    if (selected === 'submit') {
        voucherUserLink = true;
        hidePopup('link-voucher-to-user', startScanningForQRCode);
    } else {
        voucherUserLink = false;
        hidePopup('link-voucher-to-user', function() {
            activateVoucher(voucherActivationData, null);
        });
    }
});

var activateVoucher = function(data, userDetails) {
    solutionsVoucherActivateGuid = rogerthat.util.uuid();
    var tag = solutionsVoucherActivateGuid;
    rogerthat.api.call("solutions.voucher.activate",
            JSON.stringify({
                'timestamp': Math.floor(Date.now() / 1000),
                'app_id': data.voucher_scan.app_id,
                'voucher_id': data.voucher_scan.voucher_id,
                'username': data.voucher_scan.username,
                'internal_account': data.internal_account,
                'cost_center': data.cost_center,
                'value': data.amount,
                'app_user_details': userDetails,
            }),
            tag);

    showLoading(Translations.SAVING_DOT_DOT_DOT);
    setTimeout(function(){
        if (tag == solutionsVoucherActivateGuid) {
            console.log("solutions.voucher.activate timeout");
            solutionsVoucherActivateGuid = null;
            hideLoading();
            showErrorPopupOverlay(Translations.INTERNET_SLOW_CONTINUE);
        }
    }, 15000);
    voucherUserLink = false;
};

$(document).on("touchend click", "#main #redeem-voucher-popup .calculator span", function(event) {
    event.stopPropagation();
    event.preventDefault();

    var btnVal = this.innerHTML;
    var input = $('#main #redeem-voucher-popup .calculator .screen');
    if(btnVal == 'C') {
        input.text('');
        calculatorDecimalAdded = false;
    } else if(btnVal == '.') {
        if(!calculatorDecimalAdded) {
            input.text(input.text() + btnVal);
            calculatorDecimalAdded = true;
        }
    } else {
        input.text(input.text() + btnVal);
    }
});

$(document).on("touchend click", ".closeRedeemVoucherPopup", function(event) {
    event.stopPropagation();
    event.preventDefault();

    var selected = $(this).attr("redeemAction");
    console.log("closeRedeemVoucherPopup selected: " + selected);
    if (selected == "submit") {
    	var priceText = $('#main #redeem-voucher-popup .calculator .screen').text();
        var priceFloat = parseFloat(priceText);

        if(isNaN(priceFloat)) {
            $("#main #redeem-voucher-popup .error_msg").text(Translations.PRICE_IS_NOT_A_NUMBER)
                .show();
            return;
        }
        var value = Math.round(priceFloat * 100);
        if (value < 1) {
        	$("#main #redeem-voucher-popup .error_msg").text(Translations.MINIMUM + ": 0.01").show();
            return;
        }

        var valueLeft = currentScannedInfo.value - currentScannedInfo.redeemed_value;
        if (value > valueLeft) {
        	$("#main #redeem-voucher-popup .error_msg").text(Translations.MAXIMUM + ": " + (valueLeft / 100).toFixed(2))
            	.show();
            return;
        }

    	hideRedeemVoucherPopupOverlay();
        showLoading(Translations.REDEEMING_VOUCHER);
        solutionsVoucherRedeemGuid = rogerthat.util.uuid();
        var tag = solutionsVoucherRedeemGuid;

        rogerthat.api.call("solutions.voucher.redeem",
                           JSON.stringify({
                        	   'timestamp': Math.floor(Date.now() / 1000),
                   			   'app_id': currentScannedInfo.app_id,
                   			   'voucher_id': currentScannedInfo.voucher_id,
                   			   'value': value
                            }),
                            tag);

        setTimeout(function(){
            if (tag == solutionsVoucherRedeemGuid) {
                console.log("solutions.voucher.redeem timeout");
                solutionsVoucherRedeemGuid = null;
                hideLoading();
                showErrorPopupOverlay(Translations.INTERNET_SLOW_RETRY);
            }
        }, 15000);

    } else {
    	hideRedeemVoucherPopupOverlay(startScanningForQRCode);
    }
});

$(document).on("touchend click", ".closeConfirmRedeemVoucherPopup", function(event) {
    event.stopPropagation();
    event.preventDefault();
    var selected = $(this).attr("confirmRedeemAction");
    console.log("closeConfirmRedeemVoucherPopup selected: " + selected);
    if (selected == "submit") {
    	hideConfirmRedeemVoucherPopupOverlay();
    	showLoading(Translations.SAVING_DOT_DOT_DOT);
    	solutionsVoucherConfirmRedeemGuid = rogerthat.util.uuid();
        var tag = solutionsVoucherConfirmRedeemGuid;

        rogerthat.api.call("solutions.voucher.redeem.confirm",
                           JSON.stringify({
                        	   'timestamp': Math.floor(Date.now() / 1000),
                   			   'voucher_redeem_key': currentScannedInfo.voucher_redeem_key
                            }),
                            tag);

        setTimeout(function(){
            if (tag == solutionsVoucherConfirmRedeemGuid) {
                console.log("solutions.voucher.redeem.confirm timeout");
                solutionsVoucherConfirmRedeemGuid = null;
                hideLoading();
                showErrorPopupOverlay(Translations.INTERNET_SLOW_CONTINUE);
            }
        }, 15000);
    } else {
    	hideConfirmRedeemVoucherPopupOverlay(startScanningForQRCode);
    }
});

$(document).on("focus", ".scroll-input-activate", function(event){
	$("#activate-voucher-popup").data("original_offset", $("#activate-voucher-popup").offset());
	$("#activate-voucher-popup-popup").css("top", 10);
});

$(document).on("focusout", ".scroll-input-activate", function(event){
	var originalOffset = $("#activate-voucher-popup").data("original_offset");
	$("#activate-voucher-popup-popup").css("top", originalOffset.top);
});

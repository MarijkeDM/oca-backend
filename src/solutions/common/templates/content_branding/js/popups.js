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

var isHelloPopupShown = false;
var calculatorDecimalAdded = false;

// CHOICE ////////////////////////////////////

var hideQRScannedSelectPopupOverlay = function(callback) {
    console.log("hideQRScannedSelectPopupOverlay");
    if (callback != undefined) {
        $("#main #qr-scanned-select-popup").on( "popupafterclose", function() {
            $("#main #qr-scanned-select-popup").off( "popupafterclose");
            setTimeout(callback, 10);
        });
    }
    $("#main #qr-scanned-select-popup").popup("close");
    if (shouldDoubleClose)
        $("#main #qr-scanned-select-popup").popup("close");  // needs to be double for first close
};

var showQRScannedSelectPopupOverlay = function() {
    console.log("showQRScannedSelectPopupOverlay");
    if (LOYALTY_TYPE == LOYALTY_TYPE_REVENUE_DISCOUNT) {
    } else if (LOYALTY_TYPE == LOYALTY_TYPE_LOTTERY) {
    } else if (LOYALTY_TYPE == LOYALTY_TYPE_STAMPS) {
        if (!shouldShowQRScannedSelectPopupOverlayStamps()) {
            return;
        }
    }

    var TMPL_TEXT = '<button style="float: left;" class="closeQrScannedSelectPopup square-btn ui-btn ui-btn-b ui-corner-all" onclick=""></button>';
    var TMPL_TEXT_RED = '<button style="float: left;" class="closeQrScannedSelectPopup square-btn ui-btn btn-red ui-corner-all" onclick=""></button>';
    $("#main #qr-scanned-select-popup-options").empty();

    var a_1 =  $(TMPL_TEXT);
    a_1.text(Translations.ADD_LOYALTY_POINTS);
    a_1.attr("qr-scanned-select", "add");
    a_1.css("margin-right", "1em");
    $("#main #qr-scanned-select-popup-options").append(a_1);
    var a_2 =  $(TMPL_TEXT);
    a_2.text(Translations.REDEEM_LOYALTY_POINTS);
    a_2.attr("qr-scanned-select", "redeem");
    a_2.css("margin-right", "1em");
    $("#main #qr-scanned-select-popup-options").append(a_2);
    var a_3 =  $(TMPL_TEXT_RED);
    a_3.text(Translations.CANCEL);
    a_3.attr("qr-scanned-select", "cancel");
    a_3.css("margin-right", "0");
    $("#main #qr-scanned-select-popup-options").append(a_3);
    $("#main #qr-scanned-select-popup .user_name").text(getUserText());
    $("#main #qr-scanned-select-popup").popup("open", {positionTo: 'window'});
};

// ADD ////////////////////////////////////

var hideAdd = function(callback) {
    console.log("hideAdd");
    if (LOYALTY_TYPE == LOYALTY_TYPE_REVENUE_DISCOUNT) {
        hideAdd1PopupOverlay(callback);
    } else if (LOYALTY_TYPE == LOYALTY_TYPE_STAMPS) {
        hideAdd3PopupOverlay(callback);
    } else {
        console.log("ERROR: Could not process hide add, unknown loyalty type: " + LOYALTY_TYPE);
    }
};

var showAdd = function() {
    console.log("showAdd");
    if (LOYALTY_TYPE == LOYALTY_TYPE_REVENUE_DISCOUNT) {
        $("#main #add-1-popup .error_msg").hide();
        showAdd1PopupOverlay();
    } else if (LOYALTY_TYPE == LOYALTY_TYPE_STAMPS) {
        $("#main #add-3-popup .error_msg").hide();
        showAdd3PopupOverlay();
    } else {
        console.log("ERROR: Could not process show add, unknown loyalty type: " + LOYALTY_TYPE);
    }
};

// REDEEM ////////////////////////////////////

var hideRedeem = function(callback) {
    console.log("hideRedeem");
    if (LOYALTY_TYPE == LOYALTY_TYPE_REVENUE_DISCOUNT) {
        hideRedeem1PopupOverlay(callback);
    } else if (LOYALTY_TYPE == LOYALTY_TYPE_STAMPS) {
        hideRedeem3PopupOverlay(callback);
    } else {
        console.log("ERROR: Could not process hide redeem, unknown loyalty type: " + LOYALTY_TYPE);
    }
};

var showRedeem = function() {
    console.log("showRedeem");
    if (LOYALTY_TYPE == LOYALTY_TYPE_REVENUE_DISCOUNT) {
        $("#main #redeem-1-popup .error_msg").hide();
        showRedeem1PopupOverlay();
    } else if (LOYALTY_TYPE == LOYALTY_TYPE_STAMPS) {
        $("#main #redeem-3-popup .error_msg").hide();
        showRedeem3PopupOverlay();
    } else {
        console.log("ERROR: Could not process show redeem, unknown loyalty type: " + LOYALTY_TYPE);
    }
};

// COUPLE QR CODE ////////////////////////////////////

var hideCoupleQrCodePopupOverlay = function(callback) {
    console.log("hideCoupleQrCodePopupOverlay");
    if (callback != undefined) {
        $("#main #couple-qr-code-popup").on( "popupafterclose", function() {
            $("#main #couple-qr-code-popup").off( "popupafterclose");
            setTimeout(callback, 10);
        });
    }
    $("#main #couple-qr-code-popup").popup("close");  // needs to be double for first close
    if (shouldDoubleClose)
        $("#main #couple-qr-code-popup").popup("close");
};

var showCoupleQrCodePopupOverlay = function(result) {
    console.log("showCoupleQrCodePopupOverlay");
    currentScannedUrl = result.content;
    var input = $('#main #couple-qr-code-popup #email');
    input.val('');
    $("#main #couple-qr-code-popup .error_msg").hide();
    $("#main #couple-qr-code-popup").popup("open", {positionTo: 'window'});
};

// ERROR ////////////////////////////////////

var hideErrorPopupOverlay = function(callback) {
    console.log("hideErrorPopupOverlay");
    if (callback != undefined) {
        $("#main #error-popup").on( "popupafterclose", function() {
            $("#main #error-popup").off( "popupafterclose");
            setTimeout(callback, 10);
        });
    }
    $("#main #error-popup").popup("close");  // needs to be double for first close
    if (shouldDoubleClose)
        $("#main #error-popup").popup("close");
};

var showErrorPopupOverlay = function(errorMsg) {
    console.log("showErrorPopupOverlay");
    $("#main #error-popup .error_msg").text(errorMsg);
    $("#main #error-popup").popup("open", {positionTo: 'window'});
};


//HELLO ////////////////////////////////////

var hideHelloPopupOverlay = function() {
    if (!isHelloPopupShown) {
        return;
    }
    console.log("hideHelloPopupOverlay");
    $("#main #hello-popup").on( "popupafterclose", function() {
        $("#main #hello-popup").off( "popupafterclose");
        console.log("hideHelloPopupOverlay startScanningForQRCode");
        setTimeout(startScanningForQRCode, 10);
    });
    isHelloPopupShown = false;
    $("#main #hello-popup").popup("close");  // needs to be double for first close
    if (shouldDoubleClose)
        $("#main #hello-popup").popup("close");

};

var showHelloPopupOverlay = function(helloMsg) {
    console.log("showHelloPopupOverlay");
    isHelloPopupShown = true;
    $("#main #hello-popup .hello_msg").text(helloMsg);
    $("#main #hello-popup").popup("open", {positionTo: 'window'});

    $('#main').trigger('create');
};

//TEXT ////////////////////////////////////

var hideTextPopupOverlay = function(callback) {
    console.log("hideTextPopupOverlay");
    if (callback != undefined) {
        $("#main #text-popup").on( "popupafterclose", function() {
            $("#main #text-popup").off( "popupafterclose");
            setTimeout(callback, 10);
        });
    }
    $("#main #text-popup").popup("close");  // needs to be double for first close
    if (shouldDoubleClose)
        $("#main #text-popup").popup("close");
};

var showTextPopupOverlay = function(textMsg, errorMsg, subMsg, canClose, isHtml) {
    console.log("showTextPopupOverlay");
    if (isHtml) {
        $("#main #text-popup .text_msg").html(textMsg);
    } else {
        $("#main #text-popup .text_msg").text(textMsg);
    }
    if (errorMsg != null) {
        $("#main #text-popup .error_msg").show();
        if (isHtml) {
            $("#main #text-popup .error_msg").html(errorMsg);
        } else {
            $("#main #text-popup .error_msg").text(errorMsg);
        }
    } else {
        $("#main #text-popup .error_msg").hide();
    }

    if (subMsg != null) {
        $("#main #text-popup .sub_msg").show();
        if (isHtml) {
            $("#main #text-popup .sub_msg").html(subMsg);
        } else {
            $("#main #text-popup .sub_msg").text(subMsg);
        }
    } else {
        $("#main #text-popup .sub_msg").hide();
    }
    if (canClose) {
        $("#main #text-popup .closeTextPopup").show();
    } else {
        $("#main #text-popup .closeTextPopup").hide();
    }
    $("#main #text-popup").popup("open", {positionTo: 'window'});
};

var showLoading = function(text) {
    $.mobile.loading( 'show', {
        text: text,
        textVisible: true,
        theme: 'a',
        html: ""
    });
};

var hideLoading = function() {
    console.log('hiding loading');
    $.mobile.loading('hide');
};

// CLICK HANDLERS

$(document).on("touchend click", ".closeQrScannedSelectPopup", function(event) {
    event.stopPropagation();
    event.preventDefault();

    var selected = $(this).attr("qr-scanned-select");

    console.log("closeQrScannedSelectPopup selected: " + selected);
    if (selected == "add") {
        hideQRScannedSelectPopupOverlay(showAdd);
    } else if (selected == "redeem") {
        hideQRScannedSelectPopupOverlay(showRedeem);
    } else {
        hideQRScannedSelectPopupOverlay(startScanningForQRCode);
    }
});

$(document).on("touchend click", ".closeErrorPopup", function(event) {
    event.stopPropagation();
    event.preventDefault();

    var selected = $(this).attr("errorAction");
    console.log("closeErrorPopup selected: " + selected);
    hideErrorPopupOverlay(startScanningForQRCode);
});

$(document).on("touchend click", ".closeTextPopup", function() {
    event.stopPropagation();
    event.preventDefault();

    console.log("closeTextPopup");
    hideTextPopupOverlay(startScanningForQRCode);
});

$(document).on("touchend click", ".closeHelloPopup", function() {
    event.stopPropagation();
    event.preventDefault();

    console.log("closeHelloPopup");
    hideHelloPopupOverlay();
});

$(document).on("touchend click", ".closeCoupleQRCodePopup", function(event) {
    event.stopPropagation();
    event.preventDefault();

    var selected = $(this).attr("coupleAction");
    console.log("closeCoupleQRCodePopup selected: " + selected);
    if (selected == "submit") {
        var input = $('#main #couple-qr-code-popup #email');

        var re = /^(([^<>()[\]\\.,;:\s@"]+(\.[^<>()[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
        var ok = re.test(input.val().trim());
        if (!ok) {
            $("#main #couple-qr-code-popup .error_msg").text(Translations.INVALID_EMAIL_FORMAT.replace("%(email)s", input.val()));
            $("#main #couple-qr-code-popup .error_msg").show();
            return;
        }

        solutionsLoyaltyCoupleGuid = rogerthat.util.uuid();
        var tag = solutionsLoyaltyCoupleGuid;

        rogerthat.api.call("solutions.loyalty.couple",
                JSON.stringify({
                        'timestamp': Math.floor(Date.now() / 1000),
                        'url' : currentScannedUrl,
                        'email' : input.val()
                }),
                tag);

        hideCoupleQrCodePopupOverlay();
        showLoading(Translations.SAVING_DOT_DOT_DOT);

        setTimeout(function(){
            if (tag == solutionsLoyaltyCoupleGuid) {
                console.log("solutions.loyalty.couple timeout");
                solutionsLoyaltyCoupleGuid = null;
                hideLoading();
                showErrorPopupOverlay(Translations.INTERNET_SLOW_CONTINUE);
            }
        }, 15000);

    } else {
        hideCoupleQrCodePopupOverlay(startScanningForQRCode);
    }
});

$(document).on("focus", ".scroll-input-couple", function(event){
	$("#couple-qr-code-popup").data("original_offset", $("#couple-qr-code-popup").offset());
	$("#couple-qr-code-popup-popup").css("top", 10);
});

$(document).on("focusout", ".scroll-input-couple", function(event){
	var originalOffset = $("#couple-qr-code-popup").data("original_offset");
	$("#couple-qr-code-popup-popup").css("top", originalOffset.top);
});


var hidePopup = function(popupId, callback) {
    console.log('hiding popup:', popupId);
    var popupElem = $('#main #' + popupId);
    if (typeof callback === 'function') {
        popupElem.on('popupafterclose', function() {
            popupElem.off('popupafterclose');
            setTimeout(callback, 10);
        });
    }
    popupElem.popup('close');
    if (shouldDoubleClose) {
       popupElem.popup('close');
    }
}

var showPopup = function(popupId, callback) {
   console.log('showing popup:', popupId);
   var popupElem = $('#main #' + popupId);
   if(typeof callback === 'function') {
       callback.bind(popupElem)();
   }
   popupElem.popup('open', { positionTo: 'window' });
}

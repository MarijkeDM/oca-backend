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

var cameraType = null;
var currentScannedUser = {};
var currentScannedInfo = {};
var currentScannedUrl = null;

var shouldDoubleClose = false;

var slidesUUID = null;
var voucherUserLink = false;
var voucherActivationData = {};
var solutionsLoyaltyLoadGuid = null;
var solutionsLoyaltyScanGuid = null;
var solutionsLoyaltyPutGuid = null;
var solutionsLoyaltyRedeemGuid = null;
var solutionsLoyaltyCoupleGuid = null;
var solutionsVoucherResolveGuid = null;
var solutionsVoucherPinActivateGuid = null;
var solutionsVoucherActivateGuid = null;
var solutionsVoucherRedeemGuid = null;
var solutionsVoucherConfirmRedeemGuid = null;
var modules = {};

window.onload = function() {
    if (typeof rogerthat === 'undefined') {
        document.body.innerHTML = Translations.ROGERTHAT_FUNCTION_UNSUPPORTED_UPDATE;
        return;
    }

    $(document).ready(function() {
        rogerthat.callbacks.ready(onRogerthatReady);

        rogerthat.callbacks.backPressed(function() {
            console.log("BACK pressed");
            return true; // we handled the back press
        });
    });
};

// XXX ////////////////////////////////////

var setLoyaltySettings = function() {
    setLoyaltySettingsRevenueDiscount();
    setLoyaltySettingsLottery();
    setLoyaltySettingsStamps();
};

var onRogerthatReady = function() {
    cameraType = rogerthat.camera.FRONT;
    var serviceEmail = rogerthat.service.account;
    var userEmail = rogerthat.user.account;

    console.log("onRogerthatReady()");
    console.log("OSA Loyalty ADMIN v1.0.7");
    console.log("LOYALTY_TYPE: " + LOYALTY_TYPE);
    console.log("service_email: " + serviceEmail);
    console.log("user_email: " + userEmail);
    console.log("Language: " + language);

    console.log("rogerthat.system.os: " + rogerthat.system.os);
    shouldDoubleClose = rogerthat.system.os !== "android";

    $(document).on("touchend click", "#open_dashboard", function (event) {
        event.stopPropagation();
        event.preventDefault();
        if (isBacklogConnected) {
            console.log("Going to dashboard ...");
            window.location = $(this).attr("open_url") + "&si=" + encodeURIComponent(rogerthat.service.data.settings.service_identity);
        } else {
            showErrorPopupOverlay(Translations.NO_INTERNET_CONNECTION);
        }
    });

    $(document).on("touchend click", "#open_website", function (event) {
        event.stopPropagation();
        event.preventDefault();
        if (isBacklogConnected) {
            console.log("Going to website ...");
            window.location = $(this).attr("open_url");
        } else {
            showErrorPopupOverlay(Translations.NO_INTERNET_CONNECTION);
        }
    });

    setLoyaltySettings();

    var userScanned = function(result, now_) {
        console.log("scanned: " + result.userDetails.email + ":" + result.userDetails.appId);
        if (result.userDetails.email == "dummy" && result.userDetails.appId == "dummy") {
            hideLoading();
            showCoupleQrCodePopupOverlay(result);
        } else  if (LOYALTY_TYPE == LOYALTY_TYPE_REVENUE_DISCOUNT) {
            qrCodeScannedRevenueDiscount(now_, result);
        } else if (LOYALTY_TYPE == LOYALTY_TYPE_LOTTERY) {
            qrCodeScannedLottery(now_, result);
        } else if (LOYALTY_TYPE == LOYALTY_TYPE_STAMPS) {
            qrCodeScannedStamps(now_, result);
        } else if (LOYALTY_TYPE == LOYALTY_TYPE_CITY_WIDE_LOTTERY) {
            qrCodeScannedCityWideLottery(now_, result);
        } else {
            hideLoading();
            startScanningForQRCode();
        }
    };

    var onReceivedApiResult = function(method, result, error, tag){
        console.log("onReceivedApiResult");
        console.log("method: " + method);
        console.log("result: " + result);
        console.log("error: " + error);
        console.log("tag: " + tag);

        if (method == "solutions.loyalty.load") {
            if (solutionsLoyaltyLoadGuid == null || tag == null) {
                return;
            }
            if (tag == solutionsLoyaltyLoadGuid) {
                solutionsLoyaltyLoadGuid = null;
                hideLoading();
                if (result) {
                    var r = JSON.parse(result);
                    currentScannedInfo = r;
                    showQRScannedSelectPopupOverlay();
                } else {
                    showErrorPopupOverlay(error);
                }
            } else {
                if (solutionsLoyaltyLoadGuid == null) {
                    console.log("solutions.loyalty.load Did timeout");
                } else {
                    console.log("solutions.loyalty.load Did not match tag");
                }
            }
        } else if (method == "solutions.loyalty.scan") {
            if (solutionsLoyaltyScanGuid == null || tag == null) {
                return;
            }
            if (tag == solutionsLoyaltyScanGuid) {
                solutionsLoyaltyScanGuid = null;
                hideLoading();
                if (result) {
                    startScanningForQRCode();
                } else {
                    showErrorPopupOverlay(error);
                }
            } else {
                if (solutionsLoyaltyScanGuid == null) {
                    console.log("solutions.loyalty.scan Did timeout");
                } else {
                    console.log("solutions.loyalty.scan Did not match tag");
                }
            }
        } else if (method == "solutions.loyalty.put") {
            if (solutionsLoyaltyPutGuid == null || tag == null) {
                return;
            }
            if (tag == solutionsLoyaltyPutGuid) {
                solutionsLoyaltyPutGuid = null;
                hideLoading();
                if (result) {
                    var r = JSON.parse(result);
                    if (LOYALTY_TYPE == LOYALTY_TYPE_LOTTERY) {
                        processLotteryPut(r.is_put, currentScannedUser);
                    } else if (LOYALTY_TYPE == LOYALTY_TYPE_CITY_WIDE_LOTTERY) {
                    	processCityWideLotteryPut(currentScannedUser);
                    } else {
                        startScanningForQRCode();
                    }
                } else {
                    showErrorPopupOverlay(error);
                }
            } else {
                if (solutionsLoyaltyPutGuid == null) {
                    console.log("solutions.loyalty.put Did timeout");
                } else {
                    console.log("solutions.loyalty.put Did not match tag");
                }
            }
        } else if (method == "solutions.loyalty.redeem") {
            if (solutionsLoyaltyRedeemGuid == null || tag == null) {
                return;
            }
            if (tag == solutionsLoyaltyRedeemGuid) {
                solutionsLoyaltyRedeemGuid = null;
                hideLoading();
                if (result) {
                    startScanningForQRCode();
                } else {
                    showErrorPopupOverlay(error);
                }
            } else {
                if (solutionsLoyaltyRedeemGuid == null) {
                    console.log("solutions.loyalty.redeem Did timeout");
                } else {
                    console.log("solutions.loyalty.redeem Did not match tag");
                }
            }
        } else if (method == "solutions.loyalty.couple") {
            if (solutionsLoyaltyCoupleGuid == null || tag == null) {
                return;
            }
            if (tag == solutionsLoyaltyCoupleGuid) {
                solutionsLoyaltyCoupleGuid = null;
                hideLoading();
                if (result) {
                    startScanningForQRCode();
                } else {
                    showErrorPopupOverlay(error);
                }
            } else {
                if (solutionsLoyaltyCoupleGuid == null) {
                    console.log("solutions.loyalty.put Did timeout");
                } else {
                    console.log("solutions.loyalty.put Did not match tag");
                }
            }
        } else if (method == "solutions.voucher.resolve") {
            if (solutionsVoucherResolveGuid == null || tag == null) {
                return;
            }
            if (tag == solutionsVoucherResolveGuid) {
                solutionsVoucherResolveGuid = null;
                if (result) {
                	var r = JSON.parse(result);
                	currentScannedInfo = r;
                    if (r.type == 'custom_loyalty_card' || r.type == 'unknown') {
                        userScanned(r, Math.floor(Date.now() / 1000));
                    } else if (r.type == 'city_voucher') {
                           hideLoading();
	                	if (r.status == 1) {
	                		showRedeemVoucherPopupOverlay();
	                	} else if (r.status == 2) {
	                		showPinActivateVoucherPopupOverlay();
	                	} else {
	                		showErrorPopupOverlay(Translations.ERROR_OCCURED_UNKNOWN);
	                	}
                	} else {
                		hideLoading();
                		showErrorPopupOverlay(Translations.ERROR_OCCURED_UNKNOWN);
                	}
                } else {
                hideLoading();
                    showErrorPopupOverlay(error);
                }
            } else {
                if (solutionsVoucherResolveGuid == null) {
                    console.log("solutions.voucher.resolve Did timeout");
                } else {
                    console.log("solutions.voucher.resolve Did not match tag");
                }
            }
        } else if (method == "solutions.voucher.activate.pin") {
            if (solutionsVoucherPinActivateGuid == null || tag == null) {
                return;
            }
            if (tag == solutionsVoucherPinActivateGuid) {
            	solutionsVoucherPinActivateGuid = null;
                hideLoading();
                if (result) {
                	var r = JSON.parse(result);
                	currentScannedInfo.username = r.username;
                	showActivateVoucherPopupOverlay();
                } else {
                    showErrorPopupOverlay(error);
                }
            } else {
                if (solutionsVoucherPinActivateGuid == null) {
                    console.log("solutions.voucher.activate.pin Did timeout");
                } else {
                    console.log("solutions.voucher.activate.pin Did not match tag");
                }
            }
        } else if (method == "solutions.voucher.activate") {
            if (solutionsVoucherActivateGuid == null || tag == null) {
                return;
            }
            if (tag == solutionsVoucherActivateGuid) {
            	solutionsVoucherActivateGuid = null;
                hideLoading();
                if (result) {
                	startScanningForQRCode();
                } else {
                    showErrorPopupOverlay(error);
                }
            } else {
                if (solutionsVoucherActivateGuid == null) {
                    console.log("solutions.voucher.activate Did timeout");
                } else {
                    console.log("solutions.voucher.activate Did not match tag");
                }
            }
        } else if (method == "solutions.voucher.redeem") {
            if (solutionsVoucherRedeemGuid == null || tag == null) {
                return;
            }
            if (tag == solutionsVoucherRedeemGuid) {
            	solutionsVoucherRedeemGuid = null;
                hideLoading();
                if (result) {
                	var r = JSON.parse(result);
                	currentScannedInfo = r;
                	showConfirmRedeemVoucherPopupOverlay();
                } else {
                    showErrorPopupOverlay(error);
                }
            } else {
                if (solutionsVoucherRedeemGuid == null) {
                    console.log("solutions.voucher.redeem Did timeout");
                } else {
                    console.log("solutions.voucher.redeem Did not match tag");
                }
            }
        } else if (method == "solutions.voucher.redeem.confirm") {
            if (solutionsVoucherConfirmRedeemGuid == null || tag == null) {
                return;
            }
            if (tag == solutionsVoucherConfirmRedeemGuid) {
            	solutionsVoucherConfirmRedeemGuid = null;
                hideLoading();
                if (result) {
                	var r = JSON.parse(result);
                    showTextPopupOverlay(r.title, null, r.content);
                    setTimeout(function(){
                        hideTextPopupOverlay(startScanningForQRCode);
                    }, 5000);
                } else {
                    showErrorPopupOverlay(error);
                }
            } else {
                if (solutionsVoucherConfirmRedeemGuid == null) {
                    console.log("solutions.voucher.redeem.confirm Did timeout");
                } else {
                    console.log("solutions.voucher.redeem.confirm Did not match tag");
                }
            }
        } else if (method === 'solutions.coupons.resolve') {
            if (error) {
                showErrorPopupOverlay(error);
                modules.coupons.resolveCouponFailed();
            } else {
                modules.coupons.couponResolved(JSON.parse(result), tag);
            }
        } else if (method === 'solutions.coupons.redeem') {
            if (error) {
                showErrorPopupOverlay(error);
                modules.coupons.redeemCouponFailed();
            } else {
                modules.coupons.couponRedeemed(JSON.parse(result), tag);
            }
        }
    };

    rogerthat.api.callbacks.resultReceived(onReceivedApiResult);

    rogerthat.callbacks.serviceDataUpdated(function () {
        console.log("rogerthat.callbacks.serviceDataUpdated");
        setLoyaltySettings();
    });

    rogerthat.callbacks.userDataUpdated(function () {
        console.log("rogerthat.callbacks.userDataUpdated");
        setTabletFunctions();
        setPendingNotifications();
        setSlides();
        console.log("userDataUpdated startScanningForQRCode");
        startScanningForQRCode();
    });

    rogerthat.callbacks.qrCodeScanned(function(result) {
        console.log("rogerthat.callbacks.qrCodeScanned");
        console.log(result.status);
        console.log(result.content);
        var now_ = Math.floor(Date.now() / 1000);

        if (result.status == "resolving") {
            playSound('sound/scanned.mp3');
        } else if (result.status == "error") {
            hideLoading();
            showErrorPopupOverlay(result.content);
        } else if (result.userDetails && voucherUserLink) {
            // FIXME: too much global variables/data, this might
            // introduce many errors?
            activateVoucher(voucherActivationData, result.userDetails);
        } else if (result.userDetails) {
            userScanned(result, now_);
        } else {
            showLoading(Translations.LOADING_USER_INFO);
            // Check if it's a coupon
            var contentJson;
            try {
                contentJson = JSON.parse(result.content);
            } catch (exception) {
                console.log('Scanned QR code does not contain valid json', exception);
                // content is not json
            } finally {
                if (contentJson) {
                    if (processQRContent(contentJson)) {
	                    return;
                    }
                }
            }

            // Check if it's a city voucher or an unknown QR
            if (isBacklogConnected) {
                showLoading(Translations.LOADING_USER_INFO);
                solutionsVoucherResolveGuid = rogerthat.util.uuid();
                var tag = solutionsVoucherResolveGuid;
                rogerthat.api.call("solutions.voucher.resolve",
                		JSON.stringify({
                			'timestamp': Math.floor(Date.now() / 1000),
                			'url' : result.content
                		}),
                		tag);

                setTimeout(function(){
                    if (tag == solutionsVoucherResolveGuid) {
                        console.log("solutions.voucher.resolve timeout");
                        solutionsVoucherResolveGuid = null;
                        hideLoading();
                        showErrorPopupOverlay(Translations.INTERNET_SLOW_RETRY);
                    }
                }, 15000);
            } else {
                hideLoading();
                showErrorPopupOverlay(Translations.NO_INTERNET_CONNECTION);
            }
        }
    });

    rogerthat.callbacks.onBackendConnectivityChanged(function(connected) {
        console.log("rogerthat.callbacks.onBackendConnectivityChanged");
        console.log("connected: " + connected);

        isBacklogConnected = !!connected;
        updateBacklogConnectedVisibility();
    });

    setTabletFunctions();

    setTimeout(function(){
        setPendingNotifications();
        setSlides();
        startValidateBacklogConnected();

        if (rogerthat.user.data.loyalty.name) {
            showHelloPopupOverlay(Translations.HELLO_TEXT_TABLET.replace("{0}", rogerthat.user.data.loyalty.name));
            setTimeout(function () {
                hideHelloPopupOverlay();
            }, 5000);
        }
    }, 2000);
};

function checkInternetConnection() {
    'use strict';
    if (!isBacklogConnected) {
        showErrorPopupOverlay(Translations.NO_INTERNET_CONNECTION);
    }
    return isBacklogConnected;
}

function processQRContent(json) {
    'use strict';
    console.log('processing QR content', json);
    if (!json.c || !json.u) {
        return false;
    }

    if (checkInternetConnection()) {
        showLoading(Translations.loading_coupon);
        modules.coupons.resolveCoupon(json.c, json.u, function (data) {
            hideLoading();
            modules.coupons.processCouponResolved(json.c, json.u, data);
        });
    } else {
        hideLoading();
        showErrorPopupOverlay(Translations.NO_INTERNET_CONNECTION);
    }
    return true;
}

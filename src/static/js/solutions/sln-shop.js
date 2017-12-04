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

var SHOP_PAGES = {
    cart: renderCart,
    product: renderItem,
    checkout: renderCart
};
var STORE_PRODUCTS = []; // loaded via ajax call
var PRODUCT_SHORT_NAMES = {
//    BEAC: CommonTranslations.beacon, // remove beacon product
    XCTY: CommonTranslations.apps,
    POSM: CommonTranslations.flyers,
    BNNR: CommonTranslations.rollup_banner,
    KKRT: CommonTranslations.loyalty_cards
};
var EXTRA_CITY_CODE = 'XCTY', EXTRA_CITY_PRICE = 0;
var cart = [], ccInfo, callBackAfterCCLinked;

function renderItem(productCode){
    var tabs = $('#shop-tabs');
    tabs.show();
    tabs.find("li[id^='product-']").removeClass('active');
    $('#product-' + productCode).addClass('active');
    // Different kind of page only for the extra city product.
    var foundProducts = STORE_PRODUCTS.filter(function (p) {
        return p.code === productCode;
    });
    if (!foundProducts.length && STORE_PRODUCTS.length) {
        window.location.hash = '/shop/product/' + STORE_PRODUCTS[0].code;
        return;
    } else if (productCode === EXTRA_CITY_CODE) {
        renderApps();
    }else{
        renderProduct(productCode);
    }
    renderGlobals();
}

function renderProduct(argument) {
    var productCode = '';
    if (argument.code) {
        productCode = argument.code;
    } else {
        productCode = argument;
    }
    var product = STORE_PRODUCTS.filter(function(p){
        return p.code === productCode;
    })[0];
    var html = $.tmpl(templates['shop/product'], {
        product: product,
        error: argument.error,
        success: argument.success,
        loading: argument.loading,
        t: CommonTranslations,
        LEGAL_ENTITY_CURRENCY: LEGAL_ENTITY_CURRENCY
    });
    $('#store-current-page').html(html);
    $('#add-to-cart').click(function(){
        var code = $(this).attr('data-product-code');
        var count = parseInt($('#product-amount').val());
        addItemToCart({code: code, count: count, loading: true}, renderProduct, code);
    });
    renderGlobals();
}

function renderGlobals(){
    var cartCount = '', appsCount = '';
    if(cart.length){
        cartCount = '(' + cart.length + ')';
        appsCount = cart.filter(function (c) {
            return c.app_id;
        }).length;
    }
    if (appsCount) {
        appsCount = '(' + appsCount + ')';
    } else {
        appsCount = '';
    }
    $('.cart-item-count-apps').text(appsCount);
    $('.cart-item-count').text(cartCount);
}

function renderCartInternal(checkout) {
    var totalExclVat = 0, vat = 0, total = 0;
    $.each(cart, function(i, product){
        if (product.product === EXTRA_CITY_CODE) {
            var appName = ALL_APPS.filter(function(p){
                return p.id === product.app_id;
            })[0].name;
            product.service_visible_in = product.service_visible_in.replace(/%\(app_name\)s/g, appName);
        }else{
             product.description = STORE_PRODUCTS.filter(function(p){
                 return p.code === product.product;
            })[0].description;
        }
        var tot = product.price * product.count/100;
        var vatTemp = tot * VAT_PCT / 100;
        totalExclVat += tot;
        vat += vatTemp;
        total += tot + vatTemp;
    });
    var html = $.tmpl(templates['shop/shopping_cart'], {
        items: cart,
        vatPct: VAT_PCT,
        totalExclVat: totalExclVat.toFixed(2),
        vat: vat.toFixed(2),
        total: total.toFixed(2),
        checkout: checkout,
        creditCard: ccInfo,
        t: CommonTranslations,
        cartTitle: T(checkout ? 'overview_order' : 'cart'),
        LEGAL_ENTITY_CURRENCY: LEGAL_ENTITY_CURRENCY,
        customBackButton: false
    });
    $('#store-current-page').html(html);
    //attach events
    $('button[data-item-id]').click(function(){
        var app = $(this).attr('data-app-id');
        var id = $(this).attr('data-item-id');
        // Find the item in the cart that has this cityapp id
        var orderItem = cart.filter(function(cartitem){
            return cartitem.id === parseInt(id);
        })[0];
        if(orderItem){
            removeItemFromCart(orderItem, renderCart);
        }
    });
    function pollCCInfo(callback) {
        getCreditCard(function (data) {
            if (!data) {
                // data not available yet. Try again in 500 ms...
                console.info('Credit card info not available yet. Retrying...');
                setTimeout(function () {
                    pollCCInfo(callback);
                }, 500);
            } else {
                callback(data);
            }
        });
    }

    $('#change-creditcard, #link-cc, #add-creditcard').click(function () {
        var modal = $('#submit-order-error').modal('hide');
        // global var
        callBackAfterCCLinked = function () {
            pollCCInfo(function (data) {
                ccInfo = data ? data : false; // when undefined, it shows 'loading'.
                renderCartInternal(checkout);
            });
        };
        manageCreditCard();
    });
    $('#checkout').click(function () {
        // show loading instead of 'pay with creditcard'
        var $this = $(this);
        if ($this.is(':disabled')) {
            return;
        }
        $this.find('.normal').hide();
        $this.find('.loading').show();
        $this.attr('disabled', true);
        var options = {
            method: 'post',
            url: '/common/store/order/pay',
            data: {
                data: JSON.stringify({})
            },
            success: function (data) {
                // check if the save was successful.
                var modal = $('#submit-order-error').modal('show');
                modal.find('#close-message-dialog').click(function () {
                    $('#submit-order-error').modal('hide');
                });
                if (data.success) {
                    modal.find('.modal-header h3').text(CommonTranslations.order_complete);
                    modal.find('.modal-body').html('<p>' + CommonTranslations.process_asap + '</p>');
                    modal.find('#link-cc').hide();
                    modal.on('hide.bs.modal', function(e){
                        // Move the current user's cart items to the active apps variable
                        var addedApps = cart.filter(function (c) {
                            return c.app_id;
                        });
                        $.each(addedApps, function (i, app) {
                            ACTIVE_APPS.push(app.app_id);
                        });
                        // Clear the shopping cart, redirect to the shop homepage,
                        cart = [];
                        window.location.hash = '/shop/';
                    });
                } else {
                    // Show error msg
                    modal.find('.modal-header h3').text(CommonTranslations.Error);
                    modal.find('.modal-body').html('<p>' + data.errormsg + '</p>');
                    if (data.bool) { // if the error is an error related to the credit card.
                        modal.find('#link-cc').show();
                    } else {
                        modal.find('#link-cc').hide();
                    }

                }
            },
            error: function () {
                var modal = $('#submit-order-error').modal('show');
                modal.find('.modal-header h3').text('Error');
                modal.find('.modal-body').html('<p>' + CommonTranslations.order_failed_contact_cs + '</p>');
                modal.find('#link-cc').hide();
            },
            complete: function () {
                $this.find('.normal').show();
                $this.find('.loading').hide();
                $this.attr('disabled', false);
            }

        };
        sln.call(options);
    });
    renderGlobals();
}

function renderCart(checkout) {
    ccInfo = undefined;
    renderCartInternal(checkout);
    // Update credit card info, just to be sure the user didn't update it in another tab.
    var checkoutBtn = $('#checkout');
    checkoutBtn.attr('disabled', true);
    if (checkout) {
        getCreditCard(function (data) {
            ccInfo = data ? data : false;
            renderCartInternal(checkout);
            checkoutBtn.attr('disabled', false);
        });
    }
}

function renderApps(data) {
    if(!data){
        data = {};
    }
    var available = [], active = [], ordered = [], orderedApps = [];
    for(var i = 0; i < cart.length; i++){
        if(cart[i].app_id){
            orderedApps.push(cart[i].app_id);
        }
    }
    for (i = 0; i < ALL_APPS.length; i++) {
        if (ACTIVE_APPS.indexOf(ALL_APPS[i].id) !== -1) {
            active.push(ALL_APPS[i]);
        } else if (orderedApps.indexOf(ALL_APPS[i].id) !== -1) {
            ordered.push(ALL_APPS[i]);
        }else{
            var app = ALL_APPS[i];
            app.price = (EXTRA_CITY_PRICE / 100).toFixed(2);
            available.push(app);
        }
    }
    var html = $.tmpl(templates['shop/apps'], {
        ACTIVE_APPS: active,
        orderedApps: ordered,
        availableApps: available,
        error: data.error,
        t: CommonTranslations,
        LEGAL_ENTITY_CURRENCY: LEGAL_ENTITY_CURRENCY
    });
    $('#store-current-page').html(html);
    $('#ordered-apps').find('button').click(function(){
        var app = $(this).attr('data-app-id');
        // Find the item in the cart that has this cityapp id
        var orderItem = cart.filter(function(cartitem){
            return cartitem.app_id == app;
        })[0];
        if(orderItem){
            removeItemFromCart(orderItem, renderApps);
        }else{
            //re-render with error msg
            renderApps({error: CommonTranslations.item_already_remove.replace('%s', app)});
        }
    });

    $('#available-apps').find('button').click(function(){
        var $this = $(this);
        if($this.attr('disabled')){
            return;
        }
        var app = $(this).attr('disabled', true).attr('data-app-id');
        addItemToCart({app_id: app, code: EXTRA_CITY_CODE}, renderApps);
    });
    renderGlobals();
}

function removeItemFromCart(item, renderFx){
    var options = {
        method: 'post',
        url: '/common/store/order/item/delete',
        data: {
            data: JSON.stringify({
                item_id: item.id
            })
        },
        success: function (data) {
            // check if the save was successful.
            if (data.success === true) {
                cart.splice(cart.indexOf(item), 1);
                renderFx();
            } else {
                renderFx({error: data.errormsg});
            }
        },
        error: function () {
            // show generic error msg
            renderFx({error: CommonTranslations.ERROR_OCCURED_UNKNOWN});
        }
    };
    sln.call(options);
}

function addItemToCart(item, renderFx, productCode) {
    if(item.loading) {
        renderFx({code: productCode, loading: true});
    }
    var options = {
        method: 'POST',
        url: '/common/store/order/item/add',
        data: {
            data: JSON.stringify({
                item: item
            })
        },
        success: function (data) {
            // check if the save was successful.
            if (data.success) {
                // Check if there is a cart item with the same product code.
                // If so, just add the count to it instead of creating a new cart item.
                var newItem = data.order_item;
                var hasItem = false;
                for(var i = 0; i < cart.length; i++){
                    if(cart[i].product === newItem.product && newItem.product !== EXTRA_CITY_CODE) {
                        cart[i].count = newItem.count;
                        hasItem = true;
                    }
                }
                if(!hasItem){
                    cart.push(newItem);
                }
            }
            renderFx({code: productCode, success: true, error: data.errormsg});
        },
        error: function () {
            renderFx({code: productCode, error: CommonTranslations.ERROR_OCCURED_UNKNOWN});
        }
    };
    sln.call(options);
}

function getStoreProducts(callback) {
    if (STORE_PRODUCTS.length) {
        callback();
    } else {
        var options = {
            method: 'GET',
            url: '/common/store/products',
            success: function (data) {
                STORE_PRODUCTS = data;
                for (var i = 0; i < STORE_PRODUCTS.length; i++) {
                    var prod = STORE_PRODUCTS[i];
                    $('#shop-tabs').append(
                        '<li id="product-' + prod.code + '"><a href="#/shop/product/' + prod.code + '">'
                        + PRODUCT_SHORT_NAMES[prod.code] + '</a></li>');
                    if (prod.code === EXTRA_CITY_CODE) {
                        EXTRA_CITY_PRICE = prod.price;
                    }
                }
                getOrderItems(callback);
            },
            error: sln.showAjaxError
        };
        sln.call(options);
    }
}

function getOrderItems(callback) {
    var options = {
        method: 'GET',
        url: '/common/store/order_items',
        success: function(data){
            cart = data;
            callback();
        },
        error: sln.showAjaxError
    };
    sln.call(options);
}

function getCreditCard(callback) {
    var options = {
        method: 'get',
        url: '/common/billing/card/info',
        success: callback,
        error: sln.showAjaxError
    };
    sln.call(options);
}

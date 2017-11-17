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

$(function () {
    'use strict';
    LocalCache.menu = {};
    modules.menu = {
        getMenu: getMenu,
        loadMenu: loadMenu,
        renderMenu: renderMenu
    };
    var CROP_OPTIONS = {
        viewMode: 1,
        dragMode: 'move',
        aspectRatio: 1.777777777
    };
    init();

    function init() {
        ROUTES['menu'] = router;
        $("#menu").find("button[name=newcat]").click(newCategory);
        $("#import_menu").click(importMenu);
        sln.registerMsgCallback(channelUpdates);
    }

    function router(urlHash) {
        getMenu(renderMenu);
    }

    function renderMenu(menu, sourceId) {
        var menuHtmlElement = $("#menu_contents").find("#menu_test");
        var html = $.tmpl(templates.menu, {
            menu: menu,
            t: CommonTranslations,
            isFlagSet: sln.isFlagSet,
            currency: CURRENCY,
            CONSTS: CONSTS,
            menuName: LocalCache.menu.name || CommonTranslations.DEFAULT_MENU_NAME,
            advancedOrder: orderSettings.order_type == CONSTS.ORDER_TYPE_ADVANCED && MODULES.indexOf('order') !== -1,
            showVisibleInCheckboxes: shouldShowVisibility()
        });

        // the menu is loaded, enable adding a new category or editing the name
        $("#menu").find("button[name=newcat]").attr('disabled', false);
        $("#edit_menu_name").attr('disabled', false);

        menuHtmlElement.html(html);
        menuHtmlElement.find('button[action="additem"]').click(addItem);
        menuHtmlElement.find('button[action="deleteitem"]').click(deleteItem);
        menuHtmlElement.find('button[action="editItem"]').click(editItem);
        menuHtmlElement.find('button[action="deletecategory"]').click(deleteCategory);
        menuHtmlElement.find('button[action="editCategory"]').click(editCategory);
        menuHtmlElement.find('button[action="categoryUp"]').click(categoryIndexUp);
        menuHtmlElement.find('button[action="categoryDown"]').click(categoryIndexDown);
        menuHtmlElement.find('button[action="itemUp"]').click(itemIndexUp);
        menuHtmlElement.find('button[action="itemDown"]').click(itemIndexDown);
        menuHtmlElement.find('button[action="editMenuDescription"]').click(editMenuDescription);
        menuHtmlElement.find('button[action="editCategoryDescription"]').click(editCategoryDescription);
        menuHtmlElement.find('button[action="editImage"]').click(editItemImage);
        menuHtmlElement.find('input[name=itemVisibleIn]').change(itemVisibilityChanged);
        menuHtmlElement.find('.mark-all-visible-in').change(markAllVisibleChanged);
        if (sourceId) {
            try {
                $(sourceId).get(0).scrollIntoView();
            } catch (ex) {
                // Backwards compatibility
                setCategoryIndexes();
                saveMenu();
            }
        }

        var category_tables = $("div#menu table.category");
        $.each([1, 2], function (i, itemType) {
            category_tables.each(function () {
                var thizz = $(this);
                if ($("tbody", thizz).find("input:checked[value=" + itemType + "]").length)
                    $("thead", thizz).find("input.mark-all-visible-in[value=" + itemType + "]").prop('checked', true);
            });
        });
    }

    function shouldShowVisibility() {
        return MODULES.indexOf('order') !== -1
            && MODULES.indexOf('menu') !== -1
            && orderSettings.order_type === CONSTS.ORDER_TYPE_ADVANCED;
    }

    function getCategory(categoryId) {
        return LocalCache.menu.categories.filter(function (c) {
            return c.id === categoryId;
        })[0];
    }

    function getItem(category, itemId) {
        return category.items.filter(function (i) {
            return i.id === itemId;
        })[0];
    }

    function moveElementInArray(arr, oldIndex, newIndex) {
        if (newIndex > arr.length) {
            var k = newIndex - arr.length;
            while ((k--) + 1) {
                arr.push(undefined);
            }
        }
        arr.splice(newIndex, 0, arr.splice(oldIndex, 1)[0]);
    }

    function itemVisibilityChanged() {
        var $this = $(this);
        var category = getCategory($this.parents('td').attr('category_id'));
        var item = getItem(category, $this.parents('td').attr('item_id'));
        var checked = $this.prop('checked');
        var itemType = $this.val();
        var menu_div = $("div#menu");
        if (checked) {
            item.visible_in |= itemType;
            // Make sure category is checked
            menu_div.find("table#category-" + category.index).find("thead").find("input.mark-all-visible-in[value=" + itemType + "]").prop('checked', true);
        } else {
            item.visible_in &= ~itemType;
            // Count number of checked after this one was unchecked
            if (!menu_div.find("table#category-" + category.index).find("tbody").find("input:checked[value=" + itemType + "]").length)
                menu_div.find("table#category-" + category.index).find("thead").find("input.mark-all-visible-in[value=" + itemType + "]").prop('checked', false);
        }
        saveMenu(true);
    }

    function markAllVisibleChanged() {
        var $this = $(this);
        var category = getCategory($this.parents('tr').attr('category_id'));
        var checked = $this.prop('checked');
        var itemType = $this.val();
        for (var i = 0; i < category.items.length; i++) {
            if (checked) {
                category.items[i].visible_in |= itemType;
            } else {
                category.items[i].visible_in &= ~itemType;
            }
        }
        $this.parents('table').find('.visibility-checkboxes input[name=itemVisibleIn][value=' + itemType + ']')
            .prop('checked', checked);
        sln.call({
            url: "/common/menu/save",
            type: "POST",
            data: {
                menu: LocalCache.menu
            }
        });
    }

    /**
     * Saves the menu and optionally re-renders it.
     * @param noReload Does not re-render the menu after it has been saved
     * @param sourceId id of the element that triggered the save action (used for scrolling to that element)
     */
    var saveMenu = function (noReload, sourceId) {
        sln.call({
            url: "/common/menu/save",
            type: "POST",
            data: {
                menu: LocalCache.menu
            },
            success: function (data) {
                if (!data.success) {
                    loadMenu(renderMenu);
                    sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                }
            }
        });
        if (!noReload) {
            renderMenu(LocalCache.menu, sourceId);
        }
    };

    function loadMenu(callback) {
        return sln.call({
            url: "/common/menu/load",
            type: "GET",
            success: function (data) {
                LocalCache.menu = data;
                callback(LocalCache.menu);
            }
        });
    }

    function importMenu() {
        var html = $.tmpl(templates.menu_import, {
            t: CommonTranslations
        });

        var modal = sln.createModal(html);

        $('button[action="submit"]', modal).click(function () {
            var fileInput = $('#menuFile', modal)[0];
            if(fileInput.files[0] === undefined) {
                sln.alert(CommonTranslations.please_select_excel_file, null, CommonTranslations.ERROR);
                return;
            }
            var mimeType = fileInput.files[0].type;
            if(mimeType != 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' &&
               mimeType != 'application/vnd.ms-excel') {
                sln.alert(CommonTranslations.invalid_file_format, null, CommonTranslations.ERROR);
                return;
            }
            sln.readFileData(fileInput, function(base64Data) {
                sln.call({
                    showProcessing: true,
                    url: '/common/menu/import',
                    type: 'post',
                    data: {
                        file_contents: base64Data
                    },
                    success: function(data) {
                        if(data.success) {
                            modal.modal('hide');
                            getMenu(renderMenu);
                        } else {
                            sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                        }
                    },
                });
            });
        });
    }

    function getMenu(callback) {
        if (LocalCache.menu.name) {
            callback(LocalCache.menu);
        } else {
            loadMenu(callback);
        }
    }

    var deleteCategory = function () {
        var category = getCategory($(this).parents('tr').attr("category_id"));
        sln.confirm(CommonTranslations.MENU_CATEGORY_DELETE_CONFIRMATION, function () {
            LocalCache.menu.categories.splice(LocalCache.menu.categories.indexOf(category), 1);
            setCategoryIndexes();
            saveMenu();
        });
    };

    function setCategoryIndexes() {
        for (var i = 0; i < LocalCache.menu.categories.length; i++) {
            LocalCache.menu.categories[i].index = LocalCache.menu.categories.indexOf(LocalCache.menu.categories[i]);
        }
    }

    var categoryIndexUp = function () {
        var $this = $(this);
        if ($this.hasClass('disabled'))
            return;
        var category = getCategory($(this).parents('tr').attr("category_id"));
        var index = LocalCache.menu.categories.indexOf(category);
        moveElementInArray(LocalCache.menu.categories, index, index - 1);
        setCategoryIndexes();
        saveMenu(false, '#category-' + LocalCache.menu.categories.indexOf(category));
    };

    var categoryIndexDown = function () {
        var $this = $(this);
        if ($this.hasClass('disabled'))
            return;
        var category = getCategory($(this).parents('tr').attr("category_id"));
        var index = LocalCache.menu.categories.indexOf(category);
        moveElementInArray(LocalCache.menu.categories, index, index + 1);
        setCategoryIndexes();
        saveMenu(false, '#category-' + LocalCache.menu.categories.indexOf(category));
    };

    var itemIndexUp = function () {
        var $this = $(this);
        if ($this.hasClass('disabled'))
            return;
        var category = getCategory($this.parents('td').attr("category_id"));
        var itemId = $this.parents('td').attr("item_id");
        var item = getItem(category, itemId);
        var index = category.items.indexOf(item);
        moveElementInArray(category.items, index, index - 1);
        saveMenu(false, '#category-' + category.index + '-item-' + category.items.indexOf(item));
    };

    var itemIndexDown = function () {
        var $this = $(this);
        if ($this.hasClass('disabled'))
            return;
        var category = getCategory($this.parents('td').attr("category_id"));
        var itemId = $this.parents('td').attr("item_id");
        var item = getItem(category, itemId);
        var index = category.items.indexOf(item);
        moveElementInArray(category.items, index, index + 1);
        saveMenu(false, '#category-' + category.index + '-item-' + category.items.indexOf(item));
    };

    var editCategoryDescription = function () {
        var $this = $(this);
        var buttonCategory = $this.attr('button_category');
        var category = getCategory($this.attr('category_id'));
        var html = $.tmpl(templates.menu_editdescription, {
            header: CommonTranslations.EDIT_DESCRIPTION,
            cancelBtn: CommonTranslations.CANCEL,
            submitBtn: CommonTranslations.SAVE,
            category: category,
            pre: buttonCategory === 'pre'
        });

        var modal = sln.createModal(html, function () {
            $("#itemName", modal).focus();
        });
        $('button[action="submit"]', modal).click(function () {
            var description = $("#description", modal).val();
            if (buttonCategory === "pre") {
                category.predescription = description;
            } else {
                category.postdescription = description;
            }
            saveMenu(false, '#category-' + category.index);
            modal.modal('hide');
        });
    };

    var deleteItem = function () {
        var $this = $(this);
        var itemName = $this.parents('td').attr("item_id");
        var category = getCategory($this.parents('td').attr("category_id"));
        var item = getItem(category, itemName);
        sln.confirm(CommonTranslations.MENU_CATEGORY_ITEM_DELETE_CONFIRMATION, function () {
            category.items.splice(category.items.indexOf(item), 1);
            saveMenu(false, '#category-' + category.index);
        });
    };

    var editMenuDescription = function () {
        var buttonMenu = $(this).attr("button_menu");
        var menuDescription = $(this).attr("button_menu_description");
        var html = $.tmpl(templates.menu_editdescription, {
            header: CommonTranslations.EDIT_DESCRIPTION,
            cancelBtn: CommonTranslations.CANCEL,
            submitBtn: CommonTranslations.SAVE,
            category: {},
            pre: undefined
        });
        $('.modal-body #description', html).val(menuDescription);

        var modal = sln.createModal(html, function () {
            $("#itemName", modal).focus();
        });
        $('button[action="submit"]', modal).click(function () {
            var description = $("#description", modal).val();
            if (buttonMenu == "pre") {
                LocalCache.menu.predescription = description;
            } else {
                LocalCache.menu.postdescription = description;
            }
            saveMenu();
            modal.modal('hide');
        });
    };

    function editItem() {
        var $this = $(this);
        var itemName = $this.parents('td').attr('item_id');
        var category = getCategory($this.parents('td').attr('category_id'));
        var item = getItem(category, itemName);
        var html = $.tmpl(templates.menu_additem, {
            t: CommonTranslations,
            item: item,
            menuName: LocalCache.menu.name || CommonTranslations.DEFAULT_MENU_NAME,
            isFlagSet: sln.isFlagSet,
            units: UNITS,
            CONSTS: CONSTS,
            advancedOrder: orderSettings.order_type == CONSTS.ORDER_TYPE_ADVANCED && MODULES.indexOf('order') !== -1,
            showVisibleInCheckboxes: shouldShowVisibility()
        });

        var modal = sln.createModal(html, function () {
            $("#itemName", modal).focus();
            $('#itemPrice').on('blur', itemPriceBlurred).trigger('blur');
            $('#itemUnit').change(unitChanged).change();
            $('#itemShowPrice').change(showPriceChanged).change();
        });

        $('button[action="submit"]', modal).click(function () {
            var valid = validateFormCategoryItem();
            if (valid) {
                var value = $("#itemName").val();
                if (item.name == value) {
                    // do nothing
                } else {
                    var nameAlreadyInUse = false;
                    $.each(category.items, function (i, item) {
                        if (value == item.name) {
                            nameAlreadyInUse = true;
                            return false;
                        }
                    });
                    if (nameAlreadyInUse) {
                        sln.alert(CommonTranslations.PRODUCT_DUPLICATE_NAME.replace("%(name)s", value), null, CommonTranslations.ERROR);
                        return;
                    }
                }
                var values = getItemFormValues();
                for (var prop in values) {
                    if (values.hasOwnProperty(prop)) {
                        item[prop] = values[prop];
                    }
                }
                saveMenu(false, '#category-' + category.index + '-item-' + category.items.indexOf(item));
                modal.modal('hide');
            }
        });
    }

    function getItemFormValues() {
        var item = {
            id: sln.uuid()
        };
        item.name = $("#itemName").val();
        item.price = Math.round(parseFloat($("#itemPrice").val()) * 100);
        item.has_price = item.price != 0 && $('#itemShowPrice').prop('checked');
        item.description = $("#itemdescription").val();
        item.visible_in = 0;
        item.unit = parseInt($('#itemUnit').val());
        if ($('#itemUnitStepContainer').css('display') !== 'none') {
            item.step = parseInt($('#itemUnitStep').val());
        } else {
            item.step = 1;
        }
        if (!shouldShowVisibility()) {
            item.visible_in = 3; // Visible in menu and order
        } else {
            var menuItem = $('#itemVisibleInMenu');
            var order = $('#itemVisibleInOrder');
            if (menuItem.prop('checked')) {
                item.visible_in |= menuItem.val();
            }
            if (order.prop('checked')) {
                item.visible_in |= order.val();
            }
        }
        return item;
    }

    function editCategory() {
        var $this = $(this);
        var category = getCategory($this.parents('tr').attr('category_id'));
        sln.input(function (value) {
            if (!value.trim())
                return false;
            if (category.name == value) {
                // do nothing
            } else {
                var nameAlreadyInUse = false;
                $.each(LocalCache.menu.categories, function (i, c) {
                    if (value == c.name) {
                        nameAlreadyInUse = true;
                        return false;
                    }
                });
                if (nameAlreadyInUse) {
                    sln.alert(CommonTranslations.CATEGORY_DUPLICATE_NAME.replace("%(name)s", value), null, CommonTranslations.ERROR);
                    return false;
                }
            }
            category.name = value;
            saveMenu(false, '#category-' + category.index);
        }, CommonTranslations.EDIT, CommonTranslations.SAVE, CommonTranslations.ENTER_DOT_DOT_DOT, category.name);
    }

    function addItem() {
        var html = $.tmpl(templates.menu_additem, {
            t: CommonTranslations,
            item: {},
            menuName: LocalCache.menu.name || CommonTranslations.DEFAULT_MENU_NAME,
            isFlagSet: sln.isFlagSet,
            units: UNITS,
            CONSTS: CONSTS,
            advancedOrder: orderSettings.order_type == CONSTS.ORDER_TYPE_ADVANCED && MODULES.indexOf('order') !== -1,
            showVisibleInCheckboxes: shouldShowVisibility()
        });
        var category = getCategory($(this).parents('tr').attr('category_id'));
        var menu_div = $("div#menu");
        // Check the visibility checkboxes by default if the category is checked
        $.each([1, 2], function (i, itemType) {
            var checked = !!menu_div.find("#category-" + category.index).find("thead").find("input:checked[value=" + itemType + "]").length;
            $("input[type=checkbox][name=itemVisibleIn][value=" + itemType + "]", html).prop('checked', checked);
        });
        var modal = sln.createModal(html, function () {
            $("#itemName", modal).focus();
            $('#itemPrice').on('blur', itemPriceBlurred);
            $('#itemUnit').change(unitChanged);
            $('#itemShowPrice').change(showPriceChanged);
        });

        $('button[action="submit"]', modal).click(function () {
            var valid = validateFormCategoryItem();
            if (valid) {
                var value = $("#itemName").val();
                var nameAlreadyInUse = false;
                $.each(category.items, function (i, item) {
                    if (value == item.name) {
                        nameAlreadyInUse = true;
                        return false;
                    }
                });
                if (nameAlreadyInUse) {
                    sln.alert(CommonTranslations.PRODUCT_DUPLICATE_NAME.replace("%(name)s", value), null, CommonTranslations.ERROR);
                } else {
                    category.items.push(getItemFormValues());
                    saveMenu(false, '#category-' + category.index + '-item-' + (category.items.length - 1));
                    modal.modal('hide');
                }
            }
        });
    }

    function unitChanged() {
        var unit = parseInt($(this).val());
        var special = [CONSTS.UNIT_MINUTE, CONSTS.UNIT_GRAM];
        var unitText = ' / ' + CommonTranslations[UNITS[unit]];
        if (special.indexOf(unit) !== -1) {
            $('#itemUnitStepContainer').slideDown();
            $('#selectedSubUnit').text(' ' + CommonTranslations[UNITS[unit]]);
            // Always show 'kilogram' even when 'gram' is selected as prices are always per kg and not per g.
            if (unit === CONSTS.UNIT_GRAM) {
                $('#selectedUnit').text(' / ' + CommonTranslations[UNITS[CONSTS.UNIT_KG]]);
            } else {
                $('#selectedUnit').text(unitText);
            }

        } else {
            $('#selectedUnit').text(unitText);
            $('#itemUnitStepContainer').slideUp();
        }
    }

    function itemPriceBlurred() {
        var value = $(this).val();
        var isNotZero = parseInt(value * 100) !== 0;
        var priceElem = $('#itemShowPrice');
        var isChecked = priceElem.prop('checked');
        priceElem.prop('checked', isNotZero && isChecked).change();
    }

    function showPriceChanged() {
        var checked = $(this).prop('checked');
        $('#itemPrice').attr('disabled', !checked);
    }

    function newCategory() {
        sln.input(function (value) {
            if (!value.trim())
                return false;

            var nameAlreadyInUse = false;
            $.each(LocalCache.menu.categories, function (i, c) {
                if (value == c.name) {
                    nameAlreadyInUse = true;
                    return false;
                }
            });
            if (nameAlreadyInUse) {
                sln.alert(CommonTranslations.CATEGORY_DUPLICATE_NAME.replace("%(name)s", value), null, CommonTranslations.ERROR);
                return false;
            }

            LocalCache.menu.categories.push({
                id: sln.uuid(),
                name: value,
                items: [],
                predescription: null,
                postdescription: null
            });
            setCategoryIndexes();
            saveMenu();
        }, CommonTranslations.MENU_CATEGORY_NEW, CommonTranslations.ADD, CommonTranslations.ENTER_DOT_DOT_DOT);
    }

    function validateFormCategoryItem() {
        var valid = sln.validate($('#nameerror'), $("#itemName"), CommonTranslations.NAME_IS_REQUIRED);
        return valid && sln.validate($('#priceerror'), $("#itemPrice"), CommonTranslations.UNIT_PRICE_IS_REQUIRED);
    }

    $('#edit_menu_name').click(function () {
        var saveMenuName = function (name) {
            sln.call({
                url: "/common/menu/save_name",
                type: "POST",
                data: {
                    name: name
                },
                success: function (data) {
                    if (data.success) {
                        LocalCache.menu.name = name;
                    } else {
                        sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                    }
                }
            });
        };

        sln.input(saveMenuName, CommonTranslations.MENU_NAME, null, null, LocalCache.menu.name || CommonTranslations.DEFAULT_MENU_NAME);
    });

    function channelUpdates(data) {
        if (data.type == 'solutions.common.menu.name_updated') {
            $('#topmenu').find('li[menu="menu"] a').text(data.name);
        } else if (data.type == 'solutions.common.menu.item_image_configured') {
            var category = getCategory(data.category.name);
            if (category) {
                var item = getItem(category, data.item.name);
                if (item) {
                    item.image_id = data.item.image_id;

                    var modal = $('#modal-edit-menu-image');
                    var modalCategory = modal.data('category');
                    var modalItem = modal.data('item');
                    if (modalCategory && modalCategory.name == data.category.name && modalItem && modalItem.name == data.item.name) {
                        modal.find('#existing-image-container').show().find('img').attr('src',
                            '/solutions/common/public/menu/image/' + item.image_id);
                    }
                    $('td[item_id="' + item.name + '"][category="' + category.name + '"] button[action="editImage"]')
                        .addClass('active');
                }
            }
        }
    }

    function editItemImage() {
        var $this = $(this);
        var itemName = $this.parents('td').attr('item_id');
        var category = getCategory($this.parents('td').attr('category_id'));
        var item = getItem(category, itemName);
        renderMenuItemImagePopup(category, item);
    }

    function renderMenuItemImagePopup(menuCategory, menuItem) {
        var html = $.tmpl(templates.menu_edit_image, {
            t: CommonTranslations,
            item: menuItem,
            category: menuCategory
        });
        $('#menu-modal-container').html(html);
        var modal = $('#modal-edit-menu-image').data('category', menuCategory).data('item', menuItem).modal('show');
        var imagePreview = modal.find('#menu-image-upload');
        modal.find('#save-item-image').click(function () {
            // No image selected, hide the modal.
            modal.modal('hide');
        });

        modal.find('#menu-image-upload-file').on('change', function () {
            modal.find('#image-resize-container .hide').show();
            imagePreview.cropper('destroy');
            readFile(this, imagePreview, function () {
                imagePreview.cropper(CROP_OPTIONS);
                modal.find('#save-item-image').unbind('click').click(function () {
                    if ($('#menu-image-upload-file')[0].files.length !== 0) {
                        var croppedImageCanvas = imagePreview.cropper('getCroppedCanvas', {
                            width: 720,
                            height: 404
                        });
                        var resizedImageDataUrl = croppedImageCanvas.toDataURL('image/jpeg', 0.8);
                        uploadItemImage(menuItem, resizedImageDataUrl);
                    } else {
                        modal.modal('hide');
                    }
                });
            });
        });
        modal.find('#remove-menu-item-image').click(function () {
            removeMenuItemImage(menuItem);
        });
        modal.find('#show_qr_code').click(function () {
            modal.find('#upload-picture-container').hide();
            modal.find('#use-smartphone-container').show();
        });
        modal.find('#show_picture_upload').click(function () {
            modal.find('#upload-picture-container').show();
            modal.find('#use-smartphone-container').hide();
        });
        var spinner = $(TMPL_LOADING_SPINNER).css('position', 'relative');
        modal.find('#spinner-container').append(spinner);
        sln.call({
            showProcessing: false,
            url: '/common/menu/item/image/qr_url',
            data: {
                category_index: menuCategory.index,
                item_index: menuCategory.items.indexOf(menuItem)
            },
            success: function (data) {
                modal.find('#qr-code-container').append($('<img>').attr('src', data).load(function () {
                    spinner.remove();
                }));
            },
            error: function () {
            }
        });
    }

    function removeMenuItemImage(menuItem) {
        sln.call({
            url: '/common/menu/item/image/remove',
            type: 'post',
            data: {
                image_id: menuItem.image_id
            },
            success: function (data) {
                menuItem.image_id = null;
                saveMenu();
                $('#existing-image-container').remove();
            }
        });
    }

    function uploadItemImage(menuItem, imageDataUrl) {
        $('#modal-edit-menu-image').modal('hide');
        sln.call({
            url: '/common/menu/item/image/upload',
            type: 'post',
            data: {
                image: imageDataUrl,
                image_id_to_delete: menuItem.image_id || null
            },
            success: function (data) {
                if (data.success) {
                    menuItem.image_id = data.image_id;
                    saveMenu();
                } else {
                    $('#menu-image-upload').cropper('destroy');
                    sln.alert(data.errormsg);
                }
            }
        });
    }

    function readFile(input, targetElement, callback) {
        if (input.files && input.files[0]) {
            var reader = new FileReader();

            reader.onload = function (e) {
                targetElement.attr('src', reader.result);
                callback();
            };
            reader.readAsDataURL(input.files[0]);
        } else {
            sln.showBrowserNotSupported();
        }
    }
});

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

    var TEMPL_SWITCH_BUTTON = '<div class="btn-group switch-button "> \
        <button class="btn {{if state}}btn-success{{/if}}" action="on" name="${name}">{{if state}}${onLabel}{{else}}&nbsp;{{/if}}</button> \
        <button class="btn {{if !state}}btn-danger{{/if}}" action="off" name="${name}">{{if !state}}${offLabel}{{else}}&nbsp;{{/if}}</button> \
        </div>';

    var isLoadingModules = false;
    var activatedModules = [];

    init();

    function init() {
        ROUTES.functionalities = router;
        loadFunctionalities();
        $(document).on('click', '.functionality-settings', goToSettings);
        $(document).on('click', '.functionality-publish-first', showPublishFirstMessage);
    }

    function router() {
        if(!isLoadingModules) {
            loadFunctionalities();
        }
    }

    function showPublishFirstMessage() {
        var html = $.tmpl(TMPL_ALERT, {
            header: CommonTranslations.warning,
            body: CommonTranslations['unpersisted-changes'],
            closeBtn: CommonTranslations.Cancel,
        });
        var modal = sln.createModal(html);
        var publishButton = $('<button class="btn btn-warning pull-left">' + CommonTranslations.publish + '</button>');
        publishButton.click(function() {
            modal.modal('hide');
            modules.settings.publishChanges();
        });
        $('button', modal).last().before(publishButton);
    }

    function showLoadingSpinner() {
        $('#enabled_functionalities_label').hide();
        $('#disabled_functionalities_label').hide();
        $('#enabled_functionalities').before(TMPL_LOADING_SPINNER);
    }

    function hideLoadingSpinner() {
        $('#enabled_functionalities').prev().remove();
        $('#enabled_functionalities_label').show();
        $('#disabled_functionalities_label').show();
    }

    function loadFunctionalities() {
        isLoadingModules = true;
        clear();

        if(activatedModules.length) {
            renderFunctionalities(activatedModules);
            return;
        }

        showLoadingSpinner();
        sln.call({
            url: '/common/functionalities/modules/activated',
            type: 'get',
            success: function(modules) {
                activatedModules = modules;
                hideLoadingSpinner();
                renderFunctionalities(activatedModules);
            },
            error: function() {
                hideLoadingSpinner();
                sln.showAjaxError();
            }
        });
    }

    function renderFunctionalities(modules) {
        var activeCount = 0, inactiveCount = 0;
        $.each(FUNCTIONALITY_MODULES, function(i, module) {
            var enabled = activatedModules.indexOf(module) !== -1;
            var info = FUNCTIONALITY_INFO[module];
            var tile = functionalityTile(info, getCurrentLanguageMedia(info.name), enabled,
                                         module === 'broadcast' && enabled,
                                         PROVISIONED_MODULES.indexOf(module) !== -1);

            setVideoPlaybackHandler(tile, info.title);
            if(enabled) {
                activeCount++;
                $('#enabled_functionalities').append(tile);
            } else {
                inactiveCount++;
                $('#disabled_functionalities').append(tile);
            }
            tile.find('.functionality-settings > div').tooltip();
            tile.find('.functionality-publish-first > div').tooltip();
        });

        $('#enabled_functionalities_label').toggle(activeCount > 0);
        $('#disabled_functionalities_label').toggle(inactiveCount > 0);
        isLoadingModules = false;
    }

    function clear() {
        $('#enabled_functionalities').html('');
        $('#disabled_functionalities').html('');
    }

    function goToSettings() {
        var module = $(this).attr('name');
        var info = FUNCTIONALITY_INFO[module];
        var settingsLink;

        if(info.settings_section) {
            settingsLink = $('li[section=section_settings_' + info.settings_section + '] a');
        } else {
            settingsLink = $('li[section=section_settings_' + module + '] a');
        }

        if(settingsLink.length) {
            // got to settings page first
            $('li[menu=settings] a').click();
            ROUTES.settings(['settings', module]);
            settingsLink.click();
        } else {
            if(typeof ROUTES[module] === 'function') {
                ROUTES[module]();
            }
            $('li[menu=' + module + '] a').click();
        }
        window.scrollTo(0, 0);
    }

    function setModuleState(moduleName, enabled) {
        var index = activatedModules.indexOf(moduleName);
        if(enabled) {
            if(index === -1) {
                activatedModules.push(moduleName);
            }
        } else {
            if(index !== -1) {
                activatedModules.splice(index, 1);
            }
        }

        loadFunctionalities();
    }

    function enableOrDisbleModule(moduleName, enabled) {
        sln.call({
            url: '/common/functionalities/modules/enable',
            type: 'post',
            data: {
                name: moduleName,
                enabled: enabled
            },
            success: function(data) {
                if(!data.success) {
                    sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                    return;
                }
                setModuleState(moduleName, enabled);
            },
            error: sln.showAjaxError
        });
    }

    function getCurrentLanguageMedia(functionality) {
        var media = FUNCTIONALITY_INFO[functionality].media;
        var languageMedia = media[LANGUAGE];

        if (!languageMedia) {
            return media.en; // fallback to EN media
        }

        if(!languageMedia.screenshot_image && LANGUAGE != 'en') {
            languageMedia.screenshot_image = media.en.screenshot_image;
        }
        return languageMedia;
    }

    function functionalityTile(info, media, enabled, hideSwitchButton, showConfig) {
        var tile = $.tmpl(templates['functionalities/functionality'], {
            info: info,
            media: media,
            t: CommonTranslations,
            enabled: enabled,
            showConfig: showConfig,
        });

        if(!hideSwitchButton) {
            var btn = switchButton(info.name, enabled, enableOrDisbleModule,
                                   CommonTranslations.active, CommonTranslations.inactive);
            tile.append(btn);
        }
        return tile;
    }

    function switchButton(name, initState, callback, onLabel, offLabel) {
        onLabel = onLabel ? onLabel : CommonTranslations.Enabled;
        offLabel = offLabel ? offLabel : CommonTranslations.Disabled;
        initState = initState ? initState : false;

        var switchButton = $.tmpl(TEMPL_SWITCH_BUTTON, {
            name: name,
            state: initState,
            onLabel: onLabel,
            offLabel: offLabel,
        });

        var onButton = $('button[action=on]', switchButton);
        var offButton = $('button[action=off]', switchButton);
        onButton.click(stateChanged);
        offButton.click(stateChanged);

        function getCurrentState(button) {
            if(button.hasClass('btn-success')) {
                return true;
            } else if(button.hasClass('btn-danger')){
                return false;
            } else if(button.attr('action') === 'on') {
                return false;
            } else {
                return true;
            }
        }

        function stateChanged() {
            var button = $(this);
            var nextState = !getCurrentState(button);

            if(nextState) {
                onButton.addClass('btn-success').text(onLabel);
                offButton.removeClass('btn-danger').html('&nbsp;');
            } else {
                onButton.removeClass('btn-success').html('&nbsp;');
                offButton.addClass('btn-danger').text(offLabel);
            }

            if(callback) {
                callback(name, nextState);
            }
        }

        return switchButton;
    }

    function setVideoPlaybackHandler(tile, videoTitle) {
        var player = $('.youtube-player', tile);
        var videoId = player.attr('data-yt-id');

        if(!videoId) {
            return;
        }

        player.click(function () {
            $('.video-title').text(videoTitle);
            // open popup with this video
            var iframe = $('<iframe height="100%" frameborder="0" allowfullscreen>');
            iframe.attr('src', '//www.youtube.com/embed/' + videoId + '?autoplay=1&showinfo=1&fs=1');
            $('#video-yt-container').html(iframe);
            $("#video-popup").show()
                .modal('show')
                .on('hidden', function () {
                    $('#video-yt-container').empty();
                });
        });
    }

    function channelUpdates(data) {
        if(data.type === 'common.provision.success') {
            if(data.needs_reload) {
                window.location.reload();
            }
        }
    }

    sln.registerMsgCallback(channelUpdates);

});

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
    'use strict';
    var uitdatabankStatusEnabled = true;
    var gatherEvents = true;
    var TMPL_SET_EVENTS_STATUS = '<div id="uitdatabankStatus" class="alert alert-success">'
        + '    <h4>Uitdatabank.be</h4> <div id="uitdatabankStatusText" >' + CommonTranslations.STATUS_ENABLED + '</div>'
        + '</div>';

    var TMPL_SET_EVENTS_SECRET= '<label>' + CommonTranslations.SECRET + ' (uitdatabank.be v2):</label><input type="text" placeholder="' + CommonTranslations.ENTER_DOT_DOT_DOT + '" class="span4">';
    var TMPL_SET_EVENTS_KEY = '<label>' + CommonTranslations.KEY + ' (uitdatabank.be):</label><input type="text" placeholder="' + CommonTranslations.ENTER_DOT_DOT_DOT + '" class="span4">';

    var TMPL_SET_GATHER_EVENTS = '<div class="btn-group">'
        + '      <button class="btn btn-success" id="gatherEventsEnabled">' + CommonTranslations.GATHER_EVENTS_DISABLED + '</button>'
        + '      <button class="btn" id="gatherEventsDisabled">&nbsp;</button>' + '</div>';

    var gatherEventsEnabled = function() {
        setGatherEvents(!gatherEvents);
        saveCityAppSettings();
    };

    var gatherEventsDisabled = function() {
        setGatherEvents(!gatherEvents);
        saveCityAppSettings();
    };

    var setGatherEvents = function(newGatherEvents) {
        gatherEvents = newGatherEvents;
        if (newGatherEvents) {
            $('#gatherEventsEnabled').addClass("btn-success").text(CommonTranslations.GATHER_EVENTS_ENABLED);
            $('#gatherEventsDisabled').removeClass("btn-danger").html('&nbsp;');
        } else {
            $('#gatherEventsEnabled').removeClass("btn-success").html('&nbsp;');
            $('#gatherEventsDisabled').addClass("btn-danger").text(CommonTranslations.GATHER_EVENTS_DISABLED);
        }
    };

    $(".sln-set-gather-events").html(TMPL_SET_GATHER_EVENTS);
    $('#gatherEventsEnabled').click(gatherEventsEnabled);
    $('#gatherEventsDisabled').click(gatherEventsDisabled);

    $("#topmenu li a").click(menuPress);

    var saveCityAppSettings = function() {
        var allOK = true;
        if ($('.sln-set-events-key input').val() === "") {
            $('.sln-set-events-key input').addClass("error");
            allOK = false;
        } else {
            $('.sln-set-events-key input').removeClass("error");
        }
        if ($('.sln-set-events-regions').data('regions') === null) {
            $('.sln-set-events-regions').addClass("error");
            allOK = false;
        } else {
            $('.sln-set-events-regions').removeClass("error");
        }
        // do post
        var data = JSON.stringify({
            uitdatabank_secret : $('.sln-set-events-secret input').val(),
            uitdatabank_key : $('.sln-set-events-key input').val(),
            uitdatabank_regions : $('.sln-set-events-regions').data('regions'),
            gather_events : gatherEvents,
        });
        sln.call({
            url : "/common/cityapp/settings/save",
            type : "POST",
            data : {
                data : data
            },
            success : function(data) {
                if (!data.success) {
                    sln.alert(data.errormsg, null, CommonTranslations.ERROR);
                } else {
                    sln.call({
                        url : "/common/cityapp/settings/check_uitdatabank",
                        type : "GET",
                        success : function(data) {
                            if (data.success) {
                                setUitdatabankStatus(true);
                            } else {
                                setUitdatabankStatus(false, data.errormsg);
                            }
                        },
                        error : sln.showAjaxError
                    });
                }
            },
            error : sln.showAjaxError
        });
    };

    var loadCityAppSettings = function() {
        sln.call({
            url : "/common/cityapp/settings/load",
            type : "GET",
            success : function(data) {
                // check uitdatabank settings
                var secretElem = $('.sln-set-events-secret input');
                var keyElem = $('.sln-set-events-key input');
                var regionElem = $('.sln-set-events-regions');
                if(secretElem.length && keyElem.length && regionElem.length) {
                    secretElem.data('updateVal')(data.uitdatabank_secret);
                    keyElem.data('updateVal')(data.uitdatabank_key);
                    regionElem.data('regions', data.uitdatabank_regions);
                    setUitdatabankStatus(data.uitdatabank_enabled);
                    renderRegions(data.uitdatabank_regions);
                }
                setGatherEvents(data.gather_events);
            },
            error : sln.showAjaxError
        });
    };

    var setUitdatabankStatus = function (enabled, reason) {
        uitdatabankStatusEnabled = enabled;
        $('#uitdatabankStatus').toggleClass('alert-danger', !enabled).toggleClass('alert-success', enabled);
        var text = CommonTranslations.STATUS_ENABLED;
        if (!enabled) {
            text = CommonTranslations.STATUS_DISABLED + (reason === undefined ? "" : (": " + reason));
        }
        $('#uitdatabankStatusText').text(text);
    };
    
    var deleteRegion = function() {
    	var region = $(this).attr('region');
    	var regionElem = $('.sln-set-events-regions');
    	var index = regionElem.data('regions').indexOf(region);
    	if (index >= 0) {
	    	regionElem.data('regions').splice(index, 1);
	    	renderRegions(regionElem.data('regions'));
            saveCityAppSettings();
	    }
    };
    
    var renderRegions = function(regions) {
    	var htmlElement = $('.sln-set-events-regions table tbody');
    	htmlElement.empty();
    	var html = $.tmpl(templates.events_uitcalendar_settings, {
            regions : regions
        });
    	htmlElement.append(html);
    	htmlElement.find('button[action="deleteRegion"]').click(deleteRegion);
    };

    $(".sln-set-events-status").html(TMPL_SET_EVENTS_STATUS);
    $(".sln-set-events-secret").html(TMPL_SET_EVENTS_SECRET);
    $(".sln-set-events-key").html(TMPL_SET_EVENTS_KEY);
    $(".sln-set-events-uit-settings").show();

    $('#uitdatabankStatusEnabled').click(function() {
        setUitdatabankStatus(!uitdatabankStatusEnabled);
    });
    $('#uitdatabankStatusDisabled').click(function() {
        setUitdatabankStatus(!uitdatabankStatusEnabled);
    });
    
    $('#sln-set-events-add-region').click(function() {
    	sln.input(function (value) {
            if (!value.trim())
                return false;

            var regionElem = $('.sln-set-events-regions');
            regionElem.data('regions').push(value);
            renderRegions(regionElem.data('regions'));
            saveCityAppSettings();
            
        }, CommonTranslations.ADD, CommonTranslations.SAVE, CommonTranslations.ENTER_DOT_DOT_DOT);
    });

    sln.configureDelayedInput($('.sln-set-events-secret input'), saveCityAppSettings);
    sln.configureDelayedInput($('.sln-set-events-key input'), saveCityAppSettings);

    loadCityAppSettings();

    function menuPress() {
        $("#topmenu li").removeClass("active");
        var li = $(this).parent().addClass("active");
        $("div.page").hide();
        $("div#" + li.attr("menu")).show();
    }
});

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
    google.charts.load('current', {packages: ['corechart', 'bar', 'annotationchart']});
    google.charts.setOnLoadCallback(init);
    // Users
    var cursor = null;
    var connectedUsersHistory = [];
    var connectedUsersHistoryValues = [];
    var statisticsLoaded = false;
    var statisticsUsersActiveButNotLoaded = false;
    var statisticsLastWeekGained = 0;
    var statisticsLastWeekLost = 0;
    var statisticsLastMonthGained = 0;
    var statisticsLastMonthLost = 0;
    var usersGraphLoaded = false;
    // Usage
    var usageHistory = [];
    var usageGraphLoaded = false;
    var statisticsUsageActiveButNotLoaded = false;
    var appBroadcasts = {
        loaded: false,
        data: []
    };

    var elemStatistics = $("#statistics");

    var FRIENDS_TEMPLATE = '{{each(i,friend) friends}}' //
            + ' <div class="thumbnail statistics-user-avatar">' //
            + '     <img src="${friend.avatar}" />' //
            + ' <div class="statistics-user-details">' //
            + '     <p title="${friend.app_name}" >' + CommonTranslations.APP + ':  ${friend.app_name}</p>' //
            + '     <p title="${friend.name}" >${friend.name}</p>' //
            + ' </div>' //
            + '</div>' //
            + '{{/each}}';

    var USAGE_TEMPLATE = '{{each(i,mipItem) mip}}' //
            + ' <tr>' //
            + '     <td>${mipItem.name}</td>' //
            + '     <td>${mipItem.lastUsed}</td>' //
            + '     <td>${mipItem.lastWeek}</td>' //
            + '     <td>${mipItem.lastMonth}</td>' //
            + '     <td>${mipItem.lastYear}</td>' //
            + ' </tr>' //
            + '{{/each}}';

    var loading = false;
    var complete = false;
    var loadUsers = function() {
        if (loading || complete)
            return;
        loading = true;
        $("#users-loading").show();
        sln.call({
            url : "/common/friends/load",
            type : "GET",
            data : {
                batch_count : 21,
                cursor : cursor
            },
            success : function(data) {
                loading = false;
                cursor = data.cursor;
                if (!cursor)
                    complete = true;
                showConnectedUsers(data.friends);
                $("#users-loading").hide();
            },
            error : sln.showAjaxError
        });
    };

    var showConnectedUsers = function(friends) {
        var users = $("#statistics #users");
        var html = $.tmpl(FRIENDS_TEMPLATE, {
            friends : friends
        });
        users.append(html);
        var last_child = users.children().last();
        if (isItemVisible(last_child)) {
            loadUsers();
        }
    };

    $(window).scroll(function() {
        if (!cursor)
            return;
        var users = $("#statistics #users");
        var last_child = users.children().last();
        if (isItemVisible(last_child)) {
            loadUsers();
        }
    });

    var isItemVisible = function(elem) {
        var $window = $(window);

        var docViewTop = $window.scrollTop();
        var docViewBottom = docViewTop + $window.height();

        var elemTop = elem.offset().top;
        var elemBottom = elemTop + elem.height();

        return elemBottom <= docViewBottom && elemTop >= docViewTop;
    };

    var showUsage = function(menuItemPress) {
        for (var i = 0; i < menuItemPress.length; i++) {
            var mipItem = {};
            mipItem.name = menuItemPress[i].name;
            var d = lastCountList(menuItemPress[i].data);
            var epoch = d.getTime() / 1000;
            mipItem.epoch = epoch;
            mipItem.lastUsed = sln.formatDate(epoch, false);
            mipItem.lastWeek = countDaysList(menuItemPress[i].data, 7);
            mipItem.lastMonth = countDaysList(menuItemPress[i].data, 30);
            mipItem.lastYear = countDaysList(menuItemPress[i].data, 365);
            usageHistory.push(mipItem);
        }
        usageHistory.sort(function(a, b) {
            if (a.epoch == b.epoch)
                if (a.lastWeek == b.lastWeek)
                    if (a.lastMonth == b.lastMonth)
                        if (a.lastYear == b.lastYear)
                            return 0;
                        else
                            return b.lastYear - a.lastYear;
                    else
                        return b.lastMonth - a.lastMonth;
                else
                    return b.lastWeek - a.lastWeek;

            return b.epoch - a.epoch
        });
        var usage = $("#statistics #usage tbody");
        usage.empty();
        var html = $.tmpl(USAGE_TEMPLATE, {
            mip : usageHistory
        });
        usage.append(html);
    };

    function init() {
        sln.call({
            url: "/common/statistics/load",
            type: "GET",
            success: function (result) {
                var data = result.service_identity_statistics;
                var totalUsers = data.number_of_users;
                if (totalUsers > 0) {
                    $("li[menu='statistics']").removeClass('disabled');
                }

                showUsage(data.menu_item_press);
                for (var i = 0; i < data.users_gained.length; i++) {
                    var gainedToday = data.users_gained[i].count - data.users_lost[i].count;
                    connectedUsersHistoryValues.push(totalUsers);
                    totalUsers -= gainedToday;
                }
                for (var i = 0; i < connectedUsersHistoryValues.length; i++) {
                    var today = new Date(data.users_gained[i].year, data.users_gained[i].month - 1,
                        data.users_gained[i].day);
                    if (i == connectedUsersHistoryValues.length - 1) {
                        connectedUsersHistory.push([today, 0, undefined, undefined]);
                    } else {
                        connectedUsersHistory.push([today, connectedUsersHistoryValues[i], undefined, undefined]);
                    }
                }
                statisticsLastWeekGained = countDaysList(data.users_gained, 7);
                statisticsLastWeekLost = countDaysList(data.users_lost, 7);
                statisticsLastMonthGained = countDaysList(data.users_gained, 31);
                statisticsLastMonthLost = countDaysList(data.users_lost, 31);
                statisticsLoaded = true;
                if (statisticsUsersActiveButNotLoaded) {
                    showConnectedUsersHistoryChart();
                }
                if (statisticsUsageActiveButNotLoaded) {
                    showUsageHistoryChart();
                }

                elemStatistics.find("span#badgeUsersTotal").text(data.number_of_users);
                elemStatistics.find("span#badgeUsersGainedLastWeek").text(statisticsLastWeekGained);
                elemStatistics.find("span#badgeUsersLostLastWeek").text(statisticsLastWeekLost);
                elemStatistics.find("span#badgeUsersGainedLastMonth").text(statisticsLastMonthGained);
                elemStatistics.find("span#badgeUsersLostLastMonth").text(statisticsLastMonthLost);
            },
            error: sln.showAjaxError
        });
    }

    $("#show-users").click(function() {
        loadUsers();
        $(this).fadeOut();
    });

    $("li[menu=statistics] a").click(function() {
        if (usersGraphLoaded)
            return;
        if (!statisticsLoaded)
            statisticsUsersActiveButNotLoaded = true;
        showConnectedUsersHistoryChart();
    });

    $("#statistics li[section=section_usage] a").click(function() {
        if (usageGraphLoaded)
            return;
        if (!statisticsLoaded)
            statisticsUsageActiveButNotLoaded = true;
        showUsageHistoryChart();
    });

    var showConnectedUsersHistoryChart = function() {
        usersGraphLoaded = true;
        var data = new google.visualization.DataTable();
        data.addColumn('date', CommonTranslations.EVENT_DATE);
        data.addColumn('number', CommonTranslations.USERS);
        data.addColumn('string', "Users title"); // Invisible to user
        data.addColumn('string', "Users text"); // Invisible to user
        data.addRows(connectedUsersHistory);
        var chart = new google.visualization.AnnotationChart(document.getElementById('users_statistics'));
        var options = {
            displayZoomButtons: false,
            displayRangeSelector: false,
            fill: 10
        };

        chart.draw(data, options);
    };

    function rgb2hex(rgb) {
        rgb = rgb.match(/^rgba?[\s+]?\([\s+]?(\d+)[\s+]?,[\s+]?(\d+)[\s+]?,[\s+]?(\d+)[\s+]?/i);
        return (rgb && rgb.length === 4) ? "#" + ("0" + parseInt(rgb[1], 10).toString(16)).slice(-2)
                + ("0" + parseInt(rgb[2], 10).toString(16)).slice(-2)
                + ("0" + parseInt(rgb[3], 10).toString(16)).slice(-2) : '';
    }

    function showUsageHistoryChart() {
        usageGraphLoaded = true;
        var fontColorsSite = rgb2hex($('body').css("color"));

        var data_7 = new google.visualization.DataTable();
        data_7.addColumn('string', CommonTranslations.MENU_ITEM_NAME);
        data_7.addColumn('number', CommonTranslations.USED);

        var data_30 = new google.visualization.DataTable();
        data_30.addColumn('string', CommonTranslations.MENU_ITEM_NAME);
        data_30.addColumn('number', CommonTranslations.USED);

        var data_365 = new google.visualization.DataTable();
        data_365.addColumn('string', CommonTranslations.MENU_ITEM_NAME);
        data_365.addColumn('number', CommonTranslations.USED);

        if (usageHistory.length > 0) {
            $("#usage-hidden").css('display', 'none');
            $("#usage").css('display', 'block');
        }

        for (var i = 0; i < usageHistory.length; i++) {
            data_7.addRow([usageHistory[i].name, usageHistory[i].lastWeek]);
            data_30.addRow([usageHistory[i].name, usageHistory[i].lastMonth]);
            data_365.addRow([usageHistory[i].name, usageHistory[i].lastYear]);
        }

        var chart_7 = new google.visualization.PieChart(document.getElementById('usage_statistics_7'));
        var options_7 = {
            'legend': 'none',
            chartArea: {
                left: "2%",
                top: "2%",
                width: "96%",
                height: "96%"
            },
            height: 250,
            width: 250,
            backgroundColor: 'transparent'
        };

        chart_7.draw(data_7, options_7);

        var chart_30 = new google.visualization.PieChart(document.getElementById('usage_statistics_30'));
        var options_30 = {
            'legend': 'none',
            chartArea: {
                left: "2%",
                top: "2%",
                width: "96%",
                height: "96%"
            },
            height: 250,
            width: 250,
            backgroundColor: 'transparent'
        };

        chart_30.draw(data_30, options_30);

        var chart_365 = new google.visualization.PieChart(document.getElementById('usage_statistics_365'));
        var options_365 = {
            'legend': {
                textStyle: {
                    color: fontColorsSite
                }
            },
            chartArea: {
                left: "2%",
                top: "2%",
                width: "96%",
                height: "96%"
            },
            height: 250,
            width: 380,
            backgroundColor: 'transparent'
        };

        chart_365.draw(data_365, options_365);
    }

    var countDaysList = function(list, days) {
        var c = 0;
        for (var i = 0; i <= days && i < list.length; i++) {
            c += list[i].count;
        }
        return c;
    };

    var lastCountList = function(list) {
        var date = new Date();
        for (var i = 0; i < list.length; i++) {
            date = new Date(list[i].year, list[i].month - 1, list[i].day);
            if (list[i].count !== 0) {
                break;
            }
        }
        return date;
    };

    var statisticsTabPress = function() {
        elemStatistics.find("li").removeClass("active");
        var li = $(this).parent().addClass("active");
        elemStatistics.find("section").hide();
        elemStatistics.find("section#" + li.attr("section")).show();
    };

    elemStatistics.find("li a").click(statisticsTabPress);

    $('#inbox-export-button').click(function() {
        sln.call({
            url: '/common/inbox/messages/export',
            data: {
                email: $('#inbox-export-email').val()
            },
            success: function(data) {
                if(data.errormsg) {
                    sln.alert(data.errormsg);
                } else {
                    sln.alert(CommonTranslations.exporting_started, null, CommonTranslations.SUCCESS);
                }
            }
        });
    });
});

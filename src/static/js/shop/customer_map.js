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

(function () {
    'use strict';

    var icons = [{
        icon: getIconUrl('green-fa-check'),
        description: TRANSLATIONS.merchants_with_terminal
    }, {
        icon: getIconUrl('yellow'),
        description: TRANSLATIONS.merchants
    }, {
        icon: getIconUrl('white'),
        description: TRANSLATIONS.community_services
    }, {
        icon: getIconUrl('orange'),
        description: TRANSLATIONS.associations
    }, {
        icon: getIconUrl('blue'),
        description: TRANSLATIONS.care
    }];
    var TYPE_UNSPECIFIED = -1,
        TYPE_NON_PROFIT = 1,
        TYPE_PROFIT = 2,
        TYPE_CITY = 3,
        TYPE_EMERGENCY = 4;
    init();

    function init() {
        getAppServices();
    }

    var getParameterByName = function (name) {
        var match = RegExp('[?&]' + name + '=([^&]*)').exec(window.location.search);
        return match && decodeURIComponent(match[1].replace(/\+/g, ' '));
    };

    function getAppServices() {
        $.getJSON('/customers/map/' + APP_ID + '/services').done(renderMap);
    }

    function renderMap(services) {
        var infoWindow;
        var lat_center = getParameterByName('lat');
        var lon_center = getParameterByName('lon');
        var coordinatesBelgium = new google.maps.LatLng(50.623211, 4.438007);
        var center = lat_center && lon_center ? new google.maps.LatLng(parseFloat(lat_center), parseFloat(lon_center)) : coordinatesBelgium;
        var zoom = parseInt(getParameterByName('zoom') || '8');
        var map = new google.maps.Map($('#map_canvas').get(0), {
            zoom: zoom,
            center: center
        });
        var oms = new OverlappingMarkerSpiderfier(map, {
            keepSpiderfied: true
        });
        $.each(services, function (i, service) {
            service.hash = service.lat + "" + service.lon;
            var icon = getMarkerIcon(service);
            var marker = new google.maps.Marker({
                position: new google.maps.LatLng(service.lat, service.lon),
                map: map,
                icon: icon,
                cursor: 'pointer',
                service: service
            });
            oms.addMarker(marker);
        });
        oms.addListener('click', function (marker) {
            var markerContent = $('#marker_content').html();
            if (infoWindow) {
                infoWindow.close();
            }
            markerContent = markerContent
                .replace('serviceName', marker.service.name || '')
                .replace('serviceDescription', marker.service.description || '')
                .replace('address', marker.service.address ? marker.service.address.replace('\n', '<br />') : '');
            infoWindow = new google.maps.InfoWindow({
                content: markerContent
            });
            google.maps.event.addListener(map, 'closeclick', function () {
                infoWindow = null;
            });
            infoWindow.open(map, marker);
        });

        var legend = $('#legend').get(0);
        for (var key in icons) {
            if (icons.hasOwnProperty(key)) {
                var item = icons[key];
                var div = document.createElement('div');
                div.innerHTML = '<img src="' + item.icon + '" style="vertical-align:middle;"> <span>' + item.description + '</span>';
                legend.appendChild(div);
            }
        }
        map.controls[google.maps.ControlPosition.RIGHT_TOP].push(legend);
    }

    function getMarkerIcon(service) {
        var color;
        switch (service.type) {
            case TYPE_PROFIT:
                color = service.has_terminal ? 'green-fa-check' : 'yellow';
                break;
            case TYPE_NON_PROFIT:
                color = 'orange';
                break;
            case TYPE_EMERGENCY:
                color = 'blue';
                break;
            case TYPE_CITY:
            default:
                color = 'white';
                break;
        }
        return getIconUrl(color);
    }

    function getIconUrl(color) {
        return '/static/images/google-maps-marker-' + color + '.png';
    }
})();

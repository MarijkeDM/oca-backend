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
        var infoWindow,
            markers = {};
        var lat_center = getParameterByName('lat');
        var lon_center = getParameterByName('lon');
        var coordinatesBelgium = new google.maps.LatLng(50.623211, 4.438007);
        var center = lat_center && lon_center ? new google.maps.LatLng(parseFloat(lat_center), parseFloat(lon_center)) : coordinatesBelgium;
        var zoom = parseInt(getParameterByName('zoom') || '8');
        var map = new google.maps.Map($('#map_canvas').get(0), {
            zoom: zoom,
            center: center
        });
        $.each(services, function (i, service) {
            service.hash = service.lat + "" + service.lon;
            var marker = markers[service.hash];
            if (!marker) {
                var icon = getMarkerIcon(service);
                marker = new google.maps.Marker({
                    position: new google.maps.LatLng(service.lat, service.lon),
                    map: map,
                    icon: icon,
                    cursor: 'pointer'
                });
                markers[service.hash] = marker;
            }
            google.maps.event.addListener(marker, 'click', function () {
                var markerContent = $('#marker_content').html();
                if (infoWindow) {
                    infoWindow.close();
                }
                markerContent = markerContent
                    .replace('serviceName', service.name || '')
                    .replace('serviceDescription', service.description || '')
                    .replace('address', service.address ? service.address.replace('/n', '<br />') : '');
                infoWindow = new google.maps.InfoWindow({
                    content: markerContent
                });
                google.maps.event.addListener(map, 'closeclick', function () {
                    infoWindow = null;
                });
                infoWindow.open(map, marker);
            });
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
        if ([TYPE_CITY, TYPE_NON_PROFIT, TYPE_PROFIT].indexOf(service.type) === -1) {
            service.type = 3;
        }
        var color;
        switch (service.type) {
            case TYPE_PROFIT:
                color = service.has_terminal ? 'green-fa-check' : 'yellow';
                break;
            case TYPE_NON_PROFIT:
                color = 'orange';
                break;
            case TYPE_CITY:
                color = 'white';
                break;
        }
        return getIconUrl(color);
    }

    function getIconUrl(color) {
        return '/static/images/google-maps-marker-' + color + '.png';
    }
})();
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

var SLN_CONSTS = {
    LOG_ERROR_URL: "/unauthenticated/mobi/logging/web_error",
    PROCESSING_TIMEOUT: 400
};

var sln;

var TMPL_PROCESSING = '<div class="modal fade">'
 + '<div class="modal-dialog">'
 + '  <div class="modal-content">'
 + '    <div class="modal-header">'
 + '      <button type="button" class="close" data-dismiss="modal" aria-label="Close"><span aria-hidden="true">&times;</span></button>'
 + '      <h4 class="modal-title">${header}</h4>'
 + '    </div>'
 + '    <div class="modal-body">'
 + ' <div class="progress">'
 + ' <div class="progress-bar progress-bar-striped active" role="progressbar" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100" style="width: 100%">'
 + '   <span class="sr-only">Processing ...</span>'
 + ' </div>'
 + '</div>'
 + '    </div>'
 + ' </div><!-- /.modal-content -->'
 + '</div><!-- /.modal-dialog -->'
 + '</div><!-- /.modal -->';

var createLib = function() {
    return {
        BOOTSTRAP_DIALOG_TYPE_DEFAULT : BootstrapDialog.TYPE_DEFAULT,
        BOOTSTRAP_DIALOG_TYPE_INFO : BootstrapDialog.TYPE_INFO,
        BOOTSTRAP_DIALOG_TYPE_PRIMARY : BootstrapDialog.TYPE_PRIMARY,
        BOOTSTRAP_DIALOG_TYPE_SUCCESS : BootstrapDialog.TYPE_SUCCESS,
        BOOTSTRAP_DIALOG_TYPE_WARNING : BootstrapDialog.TYPE_WARNING,
        BOOTSTRAP_DIALOG_TYPE_DANGER : BootstrapDialog.TYPE_DANGER,
        createModal : function(html, onShown) {
            var modal = $(html).modal({
                backdrop : true,
                keyboard : true,
                show : false
            }).on('hidden', function() {
                modal.remove(); // remove from DOM
            });

            if (onShown) {
                modal.on('shown', function() {
                    onShown(modal);
                });
            }
            modal.modal('show');
            return modal;
        },
        _processingModal : null,
        nowUTC: function() {
            return Math.floor(new Date().getTime() / 1000);
        },
        showProcessing : function(title) {
            if (sln._processingModal)
                return;
            var html = $.tmpl(TMPL_PROCESSING, {
                header : title
            });
            sln._processingModal = sln.createModal(html);
        },
        hideProcessing : function() {
            if (!sln._processingModal)
                return;
            sln._processingModal.modal('hide');
            sln._processingModal = null;
        },
        showAjaxError : function(XMLHttpRequest, textStatus, errorThrown) {
            sln.hideProcessing();
            BootstrapDialog.show({
                type: sln.BOOTSTRAP_DIALOG_TYPE_DANGER,
                title: 'Error',
                message: "Could not load from server. Please refresh your browser to continue.",
                onhidden : function() {
                    //window.location.reload();
                }
            });
        },
        call : function(options) {
            var method = options.type || options.method;
            if (!method)
                method = "GET";
            method = method.toUpperCase();
            if(method === 'POST' && options.data && !options.data.data) {
                if(typeof(options.data) !== 'string') {
                    options.data.data = JSON.stringify(options.data);
                }
            }
            if (options.showProcessing)
                sln.showProcessing();
            var success = options.success;
            var error = options.error;
            options.success = function(data, textStatus, XMLHttpRequest) {
                if(options.showProcessing)
                    sln.hideProcessing();
                try {
                    if(success)
                        success(data, textStatus, XMLHttpRequest);
                } catch(err) {
                    sln.logError('Caught exception in success handler of ' + options.url, err);
                }
            }, options.error = function(XMLHttpRequest, textStatus, errorThrown) {
                if(options.showProcessing)
                    sln.hideProcessing();
                if(error) {
                    try {
                        error(XMLHttpRequest, textStatus, errorThrown);
                    } catch(err) {
                        sln.logError('Caught exception in error handler of ' + options.url, err);
                    }
                } else {
                    sln.showAjaxError(XMLHttpRequest, textStatus, errorThrown);
                }
            };
            return $.ajax(options);
        },
        _message_callbacks : [],
        registerMsgCallback : function(f) {
            sln._message_callbacks.push(f);
        },
        unregisterMsgCallback : function(f) {
            var i = sln._message_callbacks.indexOf(f);
            if (i > -1) {
                sln._message_callbacks.splice(i, 1);
            }
        },
        broadcast : function(data) {
            console.log("--------- channel ---------");
            console.log(data)
            $.each(sln._message_callbacks, function(i, callback) {
                try {
                    callback(data);
                } catch (err) {
                    sln.showAjaxError(null, null, err);
                }
            });
        },
        _on_message : function(msg) {
            console.log("--------- channel ---------\n" + msg.data);
            sln.broadcast(JSON.parse(msg.data));
        },
        runChannel : function(token) {
            var closing = false;
            $(window).unload(function() {
                closing = true;
            });
            var onOpen = function() {
                sln.broadcast({
                    type : "rogerthat.channel_connected"
                });
            };
            var onClose = function() {
                BootstrapDialog.show({
                    type: sln.BOOTSTRAP_DIALOG_TYPE_DANGER,
                    title: 'Problem',
                    message: "Could not renew auto updating channel automatically. Reload your browser to resolve the situation.",
                    onhidden : function() {
                        window.location.reload();
                    }
                });
            };
            var channel = new FirebaseChannel(firebaseConfig,
                                              serviceIdentity,
                                              token || firebaseToken,
                                              'channels',
                                              [userChannelId, sessionChannelId],
                                              onOpen,
                                              sln._on_message,
                                              onClose);
            channel.connect();
        },
    }
};

$(document).ready(function() {
    sln = createLib();
    sln.registerMsgCallback(function(data) {
        if (data.type == 'rogerthat.logout') {
            window.location.assign(window.location.origin);
        } else if (data.type == 'rogerthat.dologout') {
            $.ajax({
                hideProcessing : true,
                url : "/logout",
                type : "GET",
                success : function(data, textStatus, XMLHttpRequest) {
                    window.location.reload();
                },
                error : function(XMLHttpRequest, textStatus, errorThrown) {
                    window.location.reload();
                }
            });
        }
    });

    window.onerror = function(msg, url, line, column, error) {
        var stack_trace = '';
        if(column) {
            column = ':' + column;
        }
        if(error) {
            stack_trace = '\n' + printStackTrace({
                    guess: true,
                    e: error
                }).join('\n');
        }
        var errorMsg = msg + '\n in ' + url + ' at line ' + line + column + stack_trace;
        $.ajax({
            hideProcessing: true,
            url: SLN_CONSTS.LOG_ERROR_URL,
            type: "POST",
            data: {
                data: JSON.stringify({
                    description: 'Caught exception in global scope: ' + msg,
                    errorMessage: errorMsg,
                    timestamp: sln.nowUTC(),
                    user_agent: navigator.userAgent
                })
            },
            success: function(data, textStatus, XMLHttpRequest) {
            },
            error: function(XMLHttpRequest, textStatus, errorThrown) {
            }
        });
    };
});

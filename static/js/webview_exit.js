// Wires up any .webview-exit-btn on the page.
// - Inside the pywebview desktop window: calls the exposed Python
//   DesktopApi.exit_app(), which destroys the native window.
// - In a plain browser tab (e.g. testing without pywebview installed):
//   falls back to a confirm + window.close(), which most browsers will
//   only honor for windows opened by script, so we also just show a
//   friendly message if the tab can't be closed programmatically.
(function () {
    function doExit() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.exit_app) {
            window.pywebview.api.exit_app();
            return;
        }
        if (window.confirm('Close this application?')) {
            window.close();
            // window.close() is a no-op in most browsers for tabs the
            // page didn't open itself -- let the user know instead of
            // silently doing nothing.
            setTimeout(function () {
                alert("You're running this in a regular browser tab, so it can't be closed automatically. You can close the tab yourself.");
            }, 150);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.webview-exit-btn').forEach(function (btn) {
            btn.addEventListener('click', doExit);
        });
    });
})();

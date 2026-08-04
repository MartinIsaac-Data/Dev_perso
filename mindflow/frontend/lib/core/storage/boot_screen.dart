/// Dismissing the web boot screen.
///
/// `web/index.html` paints a placeholder before the engine starts, because a
/// Flutter web bundle takes seconds to load on a cold cache and a blank white
/// page for three seconds is indistinguishable from a broken deployment.
///
/// Nothing removes it on its own. The engine appends its own `<flutter-view>`
/// and leaves the rest of the document alone — so without this call the
/// placeholder sits on top of the running application for ever. That is not a
/// hypothetical: the first web build of this client rendered the login screen
/// underneath a boot screen that never went away.
library;

import 'boot_screen_io.dart' if (dart.library.js_interop) 'boot_screen_web.dart'
    as impl;

/// Called once the first frame is scheduled. A no-op everywhere but the web.
void dismissBootScreen() => impl.dismissBootScreen();

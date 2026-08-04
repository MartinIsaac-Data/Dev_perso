/// Removes the placeholder painted by `web/index.html`.
library;

import 'package:web/web.dart' as web;

void dismissBootScreen() {
  web.document.getElementById('boot')?.remove();
}

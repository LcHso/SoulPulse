// Conditional export: uses dart:html implementation on web, stub elsewhere
export 'web_notification_stub.dart'
    if (dart.library.html) 'web_notification_web.dart';

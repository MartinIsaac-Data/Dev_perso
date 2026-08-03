/// Startup wiring for notifications.
///
/// Split from `notification_service.dart` so that file stays testable without a
/// Firebase project or a loaded timezone database — this one owns the platform
/// dependencies, and nothing imports it except `main.dart`.
library;

import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:timezone/data/latest.dart' as tz_data;
import 'package:timezone/timezone.dart' as tz;

import '../time/device_timezone.dart';
import 'notification_service.dart';

/// Load the IANA database and point the notification service at it.
///
/// `zonedSchedule` needs a `TZDateTime`; a toast scheduled in the wrong zone
/// fires at the wrong hour, which is worse than not firing at all.
Future<void> initialiseNotificationTimezone({String? zone}) async {
  try {
    tz_data.initializeTimeZones();
    final name = zone ?? kFallbackTimezone;
    tz.setLocalLocation(tz.getLocation(name));
  } catch (_) {
    // An unknown zone leaves the package's default (UTC). A reminder an hour
    // out is a bug; a crash at startup is an outage.
  }
  setTimezoneConverter((when) => tz.TZDateTime.from(when, tz.local));
}

/// Register the device and mirror the reminder schedule.
///
/// Every step is best effort. A user who declines notifications, or whose
/// Firebase project is misconfigured, still gets a fully working app — the
/// in-app notification centre is the durable record, and push is a courtesy on
/// top of it.
Future<void> bootstrapNotifications(WidgetRef ref) async {
  final coordinator = ref.read(notificationCoordinatorProvider);

  String? token;
  if (transportFor(currentPlatform()) == PushTransport.fcm) {
    token = await _firebaseToken();
  }

  await coordinator.register(pushToken: token);
  // Desktop only: the server has no channel to push to, so the device schedules
  // its own toasts from the reminder list (ADR-040).
  await coordinator.syncLocalSchedule();
}

Future<String?> _firebaseToken() async {
  try {
    if (Firebase.apps.isEmpty) await Firebase.initializeApp();
    final messaging = FirebaseMessaging.instance;
    final settings = await messaging.requestPermission();
    if (settings.authorizationStatus == AuthorizationStatus.denied) return null;
    return await messaging.getToken();
  } catch (error) {
    debugPrint('Firebase indisponible : $error');
    return null;
  }
}

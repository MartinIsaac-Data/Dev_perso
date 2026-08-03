/// Push and local notifications.
///
/// Two delivery paths, and the difference is not cosmetic (ADR-040):
///
/// * **Firebase Cloud Messaging** on Android, iOS and web. The device gets a
///   token, registers it with the API, and the server pushes to it.
/// * **Local scheduling** on Windows, macOS and Linux desktop. An unpackaged
///   desktop build has no push channel at all — `flutter build windows` produces
///   a plain executable, not an MSIX with a WNS channel URI — so the client
///   reads its own reminder list from the API and schedules the toasts itself.
///
/// The consequence, and the reason the server stores locally-scheduled reminders
/// too: two views of "what is scheduled" that cannot be compared will drift. The
/// server records the intent; the device carries it out; the reminder list is
/// the shared truth.
///
/// Everything here degrades to a no-op rather than throwing. A user who declines
/// notification permission must still get a working app, and a Firebase project
/// that is misconfigured must not stop the product from recording thoughts.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show MissingPluginException;
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

import '../api/client.dart';
import '../api/planning_models.dart';
import '../storage/local_prefs.dart';

/// How the current platform can be reached. Mirrors `PushProvider` server-side.
enum PushTransport {
  fcm,
  local,
  none;

  String get wire => name;
}

/// The platform name the API expects.
String currentPlatform() {
  if (kIsWeb) return 'web';
  if (Platform.isAndroid) return 'android';
  if (Platform.isIOS) return 'ios';
  if (Platform.isWindows) return 'windows';
  if (Platform.isMacOS) return 'macos';
  if (Platform.isLinux) return 'linux';
  return 'web';
}

/// Desktop has no push channel in an unpackaged build, so it schedules locally.
PushTransport transportFor(String platform) => switch (platform) {
      'android' || 'ios' || 'web' => PushTransport.fcm,
      'windows' || 'macos' || 'linux' => PushTransport.local,
      _ => PushTransport.none,
    };

/// What the app needs from the notification plumbing. An interface, so tests do
/// not need a Firebase project and desktop does not need a mock method channel.
abstract class NotificationGateway {
  Future<bool> requestPermission();

  /// The push token for this device, or null when there is no push channel.
  Future<String?> obtainToken();

  /// Schedule a toast on the device itself. Used by the local transport.
  Future<void> scheduleLocal({
    required int id,
    required DateTime when,
    required String title,
    required String body,
    String? payload,
  });

  Future<void> cancelAllLocal();

  /// Fired when a notification is tapped. The payload carries the entry id, so
  /// the app can open the right screen.
  Stream<String> taps();
}

/// The real implementation.
class PlatformNotificationGateway implements NotificationGateway {
  PlatformNotificationGateway({FlutterLocalNotificationsPlugin? plugin})
      : _plugin = plugin ?? FlutterLocalNotificationsPlugin();

  final FlutterLocalNotificationsPlugin _plugin;
  final _taps = StreamController<String>.broadcast();
  bool _initialised = false;

  Future<void> _ensureInitialised() async {
    if (_initialised) return;
    _initialised = true;
    await _plugin.initialize(
      const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        iOS: DarwinInitializationSettings(),
        macOS: DarwinInitializationSettings(),
        linux: LinuxInitializationSettings(defaultActionName: 'Ouvrir'),
      ),
      onDidReceiveNotificationResponse: (response) {
        final payload = response.payload;
        if (payload != null && payload.isNotEmpty) _taps.add(payload);
      },
    );
  }

  @override
  Future<bool> requestPermission() async {
    await _ensureInitialised();
    try {
      if (!kIsWeb && Platform.isAndroid) {
        final android = _plugin.resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>();
        return await android?.requestNotificationsPermission() ?? false;
      }
      if (!kIsWeb && (Platform.isIOS || Platform.isMacOS)) {
        final darwin = _plugin.resolvePlatformSpecificImplementation<
            IOSFlutterLocalNotificationsPlugin>();
        return await darwin?.requestPermissions(
                alert: true, badge: true, sound: true) ??
            false;
      }
    } on MissingPluginException {
      // Desktop platforms without the plugin registered, and tests.
      return false;
    }
    return true;
  }

  @override
  Future<String?> obtainToken() async {
    // FCM is wired here by the app entry point, which owns Firebase
    // initialisation. Keeping the dependency out of this file means the desktop
    // build does not link Firebase at all.
    return null;
  }

  @override
  Future<void> scheduleLocal({
    required int id,
    required DateTime when,
    required String title,
    required String body,
    String? payload,
  }) async {
    await _ensureInitialised();
    // `zonedSchedule` needs the timezone database initialised by the caller.
    // A plain `show` at the right moment is not an option: the app will not be
    // running.
    try {
      await _plugin.zonedSchedule(
        id,
        title,
        body,
        _toTzDateTime(when),
        const NotificationDetails(
          android: AndroidNotificationDetails(
            'mindflow_reminders',
            'Rappels',
            channelDescription: 'Rappels MindFlow',
            importance: Importance.high,
            priority: Priority.high,
          ),
          iOS: DarwinNotificationDetails(),
          macOS: DarwinNotificationDetails(),
          linux: LinuxNotificationDetails(),
        ),
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        uiLocalNotificationDateInterpretation:
            UILocalNotificationDateInterpretation.absoluteTime,
        payload: payload,
      );
    } on MissingPluginException {
      // No plugin on this platform: the server-side push path covers it, or the
      // user simply does not get a toast. Never fatal.
    } on ArgumentError {
      // A moment in the past, most likely. Nothing to schedule, nothing to say.
    }
  }

  @override
  Future<void> cancelAllLocal() async {
    await _ensureInitialised();
    try {
      await _plugin.cancelAll();
    } on MissingPluginException {
      // Nothing scheduled, nothing to cancel.
    }
  }

  @override
  Stream<String> taps() => _taps.stream;

  void dispose() => _taps.close();
}

/// Ties the gateway to the API: registers the device, and keeps locally
/// scheduled reminders in step with the server's list.
class NotificationCoordinator {
  NotificationCoordinator({
    required NotificationGateway gateway,
    required MindflowApi api,
    required LocalPrefs prefs,
  })  : _gateway = gateway,
        _api = api,
        _prefs = prefs;

  final NotificationGateway _gateway;
  final MindflowApi _api;
  final LocalPrefs _prefs;

  /// Registers this device and returns whether push is actually available.
  ///
  /// The install id is generated once and kept: registration is keyed on it
  /// rather than on the token, because tokens rotate and keying on one creates
  /// a new device row per rotation — five copies of every reminder.
  Future<bool> register({String? pushToken}) async {
    final platform = currentPlatform();
    final transport = transportFor(platform);
    final installId = await _installId();

    final granted = await _gateway.requestPermission();
    final token = pushToken ??
        (transport == PushTransport.fcm ? await _gateway.obtainToken() : null);

    try {
      await _api.registerDevice(
        installId: installId,
        platform: platform,
        // Honest about what the server can do: claiming FCM without a token
        // would make the dispatcher attempt a push that cannot arrive.
        pushProvider: token != null ? PushTransport.fcm.wire : transport.wire,
        pushToken: token,
      );
    } catch (_) {
      // Registration is best effort. A user who cannot register a device still
      // sees every notification in the in-app centre.
      return false;
    }
    return granted && token != null;
  }

  /// Mirrors the server's scheduled reminders onto the device.
  ///
  /// Only for the local transport. Cancel-then-reschedule rather than a diff:
  /// the list is short, the operation is idempotent, and a diff would need a
  /// local mirror of what is scheduled — a second source of truth, which is the
  /// thing this design is trying to avoid.
  Future<int> syncLocalSchedule() async {
    if (transportFor(currentPlatform()) != PushTransport.local) return 0;

    final List<Reminder> reminders;
    try {
      reminders = await _api.listReminders();
    } catch (_) {
      // Keep whatever is already scheduled: stale reminders beat none.
      return 0;
    }

    await _gateway.cancelAllLocal();
    var scheduled = 0;
    for (final reminder in reminders.where((item) => item.isPending)) {
      if (reminder.remindAt.isBefore(DateTime.now())) continue;
      await _gateway.scheduleLocal(
        // A stable per-reminder id, so rescheduling replaces rather than
        // duplicates. The platform ids are 32-bit, hence the mask.
        id: reminder.id.hashCode & 0x7FFFFFFF,
        when: reminder.remindAt,
        title: reminder.title ?? 'Rappel MindFlow',
        body: reminder.body ?? "C'est le moment.",
        payload: reminder.entryId,
      );
      scheduled += 1;
    }
    return scheduled;
  }

  Stream<String> taps() => _gateway.taps();

  Future<String> _installId() async {
    final existing = await _prefs.getString('install_id');
    if (existing != null && existing.length >= 8) return existing;
    final generated = const Uuid().v4();
    await _prefs.setString('install_id', generated);
    return generated;
  }
}

/// `tz.TZDateTime` without importing the timezone package into every caller.
///
/// `flutter_local_notifications` requires a `TZDateTime`; the app initialises
/// the database at startup and sets the local location, so converting here is
/// safe and keeps the dependency in one file.
dynamic _toTzDateTime(DateTime when) {
  // ignore: avoid_dynamic_calls
  return _tzConverter(when);
}

/// Injected at startup by `main.dart`, which owns the timezone initialisation.
/// A function pointer rather than a direct import so this file stays testable
/// without the platform database loaded.
// ignore: prefer_function_declarations_over_variables
dynamic Function(DateTime) _tzConverter = (when) => when;

void setTimezoneConverter(dynamic Function(DateTime) converter) {
  _tzConverter = converter;
}

final notificationGatewayProvider = Provider<NotificationGateway>((ref) {
  final gateway = PlatformNotificationGateway();
  ref.onDispose(gateway.dispose);
  return gateway;
});

final notificationCoordinatorProvider =
    Provider<NotificationCoordinator>((ref) {
  return NotificationCoordinator(
    gateway: ref.watch(notificationGatewayProvider),
    api: ref.watch(apiProvider),
    prefs: ref.watch(localPrefsProvider),
  );
});

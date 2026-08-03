/// The notification centre.
///
/// This screen is the durable record — the server writes a notification row
/// *before* attempting any push, so a user whose phone was unreachable still
/// finds it here. Which is why the empty state says "aucune notification" and
/// not "check your phone settings".
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../core/api/errors.dart';
import '../../core/api/planning_models.dart';
import '../../core/design/components.dart';
import '../../core/design/tokens.dart';
import '../../core/ui/formatting.dart';
import 'planning_providers.dart';

class NotificationsScreen extends ConsumerWidget {
  const NotificationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final centre = ref.watch(notificationsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: [
          centre.maybeWhen(
            data: (data) => data.unread == 0
                ? const SizedBox.shrink()
                : TextButton(
                    onPressed: () => ref
                        .read(planningActionsProvider)
                        .markAllNotificationsRead(),
                    child: const Text('Tout marquer comme lu'),
                  ),
            orElse: () => const SizedBox.shrink(),
          ),
          const SizedBox(width: Space.sm),
        ],
      ),
      body: centre.when(
        loading: () => const MfSkeletonList(),
        error: (error, _) => MfEmpty(
          icon: Icons.notifications_off_outlined,
          title: 'Notifications indisponibles',
          message: error is ApiException ? error.userMessage : null,
        ),
        data: (data) => data.items.isEmpty
            ? const MfEmpty(
                icon: Icons.notifications_none,
                title: 'Aucune notification',
                message: 'Les rappels que vous programmez apparaîtront ici.',
              )
            : RefreshIndicator(
                onRefresh: () async {
                  ref.invalidate(notificationsProvider);
                  await ref.read(notificationsProvider.future);
                },
                child: MfContentColumn(
                  padding: EdgeInsets.zero,
                  child: ListView.separated(
                    padding: const EdgeInsets.symmetric(vertical: Space.sm),
                    itemCount: data.items.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (context, index) => _NotificationTile(
                      key: ValueKey(data.items[index].id),
                      notification: data.items[index],
                    ),
                  ),
                ),
              ),
      ),
    );
  }
}

class _NotificationTile extends ConsumerWidget {
  const _NotificationTile({required this.notification, super.key});

  final AppNotification notification;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final (icon, color) = _iconFor(notification.kind, scheme);

    return InkWell(
      onTap: () async {
        if (notification.unread) {
          await ref
              .read(planningActionsProvider)
              .markNotificationRead(notification.id);
        }
        if (!context.mounted) return;
        final entryId = notification.entryId;
        if (entryId != null) unawaited(context.push(Routes.note(entryId)));
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: Space.lg,
          vertical: Space.md,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // The unread marker is a dot beside the icon rather than a
            // background tint: a tinted row is hard to read and impossible to
            // tell apart from "selected".
            SizedBox(
              width: 8,
              child: notification.unread
                  ? Container(
                      width: 6,
                      height: 6,
                      margin: const EdgeInsets.only(top: 6),
                      decoration: BoxDecoration(
                        color: scheme.primary,
                        shape: BoxShape.circle,
                      ),
                    )
                  : null,
            ),
            const SizedBox(width: Space.sm),
            Icon(icon, size: 16, color: color),
            const SizedBox(width: Space.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    notification.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontWeight: notification.unread
                          ? FontWeight.w600
                          : FontWeight.w400,
                    ),
                  ),
                  if (notification.body != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      notification.body!,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodySmall,
                    ),
                  ],
                  const SizedBox(height: Space.xs),
                  MfMeta(label: formatRelativePast(notification.createdAt)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  static (IconData, Color) _iconFor(
          NotificationKind kind, ColorScheme scheme) =>
      switch (kind) {
        NotificationKind.reminder => (
            Icons.notifications_active_outlined,
            scheme.primary
          ),
        NotificationKind.dueSoon => (Icons.schedule, scheme.tertiary),
        NotificationKind.overdue => (Icons.error_outline, scheme.error),
        NotificationKind.captureReady => (Icons.auto_awesome, scheme.primary),
        NotificationKind.captureFailed => (
            Icons.warning_amber_outlined,
            scheme.error
          ),
        NotificationKind.reviewPending => (Icons.help_outline, scheme.tertiary),
        NotificationKind.digest => (
            Icons.summarize_outlined,
            scheme.onSurfaceVariant
          ),
        NotificationKind.system || NotificationKind.unknown => (
            Icons.info_outline,
            scheme.onSurfaceVariant
          ),
      };
}

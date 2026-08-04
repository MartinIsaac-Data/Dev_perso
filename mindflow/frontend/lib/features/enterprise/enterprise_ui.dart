/// Small shared pieces for the enterprise screens.
///
/// They live here rather than in `core/design` because they encode phase-4
/// wording, not phase-4 layout — and the wording is the part that matters. A
/// refused action must say *why* in terms the user can act on: « demandez à un
/// administrateur » is actionable, « 403 Forbidden » is not.
library;

import 'package:flutter/material.dart';

import '../../core/api/errors.dart';

/// What to show when a read fails. Falls back to a generic sentence rather than
/// a stack trace: an exception type in the interface tells the user nothing and
/// tells an attacker something.
String describeError(Object error) => switch (error) {
      ApiException(:final code, :final userMessage) =>
        code == 'permission_denied'
            ? "Vous n'avez pas les droits nécessaires. "
                'Demandez à un administrateur du compte.'
            : userMessage,
      _ => 'Une erreur est survenue. Réessayez dans un instant.',
    };

void showErrorSnack(BuildContext context, Object error) {
  ScaffoldMessenger.of(context)
      .showSnackBar(SnackBar(content: Text(describeError(error))));
}

void showMessage(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
}

/// A one-field prompt. Returns null when dismissed — distinct from an empty
/// string, which is somebody deliberately clearing the field.
Future<String?> promptForText(
  BuildContext context, {
  required String title,
  required String hint,
  String confirm = 'Valider',
  String? initial,
  String? helper,
}) {
  final controller = TextEditingController(text: initial);
  return showDialog<String>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: controller,
            autofocus: true,
            decoration: InputDecoration(hintText: hint, helperText: helper),
            onSubmitted: (value) => Navigator.of(context).pop(value),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Annuler'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(controller.text),
          child: Text(confirm),
        ),
      ],
    ),
  );
}

/// Confirmation for an action that cannot be undone.
///
/// Deliberately absent from archiving a workspace: a confirmation on a
/// reversible action trains people to dismiss confirmations, which is how the
/// irreversible one gets confirmed without being read.
Future<bool> confirmDestructive(
  BuildContext context, {
  required String title,
  required String message,
  String confirm = 'Confirmer',
}) async {
  final answer = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Annuler'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(true),
          child: Text(confirm),
        ),
      ],
    ),
  );
  return answer ?? false;
}

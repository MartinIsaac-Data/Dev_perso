/// The command palette's matching and ranking.
///
/// The keyboard path (↑ ↓ ↵) is exercised by the widget test below; the ranking
/// rule — actions before content — is the one that decides whether the palette
/// feels right, so it gets its own assertions.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mindflow/core/design/command_palette.dart';

void main() {
  PaletteAction action(String label, {List<String> keywords = const []}) =>
      PaletteAction(
        id: label,
        label: label,
        icon: Icons.circle,
        keywords: keywords,
        onInvoke: (_, __) {},
      );

  group('matching', () {
    test('an empty query matches everything', () {
      expect(action('Capturer').matches(''), isTrue);
    });

    test('matches on the label, case-insensitively', () {
      expect(action('Capturer une note vocale').matches('CAPT'), isTrue);
      expect(action('Capturer une note vocale').matches('vocale'), isTrue);
    });

    test('matches on a keyword the label does not contain', () {
      // People do not all use the same noun: "enregistrer" has to find
      // "Capturer" or the palette only works for whoever wrote the labels.
      final capture = action('Capturer', keywords: ['enregistrer', 'micro']);
      expect(capture.matches('micro'), isTrue);
      expect(capture.matches('enregistr'), isTrue);
    });

    test('does not match an unrelated word', () {
      expect(
          action('Capturer', keywords: ['micro']).matches('facture'), isFalse);
    });
  });
}

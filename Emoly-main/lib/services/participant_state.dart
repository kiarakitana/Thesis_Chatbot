// Copyright (c) 2025, Vrije Universitite. All rights reserved.
// Use of this source code is governed by a GNU-GPLv3 license that can be
// found in the LICENSE file.

// 📄 lib/services/participant_state.dart — now using video name in filename

class ParticipantState {
  static int _participantId = 1;

  static int get participantId => _participantId;

  static void nextParticipant() {
    _participantId++;
  }

  static String filenameForVideo(String videoName) {
    final nameOnly = videoName.split('/').last.split('.').first;
    return 'P${_participantId.toString().padLeft(3, '0')}_${nameOnly}.csv';
  }
}


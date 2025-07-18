// Copyright (c) 2025, Vrije Universitite. All rights reserved.
// Use of this source code is governed by a GNU-GPLv3 license that can be
// found in the LICENSE file.

// 📄 self_assessment_screen.dart — Patched to use live sensor data
// 📄 self_assessment_screen.dart — MQTT logic commented, CSV logging retained
// 📄 self_assessment_screen.dart — updated to remove ParticipantState and MQTT
// 📄 self_assessment_screen.dart — updated to use video-based CSV naming
// 📄 self_assessment_screen.dart — patched to save CSV to Downloads

import 'dart:convert';
import 'dart:io';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import '../services/sensor_stream_channel.dart';

class SelfAssessmentScreen extends StatefulWidget {
  final String participantId;
  final String videoName;

  const SelfAssessmentScreen({Key? key, required this.participantId, required this.videoName})
      : super(key: key);

  @override
  _SelfAssessmentScreenState createState() => _SelfAssessmentScreenState();
}

class _SelfAssessmentScreenState extends State<SelfAssessmentScreen> {
  int valenceScore = 5;
  int arousalScore = 5;
  int dominanceScore = 5;
  int familiarityScore = 5;

  String? selectedEmotion1;
  String? selectedEmotion2;
  final List<String> emotionOptions = [
    '😊 Joyful/Happy',
    '😂 Amusement',
    '😢 Sadness',
    '😠 Angry',
    '🤢 Disgust',
    '😐 Neutral'
  ];

  int heartRate = 0;
  String ppgGreen = '';
  String ppgIR = '';
  String ppgRed = '';

  StreamSubscription<Map<String, dynamic>>? _sensorSubscription;

  @override
  void initState() {
    super.initState();
    SensorStreamChannel.init(); // Initialize sensor socket connection
    listenToSensorStream();
  }

  void listenToSensorStream() {
    _sensorSubscription = SensorStreamChannel.sensorDataStream.listen((data) {
      final type = data['type'];
      final value = data['value'];

      if (!mounted) return;

      setState(() {
        if (type == 'heart_rate_continuous') {
          heartRate = int.tryParse(value.split(',').first) ?? heartRate;
        } else if (type == 'ppg_continuous') {
          final parts = value.split(',');
          ppgGreen = parts.length > 0 ? parts[0] : '';
          ppgIR = parts.length > 1 ? parts[1] : '';
          ppgRed = parts.length > 2 ? parts[2] : '';
        }
      });
    });
  }

  void submitSelfAssessment() async {
    final timestamp = DateTime.now().toIso8601String();
    final payload = {
      'timestamp': timestamp,
      'participant': widget.participantId,
      'video': widget.videoName,
      'valence': valenceScore,
      'arousal': arousalScore,
      'dominance': dominanceScore,
      'familiarity': familiarityScore,
      'emotion1': selectedEmotion1 ?? '',
      'emotion2': selectedEmotion2 ?? '',
      'heartRate': heartRate,
      'ppg_green': ppgGreen,
      'ppg_ir': ppgIR,
      'ppg_red': ppgRed,
    };

    SensorStreamChannel.logSelfAssessment(payload);

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Submitted')),
    );

    Navigator.pop(context);
  }

  Future<String> getDownloadsPath() async {
    if (await Permission.storage.request().isGranted) {
      final downloadsDir = Directory('/storage/emulated/0/Download');
      if (await downloadsDir.exists()) {
        return downloadsDir.path;
      }
    }
    // fallback to app docs directory
    final dir = await getApplicationDocumentsDirectory();
    return dir.path;
  }

  Future<void> saveSelfAssessmentToCSV(Map<String, dynamic> data) async {
    final path = await getDownloadsPath();
    final sanitizedVideo = widget.videoName.replaceAll(".mp4", "").replaceAll(".mp3", "");
    final filename = "P${widget.participantId.padLeft(3, '0')}_${sanitizedVideo}_response.csv";
    final file = File('$path/$filename');

    final csvLine = [
      data['timestamp'],
      data['participant'],
      data['video'],
      data['valence'],
      data['arousal'],
      data['dominance'],
      data['familiarity'],
      data['emotion1'],
      data['emotion2'],
      data['heartRate'],
      data['ppg_green'],
      data['ppg_ir'],
      data['ppg_red'],
    ].join(',') + '\n';

    final exists = await file.exists();
    if (!exists) {
      await file.writeAsString(
        'timestamp,participant,video,valence,arousal,dominance,familiarity,emotion1,emotion2,heartRate,ppg_green,ppg_ir,ppg_red\n',
        mode: FileMode.writeOnly,
      );
    }

    await file.writeAsString(csvLine, mode: FileMode.append);
  }

  @override
  void dispose() {
    _sensorSubscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(title: const Text('Self-Assessment')),
      body: Padding(
        padding: const EdgeInsets.all(24.0),
        child: SingleChildScrollView(
          child: Column(
            children: [
              buildLabeledSlider(
                title: '😊 Valence',
                description: "How pleasant or unpleasant did you feel?",
                value: valenceScore,
                onChanged: (value) => setState(() => valenceScore = value),
                imagePath: 'assets/sam/valence.png',
              ),
              buildLabeledSlider(
                title: '⚡ Arousal',
                description: "How calm or excited were you during the video?",
                value: arousalScore,
                onChanged: (value) => setState(() => arousalScore = value),
                imagePath: 'assets/sam/arousal.png',
              ),
              buildLabeledSlider(
                title: '🧠 Dominance',
                description: "How in control or overwhelmed did you feel?",
                value: dominanceScore,
                onChanged: (value) => setState(() => dominanceScore = value),
                imagePath: 'assets/sam/dominance.png',
              ),
              buildLabeledSlider(
                title: '👀 Familiarity',
                description: "How familiar was the content to you?",
                value: familiarityScore,
                onChanged: (value) => setState(() => familiarityScore = value),
                imagePath: 'assets/sam/familiarity.png',
              ),
              const SizedBox(height: 16),
              buildEmotionDropdown(
                label: '🎝 First emotion that best describes your feeling:',
                value: selectedEmotion1,
                onChanged: (val) => setState(() => selectedEmotion1 = val),
              ),
              buildEmotionDropdown(
                label: '🎝 Second emotion:',
                value: selectedEmotion2,
                onChanged: (val) => setState(() => selectedEmotion2 = val),
              ),
              const SizedBox(height: 30),
              ElevatedButton(
                onPressed: submitSelfAssessment,
                child: Text('Submit'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget buildLabeledSlider({
    required String title,
    required String description,
    required int value,
    required ValueChanged<int> onChanged,
    required String imagePath,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        Text(description, style: TextStyle(color: Colors.grey[600])),
        const SizedBox(height: 8),
        Image.asset(imagePath, height: 100),
        Slider(
          value: value.toDouble(),
          min: 1,
          max: 9,
          divisions: 8,
          label: value.toString(),
          onChanged: (val) => onChanged(val.round()),
        ),
        const SizedBox(height: 24),
      ],
    );
  }

  Widget buildEmotionDropdown({
    required String label,
    required String? value,
    required ValueChanged<String?> onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontSize: 16)),
          const SizedBox(height: 8),
          DropdownButton<String>(
            isExpanded: true,
            value: value,
            hint: const Text("Choose an emotion"),
            items: emotionOptions.map((emotion) {
              return DropdownMenuItem<String>(
                value: emotion,
                child: Text(emotion),
              );
            }).toList(),
            onChanged: onChanged,
          ),
        ],
      ),
    );
  }
}

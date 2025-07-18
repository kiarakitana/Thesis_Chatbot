// Copyright (c) 2025, Vrije Universitite. All rights reserved.
// Use of this source code is governed by a GNU-GPLv3 license that can be
// found in the LICENSE file.

// 📄 lib/services/sensor_stream_channel.dart — Updated for watch socket integration
// 📄 lib/services/sensor_stream_channel.dart — Acts as a socket server
// 📄 lib/services/sensor_stream_channel.dart — Patched for continuous write to single CSV per participant
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:permission_handler/permission_handler.dart';

class SensorStreamChannel {
  static final StreamController<Map<String, dynamic>> _sensorDataController =
      StreamController<Map<String, dynamic>>.broadcast();

  static Stream<Map<String, dynamic>> get sensorDataStream =>
      _sensorDataController.stream;

  static String? _currentParticipantId;
  static String? _currentVideoName = "";
  static bool _isLogging = false;
  static IOSink? _activeSink;
  static File? _activeFile;

  static ServerSocket? _serverSocket;
  static Socket? _watchSocket;

  static const int port = 9003;

  static void setSessionIdentifiers({required String participantId, required String videoName}) {
    _currentParticipantId = participantId;
    _currentVideoName = videoName;
    print("✅ Session Identifiers set: $participantId | $videoName");
  }

  static void setCurrentVideoName(String name) {
    _currentVideoName = name;
  }

  static Future<void> startLogging(String participantId) async {
    _currentParticipantId = participantId;
    _isLogging = true;
    final hasPermission = await _ensureStoragePermission();
    if (!hasPermission) {
      print('❌ Storage permission not granted');
      return;
    }
    final dir = Directory('/storage/emulated/0/Download');
    final filename = 'P$participantId.csv';
    _activeFile = File('${dir.path}/$filename');

    final exists = await _activeFile!.exists();
    _activeSink = _activeFile!.openWrite(mode: FileMode.append);
    if (!exists) {
      _activeSink!.writeln(
        'timestamp,participant_id,clip_name,sensor_type,sensor_channel,value,unit'
      );
    }

    print("📡 Logging to file: $filename");
  }

  static Future<void> stopLogging() async {
    _isLogging = false;
    await _activeSink?.flush();
    await _activeSink?.close();
    print("📴 Logging stopped and file closed");
  }

  static Future<void> init() async {
    print("🔧 init() called – about to start server");
    await _startSocketServer();
    print("🔧 server future completed");
    // Subscribe to the sensor data stream and write to CSV when logging
    sensorDataStream.listen((item) {
      if (_isLogging && _activeSink != null) {
        final rawTimestamp = int.tryParse(item['timestamp'].toString());
        final timestamp = rawTimestamp != null
            ? DateTime.fromMillisecondsSinceEpoch(rawTimestamp).toIso8601String()
            : item['timestamp'].toString();
        final type = item['type'].toString();
        final valStr = item['value'].toString();
        // parse sensor values into dedicated columns
        final parts = valStr.split(',');
        // Write rows for each channel/value
        if (type == 'heart_rate_continuous') {
          if (parts.isNotEmpty) {
            final hr = parts[0];
            _activeSink!.writeln([
              timestamp,
              _currentParticipantId ?? '',
              _currentVideoName ?? '',
              'heart_rate',
              '',
              hr,
              'bpm'
            ].join(','));
          }
          // Write IBI values if present as a field in the item
          if (item.containsKey('ibiList') && item['ibiList'] is List) {
            final ibiList = item['ibiList'] as List;
            for (int i = 0; i < ibiList.length; i++) {
              final ibiVal = ibiList[i];
              _activeSink!.writeln([
                timestamp,
                _currentParticipantId ?? '',
                _currentVideoName ?? '',
                'heart_rate',
                'ibi_$i',
                ibiVal,
                'ms'
              ].join(','));
            }
          }
        } else if (type == 'accelerometer') {
          // x, y, z axes
          final channels = ['x', 'y', 'z'];
          final units = 'g';
          for (var i = 0; i < parts.length && i < 3; i++) {
            _activeSink!.writeln([
              timestamp,
              _currentParticipantId ?? '',
              _currentVideoName ?? '',
              'accelerometer',
              channels[i],
              parts[i],
              units
            ].join(','));
          }
        } else if (type == 'skin_temperature_continuous') {
          // object temp, ambient temp
          if (parts.isNotEmpty) {
            _activeSink!.writeln([
              timestamp,
              _currentParticipantId ?? '',
              _currentVideoName ?? '',
              'skin_temperature',
              'object',
              parts[0],
              'C'
            ].join(','));
          }
          if (parts.length > 1) {
            _activeSink!.writeln([
              timestamp,
              _currentParticipantId ?? '',
              _currentVideoName ?? '',
              'skin_temperature',
              'ambient',
              parts[1],
              'C'
            ].join(','));
          }
        }
        // Add additional sensor types here if needed

        /*
        // --- PPG Green logging (currently disabled; uncomment to enable) ---
        else if (type == 'ppg_green') {
          // Write PPG Green value to CSV
          // You may want to use 'green' as the channel name, or leave it blank
          _activeSink!.writeln([
            timestamp,
            _currentParticipantId ?? '',
            _currentVideoName ?? '',
            'ppg_green',
            '', // or 'green'
            valStr,
            '' // unit unknown, leave blank or fill in if known
          ].join(','));
        }
        // --- End PPG Green logging ---
        */
      }
    });
  }

  static bool _isValidSensorPayload(Map<String, dynamic> data) {
    return data.containsKey("timestamp") &&
           data.containsKey("type") &&
           data.containsKey("value") &&
           data["timestamp"] != null &&
           data["type"] != null &&
           data["value"] != null;
  }

  static Future<void> _startSocketServer() async {
    print("🔧 binding to 0.0.0.0:$port");
    try {
      _serverSocket = await ServerSocket.bind(InternetAddress.anyIPv4, port, shared: true);
      print("🛰️ Phone app listening on port $port");
      _serverSocket!.listen(
        (client) {
          _watchSocket = client;
          print("🔌 Galaxy Watch connected: ${client.remoteAddress.address}");

          client
              .cast<List<int>>()
              .transform(utf8.decoder)
              .transform(const LineSplitter())
              .listen(
                (line) {
                  print("📩 Raw line from watch: $line");
                  try {
                    final parsed = jsonDecode(line.trim());
                    if (parsed is List) {
                      for (final item in parsed) {
                        _handleIncomingSensorData(item);
                      }
                    } else if (parsed is Map<String, dynamic>) {
                      _handleIncomingSensorData(parsed);
                    } else {
                      print("⚠️ Ignored malformed or incomplete JSON: $parsed");
                    }
                  } catch (e) {
                    print("❌ JSON parse error: $e");
                  }
                },
                onError: (e) => print("❌ client socket error: $e"),
                onDone: () => print("🔒 client socket closed"),
              );
        },
        onError: (err) => print("❌ server accept error: $err"),
        onDone: () => print("✅ serverSocket closed"),
      );
    } catch (e) {
      print("❌ Failed to start socket server: $e");
    }
  }

  static void _handleIncomingSensorData(Map<String, dynamic> item) {
    if (_isValidSensorPayload(item)) {
      _sensorDataController.add(item);
      // CSV writing is now handled via the stream subscription in init()
    } else {
      print("⚠️ Ignored item: \$item");
    }
  }

  static void stopSensorStream() {
    _watchSocket?.destroy();
    _serverSocket?.close();
    _watchSocket = null;
    _serverSocket = null;
    print("🚩 Socket server shut down");
  }

  static void logSelfAssessment(Map<String, dynamic> data) {
    if (_isLogging && _activeSink != null) {
      final timestamp = DateTime.now().toIso8601String();
      final participant = _currentParticipantId ?? '';
      final video = _currentVideoName ?? '';
      final valence = data['valence']?.toString() ?? '';
      final arousal = data['arousal']?.toString() ?? '';
      final dominance = data['dominance']?.toString() ?? '';
      final familiarity = data['familiarity']?.toString() ?? '';
      final emotion1 = data['emotion1']?.toString() ?? '';
      final emotion2 = data['emotion2']?.toString() ?? '';
      // self-assessment row with sensor fields blank
      final blanks = List<String>.filled(8, '');
      final row = [
        timestamp,
        participant,
        video,
        ...blanks,
        valence,
        arousal,
        dominance,
        familiarity,
        emotion1,
        emotion2
      ].join(',');
      _activeSink!.writeln(row);
      print('💾 CSV line: $row');
    } else {
      print('❌ Cannot log self-assessment, logging not active');
    }
  }

  static Future<bool> _ensureStoragePermission() async {
    final status = await Permission.manageExternalStorage.status;
    if (status.isGranted) return true;
    final result = await Permission.manageExternalStorage.request();
    return result.isGranted;
  }
}

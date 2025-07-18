// Copyright (c) 2025, Vrije Universitite. All rights reserved.
// Use of this source code is governed by a GNU-GPLv3 license that can be
// found in the LICENSE file.

// 📄 lib/screens/video_picker_screen.dart
// 📄 lib/screens/video_picker_screen.dart
import 'package:flutter/material.dart';
import '../services/sensor_stream_channel.dart';
import 'video_player_screen.dart';

class VideoPickerScreen extends StatefulWidget {
  final String participantId;
  const VideoPickerScreen({Key? key, required this.participantId}) : super(key: key);

  @override
  _VideoPickerScreenState createState() => _VideoPickerScreenState();
}

class _VideoPickerScreenState extends State<VideoPickerScreen> {
  List<String> mediaFiles = [
    'assets/videos/video1_fixed.mp4',
    'assets/videos/video2.mp4',
    'assets/videos/video3.mp4',
    'assets/videos/video4.mp4',
    'assets/videos/video5.mp4',
    'assets/videos/video6.mp4',
    'assets/videos/video7.mp4',
    'assets/videos/video8.mp4',
    'assets/videos/video9.mp4',
    'assets/videos/video10_fixed.mp4',
    'assets/videos/video11_fixed.mp4',
    'assets/videos/video12.mp4',
    'assets/videos/video13.mp4',
    'assets/videos/video14_fixed.mp4',
    'assets/videos/video15.mp4',
    'assets/videos/video16.mp4',
    'assets/videos/video17.mp4',
    'assets/videos/video18.mp4',
    'assets/videos/video19.mp4',
    'assets/videos/video20.mp4',
    'assets/videos/video21.mp4',
    'assets/videos/video22.mp4',
    'assets/videos/video23.mp4',
    'assets/videos/video24.mp4',
    'assets/music/Sample 1 - Sad Human Made Bach E Major.mp3',
    'assets/music/Sample 2 - Happy Human Made Bach A Minor.mp3',
    'assets/music/Sample 3 - AI Made Happy Bach A Minor.mp3',
    'assets/music/Sample 4 - AI Made Sad Bach E Major.mp3',
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Select a Video or Audio to Start")),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                ElevatedButton.icon(
                  icon: Icon(Icons.stop_circle),
                  label: Text("Stop Custom Experiment"),
                  onPressed: () async {
                    SensorStreamChannel.stopLogging();
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(content: Text("Experiment data saved")),
                    );
                    Navigator.pop(context);
                  },
                ),
              ],
            ),
          ),
          Expanded(
            child: ListView.builder(
              itemCount: mediaFiles.length,
              itemBuilder: (context, index) {
                final path = mediaFiles[index];
                final isAudio = path.endsWith(".mp3");
                return ListTile(
                  title: Text(path.split("/").last),
                  trailing: Icon(isAudio ? Icons.music_note : Icons.play_arrow),
                  onTap: () {
                    SensorStreamChannel.setCurrentVideoName(path.split("/").last);
                    Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => VideoPlayerScreen(
                          videoPath: path,
                          participantId: widget.participantId,
                          isAudio: isAudio,
                        ),
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

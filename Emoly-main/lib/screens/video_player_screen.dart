// 📄 video_player_screen.dart — patched to start sensor stream when video starts
// 📄 video_player_screen.dart — updated for background recording
// 📄 video_player_screen.dart — now uses participant + video filename for recording
// 📄 video_player_screen.dart — updated with End Experiment button and fullscreen video
// 📄 video_player_screen.dart — updated with End Experiment button and audio support
// 📄 video_player_screen.dart — updated with manual participant ID input and per-video CSV
// 📄 video_player_screen.dart — updated to also save sensor data CSV to Downloads

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';
import 'package:just_audio/just_audio.dart';
import 'self_assessment_screen.dart';
import '../services/sensor_stream_channel.dart';

// Removed native sensor tracking imports

class VideoPlayerScreen extends StatefulWidget {
  final String videoPath;
  final String participantId;
  final bool isAudio;

  const VideoPlayerScreen({
    required this.videoPath,
    required this.participantId,
    this.isAudio = false,
    Key? key,
  }) : super(key: key);

  @override
  State<VideoPlayerScreen> createState() => _VideoPlayerScreenState();
}

class _VideoPlayerScreenState extends State<VideoPlayerScreen> {
  late VideoPlayerController _videoController;
  final AudioPlayer _audioPlayer = AudioPlayer();
  bool _isPlaying = false;
  bool _finished = false;
  bool _isFullscreen = false;

  late String participantId;
  late String videoName;

  @override
  void initState() {
    super.initState();
    participantId = widget.participantId.padLeft(3, '0');
    videoName = widget.videoPath.split("/").last;
    SensorStreamChannel.setSessionIdentifiers(
      participantId: participantId,
      videoName: videoName,
    );
    
    // Removed native sensor start

    final isVideo = widget.videoPath.endsWith(".mp4") || widget.videoPath.endsWith(".mpg");

    if (widget.isAudio) {
      _audioPlayer.setAsset(widget.videoPath).then((_) {
        _audioPlayer.play();
        setState(() => _isPlaying = true);
        _audioPlayer.playerStateStream.listen((state) async {
          if (state.processingState == ProcessingState.completed && !_finished) {
            _finished = true;
            await _handleEndOfPlayback();
          }
        });
      });
    } else if (isVideo) {
      _videoController = VideoPlayerController.asset(widget.videoPath)
        ..initialize().then((_) {
          setState(() {});
          _videoController.play();
        });

      _videoController.addListener(() async {
        if (_videoController.value.position >= _videoController.value.duration && !_finished) {
          _finished = true;
          await _handleEndOfPlayback();
        }
      });
    }
  }

  // Removed native sensor tracking methods

  Future<void> _handleEndOfPlayback() async {
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(
        builder: (context) => SelfAssessmentScreen(
          participantId: participantId,
          videoName: videoName,
        ),
      ),
    );
  }

  @override
  void dispose() {
    if (!widget.isAudio) {
      _videoController.dispose();
    } else {
      _audioPlayer.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Video Player"),
        actions: [
          if (!widget.isAudio)
            IconButton(
              icon: Icon(_isFullscreen ? Icons.fullscreen_exit : Icons.fullscreen),
              onPressed: () {
                setState(() {
                  _isFullscreen = !_isFullscreen;
                });
              },
            ),
        ],
      ),
      body: widget.isAudio
          ? Center(child: Text("Playing audio: \$videoName"))
          : _videoController.value.isInitialized
              ? Column(
                  children: [
                    Expanded(
                      child: Center(
                        child: _isFullscreen
                            ? SizedBox.expand(
                                child: FittedBox(
                                  fit: BoxFit.cover,
                                  child: SizedBox(
                                    width: _videoController.value.size.width,
                                    height: _videoController.value.size.height,
                                    child: VideoPlayer(_videoController),
                                  ),
                                ),
                              )
                            : AspectRatio(
                                aspectRatio: _videoController.value.aspectRatio,
                                child: VideoPlayer(_videoController),
                              ),
                      ),
                    ),
                    VideoProgressIndicator(
                      _videoController,
                      allowScrubbing: true,
                      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
                    ),
                  ],
                )
              : const Center(child: CircularProgressIndicator()),
    );
  }
}

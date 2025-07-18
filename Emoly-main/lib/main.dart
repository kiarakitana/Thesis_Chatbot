// Copyright (c) 2025, Vrije University. All rights reserved.
// Use of this source code is governed by a GNU-GPLv3 license that can be
// found in the LICENSE file.
// 📄 main.dart (ColEmo + Custom Flow + ThemeCubit + Signal Indicators)
// 📄 main.dart — Minimal version with sensor stream setup
// 📄 main.dart — patched to remove MainBloc, ThemeCubit, and ColEmo dependencies
// 📄 main.dart — patched to support dynamic language selection before experiment

import 'dart:convert';
import 'dart:async'; // Added for StreamSubscription
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:emoly_flutter/services/api_service.dart';
import 'package:emoly_flutter/services/sensor_stream_channel.dart';
import 'package:emoly_flutter/screens/chat_screen.dart';

void main() {
  runApp(MyApp()); // Removed const for StatefulWidget
}

// Screen 1: Initial Start Screen
class InitialStartScreen extends StatelessWidget {
  const InitialStartScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Welcome to Aire.'),
      ),
      body: Center(
        child: ElevatedButton(
          onPressed: () {
            Navigator.push(
              context,
              MaterialPageRoute(builder: (context) => const MainBody()),
            );
          },
          child: const Text('Start Session'),
        ),
      ),
    );
  }
}

class MyApp extends StatefulWidget {
  MyApp({super.key}); // Removed const

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  final GlobalKey<NavigatorState> navigatorKey = GlobalKey<NavigatorState>();
  static const _eventChannel = EventChannel('com.example.emoly_flutter/event_channel');
  StreamSubscription? _eventSubscription;

  @override
  void initState() {
    super.initState();
    _eventSubscription = _eventChannel.receiveBroadcastStream().listen((event) {
      print("Flutter MyApp received event: $event");
      if (event == "TRIGGER_CHAT") {
        print("TRIGGER_CHAT event received, navigating to Participant ID screen.");
        // Navigate to MainBody (Participant ID screen), replacing the current screen if it's InitialStartScreen
        // or pushing it if the app is deeper (e.g. already in a chat - though this might need more sophisticated stack management later)
        navigatorKey.currentState?.pushAndRemoveUntil(
          MaterialPageRoute(builder: (context) => const MainBody()), 
          (Route<dynamic> route) => route.isFirst, // Clears stack up to the first route (InitialStartScreen)
        );
      }
    });
  }

  @override
  void dispose() {
    _eventSubscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: navigatorKey, // Assign the navigatorKey
      debugShowCheckedModeBanner: false,
      title: 'Emoly',
      theme: ThemeData(
        brightness: Brightness.dark,
        primarySwatch: Colors.indigo,
      ),
      home: const InitialStartScreen(), // Start with the new InitialStartScreen
    );
  }
}

// Screen 2: Participant ID Input Screen (formerly the main entry point)
class MainBody extends StatefulWidget {
  const MainBody({super.key});

  @override
  State<MainBody> createState() => _MainBodyState();
}

class _MainBodyState extends State<MainBody> {
  final TextEditingController _participantController = TextEditingController(text: '001');
  // Event channel listener is now removed from MainBody and handled in MyApp
  bool _isLoading = false;

  // Handles the entire process of starting a new chat session.
  Future<void> _startChat() async {
    if (_isLoading) return; // Prevent multiple taps while loading

    final id = _participantController.text.trim();
    if (id.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please enter a Participant ID before starting')),
      );
      return;
    }

    setState(() {
      _isLoading = true;
    });

    try {
      // 1. Call the ApiService to start a new chat session.
      final responseData = await ApiService.startNewChatSession(id);

      // 2. Parse the initial data from the server's response.
      final int interventionId = int.tryParse(responseData['intervention_id']?.toString() ?? '0') ?? 0;
      final List<ChatMessage> initialMessages = (responseData['history'] as List)
          .map((item) => ChatMessage.fromJson(item))
          .toList();

      // 3. Start sensor logging.
      SensorStreamChannel.startLogging(id);

      // 4. Navigate to the ChatScreen with the initial data.
      if (mounted) {
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (context) => ChatScreen(
              participantId: id,
              initialInterventionId: interventionId,
              initialMessages: initialMessages,
            ),
          ),
        );
      }
    } catch (e) {
      // Handle errors (e.g., network issues, server errors)
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error starting chat: ${e.toString()}')),
        );
      }
      print('Error in _startChat: $e');
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  void initState() {
    super.initState();
    // EventChannel listener is removed as it's handled by MyApp globally.
  }

  @override
  void dispose() {
    // _eventSubscription?.cancel(); // No longer managing subscription here
    _participantController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.indigo[200],
      appBar: AppBar(
        title: const Text('Emotional change detected', style: TextStyle(fontSize: 18.0)),
        backgroundColor: Colors.indigo[400],
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(20.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              const Text(
                'Some emotions might have stirred up.  \nLet\'s explore it together.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 16.0, color: Colors.black87),
              ),
              const SizedBox(height: 80), // Reduced space
              // Using a separate Text widget for the label for better positioning control
              Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  ' Participant ID',
                  style: TextStyle(
                    fontSize: 14.0,
                    fontWeight: FontWeight.w500,
                    color: Colors.indigo[900],
                  ),
                ),
              ),
              const SizedBox(height: 8.0),
              TextField(
                controller: _participantController,
                decoration: const InputDecoration(
                  // labelText is removed, as the label is now a separate widget
                  hintText: 'Enter your ID',
                  border: OutlineInputBorder(),
                  filled: true,
                  fillColor: Colors.white,
                  contentPadding: EdgeInsets.symmetric(horizontal: 12.0, vertical: 14.0), // Adjusted padding
                ),
                keyboardType: TextInputType.text,
              ),
              const SizedBox(height: 20),
              _isLoading
                  ? const CircularProgressIndicator()
                  : ElevatedButton(
                      onPressed: _startChat,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.indigo[400], // Set button background color
                        foregroundColor: Colors.white, // Set button text color
                      ),
                      child: const Text('Confirm ID and Start Chat'),
                    ),
            ],
          ),
        ),
      ),
    );
  }
}


import 'package:flutter/material.dart';
import 'dart:convert';
import '../services/api_service.dart';

// Data model for a single chat message.
class ChatMessage {
  final String text;
  final bool isUserMessage;

  ChatMessage({required this.text, required this.isUserMessage});

  // Creates a ChatMessage from a JSON object (from the backend).
  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    return ChatMessage(
      text: json['content'] ?? '',
      isUserMessage: json['role'] == 'user',
    );
  }

  // Converts a ChatMessage to a JSON object (for sending to the backend).
  Map<String, String> toJson() {
    return {
      'role': isUserMessage ? 'user' : 'assistant',
      'content': text,
    };
  }
}

// The main chat screen UI.
class ChatScreen extends StatefulWidget {
  final String participantId;
  final int initialInterventionId;
  final List<ChatMessage> initialMessages;

  const ChatScreen({
    Key? key,
    required this.participantId,
    required this.initialInterventionId,
    required this.initialMessages,
  }) : super(key: key);

  @override
  _ChatScreenState createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  
  // State variables that are initialized from the widget's properties.
  late List<ChatMessage> _messages;
  late int _interventionId;
  bool _isBotTyping = false;

  @override
  void initState() {
    super.initState();
    // Initialize the state from the data passed into the widget.
    _messages = widget.initialMessages;
    _interventionId = widget.initialInterventionId;
  }

  // Handles sending a message to the backend via the ApiService.
  Future<void> _sendMessage(String text) async {
    if (text.trim().isEmpty) return;

    final String userMessageText = text.trim();
    _textController.clear();

    // Add the user's message to the UI immediately for a responsive feel.
    ChatMessage userMessage = ChatMessage(text: userMessageText, isUserMessage: true);
    setState(() {
      _messages.add(userMessage);
      _isBotTyping = true;
    });
    _scrollToBottom();

    // Prepare the history for the backend. This is the state of the conversation
    // *before* the new user message was added.
    List<Map<String, String>> historyForBackend = _messages
        .where((m) => m != userMessage) // Exclude the message we just added
        .map((msg) => msg.toJson())
        .toList();

    try {
      // Call the centralized ApiService to send the message.
      final responseData = await ApiService.sendMessage(
        participantId: widget.participantId,
        interventionId: _interventionId,
        message: userMessageText,
        history: historyForBackend,
      );

      setState(() {
      _isBotTyping = false;
    });

    final dynamic botResponse = responseData['bot_response'];
    
    // Properly convert each map in history to ensure all values are strings
    final List<Map<String, String>> updatedHistoryFromServer = [];
    List<dynamic> historyFromServer = responseData['history'] ?? [];
    
    for (var item in historyFromServer) {
      if (item is Map) {
        Map<String, String> convertedItem = {};
        item.forEach((key, value) {
          convertedItem[key.toString()] = value.toString();
        });
        updatedHistoryFromServer.add(convertedItem);
      }
    }

    if (botResponse is List) {
      for (String chunk in botResponse) {
        if (chunk.isNotEmpty) {
          ChatMessage botMessageChunk = ChatMessage(text: chunk, isUserMessage: false);
          setState(() {
            _messages.add(botMessageChunk);
          });
          _scrollToBottom();
          await Future.delayed(const Duration(milliseconds: 500)); // Delay for staggered appearance
        }
      }
    } else if (botResponse is String && botResponse.isNotEmpty) {
      ChatMessage botMessage = ChatMessage(text: botResponse, isUserMessage: false);
      setState(() {
        _messages.add(botMessage);
      });
      _scrollToBottom();
    }

    // Update intervention ID from the latest history entry if available
    if (updatedHistoryFromServer.isNotEmpty) {
      final lastMessageFromServer = updatedHistoryFromServer.last;
      if (lastMessageFromServer.containsKey('intervention_id')) {
        _interventionId = int.tryParse(lastMessageFromServer['intervention_id'].toString()) ?? _interventionId;
      }
    }
    // Note: We are not replacing the entire _messages list from history anymore,
    // as we've manually added the user message and bot response chunks.
    // The history from the server is primarily for context and intervention ID updates.

    } catch (e, s) { 
    print('Error sending message: $e');
    print('Type of error: ${e.runtimeType}'); 
    print('Stack trace: $s'); 
    setState(() {
      _isBotTyping = false;
      _messages.add(ChatMessage(text: 'Error: Could not connect to the server. (Details in logs)', isUserMessage: false));
    });
    }
  }

  // Smoothly scrolls to the most recent message.
  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.indigo[200], // Light blue background for the whole chat screen
      appBar: AppBar(
        title: const Text('Chat with Aire'),
        backgroundColor: Colors.indigo[400], // Darker blue for AppBar
      ),
      body: Column(
        children: <Widget>[
          Expanded(
            child: GestureDetector(
              onTap: () => FocusScope.of(context).unfocus(), // Dismiss keyboard
              child: ListView.builder(
                controller: _scrollController,
                padding: const EdgeInsets.all(8.0),
                itemCount: _messages.length + (_isBotTyping ? 1 : 0),
                itemBuilder: (BuildContext context, int index) {
                  if (_isBotTyping && index == _messages.length) {
                    return _buildTypingIndicator();
                  }
                  return _buildMessageBubble(_messages[index]);
                },
              ),
            ),
          ),
          const Divider(height: 1.0),
          Container(
            decoration: BoxDecoration(color: Colors.indigo[50]), // Very light blue for text input area background
            child: _buildTextComposer(),
          ),
        ],
      ),
    );
  }

  // --- UI Builder Widgets ---

  // Parses text for bold markdown (**text**) and returns formatted TextSpans.
  List<TextSpan> _generateTextSpans(String text) {
    List<TextSpan> spans = [];
    RegExp exp = RegExp(r'\*\*(.*?)\*\*');
    int currentPosition = 0;

    for (Match match in exp.allMatches(text)) {
      if (match.start > currentPosition) {
        spans.add(TextSpan(text: text.substring(currentPosition, match.start)));
      }
      spans.add(TextSpan(
        text: match.group(1),
        style: const TextStyle(fontWeight: FontWeight.bold),
      ));
      currentPosition = match.end;
    }

    if (currentPosition < text.length) {
      spans.add(TextSpan(text: text.substring(currentPosition)));
    }
    if (spans.isEmpty) {
        spans.add(TextSpan(text: text));
    }
    return spans;
  }

  // Builds the visual bubble for a single chat message.
  Widget _buildMessageBubble(ChatMessage message) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 10.0),
      child: Row(
        mainAxisAlignment: message.isUserMessage ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: <Widget>[
          Flexible(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 15.0, vertical: 10.0),
              decoration: BoxDecoration(
                color: message.isUserMessage 
                    ? Colors.indigo[300] // Light blue for user messages
                    : Colors.indigo[50], // Very light blue/grey for bot messages
                borderRadius: BorderRadius.circular(20.0),
              ),
              child: RichText(
                text: TextSpan(
                  style: TextStyle(
                    fontSize: 16.0, 
                    color: message.isUserMessage 
                        ? Colors.white // User text color
                        : Colors.black87, // Bot text color
                  ),
                  children: _generateTextSpans(message.text),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // Builds the 'Aire is typing...' indicator.
  Widget _buildTypingIndicator() {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 10.0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        children: <Widget>[
          Flexible(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 15.0, vertical: 10.0),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.secondaryContainer,
                borderRadius: BorderRadius.circular(20.0),
              ),
              child: const Text(
                'Aire is typing...',
                style: TextStyle(fontSize: 16.0, fontStyle: FontStyle.italic),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // Builds the text input field and send button.
  Widget _buildTextComposer() {
    return IconTheme(
      data: IconThemeData(color: Theme.of(context).colorScheme.secondary),
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 8.0, vertical: 8.0),
        child: Row(
          children: <Widget>[
            Flexible(
              child: TextField(
                controller: _textController,
                onSubmitted: _sendMessage,
                style: const TextStyle(color: Colors.black, fontSize: 16.0), // Set input text color
                decoration: const InputDecoration.collapsed(
                  hintText: 'Send a message to Aire...',
                ),
              ),
            ),
            Container(
              margin: const EdgeInsets.symmetric(horizontal: 4.0),
              child: IconButton(
                icon: const Icon(Icons.send),
                onPressed: () => _sendMessage(_textController.text),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

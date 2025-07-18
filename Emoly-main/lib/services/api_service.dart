import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {
  // IMPORTANT: Replace with your computer's local IP address.
  // Do not use 'localhost' or '127.0.0.1' because the Flutter app runs on a different device (emulator or physical phone).
  static const String _baseUrl = 'http://192.168.0.215:5002'; // Updated to match backend server port

  // Starts a new chat session and gets the first message from the bot.
  static Future<Map<String, dynamic>> startNewChatSession(String participantId) async {
    final url = Uri.parse('$_baseUrl/chat');
    
    // This is the initial message payload for a new session
    final requestBody = {
      'participant_id': participantId,
      'message': 'start_session',
      'history': [],
      'is_new_session': true,
    };

    try {
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: json.encode(requestBody),
      ).timeout(const Duration(seconds: 20));

      if (response.statusCode == 200) {
        // Successfully received the first response from the bot
        return json.decode(response.body);
      } else {
        // Handle server errors (e.g., 500, 400)
        print('Server error: ${response.statusCode}');
        print('Response body: ${response.body}');
        throw Exception('Failed to start chat session. Server error. Body: ${response.body}');
      }
    } catch (e) {
      // Handle network errors (e.g., no connection, DNS error)
      print('Network error: $e');
      print('Exception in startNewChatSession: $e');
        if (e is http.ClientException) {
          throw Exception('Network error in startNewChatSession: $e');
        } else if (e is FormatException) {
          throw Exception('Error parsing server response in startNewChatSession: $e');
        }
        throw Exception('Generic error in startNewChatSession: $e');
    }
  }

  // Sends a follow-up message in an ongoing session.
  static Future<Map<String, dynamic>> sendMessage({
    required String participantId,
    required int interventionId,
    required String message,
    required List<Map<String, String>> history,
  }) async {
    final url = Uri.parse('$_baseUrl/chat');
    
    final requestBody = {
      'participant_id': participantId,
      'intervention_id': interventionId,
      'message': message,
      'history': history,
      'is_new_session': false, // This is always false for follow-up messages
    };

    try {
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: json.encode(requestBody),
      ).timeout(const Duration(seconds: 20));

      if (response.statusCode == 200) {
        return json.decode(response.body);
      } else {
        print('Server error: ${response.statusCode}');
        print('Response body: ${response.body}');
        throw Exception('Failed to send message. Server error. Body: ${response.body}');
      }
    } catch (e) {
      print('Exception in sendMessage: $e');
      if (e is http.ClientException) {
        throw Exception('Network error in sendMessage: $e');
      } else if (e is FormatException) {
        throw Exception('Error parsing server response in sendMessage: $e');
      }
      throw Exception('Generic error in sendMessage: $e');
    }
  }
}

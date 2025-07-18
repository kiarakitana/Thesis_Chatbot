// Copyright (c) 2025, Vrije Universitite. All rights reserved.
// Use of this source code is governed by a GNU-GPLv3 license that can be
// found in the LICENSE file.

// 📄 mqtt_service.dart — Temporarily disabled MQTT service

// import 'dart:async';
// import 'package:mqtt_client/mqtt_client.dart';
// import 'package:mqtt_client/mqtt_server_client.dart';

// class MQTTService {
//   late MqttServerClient client;

//   final StreamController<Map<String, dynamic>> _messageController = StreamController.broadcast();
//   Stream<Map<String, dynamic>> get messageStream => _messageController.stream;

//   Future<void> connect() async {
//     client = MqttServerClient('broker.hivemq.com', 'flutter_emotions_app');
//     client.port = 1883;
//     client.keepAlivePeriod = 20;
//     client.logging(on: false);
//     client.onDisconnected = () => print('❌ MQTT Disconnected');

//     final connMessage = MqttConnectMessage()
//         .withClientIdentifier('flutter_emotions_app')
//         .startClean()
//         .withWillQos(MqttQos.atLeastOnce);

//     client.connectionMessage = connMessage;

//     try {
//       await client.connect();
//       print('✅ Connected to MQTT broker');

//       // 🎯 Start listening for incoming messages
//       client.updates?.listen((List<MqttReceivedMessage<MqttMessage>> events) {
//         final recMessage = events.first.payload as MqttPublishMessage;
//         final payload = MqttPublishPayload.bytesToStringAsString(recMessage.payload.message);

//         final message = {
//           'topic': events.first.topic,
//           'message': payload,
//         };

//         print('📩 New MQTT message: \$message');
//         _messageController.add(message);
//       });

//     } catch (e) {
//       print('❌ MQTT connection failed: \$e');
//     }
//   }

//   void publish(String topic, String message) {
//     final builder = MqttClientPayloadBuilder();
//     builder.addString(message);
//     client.publishMessage(topic, MqttQos.atLeastOnce, builder.payload!);
//   }

//   void publishSensorData(Map<String, dynamic> data) {
//     final topic = 'experiment/sensor_data';
//     final payload = data.toString(); // You can use jsonEncode(data) instead if needed
//     publish(topic, payload);
//   }

//   void disconnect() {
//     _messageController.close();
//     client.disconnect();
//   }
// }

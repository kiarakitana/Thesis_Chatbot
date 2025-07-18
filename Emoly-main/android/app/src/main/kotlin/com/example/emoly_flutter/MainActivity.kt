package com.example.emoly_flutter

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.util.Log
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel

class MainActivity : FlutterActivity() {

    private val eventChannelName = "com.example.emoly_flutter/event_channel"
    private val broadcastAction = "com.example.emoly_flutter.TRIGGER_CHATBOT"
    private val TAG = "MainActivity"

    private var eventSink: EventChannel.EventSink? = null
    private var triggerReceiver: BroadcastReceiver? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        EventChannel(flutterEngine.dartExecutor.binaryMessenger, eventChannelName).setStreamHandler(
            object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                    Log.d(TAG, "EventChannel: onListen called.")
                    // Ensure any previous receiver is unregistered to prevent leaks
                    if (triggerReceiver != null) {
                        unregisterReceiver(triggerReceiver)
                        Log.d(TAG, "Unregistered a lingering BroadcastReceiver.")
                    }

                    eventSink = events
                    triggerReceiver = object : BroadcastReceiver() {
                        override fun onReceive(context: Context?, intent: Intent?) {
                            Log.d(TAG, "BroadcastReceiver received trigger. Sending event to Flutter.")
                            eventSink?.success("TRIGGER_CHAT")
                        }
                    }
                    val intentFilter = IntentFilter(broadcastAction)
                    registerReceiver(triggerReceiver, intentFilter)
                    Log.d(TAG, "Registered new BroadcastReceiver.")
                }

                override fun onCancel(arguments: Any?) {
                    Log.d(TAG, "EventChannel: onCancel called. Unregistering BroadcastReceiver.")
                    if (triggerReceiver != null) {
                        unregisterReceiver(triggerReceiver)
                        triggerReceiver = null
                    }
                    eventSink = null
                }
            }
        )
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "onDestroy called. Unregistering BroadcastReceiver if it exists.")
        if (triggerReceiver != null) {
            unregisterReceiver(triggerReceiver)
            triggerReceiver = null
        }
    }
}

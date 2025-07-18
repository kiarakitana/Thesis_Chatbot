package com.example.emoly_flutter

import android.content.Intent
import android.util.Log
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.WearableListenerService

class DataLayerListenerService : WearableListenerService() {

    private val broadcastAction = "com.example.emoly_flutter.TRIGGER_CHATBOT"

    override fun onMessageReceived(messageEvent: MessageEvent) {
        super.onMessageReceived(messageEvent)

        if (messageEvent.path == "/trigger") {
            Log.d("DataLayerListenerService", "Received trigger message from watch.")
            val intent = Intent(broadcastAction)
            sendBroadcast(intent)
        }
    }
}

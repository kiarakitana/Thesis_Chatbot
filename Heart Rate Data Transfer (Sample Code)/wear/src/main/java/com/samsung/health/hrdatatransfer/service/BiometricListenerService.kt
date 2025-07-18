package com.samsung.health.hrdatatransfer.service

import android.util.Log
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.WearableListenerService
import com.samsung.health.hrdatatransfer.data.TrackingRepositoryImpl
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject
import javax.inject.Inject

/**
 * Listens for session information messages from the phone app
 * to enable proper labeling of biometric data.
 */
@AndroidEntryPoint
class BiometricListenerService : WearableListenerService() {
    
    @Inject
    lateinit var trackingRepository: TrackingRepositoryImpl
    
    private val coroutineScope = CoroutineScope(Dispatchers.Main)
    
    companion object {
        private const val TAG = "BiometricListener"
        const val PATH_SESSION_INFO = "/session_info"
    }
    
    override fun onMessageReceived(messageEvent: MessageEvent) {
        super.onMessageReceived(messageEvent)
        
        when (messageEvent.path) {
            PATH_SESSION_INFO -> {
                coroutineScope.launch {
                    processSessionInfo(messageEvent.data)
                }
            }
        }
    }
    
    private fun processSessionInfo(data: ByteArray) {
        try {
            val jsonString = String(data, Charsets.UTF_8)
            val json = JSONObject(jsonString)
            
            val participantId = json.getString("participant_id")
            val interventionId = json.getInt("intervention_id")
            
            // Set the session info in the repository
            trackingRepository.setSessionInfo(participantId, interventionId)
            
            Log.i(TAG, "Received session info: participant=$participantId, intervention=$interventionId")
        } catch (e: Exception) {
            Log.e(TAG, "Error processing session info: ${e.message}")
        }
    }
}

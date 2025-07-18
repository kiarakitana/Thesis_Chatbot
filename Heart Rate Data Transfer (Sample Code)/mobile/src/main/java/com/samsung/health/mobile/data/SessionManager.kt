package com.samsung.health.mobile.data

import android.content.Context
import android.util.Log
import com.google.android.gms.tasks.Tasks
import com.google.android.gms.wearable.Node
import com.google.android.gms.wearable.NodeClient
import com.google.android.gms.wearable.Wearable
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manages participant session information and sends it to connected watches.
 * This class provides an interface for the Flutter app integration.
 */
@Singleton
class SessionManager @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private val nodeClient: NodeClient by lazy { Wearable.getNodeClient(context) }
    
    companion object {
        private const val TAG = "SessionManager"
        private const val SESSION_INFO_PATH = "/session_info"
    }
    
    /**
     * Sends session information to all connected watches to start biometric tracking.
     * This method will be called from the Flutter app when a new chat session starts.
     * 
     * @param participantId The ID of the participant in the study
     * @param interventionId The ID of the current intervention/session
     * @return True if the message was sent to at least one watch, false otherwise
     */
    suspend fun sendSessionInfoToWatch(participantId: String, interventionId: Int): Boolean = withContext(Dispatchers.IO) {
        try {
            Log.d(TAG, "Sending session info: P_ID=$participantId, I_ID=$interventionId")
            
            // Create JSON payload
            val sessionData = JSONObject().apply {
                put("participant_id", participantId)
                put("intervention_id", interventionId)
            }
            val payload = sessionData.toString()
            
            // Get connected nodes
            val nodes = Tasks.await(nodeClient.connectedNodes)
            if (nodes.isEmpty()) {
                Log.w(TAG, "No connected watches found!")
                return@withContext false
            }
            
            var atLeastOneSuccess = false
            for (node in nodes) {
                val success = sendMessageToNode(node, SESSION_INFO_PATH, payload)
                if (success) {
                    Log.d(TAG, "Successfully sent session info to watch: ${node.displayName}")
                    atLeastOneSuccess = true
                }
            }
            
            return@withContext atLeastOneSuccess
        } catch (e: Exception) {
            Log.e(TAG, "Error sending session info to watch", e)
            return@withContext false
        }
    }
    
    /**
     * Sends a message to a specific connected node (watch)
     */
    private suspend fun sendMessageToNode(node: Node, path: String, data: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val result = Tasks.await(
                Wearable.getMessageClient(context)
                    .sendMessage(node.id, path, data.toByteArray(Charsets.UTF_8))
            )
            return@withContext result != null
        } catch (e: Exception) {
            Log.e(TAG, "Error sending message to node ${node.id}", e)
            return@withContext false
        }
    }
}

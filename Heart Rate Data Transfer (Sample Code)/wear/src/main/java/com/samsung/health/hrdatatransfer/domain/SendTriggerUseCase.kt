package com.samsung.health.hrdatatransfer.domain

import android.content.Context
import android.util.Log
import com.google.android.gms.wearable.Wearable
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.tasks.await
import javax.inject.Inject

private const val TAG = "SendTriggerUseCase"

class SendTriggerUseCase @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private val messageClient by lazy { Wearable.getMessageClient(context) }

    suspend operator fun invoke() {
        Log.d(TAG, "Attempting to send trigger...")
        try {
            val nodes = Wearable.getNodeClient(context).connectedNodes.await()

            if (nodes.isEmpty()) {
                Log.w(TAG, "No connected phone found to send trigger.")
                return
            }

            Log.d(TAG, "Found ${nodes.size} connected node(s). Sending trigger to all.")

            nodes.forEach { node ->
                val nodeId = node.id
                messageClient.sendMessage(nodeId, "/trigger", "TRIGGER_CHAT".toByteArray())
                    .addOnSuccessListener {
                        Log.i(TAG, "Successfully sent trigger to node: ${node.displayName} ($nodeId)")
                    }
                    .addOnFailureListener {
                        Log.e(TAG, "Failed to send trigger to node: ${node.displayName} ($nodeId)", it)
                    }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Sending trigger failed with an exception.", e)
        }
    }
}

package com.samsung.health.hrdatatransfer.service

import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.WearableListenerService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.Charset
import javax.inject.Inject
import org.json.JSONObject
import org.json.JSONArray

/**
 * Service that listens for biometric data from the watch and forwards it to the server.
 * ⚠️ WARNING: This service may not be the active one. Check AndroidManifest.xml to see which service is registered.
 */
class BiometricDataService : WearableListenerService() {
    private val tag = "BiometricDataService_HRDataTransfer"
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    
    init {
        Log.w(tag, "🔍 ⚠️ CRITICAL: BiometricDataService (hrdatatransfer package) instance initialized")
        Log.w(tag, "🚨 CHECK AndroidManifest.xml - This service may NOT be the active one!")
    }
    
    // On service creation, log it for debugging
    override fun onCreate() {
        super.onCreate()
        Log.w(tag, "⭐ ⚠️ BiometricDataService (hrdatatransfer package) created")
        Log.w(tag, "📱 Package name: ${applicationContext.packageName}")
        Log.w(tag, "🔄 Ready to receive messages on path: $BIOMETRIC_DATA_PATH")
        Log.w(tag, "🚨 VERIFY: Is this the correct service in AndroidManifest.xml?")
    }
    
    override fun onDestroy() {
        super.onDestroy()
        Log.w(tag, "BiometricDataService (hrdatatransfer package) destroyed")
    }
    
    companion object {
        // Using the same TAG as the instance variable for consistency
        private const val BIOMETRIC_DATA_PATH = "/biometric_data"
        
        private const val SERVER_URL = "http://192.168.0.215:5002/store_biometrics"
    }
    
    override fun onMessageReceived(messageEvent: MessageEvent) {
        super.onMessageReceived(messageEvent)

        Log.i(tag, "📥 Message received on path: ${messageEvent.path} from node: ${messageEvent.sourceNodeId}")
        Log.i(tag, "📦 Message data size: ${messageEvent.data.size} bytes")
        
        // Log all message events for debugging
        Log.d(tag, "📋 All message details:\n" +
             "- Path: ${messageEvent.path}\n" +
             "- Source Node: ${messageEvent.sourceNodeId}\n" +
             "- Request ID: ${messageEvent.requestId}\n" +
             "- Data Size: ${messageEvent.data.size} bytes")
        
        if (messageEvent.path == BIOMETRIC_DATA_PATH) {
            try {
                val payload = messageEvent.data.toString(Charset.defaultCharset())
                Log.i(tag, "📊 Received biometric data payload length: ${payload.length} characters")
                Log.d(tag, "📋 Received biometric payload sample: ${payload.take(100)}${if(payload.length > 100) "..." else ""}")
                
                // Try to parse as JSON to verify format
                try {
                    val jsonObject = JSONObject(payload)
                    val participantId = jsonObject.getString("participant_id")
                    val interventionId = jsonObject.getInt("intervention_id")
                    val biometrics = jsonObject.getJSONArray("biometrics")
                    
                    Log.i(tag, "✅ Successfully parsed JSON. Participant ID: $participantId, Intervention ID: $interventionId, Biometrics count: ${biometrics.length()}")
                } catch (e: Exception) {
                    Log.e(tag, "❌ Failed to parse payload as valid JSON: ${e.message}")
                }
                
                // Forward to server
                sendToServer(payload)
            } catch (e: Exception) {
                Log.e(tag, "❌ Error processing biometric message: ${e.message}", e)
            }
        } else {
            Log.d(tag, "⏭️ Ignoring message on unhandled path: ${messageEvent.path}")
        }
    }
    
    private fun sendToServer(payload: String) {
        // Use coroutine to perform network operation in background
        serviceScope.launch {
            try {
                Log.i(tag, "🚀 Preparing to send data to server, payload size: ${payload.length} characters")
                
                // Change the URL to the correct server address and port
                // ⚠️ IMPORTANT: Replace 192.168.2.6 with your computer's actual IP address.
                // Do NOT use 127.0.0.1 or localhost as these refer to the phone itself, not your computer.
                // To find your computer's IP:
                // - On macOS/Linux: Open Terminal and type 'ifconfig' or 'ip addr'
                // - On Windows: Open Command Prompt and type 'ipconfig'
                // Look for your local network IP (usually starts with 192.168., 10., or 172.)
                val serverUrl = SERVER_URL
                Log.i(tag, "🌐 Server URL: $serverUrl")
                val url = URL(serverUrl)
                val connection = url.openConnection() as HttpURLConnection
                connection.apply {
                    requestMethod = "POST"
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json; charset=UTF-8")
                    setRequestProperty("Accept", "application/json")
                    connectTimeout = 10000
                    readTimeout = 10000
                }
                
                // Send data
                connection.outputStream.use { os ->
                    val input = payload.toByteArray(Charsets.UTF_8)
                    os.write(input, 0, input.size)
                }
                
                // Check response
                val responseCode = connection.responseCode
                if (responseCode in 200..299) {
                    Log.d(tag, "✅ Successfully sent biometric data to server, response: $responseCode")
                } else {
                    Log.e(tag, "❌ Failed to send biometric data to server, response: $responseCode")
                    val errorResponse = connection.errorStream?.bufferedReader()?.use { it.readText() }
                    Log.e(tag, "⚠️ Error response: $errorResponse")
                }
                
                connection.disconnect()
            } catch (e: Exception) {
                Log.e(tag, "❌ Error sending data to server: ${e.javaClass.simpleName}: ${e.message}")
                e.printStackTrace()
            }
        }
    }
}

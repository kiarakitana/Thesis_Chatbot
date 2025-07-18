/*
 * Copyright 2023 Samsung Electronics Co., Ltd. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com.samsung.health.hrdatatransfer.data

import org.json.JSONArray
import org.json.JSONObject

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.util.Log
import com.samsung.android.service.health.tracking.HealthTracker
import com.samsung.android.service.health.tracking.HealthTrackingService
import com.samsung.android.service.health.tracking.data.DataPoint
import com.samsung.android.service.health.tracking.data.HealthTrackerType
import com.samsung.android.service.health.tracking.data.ValueKey
import com.samsung.health.data.AccelerometerData
import com.samsung.health.data.TrackedData
import com.samsung.health.hrdatatransfer.R
import com.samsung.health.hrdatatransfer.data.IBIDataParsing.Companion.getValidIbiList
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.channels.trySendBlocking
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import com.google.android.gms.wearable.Wearable
import javax.inject.Inject
import javax.inject.Singleton

private const val TAG = "TrackingRepositoryImpl"

@OptIn(ExperimentalCoroutinesApi::class)
@Singleton
class TrackingRepositoryImpl
@Inject constructor(
    private val coroutineScope: CoroutineScope,
    private val healthTrackingServiceConnection: HealthTrackingServiceConnection,
    @ApplicationContext private val context: Context,
) : TrackingRepository {
    
    // Fields for session tracking
    private var currentParticipantId: String? = null
    private var currentInterventionId: Int? = null
    
    // Flag to check if session info is set before allowing tracking
    private val isSessionInfoSet: Boolean
        get() = currentParticipantId != null && currentInterventionId != null
        
    /**
     * Sets the session identification information that will be attached to all biometric readings
     */
    override fun setSessionInfo(participantId: String, interventionId: Int) {
        Log.i(TAG, "Setting session info: participant=$participantId, intervention=$interventionId")
        
        // Validate inputs
        if (participantId.isBlank()) {
            Log.e(TAG, "Cannot set session info: participantId is blank")
            return
        }
        
        if (interventionId <= 0) {
            Log.e(TAG, "Cannot set session info: invalid interventionId $interventionId")
            return
        }
        
        // Store the validated values
        currentParticipantId = participantId
        currentInterventionId = interventionId
        
        Log.i(TAG, "Session info successfully set")
    }
    
    // Batching mechanism for biometric readings
    private val biometricBatch = mutableListOf<BiometricReading>()
    private val batchSizeThreshold = 10 // Send after collecting 10 readings
    private val batchTimeThresholdMs = 15000 // Or send after 15 seconds
    private var lastBatchSendTimeMs = 0L
    
    // Using the standalone BiometricReading class from BiometricReading.kt
    // The fields are:
    // timestamp: Long, heartRate: Int?, ibi: List<Int>?, skinTemperature: Float?, participantId: String?, interventionId: Int?
    
    // This duplicate method has been removed to fix compilation error
    // The override method above will be used instead

    private val hrTrackingType = HealthTrackerType.HEART_RATE_CONTINUOUS
    private val skinTempTrackingType = HealthTrackerType.SKIN_TEMPERATURE_CONTINUOUS
    
    // Define string constants for temperature keys since we need to use strings directly
    private val OBJECT_TEMPERATURE_KEY = "object_temperature"
    private val AMBIENT_TEMPERATURE_KEY = "ambient_temperature"
    private val STATUS_KEY = "status"
    
    // Helper function for safely extracting float values from DataPoint
    private fun extractFloat(dataPoint: DataPoint, key: String): Float? {
        Log.d(TAG, "[DEBUG] extractFloat called with key: $key")
        try {
            // First try: Access through reflection on internal field
            try {
                // Look through all fields for a map that might contain our values
                for (field in dataPoint.javaClass.declaredFields) {
                    field.isAccessible = true
                    val fieldValue = field.get(dataPoint)
                    
                    // If this field is a Map, search its keys for our target
                    if (fieldValue is Map<*, *>) {
                        Log.v(TAG, "Found map field: ${field.name}")
                        val allValues = mutableListOf<Float>()
                        
                        for (entry in fieldValue.entries) {
                            try {
                                val valueObj = entry.value
                                Log.v(TAG, "Extracting value from: ${valueObj?.javaClass?.simpleName}")
                                
                                // Try to extract the actual value from Value object
                                if (valueObj != null) {
                                    try {
                                        // Log all methods available on the Value object
                                        val valueMethods = valueObj.javaClass.methods
                                        Log.d(TAG, "Value object methods: ${valueMethods.map { it.name }}")
                                        
                                        // Try toString() first - it might contain the actual value
                                        val stringValue = valueObj.toString()
                                        Log.d(TAG, "Value toString(): $stringValue")
                                        
                                        // Extract numbers from the toString() result
                                        val numberPattern = "(-?\\d+\\.?\\d*)"
                                        val matcher = Regex(numberPattern).findAll(stringValue)
                                        val matches = matcher.map { it.value.toFloatOrNull() }.filterNotNull().toList()
                                        
                                        if (matches.isNotEmpty()) {
                                            Log.d(TAG, "Extracted numbers from toString(): $matches")
                                            matches.forEach { floatValue ->
                                                allValues.add(floatValue)
                                                
                                                // Check if this could be temperature (expanded range)
                                                if (floatValue in -20.0f..60.0f) {
                                                    Log.i(TAG, "Found potential temperature value: $floatValue°C")
                                                    return floatValue
                                                }
                                            }
                                        }
                                        
                                        // Try methods from Value class
                                        for (method in valueMethods) {
                                            if (method.parameterTypes.isEmpty() && method.name != "toString" && 
                                                method.name != "hashCode" && method.name != "getClass" &&
                                                !method.name.startsWith("wait") && !method.name.startsWith("notify")) {
                                                try {
                                                    val result = method.invoke(valueObj)
                                                    Log.d(TAG, "Method '${method.name}' returned: $result (${result?.javaClass?.name})")
                                                    
                                                    // Try to convert to float
                                                    val floatValue = when (result) {
                                                        is Float -> result
                                                        is Double -> result.toFloat()
                                                        is Int -> result.toFloat()
                                                        is Number -> result.toFloat()
                                                        is String -> result.toFloatOrNull()
                                                        else -> null
                                                    }
                                                    
                                                    if (floatValue != null) {
                                                        Log.d(TAG, "Converted to float: $floatValue")
                                                        allValues.add(floatValue)
                                                        
                                                        // Check if this could be temperature (expanded range)
                                                        if (floatValue in -20.0f..60.0f) {
                                                            Log.i(TAG, "Found temperature from method '${method.name}': $floatValue°C")
                                                            return floatValue
                                                        }
                                                    }
                                                } catch (e: Exception) {
                                                    // Ignore method invocation errors
                                                }
                                            }
                                        }
                                    } catch (e: Exception) {
                                        Log.v(TAG, "Failed to extract value: ${e.message}")
                                    }
                                }
                            } catch (e: Exception) {
                                Log.v(TAG, "Error processing entry: ${e.message}")
                            }
                        }
                        
                        Log.v(TAG, "All extracted values: $allValues")
                        Log.v(TAG, "No values in temperature range found")
                    }
                }
                Log.v(TAG, "No matching key found in any map field")
            } catch (e: Exception) {
                Log.v(TAG, "Reflection approach failed: ${e.message}")
            }
            
            // Second try: Use Java reflection to call getFloat directly if it exists
            try {
                val methods = dataPoint.javaClass.methods
                val getFloatMethod = methods.firstOrNull {
                    it.name == "getFloat" && it.parameterTypes.size == 1 && 
                    it.parameterTypes[0] == String::class.java
                }
                
                if (getFloatMethod != null) {
                    Log.v(TAG, "Found getFloat method, trying to invoke it")
                    val result = getFloatMethod.invoke(dataPoint, key) as Float
                    return result
                }
            } catch (e: Exception) {
                Log.v(TAG, "getFloat method approach failed: ${e.message}")
            }
            
            // Return null if all methods fail
            Log.v(TAG, "All extraction methods failed")
            return null
        } catch (e: Exception) {
            Log.e(TAG, "Failed to extract float value for key $key: ${e.message}")
            return null
        }
    }
    
    // Helper function for safely extracting int values from DataPoint
    private fun extractInt(dataPoint: DataPoint, key: String, defaultValue: Int = 0): Int {
        Log.d(TAG, "[DEBUG] extractInt called with key: $key")
        try {
            // First try: Access through reflection on internal field
            try {
                // Look through all fields for a map that might contain our values
                for (field in dataPoint.javaClass.declaredFields) {
                    field.isAccessible = true
                    val fieldValue = field.get(dataPoint)
                    
                    // If this field is a Map, search its keys for our target
                    if (fieldValue is Map<*, *>) {
                        Log.v(TAG, "Found map field: ${field.name}")
                        for (entry in fieldValue.entries) {
                            try {
                                // Try to extract the actual key name from ValueKey object
                                val keyObj = entry.key
                                var keyName: String? = null
                                
                                if (keyObj != null) {
                                    Log.v(TAG, "Processing key object of type: ${keyObj.javaClass.name}")
                                    try {
                                        // Try common method names for getting the key name
                                        val keyMethods = keyObj.javaClass.methods
                                        Log.v(TAG, "Available methods on ${keyObj.javaClass.simpleName}: ${keyMethods.map { it.name }}")
                                        
                                        val nameMethod = keyMethods.firstOrNull { 
                                            it.name in listOf("getName", "getKey", "toString") && 
                                            it.parameterTypes.isEmpty() 
                                        }
                                        if (nameMethod != null) {
                                            Log.v(TAG, "Trying to invoke method: ${nameMethod.name}")
                                            keyName = nameMethod.invoke(keyObj) as? String
                                            Log.v(TAG, "Method ${nameMethod.name} returned: '$keyName'")
                                        } else {
                                            Log.v(TAG, "No suitable method found for key extraction")
                                        }
                                    } catch (e: Exception) {
                                        Log.v(TAG, "Failed to get key name from ${keyObj.javaClass.simpleName}: ${e.message}")
                                    }
                                }
                                
                                val displayKey = keyName ?: keyObj?.toString() ?: "null"
                                Log.v(TAG, "Checking key: $displayKey against target: $key")
                                
                                // Check if this key matches what we're looking for
                                if (keyName != null && keyName.contains(key, ignoreCase = true)) {
                                    val valueObj = entry.value
                                    Log.v(TAG, "Found matching key '$keyName', extracting value from: ${valueObj?.javaClass?.simpleName}")
                                    
                                    // Try to extract the actual value from Value object
                                    if (valueObj != null) {
                                        try {
                                            // Try common method names for getting the value
                                            val valueMethods = valueObj.javaClass.methods
                                            val valueMethod = valueMethods.firstOrNull { 
                                                it.name in listOf("asInt", "getInt", "intValue", "getValue") && 
                                                it.parameterTypes.isEmpty() 
                                            }
                                            if (valueMethod != null) {
                                                val result = valueMethod.invoke(valueObj)
                                                Log.v(TAG, "Extracted value using ${valueMethod.name}: $result")
                                                when (result) {
                                                    is Int -> return result
                                                    is Float -> return result.toInt()
                                                    is Double -> return result.toInt()
                                                    is Number -> return result.toInt()
                                                }
                                            }
                                            
                                            // Fallback: try direct access if it's already a primitive
                                            when (valueObj) {
                                                is Int -> return valueObj
                                                is Float -> return valueObj.toInt()
                                                is Double -> return valueObj.toInt()
                                                is Number -> return valueObj.toInt()
                                            }
                                        } catch (e: Exception) {
                                            Log.v(TAG, "Failed to extract value from ${valueObj.javaClass.simpleName}: ${e.message}")
                                        }
                                    }
                                }
                            } catch (e: Exception) {
                                Log.v(TAG, "Error processing map entry: ${e.message}")
                            }
                        }
                    }
                }
                Log.v(TAG, "No matching key found in any map field")
            } catch (e: Exception) {
                Log.v(TAG, "Reflection approach failed: ${e.message}")
            }
            
            // Second try: Use Java reflection to call getInt directly if it exists
            try {
                val methods = dataPoint.javaClass.methods
                val getIntMethod = methods.firstOrNull {
                    it.name == "getInt" && it.parameterTypes.size == 1 && 
                    it.parameterTypes[0] == String::class.java
                }
                
                if (getIntMethod != null) {
                    Log.v(TAG, "Found getInt method, trying to invoke it")
                    val result = getIntMethod.invoke(dataPoint, key) as Int
                    return result
                }
            } catch (e: Exception) {
                Log.v(TAG, "getInt method approach failed: ${e.message}")
            }
            
            // Return default if all methods fail
            Log.v(TAG, "All extraction methods failed, using default value: $defaultValue")
            return defaultValue
        } catch (e: Exception) {
            Log.e(TAG, "Failed to extract int value for key $key: ${e.message}")
            return defaultValue
        }
    }
    
    private fun logAllDataPointInfo(dataPoint: DataPoint) {
        try {
            // Get all fields via reflection for debugging
            Log.d(TAG, "---DataPoint Details Start---")
            Log.d(TAG, "DataPoint type: ${dataPoint.javaClass.name}")
            // Note: DataPoint doesn't have trackerType property, removed reference
            
            // Try to access any internal map/fields that might contain the values
            for (field in dataPoint.javaClass.declaredFields) {
                field.isAccessible = true
                val name = field.name
                try {
                    val value = field.get(dataPoint)
                    Log.d(TAG, "Field '$name': $value")
                    
                    // If we find a map field, dig deeper
                    if (value is Map<*, *>) {
                        Log.d(TAG, "Map '$name' contents:")
                        value.entries.forEachIndexed { index, entry ->
                            Log.d(TAG, "  $index: ${entry.key} = ${entry.value} (${entry.value?.javaClass?.name})")
                        }
                    }
                } catch (e: Exception) {
                    Log.d(TAG, "Could not access field '$name': ${e.message}")
                }
            }
            
            // Try to call common methods
            try {
                val keySetMethod = dataPoint.javaClass.getDeclaredMethod("keySet")
                keySetMethod.isAccessible = true
                val keySet = keySetMethod.invoke(dataPoint) as? Set<*>
                Log.d(TAG, "keySet: $keySet")
            } catch (e: Exception) {
                Log.d(TAG, "No keySet method available: ${e.message}")
            }
            
            Log.d(TAG, "---DataPoint Details End---")
        } catch (e: Exception) {
            Log.e(TAG, "Error logging DataPoint info: ${e.message}")
        }
    }
    private var hrListenerSet = false
    private var skinTempListenerSet = false
    private var accelListenerSet = false
    private var healthTrackingService: HealthTrackingService? = null
    private var sensorManager: SensorManager? = null
    private var accelerometerSensor: Sensor? = null
    
    // Accelerometer event listener
    private val accelerometerListener = object : SensorEventListener {
        override fun onSensorChanged(event: SensorEvent?) {
            event?.let {
                if (it.sensor.type == Sensor.TYPE_ACCELEROMETER) {
                    val x = it.values[0]
                    val y = it.values[1]
                    val z = it.values[2]
                    currentBatchData.accelerometer = AccelerometerData(x, y, z)
                    Log.i(TAG, "Accelerometer: x=$x, y=$y, z=$z")
                }
            }
        }
        
        override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {
            // Not used
        }
    }

    var errors: HashMap<String, Int> = hashMapOf(
        "0" to R.string.error_initial_state,
        "-2" to R.string.error_wearable_movement_detected,
        "-3" to R.string.error_wearable_detached,
        "-8" to R.string.error_low_ppg_signal,
        "-10" to R.string.error_low_ppg_signal_even_more,
        "-999" to R.string.error_other_sensor_running,
        "SDK_POLICY_ERROR" to R.string.SDK_POLICY_ERROR,
        "PERMISSION_ERROR" to R.string.PERMISSION_ERROR
    )

    private val maxValuesToKeep = 40
    private var heartRateTracker: HealthTracker? = null
    private var skinTemperatureTracker: HealthTracker? = null
    private var validHrData = ArrayList<TrackedData>()
    private var currentBatchData = TrackedData()
    private val batchingInterval = 10 // Batch data every 10 data points

    override fun getValidHrData(): ArrayList<TrackedData> {
        return validHrData
    }

    private fun isHRValid(hrStatus: Int): Boolean {
        return hrStatus == 1
    }

    private fun trimDataList() {
        val howManyElementsToRemove = validHrData.size - maxValuesToKeep
        repeat(howManyElementsToRemove) { validHrData.removeFirstOrNull() }
    }

    @ExperimentalCoroutinesApi
    override suspend fun track(): Flow<TrackerMessage> = callbackFlow {
        // Check if session info is set and valid
        if (currentParticipantId.isNullOrBlank()) {
            Log.e(TAG, "Cannot start tracking: participant ID not provided")
            trySendBlocking(
                TrackerMessage.TrackerErrorMessage("Participant ID required before tracking")
            )
            return@callbackFlow
        }
        
        if (currentInterventionId == null || currentInterventionId!! <= 0) {
            Log.e(TAG, "Cannot start tracking: invalid intervention ID: $currentInterventionId")
            trySendBlocking(
                TrackerMessage.TrackerErrorMessage("Valid intervention ID required before tracking")
            )
            return@callbackFlow
        }
        
        Log.i(TAG, "Starting biometric tracking with participant=$currentParticipantId, intervention=$currentInterventionId")
        val updateListener = object : HealthTracker.TrackerEventListener {
            override fun onDataReceived(dataPoints: MutableList<DataPoint>) {
                Log.d(TAG, "[DEBUG] onDataReceived called with dataPoint: ${dataPoints::class.java.simpleName}@${System.identityHashCode(dataPoints)}")
                // Skip processing if session info is not set
                if (!isSessionInfoSet) {
                    Log.w(TAG, "Received data but session info not set, skipping processing")
                    return@onDataReceived
                }
                for (dataPoint in dataPoints) {
                    var processed = false // Flag to ensure a datapoint is processed only once

                    // Log DataPoint type
                    Log.d(TAG, "Received DataPoint of type: ${dataPoint.javaClass.name}")

                    // Try to process as Heart Rate data
                    try {
                        // Attempt to get HR value. If ValueKey.HeartRateSet.HEART_RATE is not present,
                        // this will throw an exception, and we'll know it's not HR data.
                        Log.d(TAG, "[DEBUG] Attempting to extract Heart Rate value...")
                        val hrValue = dataPoint.getValue<Int>(ValueKey.HeartRateSet.HEART_RATE)
                        Log.d(TAG, "Heart Rate value extracted: $hrValue")
                        
                        // Validate heart rate value is in reasonable range (30-220 bpm)
                        if (hrValue < 30 || hrValue > 220) {
                            Log.w(TAG, "Heart rate value out of normal range: $hrValue, will still process")
                            // Continue processing even with unusual values, but log the warning
                        }
                        
                        // Since getValue succeeded, treat the HR data as valid
                        // Based on previous memory - we don't rely on status validation anymore
                        currentBatchData.hr = hrValue
                        Log.d(TAG, "Extracted HR: $hrValue")
                        
                        // Add to biometric batch for the server
                        val currentTimeMs = System.currentTimeMillis()
                        var rrInterval: Int? = null

                        // Also extract IBI data from the same data point
                        try {
                            // Apply enhanced logging for DataPoint as mentioned in memory
                            Log.d(TAG, "[DEBUG] Extracting IBI from DataPoint type: ${dataPoint.javaClass.name}")
                            
                            // Log ValueKey methods for debugging
                            try {
                                val valueKeyClass = ValueKey.HeartRateSet::class.java
                                val valueMethods = valueKeyClass.methods
                                Log.d(TAG, "ValueKey methods: ${valueMethods.joinToString { it.name }}")
                            } catch (e: Exception) {
                                Log.e(TAG, "Failed to log ValueKey methods: ${e.message}")
                            }
                            
                            val ibiList = getValidIbiList(dataPoint)
                            if (ibiList.isNotEmpty()) {
                                Log.d(TAG, "Successfully extracted IBI list with ${ibiList.size} values")
                                currentBatchData.ibi.addAll(ibiList)
                                
                                // Get the first IBI value for our biometric batch
                                rrInterval = ibiList[0]
                                Log.d(TAG, "Using first IBI value: $rrInterval ms")
                            } else {
                                Log.d(TAG, "No IBI values found in the data point")
                            }
                        } catch (e: Exception) {
                            Log.e(TAG, "Error processing IBI data: ${e.message}", e)
                            // Continue with heart rate even if IBI extraction fails
                        }
                        
                        // Add heart rate reading to biometric batch
                        biometricBatch.add(BiometricReading(
                            timestamp = currentTimeMs,
                            heartRate = hrValue,
                            ibi = rrInterval?.let { listOf(it) },
                            skinTemperature = null,
                            participantId = currentParticipantId,
                            interventionId = currentInterventionId
                        ))
                        
                        // Check if we should send the batch
                        if (biometricBatch.size >= batchSizeThreshold || 
                            (currentTimeMs - lastBatchSendTimeMs > batchTimeThresholdMs && biometricBatch.isNotEmpty())) {
                            sendBiometricBatch()
                        }
                        
                        processed = true
                    } catch (e: Exception) {
                        Log.e(TAG, "Error extracting Heart Rate data: ${e.message}")
                        // Not heart rate data, or error extracting HR. Will attempt temperature next.
                    }

                    // If not processed as HR, try to process as Skin Temperature data
                    if (!processed) {
                        try {
                            val skinTemp = extractFloat(dataPoint, OBJECT_TEMPERATURE_KEY)

                            if (skinTemp != null) { // Check if a valid temperature was extracted
                                val ambientTemp = extractFloat(dataPoint, AMBIENT_TEMPERATURE_KEY)
                                val status = extractInt(dataPoint, STATUS_KEY)

                                Log.i(TAG, "Skin Temp: $skinTemp, Ambient Temp: $ambientTemp, Status: $status")
                                // Log the full DataPoint details when skin temperature is detected
                                Log.d(TAG, "--- Skin Temperature DataPoint Details ---")
                                logAllDataPointInfo(dataPoint)
                                
                                // Add to biometric batch for the server
                                val currentTimeMs = System.currentTimeMillis()
                                biometricBatch.add(BiometricReading(
                                    timestamp = currentTimeMs,
                                    heartRate = null,
                                    ibi = null,
                                    skinTemperature = skinTemp,
                                    participantId = currentParticipantId,
                                    interventionId = currentInterventionId
                                ))
                                
                                // Check if we should send the batch
                                if (biometricBatch.size >= batchSizeThreshold || 
                                    (currentTimeMs - lastBatchSendTimeMs > batchTimeThresholdMs && biometricBatch.isNotEmpty())) {
                                    sendBiometricBatch()
                                }
                                
                                processed = true
                            }
                        } catch (e: Exception) {
                            Log.e(TAG, "Error processing skin temperature data: ${e.message}")
                        }
                    }
                    
                    // If still not processed after HR and Temperature checks, log its content.
                    if (!processed) {
                        Log.w(TAG, "DataPoint not processed as HR or Temperature. Logging its content:")
                        logAllDataPointInfo(dataPoint)
                    }

                    // Send accumulated data if new data is present and batch interval is met
                    val hasNewData = currentBatchData.hr > 0 ||
                                     currentBatchData.ibi.isNotEmpty() ||
                                     (currentBatchData.skinTemperature != 0.0f && currentBatchData.skinTemperature != -999f) ||
                                     (currentBatchData.ambientTemperature != 0.0f && currentBatchData.ambientTemperature != -999f) ||
                                     currentBatchData.accelerometer != null
                    
                    if (hasNewData && validHrData.size % batchingInterval == 0) { // Original batch condition
                        val dataToSend = currentBatchData.copy()
                        
                        coroutineScope.runCatching {
                            trySendBlocking(TrackerMessage.DataMessage(dataToSend))
                        }
                        
                        validHrData.add(dataToSend) 
                        trimDataList()
                        
                        val currentAccel = currentBatchData.accelerometer
                        currentBatchData = TrackedData()
                        currentBatchData.accelerometer = currentAccel
                    }
                }
            }

            fun getError(errorKeyFromTracker: String): String {
                val str = errors.getValue(errorKeyFromTracker)
                return context.resources.getString(str)
            }

            override fun onFlushCompleted() {

                Log.i(TAG, "onFlushCompleted()")
                coroutineScope.runCatching {
                    trySendBlocking(TrackerMessage.FlushCompletedMessage)
                }
            }

            override fun onError(trackerError: HealthTracker.TrackerError?) {

                Log.i(TAG, "onError()")
                coroutineScope.runCatching {
                    trySendBlocking(TrackerMessage.TrackerErrorMessage(getError(trackerError.toString())))
                }
            }
        }

        // Initialize heart rate tracker
        heartRateTracker = healthTrackingService!!.getHealthTracker(hrTrackingType)
        Log.d(TAG, "Heart rate tracker initialized: $heartRateTracker")
        
        // Initialize skin temperature tracker
        try {
            val availableTrackers = healthTrackingService!!.trackingCapability.supportHealthTrackerTypes
            // Find temperature type tracker if available
            val tempTrackerType = availableTrackers.find { 
                it.toString().contains("temperature", ignoreCase = true) 
            }
            
            if (tempTrackerType != null) {
                skinTemperatureTracker = healthTrackingService!!.getHealthTracker(tempTrackerType)
                Log.i(TAG, "Successfully initialized skin temperature tracker: ${tempTrackerType}")
            } else {
                Log.w(TAG, "Skin temperature tracker type not found in available trackers")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error initializing skin temperature tracker: ${e.message}")
            // Continue even if skin temperature tracking isn't available
        }

        // Set listeners for all trackers
        setListener(updateListener)

        awaitClose {
            Log.i(TAG, "Tracking flow awaitClose()")
            stopTracking()
        }
    }

    /**
     * Send the current batch of biometric readings to the phone
     * Returns true if successfully queued for sending, false otherwise
     */
    private fun sendBiometricBatch(): Boolean {
        Log.d(TAG, "[DEBUG] sendBiometricBatch called - checking batch size")
        // Check if we have readings
        if (biometricBatch.isEmpty()) {
            Log.w(TAG, "[DEBUG] Not sending biometric batch: batch is empty")
            return false
        }
        Log.d(TAG, "[DEBUG] Found ${biometricBatch.size} readings in batch")
        // Validate session info
        if (currentParticipantId.isNullOrBlank()) {
            Log.e(TAG, "Cannot send batch: participant ID not set")
            return false
        }
        
        if (currentInterventionId == null || currentInterventionId!! <= 0) {
            Log.e(TAG, "Cannot send batch: invalid intervention ID: $currentInterventionId")
            return false
        }
        
        // Make a safe copy of the batch to avoid concurrent modification
        val batchToSend = ArrayList(biometricBatch)
        if (batchToSend.isEmpty()) {
            Log.w(TAG, "Batch became empty during copy operation")
            return false
        }
        
        // Log what we're about to send
        Log.i(TAG, "Preparing to send ${batchToSend.size} biometric readings to phone")
        Log.d(TAG, "Sample data: HR=${batchToSend.firstOrNull()?.heartRate}, temp=${batchToSend.firstOrNull()?.skinTemperature}")
        
        // Update last send time
        lastBatchSendTimeMs = System.currentTimeMillis()
        
        try {
            val jsonPayload = createBiometricPayload(
                currentParticipantId!!, 
                currentInterventionId!!, 
                batchToSend
            )
            
            // Send to all connected nodes (phones)
            coroutineScope.launch(Dispatchers.IO) {
                try {
                    val nodeClient = Wearable.getNodeClient(context)
                    Log.d(TAG, "[DEBUG] Getting connected nodes...")
                    val nodes = nodeClient.connectedNodes.await()
                    Log.i(TAG, "[DEBUG] Connected nodes found: ${nodes.size}")
                    nodes.forEach { node -> 
                        Log.i(TAG, "[DEBUG] Found node: ${node.id}, display name: ${node.displayName}")
                    }
                    
                    if (nodes.isEmpty()) {
                        Log.w(TAG, "No connected phones found for sending biometric data")
                        // Don't clear the batch since we couldn't send it - we'll try again later
                        return@launch
                    }
                    
                    var sendSuccessful = false
                    
                    for (node in nodes) {
                        try {
                            Log.d(TAG, "[DEBUG] Sending ${batchToSend.size} biometric readings to node ${node.id}")
                            Log.d(TAG, "[DEBUG] JSON Payload length: ${jsonPayload.length} bytes")
                            Log.d(TAG, "[DEBUG] Sample payload content: ${jsonPayload.take(200)}${if(jsonPayload.length > 200) "..." else ""}")
                            // Send the message and get the Task result
                            val messageTask = Wearable.getMessageClient(context)
                                .sendMessage(node.id, "/biometric_data", jsonPayload.toByteArray(Charsets.UTF_8))
                            
                            Log.d(TAG, "[DEBUG] Message queued for sending, awaiting completion...")
                            // Wait for task completion
                            try {
                                messageTask.await()
                                Log.d(TAG, "[DEBUG] Message send task completed successfully")
                            } catch (e: Exception) {
                                Log.e(TAG, "[DEBUG] Message send task failed with exception: ${e.javaClass.simpleName}: ${e.message}")
                                throw e
                            }
                            
                            // Task completed successfully if no exception was thrown
                            Log.i(TAG, "Successfully sent ${batchToSend.size} readings to phone ${node.id}")
                            sendSuccessful = true
                        } catch (e: Exception) {
                            Log.e(TAG, "Error sending data to node ${node.id}: ${e.message}", e)
                            // Continue trying other nodes
                        }
                    }
                    
                    // Only clear the batch if we successfully sent to at least one node
                    if (sendSuccessful) {
                        synchronized(biometricBatch) {
                            // Remove the readings we just sent from the batch
                            biometricBatch.removeAll(batchToSend)
                            Log.d(TAG, "Cleared sent readings, ${biometricBatch.size} readings remaining in queue")
                        }
                    } else {
                        Log.w(TAG, "Failed to send batch to any nodes, will retry later")
                        // Don't clear the batch since we couldn't send it
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Error in node client operations: ${e.message}", e)
                }
            }
            
            // Return true since we've queued the send operation (even if actual sending might fail)
            return true
            
        } catch (e: Exception) {
            Log.e(TAG, "Error preparing biometric batch: ${e.message}", e)
            return false
        }
    }
    
    /**
     * Creates a JSON payload from the collected biometric data
     */
    private fun createBiometricPayload(
        participantId: String,
        interventionId: Int,
        readings: List<BiometricReading>
    ): String {
        val json = JSONObject().apply {
            put("participant_id", participantId)
            put("intervention_id", interventionId)
            
            val biometricsArray = JSONArray()
            readings.forEach { reading ->
                val readingJson = JSONObject().apply {
                    put("timestamp", reading.timestamp)
                    
                    // Add heart rate if available
                    reading.heartRate?.let { hr ->
                        put("hr", hr)
                    }
                    
                    // Handle IBI array properly
                    reading.ibi?.let { ibiList ->
                        if (ibiList.isNotEmpty()) {
                            val ibiArray = JSONArray()
                            ibiList.forEach { ibiValue -> ibiArray.put(ibiValue) }
                            put("ibi", ibiArray)
                        }
                    }
                    
                    // Add skin temperature if available
                    reading.skinTemperature?.let { temp ->
                        put("temp", temp)
                    }
                }
                biometricsArray.put(readingJson)
            }
            
            put("biometrics", biometricsArray)
        }
        
        return json.toString()
    }
    
    override fun stopTracking() {
        Log.i(TAG, "Stopping biometric tracking")
        
        // Send any remaining biometric data before stopping
        if (biometricBatch.isNotEmpty()) {
            Log.i(TAG, "Sending final batch of ${biometricBatch.size} readings before stopping")
            sendBiometricBatch()
        } else {
            Log.i(TAG, "No remaining biometric data to send")
        }
        
        unsetListener()
        currentBatchData = TrackedData() // Reset batch data
        biometricBatch.clear() // Clear the biometric batch
        
        // Keep session info as it may be needed for the next tracking session
        // User will need to explicitly set new session info if needed
    }

    private fun unsetListener() {
        // Unset heart rate listener
        if (hrListenerSet) {
            heartRateTracker?.unsetEventListener()
            hrListenerSet = false
        }
        
        // Unset skin temperature listener
        if (skinTempListenerSet) {
            skinTemperatureTracker?.unsetEventListener()
            skinTempListenerSet = false
        }
        
        // Unregister accelerometer listener
        if (accelListenerSet) {
            sensorManager?.unregisterListener(accelerometerListener)
            accelListenerSet = false
        }
    }

    private fun setListener(listener: HealthTracker.TrackerEventListener) {
        // Set heart rate listener
        if (!hrListenerSet && heartRateTracker != null) {
            heartRateTracker?.setEventListener(listener)
            Log.d(TAG, "Heart rate listener set")
            hrListenerSet = true
        } else {
            Log.w(TAG, "Heart rate listener not set - hrListenerSet: $hrListenerSet, heartRateTracker: $heartRateTracker")
        }
        
        // Set skin temperature listener
        if (!skinTempListenerSet && skinTemperatureTracker != null) {
            skinTemperatureTracker?.setEventListener(listener)
            skinTempListenerSet = true
        }
        
        // Register accelerometer listener
        if (!accelListenerSet && accelerometerSensor != null) {
            sensorManager?.registerListener(
                accelerometerListener,
                accelerometerSensor,
                SensorManager.SENSOR_DELAY_NORMAL
            )
            accelListenerSet = true
        }
    }

    override fun hasCapabilities(): Boolean {
        Log.i(TAG, "hasCapabilities()")
        healthTrackingService = healthTrackingServiceConnection.getHealthTrackingService()
        
        // Initialize sensor manager for accelerometer data if not already done
        if (sensorManager == null) {
            sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
            accelerometerSensor = sensorManager?.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        }
        
        // Check for heart rate capability
        val trackers: List<HealthTrackerType> =
            healthTrackingService!!.trackingCapability.supportHealthTrackerTypes
        val hasHeartRateCapability = trackers.contains(hrTrackingType)
        
        // Check for skin temperature capability
        // For custom tracker types like temperature we need to check differently
        val hasTemperatureCapability = trackers.any { it.toString().contains("temperature", ignoreCase = true) }
        
        // Need at least heart rate for basic functionality
        return hasHeartRateCapability
    }
}

sealed class TrackerMessage {
    class DataMessage(val trackedData: TrackedData) : TrackerMessage()
    object FlushCompletedMessage : TrackerMessage()
    class TrackerErrorMessage(val trackerError: String) : TrackerMessage()
    class TrackerWarningMessage(val trackerWarning: String) : TrackerMessage()
}
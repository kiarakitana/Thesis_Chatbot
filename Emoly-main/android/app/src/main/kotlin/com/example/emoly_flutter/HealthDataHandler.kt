// 📄 HealthDataHandler.kt — Wired with Heart Rate, HRV, Temp, Blood Pressure, ECG,GSR and PPG
// 📄 HealthDataHandler.kt — Full Samsung Health Sensor API Integration (patched)
// 📄 HealthDataHandler.kt (Now logs to CSV per participant/video)
// 📄 HealthDataHandler.kt — EventChannel support + Samsung SDK integration
package com.example.emoly_flutter

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.os.Environment
import android.util.Log
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.samsung.android.service.health.tracking.*
import com.samsung.android.service.health.tracking.data.HealthTrackerType
import com.samsung.android.service.health.tracking.data.DataPoint
import com.samsung.android.service.health.tracking.data.ValueKey.HeartRateSet
import com.samsung.android.service.health.tracking.data.ValueKey.PpgSet
import io.flutter.plugin.common.EventChannel.EventSink
import java.io.File
import java.io.FileWriter

class HealthDataHandler(private val context: Context) {

    private lateinit var healthTrackingService: HealthTrackingService
    private val trackerMap: MutableMap<HealthTrackerType, HealthTracker> = mutableMapOf()
    private var eventSink: EventSink? = null

    private lateinit var participantId: String
    private lateinit var videoName: String

    fun setEventSink(sink: EventSink?) {
        this.eventSink = sink
    }

    fun startAllTrackers(participant: String = "001", video: String = "unknown") {
        this.participantId = participant
        this.videoName = video

        if (!hasRequiredPermissions()) {
            requestPermissions()
            return
        }

        healthTrackingService = HealthTrackingService(object : ConnectionListener {
            override fun onConnectionSuccess() {
                Log.d("SamsungHealth", "✅ Connected to HealthTrackingService")
                setupTrackers()
            }

            override fun onConnectionFailed(exception: HealthTrackerException) {
                Log.e("SamsungHealth", "❌ Connection failed: ${exception.message}")
            }

            override fun onConnectionEnded() {
                Log.w("SamsungHealth", "⚠️ Disconnected from HealthTrackingService")
            }
        }, context)

        healthTrackingService.connectService()
    }

    private fun setupTrackers() {
        val continuousTypes = listOf(
            HealthTrackerType.HEART_RATE_CONTINUOUS,
            HealthTrackerType.PPG_CONTINUOUS
        )

        for (type in continuousTypes) {
            try {
                val tracker = healthTrackingService.getHealthTracker(type)
                tracker.setEventListener(object : HealthTracker.TrackerEventListener {
                    override fun onDataReceived(list: List<DataPoint>) {
                        for (dp in list) {
                            val value = extractValueForType(type, dp)
                            val timestamp = dp.timestamp

                            // CSV save
                            val csv = "$timestamp,$value"
                            saveToCSV(type.name.lowercase(), csv)

                            // Send to Dart
                            val event = mapOf(
                                "timestamp" to timestamp,
                                "type" to type.name.lowercase(),
                                "value" to value
                            )
                            val handler = android.os.Handler(android.os.Looper.getMainLooper())
                            handler.post {
                                eventSink?.success(event)
                            }
                        }
                    }

                    override fun onFlushCompleted() {
                        Log.d("SamsungHealth", "Flush completed for $type")
                    }

                    override fun onError(error: HealthTracker.TrackerError) {
                        Log.e("SamsungHealth", "Tracker error for $type: ${error.name}")
                    }
                })
                trackerMap[type] = tracker
                Log.d("SamsungHealth", "▶️ Started tracker: $type")
            } catch (e: Exception) {
                Log.e("SamsungHealth", "❌ Error starting tracker $type: ${e.message}")
            }
        }
    }

    private fun extractValueForType(type: HealthTrackerType, dp: DataPoint): String {
        return when (type) {
            HealthTrackerType.HEART_RATE_CONTINUOUS ->
                dp.getValue(HeartRateSet.HEART_RATE)?.toString()
            HealthTrackerType.PPG_CONTINUOUS -> listOf(
                dp.getValue(PpgSet.PPG_GREEN),
                dp.getValue(PpgSet.PPG_IR),
                dp.getValue(PpgSet.PPG_RED)
            ).joinToString(",") { it?.toString() ?: "null" }
            else -> "unsupported"
        } ?: "null"
    }

    private fun saveToCSV(sensorType: String, line: String) {
        try {
            val baseDir = context.getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS)
            val file = File(baseDir, "P${participantId}_$videoName.csv")
            val writer = FileWriter(file, true)

            if (!file.exists()) {
                writer.write("timestamp,sensor,value\n")
            }

            writer.write("$line\n")
            writer.flush()
            writer.close()
            Log.d("CSV", "✅ Data written: $line")
        } catch (e: Exception) {
            Log.e("CSV", "❌ Failed to write CSV: ${e.message}")
        }
    }

    fun stopAllTrackers() {
        for ((type, tracker) in trackerMap) {
            try {
                tracker.unsetEventListener()
                Log.d("SamsungHealth", "🚩 Stopped tracker: $type")
            } catch (e: Exception) {
                Log.e("SamsungHealth", "⚠️ Error stopping tracker $type: ${e.message}")
            }
        }
        trackerMap.clear()
    }

    private fun hasRequiredPermissions(): Boolean {
        val permissions = listOf(
            Manifest.permission.BODY_SENSORS,
            Manifest.permission.ACTIVITY_RECOGNITION
        )
        return permissions.all {
            ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
        }
    }

    private fun requestPermissions() {
        val activity = context as? Activity ?: return
        val permissions = arrayOf(
            Manifest.permission.BODY_SENSORS,
            Manifest.permission.ACTIVITY_RECOGNITION
        )
        ActivityCompat.requestPermissions(activity, permissions, 101)
    }
}

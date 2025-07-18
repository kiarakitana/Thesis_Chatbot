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

package com.samsung.health.hrdatatransfer.presentation

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.samsung.android.service.health.tracking.HealthTrackerException
import com.samsung.health.data.TrackedData
import com.samsung.health.hrdatatransfer.data.ConnectionMessage
import com.samsung.health.hrdatatransfer.data.TrackerMessage
import com.samsung.health.hrdatatransfer.domain.AreTrackingCapabilitiesAvailableUseCase
import com.samsung.health.hrdatatransfer.domain.MakeConnectionToHealthTrackingServiceUseCase
import com.samsung.health.hrdatatransfer.domain.SendMessageUseCase
import com.samsung.health.hrdatatransfer.domain.StopTrackingUseCase
import com.samsung.health.hrdatatransfer.domain.SendTriggerUseCase
import com.samsung.health.hrdatatransfer.domain.SetSessionInfoUseCase
import com.samsung.health.hrdatatransfer.domain.TrackHeartRateUseCase
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

private const val TAG = "MainViewModel"

@HiltViewModel
class MainViewModel @Inject constructor(
    private val areTrackingCapabilitiesAvailableUseCase: AreTrackingCapabilitiesAvailableUseCase,
    private val trackHeartRateUseCase: TrackHeartRateUseCase,
    private val stopTrackingUseCase: StopTrackingUseCase,
    private val sendTriggerUseCase: SendTriggerUseCase,
    private val sendMessageUseCase: SendMessageUseCase,
    private val setSessionInfoUseCase: SetSessionInfoUseCase,
    private val makeConnectionToHealthTrackingServiceUseCase: MakeConnectionToHealthTrackingServiceUseCase
) : ViewModel() {

    private val _messageSentToast = MutableSharedFlow<Boolean>()
    val messageSentToast = _messageSentToast.asSharedFlow()

    private val _trackingState =
        MutableStateFlow(
            TrackingState(
                trackingRunning = false,
                trackingError = false,
                valueHR = "-",
                valueIBI = arrayListOf(),
                message = ""
            )
        )
    val trackingState: StateFlow<TrackingState> = _trackingState

    private val _connectionState =
        MutableStateFlow(ConnectionState(connected = false, message = "", null))
    val connectionState: StateFlow<ConnectionState> = _connectionState
    
    // Session management state
    private val _sessionState = MutableStateFlow(SessionState())
    val sessionState: StateFlow<SessionState> = _sessionState

    private var currentHR = "-"
    private var currentIBI = ArrayList<Int>(4)
    private var isTriggerSent = false

    fun stopTracking() {
        stopTrackingUseCase()
        trackingJob?.cancel()
        isTriggerSent = false
        _trackingState.value = TrackingState(
            trackingRunning = false,
            trackingError = false,
            valueHR = "-",
            valueIBI = arrayListOf(),
            message = ""
        )
    }

    fun setUpTracking() {
        Log.i(TAG, "setUpTracking()")
        viewModelScope.launch {
            makeConnectionToHealthTrackingServiceUseCase().collect { connectionMessage ->
                Log.i(TAG, "makeConnectionToHealthTrackingServiceUseCase().collect")
                when (connectionMessage) {
                    is ConnectionMessage.ConnectionSuccessMessage -> {
                        Log.i(TAG, "ConnectionMessage.ConnectionSuccessMessage")
                        _connectionState.value = ConnectionState(
                            connected = true,
                            message = "Connected to Health Tracking Service",
                            connectionException = null
                        )
                    }

                    is ConnectionMessage.ConnectionFailedMessage -> {
                        Log.i(TAG, "Connection: Sth went wrong")
                        _connectionState.value = ConnectionState(
                            connected = false,
                            message = "Connection to Health Tracking Service failed",
                            connectionException = connectionMessage.exception
                        )
                    }

                    is ConnectionMessage.ConnectionEndedMessage -> {
                        Log.i(TAG, "Connection ended")
                        _connectionState.value = ConnectionState(
                            connected = false,
                            message = "Connection ended. Try again later",
                            connectionException = null
                        )
                    }
                }
            }
        }
    }

    fun sendMessage() {
        viewModelScope.launch {
            if (sendMessageUseCase()) {
                _messageSentToast.emit(true)
            } else {
                _messageSentToast.emit(false)
            }
        }
    }

    private fun processExerciseUpdate(trackedData: TrackedData) {
                if (trackedData.hr > 90 && !isTriggerSent) {
            viewModelScope.launch {
                sendTriggerUseCase()
            }
            isTriggerSent = true
            Log.i(TAG, "Heart rate threshold exceeded (>87). Firing SendTriggerUseCase.")
        }

        val hr = trackedData.hr
        val ibi = trackedData.ibi
        Log.i(TAG, "last HeartRate: $hr, last IBI: $ibi")
        currentHR = hr.toString()
        currentIBI = ibi

        _trackingState.value = TrackingState(
            trackingRunning = true,
            trackingError = false,
            valueHR = if (hr > 0) hr.toString() else "-",
            valueIBI = ibi,
            message = ""
        )
    }

    private var trackingJob: Job? = null

    fun startTracking() {
        // Show session dialog instead of immediately starting tracking
        showSessionDialog()
    }
    
    // Shows the session info dialog
    fun showSessionDialog() {
        _sessionState.value = _sessionState.value.copy(showSessionDialog = true)
    }
    
    // Hides the session info dialog
    fun hideSessionDialog() {
        _sessionState.value = _sessionState.value.copy(showSessionDialog = false)
    }
    
    // Set session info and start tracking
    fun setSessionInfoAndStartTracking(participantId: String, interventionId: Int) {
        _sessionState.value = _sessionState.value.copy(
            participantId = participantId,
            interventionId = interventionId,
            showSessionDialog = false
        )
        startTrackingWithSessionInfo()
    }
    
    // Internal function to start tracking with session info
    private fun startTrackingWithSessionInfo() {
        try {
            trackingJob?.cancel()
            isTriggerSent = false
            
            // Get session info from state
            val participantId = _sessionState.value.participantId
            val interventionId = _sessionState.value.interventionId
            
            // Validate session info
            if (participantId.isBlank() || interventionId <= 0) {
                Log.e(TAG, "Invalid session info: participantId='$participantId', interventionId=$interventionId")
                _trackingState.value = TrackingState(
                    trackingRunning = false,
                    trackingError = true,
                    valueHR = "-",
                    valueIBI = arrayListOf(),
                    message = "Invalid session information provided"
                )
                return
            }
            
            Log.i(TAG, "Starting tracking with session info: $participantId/$interventionId")
            
            // First set the session info in the repository
            setSessionInfoUseCase(participantId, interventionId)
            
            if (areTrackingCapabilitiesAvailableUseCase()) {
            trackingJob = viewModelScope.launch {
                trackHeartRateUseCase().collect { trackerMessage ->
                    when (trackerMessage) {
                        is TrackerMessage.DataMessage -> {
                            processExerciseUpdate(trackerMessage.trackedData)
                            Log.i(TAG, "TrackerMessage.DataReceivedMessage")
                        }

                        is TrackerMessage.FlushCompletedMessage -> {
                            Log.i(TAG, "TrackerMessage.FlushCompletedMessage")
                            _trackingState.value = TrackingState(
                                trackingRunning = false,
                                trackingError = false,
                                valueHR = "-",
                                valueIBI = arrayListOf(),
                                message = ""
                            )
                        }

                        is TrackerMessage.TrackerErrorMessage -> {
                            Log.i(TAG, "TrackerMessage.TrackerErrorMessage")
                            _trackingState.value = TrackingState(
                                trackingRunning = false,
                                trackingError = true,
                                valueHR = "-",
                                valueIBI = arrayListOf(),
                                message = trackerMessage.trackerError
                            )
                        }

                        is TrackerMessage.TrackerWarningMessage -> {
                            Log.i(TAG, "TrackerMessage.TrackerWarningMessage")
                            _trackingState.value = TrackingState(
                                trackingRunning = true,
                                trackingError = false,
                                valueHR = "-",
                                valueIBI = currentIBI,
                                message = trackerMessage.trackerWarning
                            )
                        }
                        
                        // Handle any other possible message types that might be added in the future
                        else -> {
                            Log.w(TAG, "Unhandled tracker message type: $trackerMessage")
                        }
                    }
                }
            }
        } else {
            _trackingState.value = TrackingState(
                trackingRunning = false,
                trackingError = true,
                valueHR = "-",
                valueIBI = arrayListOf(),
                message = "Tracking capabilities are not available"
            )
        }
        } catch (e: Exception) {
            Log.e(TAG, "Exception during tracking startup: ${e.message}", e)
            _trackingState.value = TrackingState(
                trackingRunning = false,
                trackingError = true,
                valueHR = "-",
                valueIBI = arrayListOf(),
                message = "Error starting tracking: ${e.message ?: "Unknown error"}"
            )
        }
    }
}

data class ConnectionState(
    val connected: Boolean,
    val message: String,
    val connectionException: HealthTrackerException?
)

data class TrackingState(
    val trackingRunning: Boolean,
    val trackingError: Boolean,
    val valueHR: String,
    val valueIBI: ArrayList<Int>,
    val message: String
)

// Session management state data class
data class SessionState(
    val showSessionDialog: Boolean = false,
    val participantId: String = "",
    val interventionId: Int = 0
)

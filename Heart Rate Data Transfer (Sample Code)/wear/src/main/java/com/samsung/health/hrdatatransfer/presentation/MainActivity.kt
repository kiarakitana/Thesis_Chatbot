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

import android.annotation.SuppressLint
import android.os.Bundle
import android.util.Log
import android.view.WindowManager
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.samsung.health.hrdatatransfer.R
import com.samsung.health.hrdatatransfer.presentation.ui.MainScreen
import com.samsung.health.hrdatatransfer.presentation.ui.Permission
import dagger.hilt.android.AndroidEntryPoint

private const val TAG = "MainActivity"

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    private val viewModel by viewModels<MainViewModel>()

    @SuppressLint("VisibleForTests")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            val trackingState by viewModel.trackingState.collectAsStateWithLifecycle()
            val connectionState by viewModel.connectionState.collectAsStateWithLifecycle()
            val sessionState by viewModel.sessionState.collectAsStateWithLifecycle()
            if (trackingState.trackingRunning) {
                window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            } else {
                window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
            LaunchedEffect(Unit) {
                viewModel
                    .messageSentToast
                    .collect { message ->
                        Toast.makeText(
                            applicationContext,
                            if (message) R.string.sending_success else R.string.sending_failed,
                            Toast.LENGTH_SHORT,
                        ).show()
                    }
            }
            Log.i(
                TAG, "connected: ${connectionState.connected}, " +
                        "message: ${connectionState.message}, " +
                        "connectionException: ${connectionState.connectionException}"
            )
            connectionState.connectionException?.resolve(this)
            Permission {
                MainScreen(
                    connected = connectionState.connected,
                    connectionMessage = connectionState.message,
                    trackingRunning = trackingState.trackingRunning,
                    trackingError = trackingState.trackingError,
                    trackingMessage = trackingState.message,
                    valueHR = trackingState.valueHR,
                    valueIBI = trackingState.valueIBI,
                    onStart = { 
                        // This will trigger showing the session dialog if needed
                        viewModel.startTracking() 
                        Log.i(TAG, "startTracking()") 
                    },
                    onStop = { 
                        viewModel.stopTracking()
                        Log.i(TAG, "stopTracking()") 
                    },
                    onSend = { 
                        viewModel.sendMessage() 
                        Log.i(TAG, "sendMessage()") 
                    },
                    // Pass along the session dialog state and handlers
                    showSessionDialog = sessionState.showSessionDialog,
                    onSessionInfoProvided = { participantId, interventionId ->
                        viewModel.setSessionInfoAndStartTracking(participantId, interventionId)
                        Log.i(TAG, "Starting with P_ID=$participantId, I_ID=$interventionId")
                    },
                    onDismissSessionDialog = {
                        viewModel.hideSessionDialog()
                    }                    
                )
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (!viewModel.connectionState.value.connected) {
            viewModel.setUpTracking()
        }
    }
}
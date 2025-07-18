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

package com.samsung.health.mobile.presentation

import android.content.Intent
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.Composable
import com.samsung.health.mobile.presentation.ui.MainScreen
import dagger.hilt.android.AndroidEntryPoint

private const val TAG = "MainActivity"

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.d(TAG, "onCreate: Setting content view")
        setContent { TheApp(intent) }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        Log.d(TAG, "onNewIntent: Setting content view")
        setContent { TheApp(intent) }
    }

    override fun onResume() {
        super.onResume()
        Log.i(TAG, "onResume()")
    }
}

@Composable
fun TheApp(intent: Intent?) {
    Log.d(TAG, "TheApp composable invoked.")
    if (intent?.getStringExtra("message") != null) {
        Log.d(TAG, "Intent has a message. Decoding and showing MainScreen with data.")
        val txt = intent.getStringExtra("message").toString()

        val measurementResults = HelpFunctions.decodeMessage(txt)
        MainScreen(measurementResults)
    } else {
        Log.d(TAG, "Intent has no message. Showing MainScreen with empty list.")
        MainScreen(emptyList())
    }
}

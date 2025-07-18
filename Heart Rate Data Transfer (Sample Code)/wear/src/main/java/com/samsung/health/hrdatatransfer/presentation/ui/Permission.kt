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

package com.samsung.health.hrdatatransfer.presentation.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.wear.compose.material.Button
import androidx.wear.compose.material.Text
import com.google.accompanist.permissions.ExperimentalPermissionsApi
import com.google.accompanist.permissions.isGranted
import com.google.accompanist.permissions.rememberPermissionState
import com.google.accompanist.permissions.shouldShowRationale
import com.samsung.health.hrdatatransfer.R

@OptIn(ExperimentalPermissionsApi::class)
@Composable
fun Permission(
    onPermissionGranted: @Composable () -> Unit,
) {
    val bodySensorPermissionState =
        rememberPermissionState(android.Manifest.permission.BODY_SENSORS)

    if (bodySensorPermissionState.status.isGranted) {
        onPermissionGranted()
    } else {
        Column(
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            val textToShow = if (bodySensorPermissionState.status.shouldShowRationale) {
                stringResource(R.string.permission_should_show_rationale)
            } else {
                stringResource(R.string.permission_permanently_denied)
            }
            Text(
                modifier = Modifier.width(180.dp),
                textAlign = TextAlign.Center,
                fontSize = 13.sp,
                text = textToShow
            )
            Spacer(modifier = Modifier.size(10.dp))
            Button(onClick = { bodySensorPermissionState.launchPermissionRequest() }) {
                Text(text = "Grant Permission")
            }
        }
    }
}
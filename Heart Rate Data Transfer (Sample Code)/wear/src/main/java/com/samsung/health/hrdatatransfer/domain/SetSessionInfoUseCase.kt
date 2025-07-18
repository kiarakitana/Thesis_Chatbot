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

package com.samsung.health.hrdatatransfer.domain

import com.samsung.health.hrdatatransfer.data.TrackingRepository
import javax.inject.Inject

/**
 * Use case for setting session information in the tracking repository
 */
class SetSessionInfoUseCase @Inject constructor(private val trackingRepository: TrackingRepository) {
    
    /**
     * Sets the session identification that will be attached to biometric readings
     * 
     * @param participantId Participant identifier
     * @param interventionId Intervention identifier
     */
    operator fun invoke(participantId: String, interventionId: Int) {
        trackingRepository.setSessionInfo(participantId, interventionId)
    }
}

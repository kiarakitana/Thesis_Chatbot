package com.samsung.health.hrdatatransfer.presentation.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.wear.compose.material.Button
import androidx.wear.compose.material.ButtonDefaults
import androidx.wear.compose.material.MaterialTheme
import androidx.wear.compose.material.Text
import androidx.wear.compose.material.dialog.Dialog

/**
 * Dialog to collect session information (participant ID and intervention ID)
 * before starting biometric recording
 */
@Composable
fun SessionInputDialog(
    onSessionInfoProvided: (String, Int) -> Unit,
    onDismiss: () -> Unit,
    showSessionDialog: Boolean
) {
    if (!showSessionDialog) return
    
    var participantId by remember { mutableStateOf("") }
    var interventionIdText by remember { mutableStateOf("") }
    var showError by remember { mutableStateOf(false) }
    
    Dialog(
        showDialog = showSessionDialog,
        onDismissRequest = onDismiss
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            // Title
            Text(
                text = "Session Info",
                textAlign = TextAlign.Center,
                style = MaterialTheme.typography.title2,
                modifier = Modifier.padding(bottom = 8.dp)
            )

            // Participant ID field
            Text(
                text = "Participant ID:", 
                fontSize = 12.sp,
                modifier = Modifier.padding(top = 8.dp)
            )
            
            // Using non-material TextInput for simplicity
            androidx.compose.foundation.text.BasicTextField(
                value = participantId,
                onValueChange = { participantId = it },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(4.dp),
                textStyle = MaterialTheme.typography.body2.copy(color = Color.White),
                singleLine = true
            )
            
            Spacer(modifier = Modifier.height(8.dp))
            
            // Intervention ID field
            Text(
                text = "Intervention ID:", 
                fontSize = 12.sp
            )
            
            androidx.compose.foundation.text.BasicTextField(
                value = interventionIdText,
                onValueChange = { interventionIdText = it },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(4.dp),
                textStyle = MaterialTheme.typography.body2.copy(color = Color.White),
                singleLine = true
            )
            
            if (showError) {
                Text(
                    text = "Please fill both fields correctly",
                    color = Color.Red,
                    fontSize = 10.sp,
                    modifier = Modifier.padding(top = 4.dp)
                )
            }
            
            Spacer(modifier = Modifier.height(16.dp))
            
            // Action buttons
            Button(
                onClick = {
                    if (participantId.isNotBlank() && interventionIdText.isNotBlank()) {
                        try {
                            val interventionId = interventionIdText.toInt()
                            onSessionInfoProvided(participantId, interventionId)
                        } catch (e: NumberFormatException) {
                            showError = true
                        }
                    } else {
                        showError = true
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.primaryButtonColors()
            ) {
                Text("Start Recording")
            }
            
            Spacer(modifier = Modifier.height(8.dp))
            
            Button(
                onClick = onDismiss,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.secondaryButtonColors()
            ) {
                Text("Cancel")
            }
        }
    }
}

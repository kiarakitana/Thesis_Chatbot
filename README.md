# Therapeutic Chatbot with Biometric Monitoring

This repository contains a therapeutic chatbot application integrated with a biometric data collection system that monitors physiological responses during therapeutic conversations.

## Project Structure

- **Emoly-main/**: Contains the therapeutic chatbot Android application and backend server
- **Heart Rate Data Transfer/**: Contains the biometric data collection Android application

## Prerequisites

- Android Studio (latest version)
- Python 3.8+ with pip
- Android device with Samsung Health SDK support
- OpenAI API Key

## Installation and Setup

### 1. Python Server Setup

1. Navigate to the server directory:
   ```
   cd Emoly-main/python_chatbot
   ```

2. Install required Python packages:
   ```
   pip install flask openai pandas sqlite3 numpy scipy
   ```

3. Configure the OpenAI API key:
   - Create a `.env` file in the `python_chatbot` directory
   - Add the following line with your API key:
     ```
     OPENAI_API_KEY=your_api_key_here
     ```

### 2. Android Apps Installation

#### Therapeutic Chatbot App (Emoly-main)

This is the Aire chatbot.

1. Open Android Studio
2. Select "Open an existing project" and navigate to the `Emoly-main` directory
3. Allow Gradle sync to complete
4. Configure `api_service.dart ` and `network_security_config.xml` to point to your server address
5. Build and deploy the app to your Android device:
   - Connect your Android device via USB with debugging enabled
   - Select your device from the device dropdown
   - Click "Run" (green play button)

#### Biometric Data Collection App (Heart Rate Data Transfer)

This is the biometric sensor app. It has a wearable device component and a mobile device component.

1. Open Android Studio
2. Select "Open an existing project" and navigate to the `Heart Rate Data Transfer` directory
3. Allow Gradle sync to complete
4. Ensure the Samsung Health SDK permissions are properly configured
5. Configure `BiometricDataService.kt` and `network_security_config.xml` to point to your server address
6. Build and deploy the app to your Android devices (wearable device and mobile device):
   - Connect your Android device via USB with debugging enabled
   - Select your device from the device dropdown
   - Click "Run" (green play button)

## Running the System

### 1. Start the Python Server

1. Navigate to the server directory:
   ```
   cd Emoly-main/python_chatbot
   ```

2. Run the server:
   ```
   python refractored_bot.py
   ```
   
   The server will start on `http://localhost:5000` by default.

3. To allow connections from Android devices, use your computer's local IP address:
   ```
   python refractored_bot.py --host 0.0.0.0
   ```
   
   Then update the API endpoint in the chatbot app to use `http://your_local_ip:5000`.

### 2. Run the Biometric Data Collection App

1. Launch the Heart Rate Data Transfer app on your Android device
2. Grant necessary permissions for Samsung Health SDK
3. Follow the on-screen instructions to start biometric monitoring
4. The app should collect heart rate, interbeat interval (IBI), and skin temperature data

### 3. Run the Therapeutic Chatbot App

1. Launch the Emoly app on your Android device
2. Enter a participant ID when prompted
3. Start a new chat session
4. The chatbot will guide the user through multiple phases:
   - Phase 1: Initial emotion assessment
   - Phase 2a: First emotion regulation strategy
   - Phase 2b: Second emotion regulation strategy
   - Phase 3: Final reflection and wrap-up

## Troubleshooting

### Common Issues

1. **Samsung Health SDK Issues**:
   - If biometric data is not being collected, check that the app has proper permissions.
   - The heart rate extraction uses `getValue<Int>(ValueKey.HeartRateSet.HEART_RATE)` and doesn't require status validation.

2. **Phase Transition Problems**:
   - Ensure the chatbot is using the exact required phrases for phase transitions (e.g., "move on to phase 2b by typing 'endphase()'").

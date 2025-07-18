# Keep all Samsung SDK classes
-keep class com.samsung.** { *; }
-dontwarn com.samsung.**

# Keep all MQTT classes (used by Eclipse Paho client)
-keep class org.eclipse.paho.** { *; }
-dontwarn org.eclipse.paho.**

# Optional: Keep your own classes if you use reflection anywhere
-keep class com.example.emoly_flutter.** { *; }

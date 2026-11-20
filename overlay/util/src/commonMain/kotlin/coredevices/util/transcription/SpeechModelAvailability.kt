package coredevices.util.transcription

/** Whether an on-device speech engine has the model it needs for the configured language. */
enum class SpeechModelAvailability {
    Installed,
    Downloading,
    NotDownloaded,
    Unsupported,
}

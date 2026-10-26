package org.ssas.board.core

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
data class BellPeriod(val number: Int, val start: String, val end: String, val kind: String)

@Serializable
data class Slot(val day: Int, val period: Int, val class_code: String)

@Serializable
data class ClassFileRef(val class_code: String, val file: String, val sha256: String, val students: Int = 0)

@Serializable
data class CaptureSettings(
    val offset_min: Double = 3.0,
    val window_min: Double = 5.0,
    val shots_s: List<Int> = listOf(0, 10, 25, 45, 75, 120, 180, 240),
    val min_valid_frames: Int = 3,
)

@Serializable
data class ServerSettings(val url: String = "", val cert_sha256: String = "", val token: String = "")

/** board.json written by SSAS Studio for one board (docs/data-format.md). */
@Serializable
data class BoardConfig(
    val format: String,
    val version: Int,
    val board_code: String,
    val kind: String,
    val name: String = "",
    val school_name: String = "",
    val exported_at: String = "",
    val school_days: List<Int>,
    val bell: List<BellPeriod>,
    val slots: List<Slot>,
    val classes: List<ClassFileRef>,
    val capture: CaptureSettings = CaptureSettings(),
    val models: Map<String, ModelRef> = emptyMap(),
    val server: ServerSettings = ServerSettings(),
    val admin_pin_sha256: String = "",
    val sound: Boolean = true,
) {
    fun checkPin(pin: String): Boolean = Hashing.sha256Hex("$board_code:$pin".toByteArray()) == admin_pin_sha256

    companion object {
        private val json = Json { ignoreUnknownKeys = true }

        fun parse(text: String): BoardConfig {
            val c = json.decodeFromString(serializer(), text)
            require(c.format == "ssas.board") { "Not a board file" }
            require(c.version <= 1) { "board.json made by a newer SSAS Studio" }
            return c
        }
    }
}

object Hashing {
    fun sha256Hex(bytes: ByteArray): String {
        val md = java.security.MessageDigest.getInstance("SHA-256")
        return md.digest(bytes).joinToString("") { "%02x".format(it) }
    }

    fun sha256Hex(file: java.io.File): String {
        val md = java.security.MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buf = ByteArray(1 shl 20)
            while (true) {
                val n = input.read(buf)
                if (n <= 0) break
                md.update(buf, 0, n)
            }
        }
        return md.digest().joinToString("") { "%02x".format(it) }
    }
}

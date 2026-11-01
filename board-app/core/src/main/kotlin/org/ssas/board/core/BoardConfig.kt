package org.ssas.board.core

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/** One row of the organisation's daily times. Attendance is taken only in sessions of kind "session". */
@Serializable
data class SessionTime(val number: Int, val start: String, val end: String, val kind: String)

/** On [day] (1 = Monday), session [session] of group [group_code] is in front of this screen. */
@Serializable
data class Slot(val day: Int, val session: Int, val group_code: String)

@Serializable
data class GroupFileRef(val group_code: String, val file: String, val sha256: String, val people: Int = 0)

@Serializable
data class CaptureSettings(
    val offset_min: Double = 3.0,
    val window_min: Double = 5.0,
    val shots_s: List<Int> = listOf(0, 10, 25, 45, 75, 120, 180, 240),
    val min_valid_frames: Int = 3,
)

@Serializable
data class ServerSettings(val url: String = "", val cert_sha256: String = "", val token: String = "")

/** board.json written by SSAS Studio for one screen (format "ssas.board", version 2; docs/data-format.md). */
@Serializable
data class BoardConfig(
    val format: String,
    val version: Int,
    val board_code: String,
    val kind: String,
    val name: String = "",
    val org_name: String = "",
    val exported_at: String = "",
    val days: List<Int>,
    val sessions: List<SessionTime>,
    val slots: List<Slot>,
    val groups: List<GroupFileRef>,
    val capture: CaptureSettings = CaptureSettings(),
    val models: Map<String, ModelRef> = emptyMap(),
    val server: ServerSettings = ServerSettings(),
    val admin_pin_sha256: String = "",
    val sound: Boolean = true,
) {
    fun checkPin(pin: String): Boolean = Hashing.sha256Hex("$board_code:$pin".toByteArray()) == admin_pin_sha256

    companion object {
        const val FORMAT = "ssas.board"
        const val VERSION = 2
        private val json = Json { ignoreUnknownKeys = true }

        fun parse(text: String): BoardConfig {
            val tree = json.parseToJsonElement(text).jsonObject
            checkFormat(tree["format"]?.jsonPrimitive?.contentOrNull, tree["version"]?.jsonPrimitive?.intOrNull, FORMAT, VERSION, "board.json")
            val c = json.decodeFromJsonElement(serializer(), tree)
            // Every name below is used as a file or folder name on the screen: never let one point elsewhere.
            SafeName.check(c.board_code)
            c.groups.forEach { SafeName.check(it.group_code); SafeName.check(it.file) }
            c.models.values.forEach { SafeName.check(it.file) }
            return c
        }
    }
}

/** Checked before reading the rest, so an old file gives a clear message instead of "missing field". */
internal fun checkFormat(format: String?, version: Int?, expected: String, expectedVersion: Int, what: String) {
    require(format == expected) { "Not a $what file" }
    require(version == expectedVersion) {
        if ((version ?: 0) < expectedVersion) "$what is from an older SSAS Studio: export again with Studio 0.2"
        else "$what is from a newer SSAS Studio: update this app"
    }
}

/** File and folder names that come from the USB stick. */
object SafeName {
    private val ok = Regex("^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")

    fun isSafe(name: String) = ok.matches(name) && ".." !in name

    fun check(name: String): String {
        require(isSafe(name)) { "Unsafe file name in the USB package: ${name.take(40)}" }
        return name
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

package org.ssas.board

import android.content.Context
import org.ssas.board.core.BoardConfig
import org.ssas.board.core.GroupModel
import org.ssas.board.core.ResultPayload
import java.io.File
import java.time.LocalDate

/** Files the board keeps in its private storage. */
class BoardStore(context: Context) {
    private val root = context.filesDir
    val configDir = File(root, "config").apply { mkdirs() }
    val modelsDir = File(root, "models").apply { mkdirs() }
    val resultsDir = File(root, "results").apply { mkdirs() }
    val pendingDir = File(root, "pending").apply { mkdirs() }
    /** Results the server refused for good (broken or too old); kept so they can still be exported to USB. */
    val rejectedDir = File(root, "rejected").apply { mkdirs() }
    private val prefs = context.getSharedPreferences("ssas", Context.MODE_PRIVATE)

    val boardFile get() = File(configDir, "board.json")

    fun config(): BoardConfig? = boardFile.takeIf { it.exists() }?.let {
        runCatching { BoardConfig.parse(it.readText()) }.getOrNull()
    }

    fun groupModel(code: String): GroupModel? {
        val ref = config()?.groups?.firstOrNull { it.group_code == code } ?: return null
        val f = File(configDir, ref.file)
        return if (f.exists()) runCatching { GroupModel.parse(f.readText()) }.getOrNull() else null
    }

    fun isReady(): Boolean {
        val c = config() ?: return false
        val det = c.models["detector"]?.file ?: return false
        val emb = c.models["embedder"]?.file ?: return false
        return File(modelsDir, det).exists() && File(modelsDir, emb).exists() &&
            c.groups.all { File(configDir, it.file).exists() }
    }

    // ----- results -----
    fun saveResult(r: ResultPayload, test: Boolean) {
        val name = "${r.date}_S${r.session}_${r.group_code}${if (test) "_test" else ""}.json"
        val text = r.toJson()
        File(resultsDir, name).writeText(text)
        if (!test) File(pendingDir, name).writeText(text)
        // Keep 60 days of results on the board.
        val cutoff = LocalDate.now().minusDays(60).toString()
        resultsDir.listFiles()?.filter { it.name < cutoff }?.forEach { it.delete() }
    }

    fun results(): List<File> = resultsDir.listFiles()?.sortedByDescending { it.name } ?: emptyList()

    fun pending(): List<File> = pendingDir.listFiles()?.sortedBy { it.name } ?: emptyList()

    fun rejected(): List<File> = rejectedDir.listFiles()?.sortedBy { it.name } ?: emptyList()

    // ----- capture windows already done -----
    fun isDone(key: String) = prefs.getStringSet("done", emptySet())!!.contains(key)

    fun markDone(key: String) {
        val minDate = LocalDate.now().minusDays(1).toString()
        val keep = prefs.getStringSet("done", emptySet())!!.filter { it.take(10) >= minDate }
        prefs.edit().putStringSet("done", (keep + key).toSet()).apply()
    }

    var lastError: String?
        get() = prefs.getString("last_error", null)
        set(v) { prefs.edit().putString("last_error", v).apply() }

    var lastCapture: String?
        get() = prefs.getString("last_capture", null)
        set(v) { prefs.edit().putString("last_capture", v).apply() }

    // ----- admin PIN: 5 wrong tries lock the menu for 5 minutes (kept across restarts) -----
    fun pinLockRemainingMs(): Long =
        (prefs.getLong("pin_locked_until", 0) - System.currentTimeMillis()).coerceIn(0, PIN_LOCK_MS)

    /** Count a wrong PIN; returns the tries left (0 = now locked). */
    fun pinWrong(): Int {
        val failures = prefs.getInt("pin_failures", 0) + 1
        if (failures >= PIN_TRIES) {
            prefs.edit().putInt("pin_failures", 0).putLong("pin_locked_until", System.currentTimeMillis() + PIN_LOCK_MS).apply()
            return 0
        }
        prefs.edit().putInt("pin_failures", failures).apply()
        return PIN_TRIES - failures
    }

    fun pinRight() = prefs.edit().putInt("pin_failures", 0).apply()

    companion object {
        const val PIN_TRIES = 5
        const val PIN_LOCK_MS = 5 * 60_000L
    }
}

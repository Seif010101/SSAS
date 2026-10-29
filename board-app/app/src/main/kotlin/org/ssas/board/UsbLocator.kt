package org.ssas.board

import android.content.Context
import android.os.Build
import android.os.Environment
import android.os.storage.StorageManager
import org.ssas.board.core.UsbPackage
import java.io.File

/**
 * Finds the SSAS-USB folder by itself, without the system folder picker (many boards have none).
 * It looks on every mounted storage volume, the usual USB mount folders, and the board's own storage.
 */
object UsbLocator {
    data class Found(val root: File) {
        val label: String get() = root.path
    }

    /** Folders that were looked at (shown to the user when nothing is found). */
    fun candidateRoots(context: Context): List<File> {
        val roots = LinkedHashSet<File>()
        val sm = context.getSystemService(StorageManager::class.java)
        for (v in sm?.storageVolumes.orEmpty()) {
            val dir = if (Build.VERSION.SDK_INT >= 30) v.directory else runCatching {
                v.javaClass.getMethod("getPath").invoke(v) as String
            }.getOrNull()?.let(::File)
            dir?.let(roots::add)
        }
        for (parent in listOf("/storage", "/mnt/media_rw", "/mnt")) {
            File(parent).listFiles()?.filter { it.isDirectory && it.name !in SKIP }?.forEach(roots::add)
        }
        @Suppress("DEPRECATION")
        val internal = Environment.getExternalStorageDirectory()
        roots += internal
        roots += File(internal, Environment.DIRECTORY_DOWNLOADS)
        return roots.toList()
    }

    /** Every place with a readable SSAS-USB package, internal storage last. */
    fun find(context: Context): List<Found> = candidateRoots(context)
        .filter { root -> runCatching { File(root, UsbPackage.FOLDER).let { File(it, "ssas-usb.json").canRead() || File(it, "screens").isDirectory } }.getOrDefault(false) }
        .distinctBy { runCatching { it.canonicalPath }.getOrDefault(it.path) }
        .map(::Found)

    /** This app's own folder on each removable volume: the only place on a USB stick an app may write. */
    fun writableUsbDirs(context: Context): List<File> {
        @Suppress("DEPRECATION")
        val internal = Environment.getExternalStorageDirectory().canonicalPath
        return context.getExternalFilesDirs(null).filterNotNull().filter { dir ->
            !dir.canonicalPath.startsWith(internal) && runCatching { Environment.isExternalStorageRemovable(dir) }.getOrDefault(true)
        }
    }

    private val SKIP = setOf("self", "emulated", "asec", "obb", "secure", "user", "runtime", "expand", "vendor")
}

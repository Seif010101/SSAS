package org.ssas.board.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import java.io.InputStream

/**
 * A folder tree to read the SSAS-USB package from. Two implementations: [FileTree] (plain files, used when the
 * board can read the USB stick directly) and the app's SAF tree (when a system folder picker exists).
 * Paths are lists of names below the tree's root.
 */
interface UsbTree {
    /** Names in a folder, with true for sub-folders. Empty when the folder does not exist. */
    fun list(path: List<String>): Map<String, Boolean>
    fun open(path: List<String>): InputStream
    fun size(path: List<String>): Long = -1L
    /** Human-readable location, shown in messages. */
    val label: String
}

class FileTree(val root: File) : UsbTree {
    private fun file(path: List<String>) = path.fold(root) { f, name -> File(f, name) }
    override fun list(path: List<String>): Map<String, Boolean> =
        file(path).listFiles()?.associate { it.name to it.isDirectory } ?: emptyMap()
    override fun open(path: List<String>): InputStream = file(path).inputStream()
    override fun size(path: List<String>): Long = file(path).length()
    override val label: String get() = root.path
}

/** Reads and installs the SSAS-USB package that SSAS Studio writes (docs/data-format.md). */
class UsbPackage(private val tree: UsbTree) {
    /** Where SSAS-USB is inside the tree: the root itself, or a child folder called SSAS-USB. */
    val base: List<String> = when {
        "ssas-usb.json" in tree.list(emptyList()) -> emptyList()
        tree.list(emptyList())[FOLDER] == true -> listOf(FOLDER)
        else -> throw IllegalStateException("No $FOLDER folder in ${tree.label}. Export it from SSAS Studio first.")
    }

    private fun p(vararg names: String) = base + names
    private fun readText(path: List<String>) = tree.open(path).use { it.readBytes().toString(Charsets.UTF_8) }

    /** Board codes on the USB. */
    fun boards(): List<String> {
        if ("ssas-usb.json" in tree.list(base)) {
            val index = Json.parseToJsonElement(readText(p("ssas-usb.json"))).jsonObject
            index["boards"]?.jsonArray?.map { it.jsonPrimitive.content }?.let { return it.sorted() }
        }
        return tree.list(p("screens")).filterValues { it }.keys.sorted()
    }

    /**
     * Copy everything [board] needs into [configDir] and [modelsDir], checking every SHA-256. The old configuration
     * is replaced only when everything arrived intact. [progress] gets (message, 0..1).
     */
    fun install(board: String, configDir: File, modelsDir: File, progress: (String, Float) -> Unit = { _, _ -> }): BoardConfig {
        val dir = p("screens", board)
        val files = tree.list(dir)
        check(files.isNotEmpty()) { "Board $board not found on the USB" }
        check("board.json" in files) { "board.json missing for $board" }
        val text = readText(dir + "board.json")
        val config = BoardConfig.parse(text)

        modelsDir.mkdirs()
        val tmp = File(configDir.parentFile, "import-tmp").apply { deleteRecursively(); mkdirs() }
        try {
            for ((i, ref) in config.classes.withIndex()) {
                progress("Class ${ref.class_code}", 0.05f + 0.1f * i / config.classes.size.coerceAtLeast(1))
                check(ref.file in files) { "${ref.file} missing for $board" }
                val out = File(tmp, ref.file)
                copy(dir + ref.file, out)
                check(Hashing.sha256Hex(out) == ref.sha256) { "${ref.file} is damaged (checksum). Export again." }
            }
            val models = config.models.values.toList()
            val onUsb = tree.list(p("models"))
            for ((i, m) in models.withIndex()) {
                val target = File(modelsDir, m.file)
                if (target.exists() && Hashing.sha256Hex(target) == m.sha256) continue
                check(m.file in onUsb) { "Model ${m.file} missing on the USB" }
                val part = File(modelsDir, m.file + ".part")
                copy(p("models", m.file), part) { f -> progress("Copying ${m.file}", 0.15f + 0.8f * (i + f) / models.size) }
                check(Hashing.sha256Hex(part) == m.sha256) { part.delete(); "${m.file} is damaged (checksum). Export again." }
                target.delete()
                check(part.renameTo(target)) { "Could not save ${m.file}" }
            }
            configDir.mkdirs()
            configDir.listFiles()?.forEach { it.delete() }
            tmp.listFiles()?.forEach { it.renameTo(File(configDir, it.name)) }
            File(configDir, "board.json").writeText(text)
        } finally {
            tmp.deleteRecursively()
        }
        progress("Done", 1f)
        return config
    }

    private fun copy(path: List<String>, to: File, onProgress: ((Float) -> Unit)? = null) {
        val size = tree.size(path)
        tree.open(path).use { input ->
            to.outputStream().use { output ->
                val buf = ByteArray(1 shl 20)
                var done = 0L
                while (true) {
                    val n = input.read(buf)
                    if (n <= 0) break
                    output.write(buf, 0, n)
                    done += n
                    if (size > 0) onProgress?.invoke(done.toFloat() / size)
                }
            }
        }
    }

    companion object {
        const val FOLDER = "SSAS-USB"

        /** Result files plus a summary.csv (opens in Excel), as name -> bytes. */
        fun resultFiles(results: List<File>): Map<String, ByteArray> {
            val out = LinkedHashMap<String, ByteArray>()
            val csv = StringBuilder("date,period,class,student_id,student_name,status\n")
            for (f in results) {
                out[f.name] = f.readBytes()
                runCatching {
                    val r = ResultPayload.parse(f.readText())
                    for (s in r.students) {
                        csv.append("${r.date},${r.period},${r.class_code},${s.id},\"${s.name.replace("\"", "'")}\",${s.status}\n")
                    }
                }
            }
            out["summary.csv"] = ("﻿" + csv).toByteArray(Charsets.UTF_8)
            return out
        }

        /** Write the results into [dir]/SSAS-Results/[board]/. Returns the folder. */
        fun writeResults(dir: File, board: String, results: List<File>): File {
            val target = File(File(dir, "SSAS-Results"), board).apply { mkdirs() }
            check(target.isDirectory) { "Could not create ${target.path}" }
            for ((name, bytes) in resultFiles(results)) File(target, name).writeBytes(bytes)
            return target
        }
    }
}

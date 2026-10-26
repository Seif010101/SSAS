package org.ssas.board

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.ssas.board.core.BoardConfig
import org.ssas.board.core.Hashing
import java.io.File

/** Reads the SSAS-USB folder (chosen with the system folder picker) and installs one board's files. */
class UsbImporter(private val context: Context, private val tree: Uri) {
    private val resolver = context.contentResolver

    data class Entry(val name: String, val uri: Uri, val isDir: Boolean)

    private fun children(docId: String): List<Entry> {
        val uri = DocumentsContract.buildChildDocumentsUriUsingTree(tree, docId)
        val out = ArrayList<Entry>()
        resolver.query(uri, arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
        ), null, null, null)?.use { c ->
            while (c.moveToNext()) {
                val id = c.getString(0)
                out.add(Entry(c.getString(1), DocumentsContract.buildDocumentUriUsingTree(tree, id),
                    c.getString(2) == DocumentsContract.Document.MIME_TYPE_DIR))
            }
        }
        return out
    }

    private fun Entry.id() = DocumentsContract.getDocumentId(uri)

    private val rootId = DocumentsContract.getTreeDocumentId(tree)

    /** The SSAS-USB folder: either the chosen folder itself or a child called SSAS-USB. */
    private fun usbRoot(): String {
        val kids = children(rootId)
        if (kids.any { it.name == "ssas-usb.json" }) return rootId
        kids.firstOrNull { it.isDir && it.name == "SSAS-USB" }?.let { return it.id() }
        throw IllegalStateException("This folder does not contain SSAS-USB. Choose the USB stick or its SSAS-USB folder.")
    }

    private fun child(dirId: String, name: String): Entry? = children(dirId).firstOrNull { it.name == name }

    private fun readText(e: Entry) = resolver.openInputStream(e.uri)!!.use { it.readBytes().toString(Charsets.UTF_8) }

    /** Board codes available on the USB. */
    fun boards(): List<String> {
        val root = usbRoot()
        val index = child(root, "ssas-usb.json")?.let { Json.parseToJsonElement(readText(it)).jsonObject }
        index?.get("boards")?.jsonArray?.map { it.jsonPrimitive.content }?.let { return it.sorted() }
        val screens = child(root, "screens") ?: return emptyList()
        return children(screens.id()).filter { it.isDir }.map { it.name }.sorted()
    }

    /** Copy everything this board needs into private storage. [progress] gets (message, 0..1). */
    fun install(board: String, store: BoardStore, progress: (String, Float) -> Unit): BoardConfig {
        val root = usbRoot()
        val screens = child(root, "screens") ?: error("screens folder missing on the USB")
        val dir = child(screens.id(), board) ?: error("Board $board not found on the USB")
        val boardJson = child(dir.id(), "board.json") ?: error("board.json missing for $board")
        val text = readText(boardJson)
        val config = BoardConfig.parse(text)

        val tmp = File(store.configDir.parentFile, "import-tmp").apply { deleteRecursively(); mkdirs() }
        for ((i, ref) in config.classes.withIndex()) {
            progress("Class ${ref.class_code}", 0.05f + 0.1f * i / config.classes.size.coerceAtLeast(1))
            val e = child(dir.id(), ref.file) ?: error("${ref.file} missing for $board")
            val out = File(tmp, ref.file)
            copy(e.uri, out)
            check(Hashing.sha256Hex(out) == ref.sha256) { "${ref.file} is damaged (checksum). Export again." }
        }
        val models = child(root, "models") ?: error("models folder missing on the USB")
        val modelEntries = config.models.values.toList()
        for ((i, m) in modelEntries.withIndex()) {
            val target = File(store.modelsDir, m.file)
            if (target.exists() && Hashing.sha256Hex(target) == m.sha256) continue
            val e = child(models.id(), m.file) ?: error("Model ${m.file} missing on the USB")
            val part = File(store.modelsDir, m.file + ".part")
            copy(e.uri, part) { f -> progress("Copying ${m.file}", 0.15f + 0.8f * (i + f) / modelEntries.size) }
            check(Hashing.sha256Hex(part) == m.sha256) { "${m.file} is damaged (checksum). Export again." }
            part.renameTo(target)
        }
        // Replace the old configuration only when everything arrived intact.
        store.configDir.listFiles()?.forEach { it.delete() }
        tmp.listFiles()?.forEach { it.renameTo(File(store.configDir, it.name)) }
        tmp.deleteRecursively()
        store.boardFile.writeText(text)
        progress("Done", 1f)
        return config
    }

    private fun copy(uri: Uri, to: File, onProgress: ((Float) -> Unit)? = null) {
        val size = runCatching {
            resolver.query(uri, arrayOf(DocumentsContract.Document.COLUMN_SIZE), null, null, null)?.use {
                if (it.moveToFirst()) it.getLong(0) else -1L
            } ?: -1L
        }.getOrDefault(-1L)
        resolver.openInputStream(uri)!!.use { input ->
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

    /** Write all result files (and a CSV summary) into SSAS-Results/<board>/ on the chosen folder. */
    fun exportResults(store: BoardStore, board: String): Int {
        fun mkdir(parentId: String, name: String): String {
            child(parentId, name)?.let { return it.id() }
            val parent = DocumentsContract.buildDocumentUriUsingTree(tree, parentId)
            val created = DocumentsContract.createDocument(resolver, parent, DocumentsContract.Document.MIME_TYPE_DIR, name)
                ?: error("Could not create $name on the USB")
            return DocumentsContract.getDocumentId(created)
        }
        fun write(dirId: String, name: String, mime: String, bytes: ByteArray) {
            child(dirId, name)?.let { DocumentsContract.deleteDocument(resolver, it.uri) }
            val parent = DocumentsContract.buildDocumentUriUsingTree(tree, dirId)
            val doc = DocumentsContract.createDocument(resolver, parent, mime, name) ?: error("Could not write $name")
            resolver.openOutputStream(doc)!!.use { it.write(bytes) }
        }
        val dir = mkdir(mkdir(rootId, "SSAS-Results"), board)
        val files = store.results()
        val csv = StringBuilder("date,period,class,student_id,student_name,status\n")
        for (f in files) {
            write(dir, f.name, "application/json", f.readBytes())
            runCatching {
                val r = org.ssas.board.core.ResultPayload.parse(f.readText())
                for (s in r.students) csv.append("${r.date},${r.period},${r.class_code},${s.id},\"${s.name.replace("\"", "'")}\",${s.status}\n")
            }
        }
        write(dir, "summary.csv", "text/csv", ("﻿" + csv).toByteArray(Charsets.UTF_8))
        return files.size
    }
}


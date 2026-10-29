package org.ssas.board

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import org.ssas.board.core.UsbTree
import java.io.InputStream

/** A folder chosen with the system folder picker (only on boards that have one). Paths are names below it. */
class SafTree(context: Context, private val tree: Uri) : UsbTree {
    private val resolver = context.contentResolver
    private val rootId = DocumentsContract.getTreeDocumentId(tree)

    private data class Entry(val id: String, val name: String, val isDir: Boolean)

    private fun children(docId: String): List<Entry> {
        val uri = DocumentsContract.buildChildDocumentsUriUsingTree(tree, docId)
        val out = ArrayList<Entry>()
        resolver.query(uri, arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
        ), null, null, null)?.use { c ->
            while (c.moveToNext()) out.add(Entry(c.getString(0), c.getString(1), c.getString(2) == DocumentsContract.Document.MIME_TYPE_DIR))
        }
        return out
    }

    private fun idOf(path: List<String>): String? = path.fold(rootId as String?) { id, name ->
        id?.let { children(it).firstOrNull { e -> e.name == name }?.id }
    }

    private fun docUri(path: List<String>) =
        DocumentsContract.buildDocumentUriUsingTree(tree, idOf(path) ?: throw IllegalStateException("${path.last()} not found"))

    override fun list(path: List<String>): Map<String, Boolean> =
        idOf(path)?.let { id -> children(id).associate { it.name to it.isDir } } ?: emptyMap()

    override fun open(path: List<String>): InputStream =
        resolver.openInputStream(docUri(path)) ?: throw IllegalStateException("Cannot read ${path.last()}")

    override fun size(path: List<String>): Long = runCatching {
        resolver.query(docUri(path), arrayOf(DocumentsContract.Document.COLUMN_SIZE), null, null, null)?.use {
            if (it.moveToFirst()) it.getLong(0) else -1L
        } ?: -1L
    }.getOrDefault(-1L)

    override val label: String get() = tree.toString()

    /** Write name -> bytes into SSAS-Results/<board>/ under the chosen folder. */
    fun writeResults(board: String, files: Map<String, ByteArray>) {
        fun mkdir(parentId: String, name: String): String {
            children(parentId).firstOrNull { it.name == name }?.let { return it.id }
            val parent = DocumentsContract.buildDocumentUriUsingTree(tree, parentId)
            val created = DocumentsContract.createDocument(resolver, parent, DocumentsContract.Document.MIME_TYPE_DIR, name)
                ?: error("Could not create $name")
            return DocumentsContract.getDocumentId(created)
        }
        val dir = mkdir(mkdir(rootId, "SSAS-Results"), board)
        val parent = DocumentsContract.buildDocumentUriUsingTree(tree, dir)
        for ((name, bytes) in files) {
            children(dir).firstOrNull { it.name == name }?.let {
                DocumentsContract.deleteDocument(resolver, DocumentsContract.buildDocumentUriUsingTree(tree, it.id))
            }
            val mime = if (name.endsWith(".csv")) "text/csv" else "application/json"
            val doc = DocumentsContract.createDocument(resolver, parent, mime, name) ?: error("Could not write $name")
            resolver.openOutputStream(doc)!!.use { it.write(bytes) }
        }
    }
}

package org.ssas.board.core

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Base64

/** One registered person of a group: the id and the name shown in results. */
@Serializable
data class PersonRef(val id: String, val name: String)

@Serializable
data class Matrix(val dtype: String, val shape: List<Int>, val data: String)

@Serializable
data class Thresholds(val accept: Float, val strong: Float, val margin: Float)

@Serializable
data class ModelRef(val file: String, val sha256: String)

/** group-<code>.json as SSAS Studio writes it (format "ssas.group-model", version 2; docs/data-format.md). */
@Serializable
data class GroupModelFile(
    val format: String,
    val version: Int,
    val group_code: String,
    val created_at: String,
    val method: String,
    val models: Map<String, ModelRef> = emptyMap(),
    val people: List<PersonRef>,
    val weights: Matrix,
    val thresholds: Thresholds,
)

/** Result of matching one face against a group: the person's row, or null when nobody matched well enough. */
data class Match(val personIndex: Int?, val score: Float, val second: Float, val strong: Boolean)

/**
 * The model of one group, trained by SSAS Studio (studio/ssas_studio/core/groupmodel.py): one row of 512 numbers
 * per person. A face matches the person whose row is most similar, if that similarity passes the thresholds.
 */
class GroupModel(val file: GroupModelFile) {
    val code get() = file.group_code
    val people get() = file.people
    private val dim: Int
    private val rows: Array<FloatArray>

    init {
        checkFormat(file.format, file.version, FORMAT, VERSION, "group model")
        require(file.weights.dtype == "float32")
        val (n, d) = file.weights.shape
        require(n == file.people.size) { "One weight row per person expected" }
        dim = d
        val bb = ByteBuffer.wrap(Base64.getDecoder().decode(file.weights.data)).order(ByteOrder.LITTLE_ENDIAN)
        val fb = bb.asFloatBuffer()
        rows = Array(n) { r -> FloatArray(d) { fb.get(r * d + it) } }
    }

    fun match(embedding: FloatArray): Match {
        require(embedding.size == dim)
        var best = -1
        var top = -2f
        var second = -2f
        for ((i, w) in rows.withIndex()) {
            val s = Embedder.dot(w, embedding)
            if (s > top) {
                second = top; top = s; best = i
            } else if (s > second) {
                second = s
            }
        }
        val t = file.thresholds
        val accepted = top >= t.accept && top - second >= t.margin
        return Match(if (accepted) best else null, top, second, accepted && top >= t.strong)
    }

    companion object {
        const val FORMAT = "ssas.group-model"
        const val VERSION = 2
        private val json = Json { ignoreUnknownKeys = true }
        fun parse(text: String): GroupModel {
            val tree = json.parseToJsonElement(text).jsonObject
            checkFormat(tree["format"]?.jsonPrimitive?.contentOrNull, tree["version"]?.jsonPrimitive?.intOrNull, FORMAT, VERSION, "group model")
            return GroupModel(json.decodeFromJsonElement(GroupModelFile.serializer(), tree))
        }
    }
}

package org.ssas.board.core

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Base64

@Serializable
data class StudentRef(val id: String, val name: String)

@Serializable
data class Matrix(val dtype: String, val shape: List<Int>, val data: String)

@Serializable
data class Thresholds(val accept: Float, val strong: Float, val margin: Float)

@Serializable
data class ModelRef(val file: String, val sha256: String)

@Serializable
data class ClassModelFile(
    val format: String,
    val version: Int,
    val class_code: String,
    val created_at: String,
    val method: String,
    val models: Map<String, ModelRef> = emptyMap(),
    val students: List<StudentRef>,
    val weights: Matrix,
    val thresholds: Thresholds,
)

/** Result of matching one face against a class. */
data class Match(val studentIndex: Int?, val score: Float, val second: Float, val strong: Boolean)

/** The per-class model made by SSAS Studio (studio/ssas_studio/core/classmodel.py). */
class ClassModel(val file: ClassModelFile) {
    val code get() = file.class_code
    val students get() = file.students
    private val dim: Int
    private val rows: Array<FloatArray>

    init {
        require(file.format == "ssas.class-model") { "Not a class model" }
        require(file.version <= 1) { "Class model made by a newer SSAS Studio" }
        require(file.weights.dtype == "float32")
        val (n, d) = file.weights.shape
        require(n == file.students.size) { "One weight row per student expected" }
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
        private val json = Json { ignoreUnknownKeys = true }
        fun parse(text: String) = ClassModel(json.decodeFromString(ClassModelFile.serializer(), text))
    }
}

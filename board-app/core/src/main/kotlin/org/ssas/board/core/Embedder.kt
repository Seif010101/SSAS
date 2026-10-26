package org.ssas.board.core

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.FloatBuffer
import kotlin.math.sqrt

/** ArcFace embedder (InsightFace w600k_r50): aligned 112x112 RGB face -> 512-d unit vector. */
class Embedder(private val env: OrtEnvironment, private val session: OrtSession) {
    private val inputName = session.inputNames.first()

    fun embed(crops: List<RgbImage>): List<FloatArray> {
        if (crops.isEmpty()) return emptyList()
        val out = ArrayList<FloatArray>()
        for (chunk in crops.chunked(8)) {
            val plane = 112 * 112
            val input = FloatArray(chunk.size * 3 * plane)
            for ((b, img) in chunk.withIndex()) {
                require(img.width == 112 && img.height == 112)
                val base = b * 3 * plane
                for (p in 0 until plane) for (c in 0 until 3) {
                    input[base + c * plane + p] = ((img.data[p * 3 + c].toInt() and 0xFF) - 127.5f) / 127.5f
                }
            }
            val shape = longArrayOf(chunk.size.toLong(), 3, 112, 112)
            OnnxTensor.createTensor(env, FloatBuffer.wrap(input), shape).use { t ->
                session.run(mapOf(inputName to t)).use { res ->
                    val fb = (res.get(0) as OnnxTensor).floatBuffer
                    val dim = fb.remaining() / chunk.size
                    for (b in chunk.indices) {
                        val v = FloatArray(dim) { fb.get(b * dim + it) }
                        out.add(normalize(v))
                    }
                }
            }
        }
        return out
    }

    companion object {
        fun normalize(v: FloatArray): FloatArray {
            var s = 0.0
            for (x in v) s += x.toDouble() * x
            val n = sqrt(s).toFloat().coerceAtLeast(1e-12f)
            return FloatArray(v.size) { v[it] / n }
        }

        fun dot(a: FloatArray, b: FloatArray): Float {
            var s = 0f
            for (i in a.indices) s += a[i] * b[i]
            return s
        }
    }
}

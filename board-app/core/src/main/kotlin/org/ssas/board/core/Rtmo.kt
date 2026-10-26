package org.ssas.board.core

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.FloatBuffer

/** A person found by the pose model: box, score and 17 COCO keypoints (x, y, score). */
class Person(val box: FloatArray, val score: Float, val keypoints: FloatArray) {
    fun kp(i: Int) = floatArrayOf(keypoints[i * 3], keypoints[i * 3 + 1], keypoints[i * 3 + 2])

    /** Rough head box from nose / eyes / ears; null when the head is not visible. */
    fun headBox(minScore: Float = 0.3f): FloatArray? {
        var x1 = Float.MAX_VALUE; var y1 = Float.MAX_VALUE; var x2 = -Float.MAX_VALUE; var y2 = -Float.MAX_VALUE
        var n = 0
        for (i in 0..4) {
            val (x, y, s) = kp(i).let { Triple(it[0], it[1], it[2]) }
            if (s < minScore) continue
            x1 = minOf(x1, x); y1 = minOf(y1, y); x2 = maxOf(x2, x); y2 = maxOf(y2, y); n++
        }
        if (n < 2) return null
        val w = maxOf(x2 - x1, (box[2] - box[0]) * 0.25f)
        val cx = (x1 + x2) / 2
        val cy = (y1 + y2) / 2
        return floatArrayOf(cx - w, cy - w * 1.1f, cx + w, cy + w * 0.9f)
    }

    companion object {
        /** COCO skeleton: pairs of keypoint indices joined by a line (the "stick figure"). */
        val SKELETON = arrayOf(
            intArrayOf(5, 6), intArrayOf(5, 7), intArrayOf(7, 9), intArrayOf(6, 8), intArrayOf(8, 10),
            intArrayOf(5, 11), intArrayOf(6, 12), intArrayOf(11, 12), intArrayOf(11, 13), intArrayOf(13, 15),
            intArrayOf(12, 14), intArrayOf(14, 16), intArrayOf(0, 5), intArrayOf(0, 6),
        )
    }
}

/**
 * RTMO multi-person pose model (OpenMMLab, ONNX "end2end" export).
 * Input: BGR pixels 0..255 (no normalisation), letterboxed to 640x640 with value 114.
 * Outputs: dets (1, N, 5) = x1, y1, x2, y2, score; keypoints (1, N, 17, 3) = x, y, score.
 */
class Rtmo(private val env: OrtEnvironment, private val session: OrtSession, private val size: Int = 640) {
    var scoreThreshold = 0.3f
    private val inputName = session.inputNames.first()

    fun detect(img: RgbImage): List<Person> {
        val ratio = minOf(size.toFloat() / img.height, size.toFloat() / img.width)
        val newW = (img.width * ratio).toInt()
        val newH = (img.height * ratio).toInt()
        val resized = if (newW * 2 < img.width) img.downscaleArea(newW, newH) else img.resize(newW, newH)
        val plane = size * size
        val input = FloatArray(3 * plane) { 114f }
        for (y in 0 until newH) for (x in 0 until newW) {
            val o = (y * newW + x) * 3
            val p = y * size + x
            input[p] = (resized.data[o + 2].toInt() and 0xFF).toFloat() // B
            input[plane + p] = (resized.data[o + 1].toInt() and 0xFF).toFloat() // G
            input[2 * plane + p] = (resized.data[o].toInt() and 0xFF).toFloat() // R
        }
        val people = ArrayList<Person>()
        OnnxTensor.createTensor(env, FloatBuffer.wrap(input), longArrayOf(1, 3, size.toLong(), size.toLong())).use { t ->
            session.run(mapOf(inputName to t)).use { res ->
                var dets: OnnxTensor? = null
                var kps: OnnxTensor? = null
                for (i in 0 until res.size()) {
                    val v = res.get(i) as OnnxTensor
                    val shape = v.info.shape
                    if (shape.size == 3 && shape[2] == 5L) dets = v
                    if (shape.size == 4) kps = v
                }
                val d = dets?.floatBuffer ?: return people
                val k = kps?.floatBuffer ?: return people
                val n = dets.info.shape[1].toInt()
                val nk = kps.info.shape[2].toInt()
                for (i in 0 until n) {
                    val score = d.get(i * 5 + 4)
                    if (score < scoreThreshold) continue
                    val box = FloatArray(4) { d.get(i * 5 + it) / ratio }
                    val kp = FloatArray(nk * 3) { j -> if (j % 3 == 2) k.get(i * nk * 3 + j) else k.get(i * nk * 3 + j) / ratio }
                    people.add(Person(box, score, kp))
                }
            }
        }
        return people
    }
}

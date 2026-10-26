package org.ssas.board.core

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.FloatBuffer

/** A detected face: box (x1, y1, x2, y2), score and 5 landmarks (x, y) * 5. */
class Face(val box: FloatArray, val score: Float, val kps: FloatArray) {
    val width get() = box[2] - box[0]
    val height get() = box[3] - box[1]
    val centerX get() = (box[0] + box[2]) / 2
    val centerY get() = (box[1] + box[3]) / 2
}

/** SCRFD face detector (InsightFace det_10g); port of studio/ssas_studio/core/detect.py. */
class Scrfd(private val env: OrtEnvironment, private val session: OrtSession) {
    var scoreThreshold = 0.5f
    var nmsThreshold = 0.4f
    private val inputName = session.inputNames.first()
    private val outputNames = session.outputNames.toList()

    init {
        require(outputNames.size == 9) { "Unexpected detector model (expected 9 outputs)" }
    }

    fun detect(img: RgbImage, inW: Int, inH: Int): List<Face> {
        val (newW, newH) = if (img.height.toDouble() / img.width > inH.toDouble() / inW) {
            (inH * img.width / img.height) to inH
        } else {
            inW to (inW * img.height / img.width)
        }
        val scale = newH.toFloat() / img.height
        val resized = if (newW * 2 < img.width) img.downscaleArea(newW, newH) else img.resize(newW, newH)
        val plane = inW * inH
        val input = FloatArray(3 * plane) { (0f - 127.5f) / 128f }
        for (y in 0 until newH) for (x in 0 until newW) {
            val o = (y * newW + x) * 3
            val p = y * inW + x
            for (c in 0 until 3) input[c * plane + p] = ((resized.data[o + c].toInt() and 0xFF) - 127.5f) / 128f
        }
        val tensor = OnnxTensor.createTensor(env, FloatBuffer.wrap(input), longArrayOf(1, 3, inH.toLong(), inW.toLong()))
        val boxes = ArrayList<FloatArray>()
        val scores = ArrayList<Float>()
        val kpss = ArrayList<FloatArray>()
        tensor.use {
            session.run(mapOf(inputName to tensor)).use { res ->
                val outs = outputNames.map { (res.get(it).get() as OnnxTensor).floatBuffer }
                for ((i, stride) in intArrayOf(8, 16, 32).withIndex()) {
                    val sc = outs[i]
                    val bb = outs[i + 3]
                    val kp = outs[i + 6]
                    val h = inH / stride
                    val w = inW / stride
                    val n = h * w * 2
                    for (a in 0 until n) {
                        val s = sc.get(a)
                        if (s < scoreThreshold) continue
                        val cell = a / 2
                        val cx = (cell % w) * stride.toFloat()
                        val cy = (cell / w) * stride.toFloat()
                        boxes.add(floatArrayOf(
                            (cx - bb.get(a * 4) * stride) / scale,
                            (cy - bb.get(a * 4 + 1) * stride) / scale,
                            (cx + bb.get(a * 4 + 2) * stride) / scale,
                            (cy + bb.get(a * 4 + 3) * stride) / scale,
                        ))
                        scores.add(s)
                        kpss.add(FloatArray(10) { k ->
                            val base = if (k % 2 == 0) cx else cy
                            (base + kp.get(a * 10 + k) * stride) / scale
                        })
                    }
                }
            }
        }
        val keep = nms(boxes, scores, nmsThreshold)
        return keep.map { Face(boxes[it], scores[it], kpss[it]) }.sortedByDescending { it.width * it.height }
    }

    companion object {
        /** A detector input size (multiples of 32) keeping the frame aspect ratio. */
        fun sizeFor(width: Int, height: Int, longSide: Int): Pair<Int, Int> =
            if (width >= height) {
                longSide to maxOf(32, Math.round(longSide.toDouble() * height / width / 32.0).toInt() * 32)
            } else {
                maxOf(32, Math.round(longSide.toDouble() * width / height / 32.0).toInt() * 32) to longSide
            }

        fun nms(boxes: List<FloatArray>, scores: List<Float>, thresh: Float): List<Int> {
            val order = scores.indices.sortedByDescending { scores[it] }.toMutableList()
            val keep = ArrayList<Int>()
            while (order.isNotEmpty()) {
                val i = order.removeAt(0)
                keep.add(i)
                val a = boxes[i]
                val areaA = (a[2] - a[0] + 1) * (a[3] - a[1] + 1)
                order.removeAll { j ->
                    val b = boxes[j]
                    val w = maxOf(0f, minOf(a[2], b[2]) - maxOf(a[0], b[0]) + 1)
                    val h = maxOf(0f, minOf(a[3], b[3]) - maxOf(a[1], b[1]) + 1)
                    val inter = w * h
                    val areaB = (b[2] - b[0] + 1) * (b[3] - b[1] + 1)
                    inter / (areaA + areaB - inter) > thresh
                }
            }
            return keep
        }
    }
}

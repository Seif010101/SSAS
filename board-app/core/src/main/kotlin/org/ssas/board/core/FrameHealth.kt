package org.ssas.board.core

import kotlin.math.sqrt

/** Cheap checks that tell a broken camera picture from a real classroom. */
object FrameHealth {
    data class Report(val ok: Boolean, val reason: String?, val mean: Double, val std: Double, val signature: Long)

    fun check(img: RgbImage, previousSignature: Long? = null): Report {
        val step = maxOf(1, minOf(img.width, img.height) / 90)
        var n = 0
        var sum = 0.0
        var sumSq = 0.0
        var sig = 1125899906842597L
        var y = 0
        while (y < img.height) {
            var x = 0
            while (x < img.width) {
                val g = (img.get(x, y, 0) * 299 + img.get(x, y, 1) * 587 + img.get(x, y, 2) * 114) / 1000
                sum += g
                sumSq += g.toDouble() * g
                sig = 31 * sig + g
                n++
                x += step
            }
            y += step
        }
        val mean = sum / n
        val std = sqrt((sumSq / n - mean * mean).coerceAtLeast(0.0))
        val reason = when {
            mean < 15 && std < 5 -> "black picture (camera covered, off, or switched to another input)"
            std < 6 -> "uniform picture (lens covered?)"
            previousSignature != null && previousSignature == sig -> "frozen picture"
            else -> null
        }
        return Report(reason == null, reason, mean, std, sig)
    }
}

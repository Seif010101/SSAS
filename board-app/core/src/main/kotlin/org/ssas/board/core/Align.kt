package org.ssas.board.core

/** Similarity transform and the 112x112 ArcFace alignment (same maths as studio/ssas_studio/core/align.py). */
object Align {
    val ARCFACE_DST = doubleArrayOf(
        38.2946, 51.6963,
        73.5318, 51.5014,
        56.0252, 71.7366,
        41.5493, 92.3655,
        70.7299, 92.2041,
    )

    /** Least-squares 2D similarity (rotation + uniform scale + translation). Returns [a, b, tx, c, d, ty]. */
    fun similarity(src: DoubleArray, dst: DoubleArray): DoubleArray {
        val n = src.size / 2
        var sx = 0.0; var sy = 0.0; var dx = 0.0; var dy = 0.0
        for (i in 0 until n) {
            sx += src[2 * i]; sy += src[2 * i + 1]; dx += dst[2 * i]; dy += dst[2 * i + 1]
        }
        sx /= n; sy /= n; dx /= n; dy /= n
        var num1 = 0.0; var num2 = 0.0; var den = 0.0
        for (i in 0 until n) {
            val ax = src[2 * i] - sx; val ay = src[2 * i + 1] - sy
            val bx = dst[2 * i] - dx; val by = dst[2 * i + 1] - dy
            num1 += ax * bx + ay * by
            num2 += ax * by - ay * bx
            den += ax * ax + ay * ay
        }
        val a = num1 / den
        val b = num2 / den
        val tx = dx - (a * sx - b * sy)
        val ty = dy - (b * sx + a * sy)
        return doubleArrayOf(a, -b, tx, b, a, ty)
    }

    /** Warp [img] with the 2x3 matrix [m] (src -> dst) into a size x size image (bilinear, black border). */
    fun warp(img: RgbImage, m: DoubleArray, size: Int): RgbImage {
        val det = m[0] * m[4] - m[1] * m[3]
        val i0 = m[4] / det; val i1 = -m[1] / det
        val i3 = -m[3] / det; val i4 = m[0] / det
        val i2 = -(i0 * m[2] + i1 * m[5])
        val i5 = -(i3 * m[2] + i4 * m[5])
        val out = RgbImage(size, size)
        for (y in 0 until size) for (x in 0 until size) {
            val srcX = i0 * x + i1 * y + i2
            val srcY = i3 * x + i4 * y + i5
            for (c in 0 until 3) {
                val v = img.sample(srcX, srcY, c)
                out.data[(y * size + x) * 3 + c] = (v + 0.5).toInt().coerceIn(0, 255).toByte()
            }
        }
        return out
    }

    fun normCrop(img: RgbImage, kps: FloatArray, size: Int = 112): RgbImage {
        val src = DoubleArray(10) { kps[it].toDouble() }
        val dst = DoubleArray(10) { ARCFACE_DST[it] * size / 112.0 }
        return warp(img, similarity(src, dst), size)
    }
}

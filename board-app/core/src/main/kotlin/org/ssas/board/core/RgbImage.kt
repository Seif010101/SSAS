package org.ssas.board.core

import kotlin.math.floor
import kotlin.math.min

/** An 8-bit RGB image, pixels stored row by row as R, G, B bytes. */
class RgbImage(val width: Int, val height: Int, val data: ByteArray = ByteArray(width * height * 3)) {
    init {
        require(data.size == width * height * 3) { "data size does not match ${width}x$height" }
    }

    fun get(x: Int, y: Int, c: Int): Int = data[(y * width + x) * 3 + c].toInt() and 0xFF

    /** Bilinear sample at a real-valued position; outside the image returns [border]. */
    fun sample(x: Double, y: Double, c: Int, border: Int = 0): Double {
        val x0 = floor(x).toInt()
        val y0 = floor(y).toInt()
        val fx = x - x0
        val fy = y - y0
        fun px(xx: Int, yy: Int): Int =
            if (xx < 0 || yy < 0 || xx >= width || yy >= height) border else get(xx, yy, c)
        val a = px(x0, y0) * (1 - fx) + px(x0 + 1, y0) * fx
        val b = px(x0, y0 + 1) * (1 - fx) + px(x0 + 1, y0 + 1) * fx
        return a * (1 - fy) + b * fy
    }

    /** Resize with bilinear interpolation (pixel-centre aligned, like OpenCV INTER_LINEAR). */
    fun resize(newWidth: Int, newHeight: Int): RgbImage {
        val out = RgbImage(newWidth, newHeight)
        val sx = width.toDouble() / newWidth
        val sy = height.toDouble() / newHeight
        for (y in 0 until newHeight) {
            val srcY = ((y + 0.5) * sy - 0.5).coerceIn(0.0, (height - 1).toDouble())
            for (x in 0 until newWidth) {
                val srcX = ((x + 0.5) * sx - 0.5).coerceIn(0.0, (width - 1).toDouble())
                for (c in 0 until 3) {
                    val v = sample(srcX, srcY, c)
                    out.data[(y * newWidth + x) * 3 + c] = (v + 0.5).toInt().coerceIn(0, 255).toByte()
                }
            }
        }
        return out
    }

    /** Area-averaging downscale (used for large camera frames before detection). */
    fun downscaleArea(newWidth: Int, newHeight: Int): RgbImage {
        if (newWidth >= width || newHeight >= height) return resize(newWidth, newHeight)
        val out = RgbImage(newWidth, newHeight)
        val sx = width.toDouble() / newWidth
        val sy = height.toDouble() / newHeight
        for (y in 0 until newHeight) {
            val y0 = (y * sy).toInt()
            val y1 = min(height, ((y + 1) * sy).toInt().coerceAtLeast(y0 + 1))
            for (x in 0 until newWidth) {
                val x0 = (x * sx).toInt()
                val x1 = min(width, ((x + 1) * sx).toInt().coerceAtLeast(x0 + 1))
                for (c in 0 until 3) {
                    var sum = 0
                    for (yy in y0 until y1) for (xx in x0 until x1) sum += get(xx, yy, c)
                    out.data[(y * newWidth + x) * 3 + c] = (sum / ((y1 - y0) * (x1 - x0))).toByte()
                }
            }
        }
        return out
    }

    companion object {
        /** From packed ARGB ints (Android Bitmap.getPixels / Java BufferedImage.getRGB). */
        fun fromArgb(width: Int, height: Int, argb: IntArray): RgbImage {
            val img = RgbImage(width, height)
            for (i in 0 until width * height) {
                val p = argb[i]
                img.data[i * 3] = (p shr 16 and 0xFF).toByte()
                img.data[i * 3 + 1] = (p shr 8 and 0xFF).toByte()
                img.data[i * 3 + 2] = (p and 0xFF).toByte()
            }
            return img
        }
    }
}

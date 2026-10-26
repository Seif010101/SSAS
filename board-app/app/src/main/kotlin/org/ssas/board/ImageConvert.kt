package org.ssas.board

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.media.Image
import org.ssas.board.core.RgbImage

object ImageConvert {
    fun fromJpeg(bytes: ByteArray): Pair<RgbImage, Bitmap>? {
        val opts = BitmapFactory.Options().apply { inPreferredConfig = Bitmap.Config.ARGB_8888 }
        val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts) ?: return null
        return fromBitmap(bmp) to bmp
    }

    fun fromBitmap(bmp: Bitmap): RgbImage {
        val px = IntArray(bmp.width * bmp.height)
        bmp.getPixels(px, 0, bmp.width, 0, 0, bmp.width, bmp.height)
        return RgbImage.fromArgb(bmp.width, bmp.height, px)
    }

    /** YUV_420_888 camera image to RGB (handles row/pixel strides). */
    fun fromYuv(image: Image): RgbImage {
        val w = image.width
        val h = image.height
        val y = image.planes[0]
        val u = image.planes[1]
        val v = image.planes[2]
        val yb = y.buffer
        val ub = u.buffer
        val vb = v.buffer
        val out = RgbImage(w, h)
        for (row in 0 until h) {
            for (col in 0 until w) {
                val yy = (yb.get(row * y.rowStride + col * y.pixelStride).toInt() and 0xFF) - 16
                val uvRow = row / 2
                val uvCol = col / 2
                val uu = (ub.get(uvRow * u.rowStride + uvCol * u.pixelStride).toInt() and 0xFF) - 128
                val vv = (vb.get(uvRow * v.rowStride + uvCol * v.pixelStride).toInt() and 0xFF) - 128
                val c = 1.164f * yy
                val r = (c + 1.596f * vv).toInt().coerceIn(0, 255)
                val g = (c - 0.392f * uu - 0.813f * vv).toInt().coerceIn(0, 255)
                val b = (c + 2.017f * uu).toInt().coerceIn(0, 255)
                val o = (row * w + col) * 3
                out.data[o] = r.toByte()
                out.data[o + 1] = g.toByte()
                out.data[o + 2] = b.toByte()
            }
        }
        return out
    }

    fun toBitmap(img: RgbImage): Bitmap {
        val px = IntArray(img.width * img.height) { i ->
            val o = i * 3
            (0xFF shl 24) or ((img.data[o].toInt() and 0xFF) shl 16) or
                ((img.data[o + 1].toInt() and 0xFF) shl 8) or (img.data[o + 2].toInt() and 0xFF)
        }
        return Bitmap.createBitmap(px, img.width, img.height, Bitmap.Config.ARGB_8888)
    }
}

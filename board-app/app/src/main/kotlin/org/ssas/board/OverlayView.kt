package org.ssas.board

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.view.View
import org.ssas.board.core.Person

/** Draws a box around each head and a stick figure for each person (one colour, no names). */
class OverlayView(context: Context) : View(context) {
    var overlay: LiveState.Overlay? = null
        set(v) { field = v; invalidate() }

    private val boxPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#5EEAD4"); style = Paint.Style.STROKE; strokeWidth = 4f
    }
    private val bonePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#CCFFFFFF"); style = Paint.Style.STROKE; strokeWidth = 3f; strokeCap = Paint.Cap.ROUND
    }
    private val jointPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#5EEAD4") }

    override fun onDraw(canvas: Canvas) {
        val o = overlay ?: return
        // The picture is shown "fit centre": same scale on both axes, centred.
        val scale = minOf(width.toFloat() / o.width, height.toFloat() / o.height)
        val ox = (width - o.width * scale) / 2
        val oy = (height - o.height * scale) / 2
        fun x(v: Float) = ox + v * scale
        fun y(v: Float) = oy + v * scale
        for (p in o.people) drawPerson(canvas, p, ::x, ::y)
        for (f in o.faces) canvas.drawRect(x(f.box[0]), y(f.box[1]), x(f.box[2]), y(f.box[3]), boxPaint)
    }

    private fun drawPerson(canvas: Canvas, p: Person, x: (Float) -> Float, y: (Float) -> Float) {
        for (bone in Person.SKELETON) {
            val a = p.kp(bone[0])
            val b = p.kp(bone[1])
            if (a[2] < 0.3f || b[2] < 0.3f) continue
            canvas.drawLine(x(a[0]), y(a[1]), x(b[0]), y(b[1]), bonePaint)
        }
        for (i in 0 until 17) {
            val k = p.kp(i)
            if (k[2] >= 0.3f) canvas.drawCircle(x(k[0]), y(k[1]), 4f, jointPaint)
        }
        val head = p.headBox() ?: return
        canvas.drawRect(x(head[0]), y(head[1]), x(head[2]), y(head[3]), boxPaint)
    }
}

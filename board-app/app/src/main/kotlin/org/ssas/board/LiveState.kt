package org.ssas.board

import android.graphics.Bitmap
import android.os.Handler
import android.os.Looper
import org.ssas.board.core.Face
import org.ssas.board.core.Person

/** What the screen shows: shared between the camera service and the activity. */
object LiveState {
    data class Overlay(val width: Int, val height: Int, val faces: List<Face>, val people: List<Person>)

    @Volatile var status: String = ""
    @Volatile var capturing: Boolean = false
    @Volatile var frame: Bitmap? = null
    @Volatile var overlay: Overlay? = null

    private val main = Handler(Looper.getMainLooper())
    private val listeners = mutableSetOf<() -> Unit>()

    fun addListener(l: () -> Unit) = synchronized(listeners) { listeners.add(l) }
    fun removeListener(l: () -> Unit) = synchronized(listeners) { listeners.remove(l) }

    fun changed() {
        val copy = synchronized(listeners) { listeners.toList() }
        main.post { copy.forEach { it() } }
    }
}

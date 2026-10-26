package org.ssas.board

import android.media.AudioManager
import android.media.ToneGenerator

/** A soft beep when the camera starts and when it stops. */
object Sounds {
    fun start() = play(ToneGenerator.TONE_PROP_BEEP)
    fun end() = play(ToneGenerator.TONE_PROP_BEEP2)

    private fun play(tone: Int) {
        runCatching {
            val tg = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 35)
            tg.startTone(tone, 180)
            Thread { Thread.sleep(400); tg.release() }.start()
        }
    }
}

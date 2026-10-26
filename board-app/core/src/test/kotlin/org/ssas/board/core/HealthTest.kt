package org.ssas.board.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class HealthTest {
    @Test
    fun blackAndFrozenPicturesAreNotValid() {
        val black = RgbImage(320, 180)
        assertFalse(FrameHealth.check(black).ok)
        val real = TestSupport.image("astronaut.png")
        val first = FrameHealth.check(real)
        assertTrue(first.ok)
        val again = FrameHealth.check(real, first.signature)
        assertEquals("frozen picture", again.reason)
    }
}

package org.ssas.board.core

import java.time.LocalDate
import java.time.LocalDateTime
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class ScheduleTest {
    private val config = BoardConfig.parse(
        """
        {"format":"ssas.board","version":1,"board_code":"9A1","kind":"class",
         "school_days":[1,2,3,4,5],
         "bell":[{"number":1,"start":"07:30","end":"08:15","kind":"class"},
                 {"number":0,"start":"08:15","end":"08:35","kind":"break"},
                 {"number":2,"start":"08:35","end":"09:20","kind":"class"}],
         "slots":[{"day":1,"period":1,"class_code":"9A1"},{"day":1,"period":2,"class_code":"9A1"}],
         "classes":[],"capture":{"offset_min":3,"window_min":5},
         "admin_pin_sha256":"${Hashing.sha256Hex("9A1:2468".toByteArray())}",
         "future_field":"ignored"}
        """.trimIndent()
    )
    private val monday = LocalDate.of(2026, 10, 26)

    @Test
    fun windowsFollowTheTimetable() {
        val s = Schedule(config)
        val w = s.windowsOn(monday)
        assertEquals(listOf(1, 2), w.map { it.period })
        assertEquals(LocalDateTime.of(monday, java.time.LocalTime.of(7, 33)), w[0].opens)
        assertEquals(LocalDateTime.of(monday, java.time.LocalTime.of(7, 38)), w[0].closes)
        assertEquals(0, s.windowsOn(monday.plusDays(1)).size) // no slots on Tuesday
        assertEquals(0, s.windowsOn(monday.plusDays(5)).size) // Saturday is not a school day
    }

    @Test
    fun activeAndNext() {
        val s = Schedule(config)
        assertNull(s.active(LocalDateTime.of(monday, java.time.LocalTime.of(7, 32))))
        assertEquals(1, s.active(LocalDateTime.of(monday, java.time.LocalTime.of(7, 35)))!!.period)
        assertEquals(2, s.next(LocalDateTime.of(monday, java.time.LocalTime.of(7, 50)))!!.period)
        // After the last lesson, the next window is next Monday.
        assertEquals(monday.plusDays(7), s.next(LocalDateTime.of(monday, java.time.LocalTime.of(12, 0)))!!.date)
    }

    @Test
    fun adminPin() {
        assertEquals(true, config.checkPin("2468"))
        assertEquals(false, config.checkPin("0000"))
    }
}

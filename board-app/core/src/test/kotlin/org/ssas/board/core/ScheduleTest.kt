package org.ssas.board.core

import java.time.LocalDate
import java.time.LocalDateTime
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ScheduleTest {
    private fun boardJson(file: String = "group-9A1.json") = """
        {"format":"ssas.board","version":2,"board_code":"9A1","kind":"group",
         "days":[1,2,3,4,5],
         "sessions":[{"number":1,"start":"07:30","end":"08:15","kind":"session"},
                     {"number":0,"start":"08:15","end":"08:35","kind":"break"},
                     {"number":2,"start":"08:35","end":"09:20","kind":"session"}],
         "slots":[{"day":1,"session":1,"group_code":"9A1"},{"day":1,"session":2,"group_code":"9A1"}],
         "groups":[{"group_code":"9A1","file":"$file","sha256":"x"}],"capture":{"offset_min":3,"window_min":5},
         "admin_pin_sha256":"${Hashing.sha256Hex("9A1:493817".toByteArray())}",
         "future_field":"ignored"}
        """.trimIndent()

    private val config = BoardConfig.parse(boardJson())
    private val monday = LocalDate.of(2026, 10, 26)

    @Test
    fun windowsFollowTheTimetable() {
        val s = Schedule(config)
        val w = s.windowsOn(monday)
        assertEquals(listOf(1, 2), w.map { it.session })
        assertEquals(LocalDateTime.of(monday, java.time.LocalTime.of(7, 33)), w[0].opens)
        assertEquals(LocalDateTime.of(monday, java.time.LocalTime.of(7, 38)), w[0].closes)
        assertEquals(0, s.windowsOn(monday.plusDays(1)).size) // no slots on Tuesday
        assertEquals(0, s.windowsOn(monday.plusDays(5)).size) // Saturday is not a working day
    }

    @Test
    fun activeAndNext() {
        val s = Schedule(config)
        assertNull(s.active(LocalDateTime.of(monday, java.time.LocalTime.of(7, 32))))
        assertEquals(1, s.active(LocalDateTime.of(monday, java.time.LocalTime.of(7, 35)))!!.session)
        assertEquals(2, s.next(LocalDateTime.of(monday, java.time.LocalTime.of(7, 50)))!!.session)
        // After the last session, the next window is next Monday.
        assertEquals(monday.plusDays(7), s.next(LocalDateTime.of(monday, java.time.LocalTime.of(12, 0)))!!.date)
    }

    @Test
    fun adminPin() {
        assertEquals(true, config.checkPin("493817"))
        assertEquals(false, config.checkPin("0000"))
    }

    @Test
    fun oldOrUnsafeBoardFilesAreRefused() {
        val v1 = """{"format":"ssas.board","version":1,"board_code":"9A1","kind":"class","school_days":[1],"bell":[],
            "slots":[],"classes":[]}"""
        val old = assertFailsWith<IllegalArgumentException> { BoardConfig.parse(v1) }
        assertTrue(old.message!!.contains("export again"), old.message)
        for (bad in listOf("../../shared_prefs/ssas.xml", "..", "/etc/passwd", ".hidden", "a/b.json")) {
            assertFailsWith<IllegalArgumentException>(bad) { BoardConfig.parse(boardJson(file = bad)) }
        }
    }
}

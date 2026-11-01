package org.ssas.board.core

import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime

/** One start-of-session capture: when the camera may open and must close. */
data class CaptureWindow(
    val date: LocalDate,
    val session: Int,
    val groupCode: String,
    val sessionStart: LocalDateTime,
    val sessionEnd: LocalDateTime,
    val opens: LocalDateTime,
    val closes: LocalDateTime,
) {
    val key get() = "$date-S$session-$groupCode"
}

/** Works out the capture windows of this screen from its board.json, using the screen's own clock. */
class Schedule(private val config: BoardConfig) {
    private val sessions = config.sessions.filter { it.kind == "session" }.associateBy { it.number }

    fun windowsOn(date: LocalDate): List<CaptureWindow> {
        val day = date.dayOfWeek.value // Monday = 1 ... Sunday = 7, same as SSAS Studio
        if (day !in config.days) return emptyList()
        val cap = config.capture
        return config.slots.filter { it.day == day }.mapNotNull { slot ->
            val s = sessions[slot.session] ?: return@mapNotNull null
            val start = LocalDateTime.of(date, LocalTime.parse(s.start))
            val end = LocalDateTime.of(date, LocalTime.parse(s.end))
            val opens = start.plusSeconds((cap.offset_min * 60).toLong())
            val closes = minOf(opens.plusSeconds((cap.window_min * 60).toLong()), end)
            if (!closes.isAfter(opens)) null
            else CaptureWindow(date, slot.session, slot.group_code, start, end, opens, closes)
        }.sortedBy { it.opens }
    }

    /** The window that is open right now, if any. */
    fun active(now: LocalDateTime): CaptureWindow? =
        windowsOn(now.toLocalDate()).firstOrNull { !now.isBefore(it.opens) && now.isBefore(it.closes) }

    /** The next window that has not closed yet (today or in the next 7 days). */
    fun next(now: LocalDateTime): CaptureWindow? {
        for (d in 0..7) {
            val date = now.toLocalDate().plusDays(d.toLong())
            windowsOn(date).firstOrNull { it.closes.isAfter(now) }?.let { return it }
        }
        return null
    }
}

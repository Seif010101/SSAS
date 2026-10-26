package org.ssas.board.core

import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime

/** One start-of-lesson capture: when the camera may open and must close. */
data class CaptureWindow(
    val date: LocalDate,
    val period: Int,
    val classCode: String,
    val lessonStart: LocalDateTime,
    val lessonEnd: LocalDateTime,
    val opens: LocalDateTime,
    val closes: LocalDateTime,
) {
    val key get() = "$date-P$period-$classCode"
}

/** Works out the capture windows of this board from its board.json, using the board's own clock. */
class Schedule(private val config: BoardConfig) {
    private val periods = config.bell.filter { it.kind == "class" }.associateBy { it.number }

    fun windowsOn(date: LocalDate): List<CaptureWindow> {
        val day = date.dayOfWeek.value // Monday = 1 ... Sunday = 7, same as SSAS Studio
        if (day !in config.school_days) return emptyList()
        val cap = config.capture
        return config.slots.filter { it.day == day }.mapNotNull { slot ->
            val p = periods[slot.period] ?: return@mapNotNull null
            val start = LocalDateTime.of(date, LocalTime.parse(p.start))
            val end = LocalDateTime.of(date, LocalTime.parse(p.end))
            val opens = start.plusSeconds((cap.offset_min * 60).toLong())
            val closes = minOf(opens.plusSeconds((cap.window_min * 60).toLong()), end)
            if (!closes.isAfter(opens)) null
            else CaptureWindow(date, slot.period, slot.class_code, start, end, opens, closes)
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

package org.ssas.board.core

import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

@Serializable
data class StudentResult(val id: String, val name: String, val status: String, val score: Float? = null)

/** The text result a board sends to the server (and keeps on the board). Format "ssas.result" v1. */
@Serializable
data class ResultPayload(
    val format: String = "ssas.result",
    val version: Int = 1,
    val board_code: String,
    val class_code: String,
    val date: String,
    val period: Int,
    val lesson_start: String,
    val captured_at: String,
    val frames: Int,
    val valid_frames: Int,
    val unknown_max: Int,
    val suspicious_max: Int,
    val camera_problem: String? = null,
    val model_created_at: String,
    val app_version: String,
    val students: List<StudentResult>,
) {
    fun toJson(): String = json.encodeToString(this)

    companion object {
        private val json = Json { prettyPrint = true; encodeDefaults = true }
        fun parse(text: String): ResultPayload = Json { ignoreUnknownKeys = true }.decodeFromString(serializer(), text)

        fun build(
            board: BoardConfig, window: CaptureWindow, model: ClassModel, result: AttendanceResult,
            capturedAt: String, appVersion: String, cameraProblem: String?,
        ) = ResultPayload(
            board_code = board.board_code,
            class_code = window.classCode,
            date = window.date.toString(),
            period = window.period,
            lesson_start = window.lessonStart.toString(),
            captured_at = capturedAt,
            frames = result.totalFrames,
            valid_frames = result.validFrames,
            unknown_max = result.unknownMax,
            suspicious_max = result.suspiciousMax,
            camera_problem = cameraProblem,
            model_created_at = model.file.created_at,
            app_version = appVersion,
            students = model.students.mapIndexed { i, s ->
                StudentResult(s.id, s.name, result.statuses[i].name.lowercase(),
                    result.bestScore[i].takeIf { it > -1f })
            },
        )
    }
}

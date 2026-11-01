package org.ssas.board.core

import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

@Serializable
data class PersonResult(val id: String, val name: String, val status: String, val score: Float? = null)

/** The text result a screen sends to the server (and keeps). Format "ssas.result", version 2 (docs/data-format.md). */
@Serializable
data class ResultPayload(
    val format: String = "ssas.result",
    val version: Int = 2,
    val board_code: String,
    val group_code: String,
    val date: String,
    val session: Int,
    val session_start: String,
    val captured_at: String,
    val frames: Int,
    val valid_frames: Int,
    val unknown_max: Int,
    val suspicious_max: Int,
    val camera_problem: String? = null,
    val model_created_at: String,
    val app_version: String,
    val people: List<PersonResult>,
) {
    fun toJson(): String = json.encodeToString(this)

    companion object {
        private val json = Json { prettyPrint = true; encodeDefaults = true }
        fun parse(text: String): ResultPayload = Json { ignoreUnknownKeys = true }.decodeFromString(serializer(), text)

        fun build(
            board: BoardConfig, window: CaptureWindow, model: GroupModel, result: AttendanceResult,
            capturedAt: String, appVersion: String, cameraProblem: String?,
        ) = ResultPayload(
            board_code = board.board_code,
            group_code = window.groupCode,
            date = window.date.toString(),
            session = window.session,
            session_start = window.sessionStart.toString(),
            captured_at = capturedAt,
            frames = result.totalFrames,
            valid_frames = result.validFrames,
            unknown_max = result.unknownMax,
            suspicious_max = result.suspiciousMax,
            camera_problem = cameraProblem,
            model_created_at = model.file.created_at,
            app_version = appVersion,
            people = model.people.mapIndexed { i, p ->
                PersonResult(p.id, p.name, result.statuses[i].name.lowercase(), result.bestScore[i].takeIf { it > -1f })
            },
        )
    }
}

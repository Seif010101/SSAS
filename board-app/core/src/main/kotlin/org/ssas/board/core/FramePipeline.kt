package org.ssas.board.core

import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtLoggingLevel
import ai.onnxruntime.OrtSession
import java.io.File

/** Everything found in one frame (also used to draw boxes and stick figures on screen). */
data class FrameAnalysis(
    val observation: FrameObservation,
    val scores: Map<Int, Float>,
    val faces: List<Face>,
    val people: List<Person>,
    val health: FrameHealth.Report,
)

/**
 * Loads the ONNX models and analyses camera frames for one class.
 * Create it when a capture starts and close it afterwards to free the memory.
 */
class FramePipeline(
    modelsDir: File,
    detectorFile: String = "det_10g.onnx",
    embedderFile: String = "w600k_r50.onnx",
    poseFile: String = "rtmo-s.onnx",
    threads: Int = 2,
    private val detectLongSide: Int = 1920,
) : AutoCloseable {
    private val env = OrtEnvironment.getEnvironment()
    private val options = OrtSession.SessionOptions().apply {
        setIntraOpNumThreads(threads)
        setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        setSessionLogLevel(OrtLoggingLevel.ORT_LOGGING_LEVEL_ERROR)
    }
    private val detSession = env.createSession(File(modelsDir, detectorFile).path, options)
    private val embSession = env.createSession(File(modelsDir, embedderFile).path, options)
    private val poseSession = File(modelsDir, poseFile).takeIf { it.exists() }?.let { env.createSession(it.path, options) }
    val detector = Scrfd(env, detSession)
    val embedder = Embedder(env, embSession)
    val pose = poseSession?.let { Rtmo(env, it) }
    val hasPose get() = pose != null
    private var lastSignature: Long? = null

    /** Find people and faces only (for the on-screen preview, no recognition). */
    fun preview(img: RgbImage, longSide: Int = 960): Pair<List<Face>, List<Person>> {
        val (w, h) = Scrfd.sizeFor(img.width, img.height, longSide)
        return detector.detect(img, w, h) to (pose?.detect(img) ?: emptyList())
    }

    fun analyse(img: RgbImage, model: ClassModel, minFacePx: Float = 12f): FrameAnalysis {
        val health = FrameHealth.check(img, lastSignature)
        lastSignature = health.signature
        if (!health.ok) {
            return FrameAnalysis(FrameObservation(valid = false), emptyMap(), emptyList(), emptyList(), health)
        }
        val (w, h) = Scrfd.sizeFor(img.width, img.height, detectLongSide)
        val faces = detector.detect(img, w, h).filter { it.width >= minFacePx }
        val people = pose?.detect(img) ?: emptyList()

        // A face counts only if it sits on a body (a photo or phone held up has no body under it).
        val attached = if (pose == null) faces else faces.filter { f -> people.any { p -> faceOnBody(f, p) } }
        val suspicious = faces.size - attached.size

        val crops = attached.map { Align.normCrop(img, it.kps) }
        val embeddings = embedder.embed(crops)
        val recognised = HashMap<Int, Boolean>()
        val scores = HashMap<Int, Float>()
        var unknown = 0
        val bestFor = HashMap<Int, Float>()
        for (e in embeddings) {
            val m = model.match(e)
            val idx = m.studentIndex
            if (idx == null) {
                unknown++
                continue
            }
            // One student can only be one face: a second face matching the same student is unknown.
            if (bestFor.containsKey(idx)) {
                unknown++
                if (m.score <= bestFor.getValue(idx)) continue
            }
            bestFor[idx] = m.score
            recognised[idx] = m.strong
            scores[idx] = m.score
        }
        val obs = FrameObservation(
            valid = true, recognised = recognised, unknownFaces = unknown,
            bodies = if (pose == null) -1 else people.size, faces = attached.size, suspicious = suspicious,
        )
        return FrameAnalysis(obs, scores, faces, people, health)
    }

    private fun faceOnBody(f: Face, p: Person): Boolean {
        val head = p.headBox()
        if (head != null) {
            return f.centerX in head[0]..head[2] && f.centerY in head[1]..head[3]
        }
        val b = p.box
        val topThird = b[1] + (b[3] - b[1]) / 3
        return f.centerX in b[0]..b[2] && f.centerY in b[1]..topThird
    }

    override fun close() {
        detSession.close()
        embSession.close()
        poseSession?.close()
        options.close()
    }
}

package org.ssas.board.core

import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.io.File
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** The Kotlin pipeline must give the same answers as the Python one in SSAS Studio. */
class ParityTest {
    private val env = OrtEnvironment.getEnvironment()

    private fun session(name: String): OrtSession =
        env.createSession(File(TestSupport.modelsDir, name).path, OrtSession.SessionOptions())

    @Test
    fun detectorMatchesPython() {
        TestSupport.requireModels("det_10g.onnx")
        val det = Scrfd(env, session("det_10g.onnx"))
        val faces = det.detect(TestSupport.image("astronaut.png"), 640, 640)
        val ref = TestSupport.faces("astronaut_640")
        assertEquals(ref.size, faces.size)
        for (i in 0 until 4) assertTrue(abs(faces[0].box[i] - ref[0].first[i]) < 3f, "box[$i] ${faces[0].box[i]} vs ${ref[0].first[i]}")
        for (i in 0 until 10) assertTrue(abs(faces[0].kps[i] - ref[0].second[i]) < 3f, "kps[$i]")
    }

    @Test
    fun detectorFindsSmallBackRowFace() {
        TestSupport.requireModels("det_10g.onnx")
        val det = Scrfd(env, session("det_10g.onnx"))
        val (w, h) = Scrfd.sizeFor(1920, 1080, 1920)
        assertEquals(1920 to 1088, w to h)
        val faces = det.detect(TestSupport.image("frame_small_face.png"), w, h)
        val ref = TestSupport.faces("frame_1920")
        assertTrue(faces.isNotEmpty())
        assertTrue(abs(faces[0].box[0] - ref[0].first[0]) < 4f)
    }

    @Test
    fun embeddingMatchesPython() {
        TestSupport.requireModels("det_10g.onnx", "w600k_r50.onnx")
        val det = Scrfd(env, session("det_10g.onnx"))
        val emb = Embedder(env, session("w600k_r50.onnx"))
        val img = TestSupport.image("astronaut.png")
        val face = det.detect(img, 640, 640).first()
        val e = emb.embed(listOf(Align.normCrop(img, face.kps))).first()
        val cos = Embedder.dot(e, TestSupport.floats("astronaut_embedding"))
        assertTrue(cos > 0.99f, "cosine with Python = $cos")
        val other = Embedder.dot(e, TestSupport.floats("cameraman_embedding"))
        assertTrue(other < 0.3f, "different person must not match ($other)")
    }

    @Test
    fun fullPipelineRecognisesStudent() {
        TestSupport.requireModels("det_10g.onnx", "w600k_r50.onnx")
        val model = ClassModel.parse(TestSupport.text("class-TEST.json"))
        FramePipeline(TestSupport.modelsDir, poseFile = "missing.onnx", detectLongSide = 640).use { p ->
            val a = p.analyse(TestSupport.image("astronaut.png"), model)
            assertTrue(a.observation.valid)
            assertEquals(setOf(0), a.observation.recognised.keys)
            val c = p.analyse(TestSupport.image("cameraman.png"), model)
            assertEquals(setOf(1), c.observation.recognised.keys)
        }
    }
}

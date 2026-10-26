package org.ssas.board.core

import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.io.File
import kotlin.test.Test
import kotlin.test.assertTrue

class PoseTest {
    @Test
    fun rtmoFindsTheAstronautWithAHead() {
        TestSupport.requireModels("rtmo-s.onnx")
        val env = OrtEnvironment.getEnvironment()
        val rtmo = Rtmo(env, env.createSession(File(TestSupport.modelsDir, "rtmo-s.onnx").path, OrtSession.SessionOptions()))
        val people = rtmo.detect(TestSupport.image("astronaut.png"))
        assertTrue(people.isNotEmpty(), "no person found")
        val head = people.maxByOrNull { it.score }!!.headBox()
        assertTrue(head != null, "no head keypoints")
        // The face (from the detector test) is around x 180..270, y 60..180.
        val cx = (head[0] + head[2]) / 2
        val cy = (head[1] + head[3]) / 2
        assertTrue(cx in 170f..290f && cy in 50f..200f, "head centre $cx,$cy")
    }
}

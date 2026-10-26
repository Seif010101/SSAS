package org.ssas.board.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.float
import org.junit.jupiter.api.Assumptions.assumeTrue
import java.io.File
import javax.imageio.ImageIO

object TestSupport {
    val modelsDir: File = File(System.getProperty("ssas.models") ?: "../.models")

    fun requireModels(vararg files: String) {
        assumeTrue(files.all { File(modelsDir, it).exists() }, "models not found in $modelsDir (set SSAS_MODELS_DIR)")
    }

    fun image(name: String): RgbImage {
        val stream = javaClass.classLoader.getResourceAsStream(name) ?: error("missing test resource $name")
        val img = ImageIO.read(stream)
        val argb = img.getRGB(0, 0, img.width, img.height, null, 0, img.width)
        return RgbImage.fromArgb(img.width, img.height, argb)
    }

    fun text(name: String): String =
        javaClass.classLoader.getResourceAsStream(name)!!.readBytes().toString(Charsets.UTF_8)

    val parity: JsonObject by lazy { Json.parseToJsonElement(text("parity.json")).jsonObject }

    fun floats(key: String): FloatArray = parity[key]!!.jsonArray.map { it.jsonPrimitive.float }.toFloatArray()

    fun faces(key: String): List<Pair<FloatArray, FloatArray>> = parity[key]!!.jsonArray.map { f ->
        val o = f.jsonObject
        o["box"]!!.jsonArray.map { it.jsonPrimitive.float }.toFloatArray() to
            o["kps"]!!.jsonArray.map { it.jsonPrimitive.float }.toFloatArray()
    }
}

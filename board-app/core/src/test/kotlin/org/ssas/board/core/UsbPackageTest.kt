package org.ssas.board.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.junit.jupiter.api.io.TempDir
import java.io.File

class UsbPackageTest {
    private fun sha(b: ByteArray) = Hashing.sha256Hex(b)

    /** A SSAS-USB folder like Studio writes, with one board, one class file and two "models". */
    private fun makeUsb(stick: File, classBytes: ByteArray = "class-model".toByteArray()): File {
        val usb = File(stick, "SSAS-USB")
        val board = File(usb, "screens/9A3").apply { mkdirs() }
        val models = File(usb, "models").apply { mkdirs() }
        File(board, "class-9A3.json").writeBytes(classBytes)
        val det = "detector".toByteArray(); val emb = "embedder".toByteArray()
        File(models, "det_10g.onnx").writeBytes(det)
        File(models, "w600k_r50.onnx").writeBytes(emb)
        File(board, "board.json").writeText(
            """{"format":"ssas.board","version":1,"board_code":"9A3","kind":"class","school_days":[1],
            "bell":[],"slots":[],"classes":[{"class_code":"9A3","file":"class-9A3.json","sha256":"${sha("class-model".toByteArray())}"}],
            "models":{"detector":{"file":"det_10g.onnx","sha256":"${sha(det)}"},"embedder":{"file":"w600k_r50.onnx","sha256":"${sha(emb)}"}}}"""
        )
        File(usb, "ssas-usb.json").writeText("""{"format":"ssas.usb","version":1,"boards":["9A3"]}""")
        return usb
    }

    @Test
    fun findsTheFolderOnTheStickOrAsTheRoot(@TempDir tmp: File) {
        val usb = makeUsb(tmp)
        assertEquals(listOf("9A3"), UsbPackage(FileTree(tmp)).boards())
        assertEquals(listOf("9A3"), UsbPackage(FileTree(usb)).boards())
        assertThrows<IllegalStateException> { UsbPackage(FileTree(File(tmp, "screens"))) }
    }

    @Test
    fun installsAndChecksEveryFile(@TempDir tmp: File) {
        makeUsb(File(tmp, "stick"))
        val config = File(tmp, "board/config"); val models = File(tmp, "board/models")
        val steps = mutableListOf<String>()
        val c = UsbPackage(FileTree(File(tmp, "stick"))).install("9A3", config, models) { m, _ -> steps += m }
        assertEquals("9A3", c.board_code)
        assertTrue(File(config, "board.json").exists() && File(config, "class-9A3.json").exists())
        assertTrue(File(models, "det_10g.onnx").exists() && File(models, "w600k_r50.onnx").exists())
        assertEquals("Done", steps.last())
        assertTrue(!File(tmp, "board/import-tmp").exists())
    }

    @Test
    fun aDamagedFileKeepsTheOldConfiguration(@TempDir tmp: File) {
        makeUsb(File(tmp, "stick"), classBytes = "tampered".toByteArray())
        val config = File(tmp, "board/config").apply { mkdirs() }
        File(config, "board.json").writeText("old")
        val e = assertThrows<IllegalStateException> {
            UsbPackage(FileTree(File(tmp, "stick"))).install("9A3", config, File(tmp, "board/models"))
        }
        assertTrue(e.message!!.contains("damaged"))
        assertEquals("old", File(config, "board.json").readText())
    }

    @Test
    fun writesResultsAndASummary(@TempDir tmp: File) {
        val result = File(tmp, "2026-10-29_P1_9A3.json").apply {
            writeText(
                """{"board_code":"9A3","class_code":"9A3","date":"2026-10-29","period":1,"lesson_start":"07:30",
                "captured_at":"x","frames":3,"valid_frames":3,"unknown_max":0,"suspicious_max":0,"model_created_at":"x",
                "app_version":"t","students":[{"id":"9A3-001","name":"seif","status":"present"}]}"""
            )
        }
        val dir = UsbPackage.writeResults(File(tmp, "usb"), "9A3", listOf(result))
        assertEquals(File(tmp, "usb/SSAS-Results/9A3"), dir)
        assertTrue(File(dir, result.name).exists())
        assertTrue(File(dir, "summary.csv").readText().contains("9A3-001,\"seif\",present"))
    }
}

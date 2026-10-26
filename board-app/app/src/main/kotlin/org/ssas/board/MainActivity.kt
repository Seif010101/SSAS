package org.ssas.board

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.SurfaceTexture
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.view.TextureView
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import org.ssas.board.core.FramePipeline

/**
 * The only screen: the camera picture with head boxes and stick figures, and a small status line.
 * No settings for teachers; the hidden admin menu (long-press the title + PIN) imports from USB etc.
 */
class MainActivity : Activity() {
    private lateinit var store: BoardStore
    private lateinit var texture: TextureView
    private lateinit var still: ImageView
    private lateinit var overlay: OverlayView
    private lateinit var title: TextView
    private lateinit var status: TextView
    private lateinit var setupPanel: LinearLayout
    private val main = Handler(Looper.getMainLooper())

    private var camera: CameraController? = null
    private var pipeline: FramePipeline? = null
    private var analysisThread: HandlerThread? = null
    private var lastAnalysis = 0L
    @Volatile private var analysing = false
    private val listener: () -> Unit = { refresh() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = BoardStore(this)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        buildUi()
        askPermissions()
    }

    // ---------- UI ----------
    private fun buildUi() {
        val root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        texture = TextureView(this)
        root.addView(texture, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT, Gravity.CENTER))
        still = ImageView(this).apply { scaleType = ImageView.ScaleType.FIT_CENTER; visibility = View.GONE }
        root.addView(still, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        overlay = OverlayView(this)
        root.addView(overlay, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))

        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#B3000000"))
            setPadding(32, 18, 32, 18)
        }
        title = TextView(this).apply {
            setTextColor(Color.WHITE); textSize = 22f; setTypeface(typeface, android.graphics.Typeface.BOLD)
            setOnLongClickListener { askPin(); true }
        }
        status = TextView(this).apply { setTextColor(Color.parseColor("#CBD5E1")); textSize = 16f }
        bar.addView(title)
        bar.addView(status)
        root.addView(bar, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP))

        setupPanel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(48, 48, 48, 48)
            setBackgroundColor(Color.parseColor("#0F172A"))
            addView(TextView(context).apply {
                text = "This board is not set up yet.\n\nPlug in the USB stick made by SSAS Studio, press the button and choose the USB stick (or its SSAS-USB folder)."
                setTextColor(Color.WHITE); textSize = 20f; gravity = Gravity.CENTER
            })
            addView(Button(context).apply {
                text = "Import from USB"
                textSize = 20f
                setOnClickListener { pickFolder(REQ_IMPORT) }
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = 40 })
        }
        root.addView(setupPanel, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        setContentView(root)
    }

    private fun refresh() {
        val config = store.config()
        val ready = config != null && store.isReady()
        setupPanel.visibility = if (ready) View.GONE else View.VISIBLE
        title.text = if (config == null) "SSAS Board" else "SSAS Board · ${config.board_code}${if (config.kind == "lab") " (${config.name})" else ""}"
        val armed = if (AttendanceService.armed) "Ready ✓" else "Not running — open the app again"
        status.text = listOfNotNull(armed, LiveState.status.ifBlank { null },
            store.lastCapture?.let { "Last: $it" }).joinToString("   ·   ")
        if (LiveState.capturing) {
            stopPreview()
            texture.visibility = View.GONE
            still.visibility = View.VISIBLE
            LiveState.frame?.let { still.setImageBitmap(it) }
            overlay.overlay = LiveState.overlay
        } else {
            still.visibility = View.GONE
            texture.visibility = View.VISIBLE
            if (ready && hasCamera() && hasWindowFocus()) startPreview()
        }
    }

    override fun onResume() {
        super.onResume()
        LiveState.addListener(listener)
        refresh()
    }

    override fun onPause() {
        LiveState.removeListener(listener)
        stopPreview()
        super.onPause()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) refresh()
    }

    // ---------- permissions & service ----------
    private fun hasCamera() = checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

    private fun askPermissions() {
        val need = mutableListOf<String>()
        if (!hasCamera()) need += Manifest.permission.CAMERA
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            need += Manifest.permission.POST_NOTIFICATIONS
        }
        if (need.isEmpty()) arm() else requestPermissions(need.toTypedArray(), REQ_PERMS)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (hasCamera()) arm() else status.text = "Camera permission is needed. Open the app again and allow the camera."
    }

    private fun arm() {
        AttendanceService.start(this)
        // Opened automatically at power-on (Hikvision Auto-Launch): go to the background straight away.
        if (SystemClock.elapsedRealtime() < 4 * 60 * 1000 && store.isReady() && intent?.getBooleanExtra("from_admin", false) != true) {
            main.postDelayed({ moveTaskToBack(true) }, 1500)
        }
        main.postDelayed({ refresh() }, 800)
    }

    // ---------- live preview ----------
    private fun startPreview() {
        if (camera != null || LiveState.capturing) return
        val st = texture.surfaceTexture
        if (st == null) {
            texture.surfaceTextureListener = object : TextureView.SurfaceTextureListener {
                override fun onSurfaceTextureAvailable(s: SurfaceTexture, w: Int, h: Int) = refresh()
                override fun onSurfaceTextureSizeChanged(s: SurfaceTexture, w: Int, h: Int) {}
                override fun onSurfaceTextureDestroyed(s: SurfaceTexture) = true
                override fun onSurfaceTextureUpdated(s: SurfaceTexture) {}
            }
            return
        }
        val t = HandlerThread("ssas-preview").apply { start() }
        analysisThread = t
        val h = Handler(t.looper)
        h.post {
            try {
                val cfg = store.config() ?: return@post
                pipeline = FramePipeline(store.modelsDir,
                    detectorFile = cfg.models["detector"]?.file ?: "det_10g.onnx",
                    embedderFile = cfg.models["embedder"]?.file ?: "w600k_r50.onnx",
                    poseFile = cfg.models["pose"]?.file ?: "rtmo-s.onnx", threads = 2)
                val cam = CameraController(this)
                cam.open(st, onPreviewFrame = { img ->
                    val now = SystemClock.elapsedRealtime()
                    if (!analysing && now - lastAnalysis > 900) {
                        lastAnalysis = now
                        analysing = true
                        val rgb = ImageConvert.fromYuv(img)
                        h.post {
                            try {
                                val (faces, people) = pipeline?.preview(rgb, 640) ?: return@post
                                val o = LiveState.Overlay(rgb.width, rgb.height, faces, people)
                                main.post { overlay.overlay = o }
                            } finally { analysing = false }
                        }
                    }
                }, withStills = false)
                camera = cam
                main.post { fitTexture(cam) }
            } catch (e: Exception) {
                main.post { status.text = "Camera preview: ${e.message}" }
            }
        }
    }

    private fun fitTexture(cam: CameraController) {
        // Keep the picture's aspect ratio (preview frames are 4:3 or 16:9).
        val parent = texture.parent as View
        val pw = parent.width.toFloat()
        val ph = parent.height.toFloat()
        if (pw == 0f || ph == 0f) return
        val ratio = cam.previewAspect
        val (w, h) = if (pw / ph > ratio) (ph * ratio) to ph else pw to (pw / ratio)
        texture.layoutParams = FrameLayout.LayoutParams(w.toInt(), h.toInt(), Gravity.CENTER)
    }

    private fun stopPreview() {
        val cam = camera
        camera = null
        val p = pipeline
        pipeline = null
        val t = analysisThread
        analysisThread = null
        overlay.overlay = null
        if (t != null) {
            Handler(t.looper).post {
                runCatching { cam?.close() }
                runCatching { p?.close() }
                t.quitSafely()
            }
        } else {
            runCatching { cam?.close() }
        }
    }

    // ---------- admin ----------
    private fun askPin() {
        val config = store.config()
        if (config == null) { adminMenu(); return }
        val input = EditText(this).apply { inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD; hint = "PIN" }
        AlertDialog.Builder(this).setTitle("Admin PIN").setView(input)
            .setPositiveButton("OK") { _, _ ->
                if (config.checkPin(input.text.toString())) adminMenu() else status.text = "Wrong PIN"
            }
            .setNegativeButton("Cancel", null).show()
    }

    private fun adminMenu() {
        val items = arrayOf(
            "Import from USB",
            "Take attendance now (test)",
            "Export results to USB",
            "Show last results",
            "Allow restart after power cut (display over other apps)",
            "Hide this screen",
        )
        AlertDialog.Builder(this).setTitle("SSAS Board — admin").setItems(items) { _, which ->
            when (which) {
                0 -> pickFolder(REQ_IMPORT)
                1 -> { stopPreview(); AttendanceService.start(this, test = true) }
                2 -> pickFolder(REQ_EXPORT)
                3 -> showResults()
                4 -> startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
                5 -> moveTaskToBack(true)
            }
        }.show()
    }

    private fun showResults() {
        val files = store.results().take(20)
        val text = if (files.isEmpty()) "No results yet." else files.joinToString("\n") { f ->
            runCatching {
                val r = org.ssas.board.core.ResultPayload.parse(f.readText())
                val c = r.students.groupingBy { it.status }.eachCount()
                "${r.date} P${r.period} ${r.class_code}: ${c["present"] ?: 0} present, ${c["absent"] ?: 0} absent, ${c["needs_review"] ?: 0} review" +
                    (if (f.name.contains("_test")) " [test]" else "")
            }.getOrDefault(f.name)
        }
        val pending = store.pending().size
        AlertDialog.Builder(this).setTitle("Last results").setMessage(
            text + "\n\nWaiting to be sent to the server: $pending" + (store.lastError?.let { "\nLast problem: $it" } ?: "")
        ).setPositiveButton("OK", null).show()
    }

    @Suppress("DEPRECATION")
    private fun pickFolder(request: Int) {
        val i = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).addFlags(
            Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
        )
        try {
            startActivityForResult(i, request)
        } catch (e: Exception) {
            AlertDialog.Builder(this).setMessage("This board has no folder picker: ${e.message}").setPositiveButton("OK", null).show()
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data ?: return
        if (resultCode != RESULT_OK) return
        when (requestCode) {
            REQ_IMPORT -> importFrom(uri)
            REQ_EXPORT -> exportTo(uri)
        }
    }

    private fun progressDialog(title: String): Pair<AlertDialog, TextView> {
        val tv = TextView(this).apply { setPadding(48, 32, 48, 32); textSize = 18f }
        val d = AlertDialog.Builder(this).setTitle(title).setView(tv).setCancelable(false).create()
        d.show()
        return d to tv
    }

    private fun importFrom(uri: Uri) {
        val importer = UsbImporter(this, uri)
        Thread {
            val boards = runCatching { importer.boards() }
            main.post {
                boards.onFailure { msg(it.message ?: "Could not read the USB") }
                boards.onSuccess { list ->
                    if (list.isEmpty()) return@onSuccess msg("No boards found on the USB.")
                    AlertDialog.Builder(this).setTitle("Which board is this?").setItems(list.toTypedArray()) { _, i ->
                        install(importer, list[i])
                    }.show()
                }
            }
        }.start()
    }

    private fun install(importer: UsbImporter, board: String) {
        stopPreview()
        val (dialog, text) = progressDialog("Importing $board")
        Thread {
            val r = runCatching {
                importer.install(board, store) { m, f -> main.post { text.text = "$m\n${(f * 100).toInt()}%" } }
            }
            main.post {
                dialog.dismiss()
                r.onSuccess { msg("Board ${it.board_code} is ready.\nIt will take attendance by itself at the start of each lesson.") }
                r.onFailure { msg("Import failed: ${it.message}") }
                refresh()
            }
        }.start()
    }

    private fun exportTo(uri: Uri) {
        val board = store.config()?.board_code ?: "board"
        Thread {
            val r = runCatching { UsbImporter(this, uri).exportResults(store, board) }
            main.post {
                r.onSuccess { msg("$it result files copied to SSAS-Results/$board on the USB.") }
                r.onFailure { msg("Export failed: ${it.message}") }
            }
        }.start()
    }

    private fun msg(text: String) {
        AlertDialog.Builder(this).setMessage(text).setPositiveButton("OK", null).show()
    }

    companion object {
        private const val REQ_PERMS = 1
        private const val REQ_IMPORT = 2
        private const val REQ_EXPORT = 3
    }
}

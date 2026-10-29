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
import org.ssas.board.core.FileTree
import org.ssas.board.core.FramePipeline
import org.ssas.board.core.UsbPackage
import org.ssas.board.core.UsbTree

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
                text = "This board is not set up yet.\n\nPlug in the USB stick made by SSAS Studio and press the button. The board finds the SSAS-USB folder by itself."
                setTextColor(Color.WHITE); textSize = 20f; gravity = Gravity.CENTER
            })
            addView(Button(context).apply {
                text = "Import from USB"
                textSize = 20f
                setOnClickListener { startImport() }
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
        if (requestCode == REQ_STORAGE) {
            if (hasStorage()) startImport() else msg("Storage permission is needed to read the USB stick. Press Import again and allow it.")
            return
        }
        if (hasCamera()) arm() else status.text = "Camera permission is needed. Open the app again and allow the camera."
    }

    private fun hasStorage() = checkSelfPermission(Manifest.permission.READ_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED

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
                0 -> startImport()
                1 -> { stopPreview(); AttendanceService.start(this, test = true) }
                2 -> startExport()
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

    // ---------- USB: import and export ----------
    // The board looks for the SSAS-USB folder by itself (UsbLocator); the system folder picker is only a fallback,
    // because most boards do not have one.

    private fun hasFolderPicker() = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).resolveActivity(packageManager) != null

    private fun startImport() {
        if (!hasStorage()) {
            requestPermissions(arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE, Manifest.permission.WRITE_EXTERNAL_STORAGE), REQ_STORAGE)
            return
        }
        val (dialog, _) = progressDialog("Looking for the USB stick…")
        Thread {
            val found = runCatching { UsbLocator.find(this) }.getOrDefault(emptyList())
            main.post {
                dialog.dismiss()
                when (found.size) {
                    0 -> notFound()
                    1 -> openPackage(FileTree(found[0].root))
                    else -> AlertDialog.Builder(this).setTitle("Which USB stick?")
                        .setItems(found.map { it.label }.toTypedArray()) { _, i -> openPackage(FileTree(found[i].root)) }
                        .show()
                }
            }
        }.start()
    }

    private fun notFound() {
        val searched = UsbLocator.candidateRoots(this).joinToString("\n") { it.path }
        val b = AlertDialog.Builder(this).setTitle("No SSAS-USB folder found").setMessage(
            "Plug in the USB stick made by SSAS Studio (Export to USB), wait a few seconds and try again.\n\n" +
                "Or copy the SSAS-USB folder into this board's Download folder with its file manager.\n\nSearched:\n$searched"
        ).setPositiveButton("Try again") { _, _ -> startImport() }.setNegativeButton("Close", null)
        if (hasFolderPicker()) b.setNeutralButton("Choose folder…") { _, _ -> pickFolder(REQ_IMPORT) }
        b.show()
    }

    private fun openPackage(tree: UsbTree) {
        Thread {
            val r = runCatching { UsbPackage(tree).let { it to it.boards() } }
            main.post {
                r.onFailure { msg(it.message ?: "Could not read the USB stick") }
                r.onSuccess { (pkg, boards) ->
                    if (boards.isEmpty()) return@onSuccess msg("No boards found in ${tree.label}.")
                    AlertDialog.Builder(this).setTitle("Which board is this?").setItems(boards.toTypedArray()) { _, i ->
                        install(pkg, boards[i])
                    }.show()
                }
            }
        }.start()
    }

    private fun install(pkg: UsbPackage, board: String) {
        stopPreview()
        val (dialog, text) = progressDialog("Importing $board")
        Thread {
            val r = runCatching {
                pkg.install(board, store.configDir, store.modelsDir) { m, f -> main.post { text.text = "$m\n${(f * 100).toInt()}%" } }
            }
            main.post {
                dialog.dismiss()
                r.onSuccess { msg("Board ${it.board_code} is ready.\nIt will take attendance by itself at the start of each lesson.") }
                r.onFailure { msg("Import failed: ${it.message}") }
                refresh()
            }
        }.start()
    }

    /** Apps may only write into their own folder on a USB stick: <USB>/Android/data/<app>/files/SSAS-Results/<board>. */
    private fun startExport() {
        val board = store.config()?.board_code ?: "board"
        val dirs = UsbLocator.writableUsbDirs(this)
        if (dirs.isEmpty()) {
            val b = AlertDialog.Builder(this).setMessage("No USB stick found. Plug it in, wait a few seconds and try again.")
                .setPositiveButton("Try again") { _, _ -> startExport() }.setNegativeButton("Close", null)
            if (hasFolderPicker()) b.setNeutralButton("Choose folder…") { _, _ -> pickFolder(REQ_EXPORT) }
            b.show()
            return
        }
        Thread {
            val r = runCatching { UsbPackage.writeResults(dirs[0], board, store.results()) }
            main.post {
                r.onSuccess { dir ->
                    msg("${store.results().size} result files and summary.csv copied to the USB stick, in:\n\n" +
                        "Android/data/$packageName/files/SSAS-Results/$board\n\n($dir)")
                }
                r.onFailure { msg("Export failed: ${it.message}") }
            }
        }.start()
    }

    @Suppress("DEPRECATION")
    private fun pickFolder(request: Int) {
        val i = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).addFlags(
            Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
        )
        try {
            startActivityForResult(i, request)
        } catch (e: Exception) {
            msg("This board has no folder picker: ${e.message}")
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data ?: return
        if (resultCode != RESULT_OK) return
        when (requestCode) {
            REQ_IMPORT -> openPackage(SafTree(this, uri))
            REQ_EXPORT -> {
                val board = store.config()?.board_code ?: "board"
                Thread {
                    val r = runCatching { SafTree(this, uri).writeResults(board, UsbPackage.resultFiles(store.results())) }
                    main.post {
                        r.onSuccess { msg("Results copied to SSAS-Results/$board.") }
                        r.onFailure { msg("Export failed: ${it.message}") }
                    }
                }.start()
            }
        }
    }

    private fun progressDialog(title: String): Pair<AlertDialog, TextView> {
        val tv = TextView(this).apply { setPadding(48, 32, 48, 32); textSize = 18f }
        val d = AlertDialog.Builder(this).setTitle(title).setView(tv).setCancelable(false).create()
        d.show()
        return d to tv
    }

    private fun msg(text: String) {
        AlertDialog.Builder(this).setMessage(text).setPositiveButton("OK", null).show()
    }

    companion object {
        private const val REQ_PERMS = 1
        private const val REQ_IMPORT = 2
        private const val REQ_EXPORT = 3
        private const val REQ_STORAGE = 4
    }
}

package org.ssas.board

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.os.Process
import android.util.Log
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.ssas.board.core.AttendanceAggregator
import org.ssas.board.core.CaptureWindow
import org.ssas.board.core.FramePipeline
import org.ssas.board.core.ResultPayload
import org.ssas.board.core.Schedule
import java.time.LocalDateTime
import java.time.temporal.ChronoUnit
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Runs all day in the background (foreground service of type "camera", started while the app was
 * visible so Android keeps camera access). Opens the camera only inside the capture windows of the
 * timetable, takes attendance, closes the camera and stores / sends the text result.
 */
class AttendanceService : Service() {
    private lateinit var store: BoardStore
    private lateinit var scheduler: ScheduledExecutorService
    private val worker = Executors.newSingleThreadExecutor { r ->
        Thread({ Process.setThreadPriority(Process.THREAD_PRIORITY_BACKGROUND); r.run() }, "ssas-capture")
    }
    private val busy = AtomicBoolean(false)

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        store = BoardStore(this)
        armed = true
        goForeground("Ready")
        scheduler = Executors.newSingleThreadScheduledExecutor()
        scheduler.scheduleWithFixedDelay({ safely { tick() } }, 2, 20, TimeUnit.SECONDS)
        scheduler.scheduleWithFixedDelay({ safely { heartbeatAndUpload() } }, 30, 300, TimeUnit.SECONDS)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_TEST) {
            safely { startCapture(test = true) }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        armed = false
        scheduler.shutdownNow()
        worker.shutdownNow()
        super.onDestroy()
    }

    private fun safely(block: () -> Unit) {
        try { block() } catch (t: Throwable) {
            Log.e(TAG, "error", t)
            store.lastError = "${LocalDateTime.now().truncatedTo(ChronoUnit.SECONDS)}: ${t.message ?: t.javaClass.simpleName}"
        }
    }

    private fun tick() {
        val config = store.config() ?: return status("Not set up — import from USB")
        val now = LocalDateTime.now()
        val schedule = Schedule(config)
        val active = schedule.active(now)
        if (active != null && !store.isDone(active.key) && !busy.get()) {
            startCapture(test = false, window = active)
        } else if (!busy.get()) {
            val next = schedule.next(now)
            status(if (next == null) "No lessons in the timetable" else "Next attendance: ${next.classCode} · ${next.date} ${next.opens.toLocalTime().truncatedTo(ChronoUnit.MINUTES)}")
        }
    }

    private fun startCapture(test: Boolean, window: CaptureWindow? = null) {
        if (!busy.compareAndSet(false, true)) return
        worker.execute {
            try { capture(test, window) } catch (t: Throwable) {
                Log.e(TAG, "capture failed", t)
                store.lastError = "${LocalDateTime.now().truncatedTo(ChronoUnit.SECONDS)}: ${t.message ?: t.javaClass.simpleName}"
            } finally {
                busy.set(false)
                LiveState.capturing = false
                LiveState.changed()
            }
        }
    }

    private fun capture(test: Boolean, given: CaptureWindow?) {
        val config = store.config() ?: return
        val now = LocalDateTime.now()
        val window = given ?: run {
            // Test capture: use the class of the current or next lesson for 1 minute.
            val code = Schedule(config).active(now)?.classCode ?: Schedule(config).next(now)?.classCode
                ?: config.classes.firstOrNull()?.class_code ?: return
            CaptureWindow(now.toLocalDate(), 0, code, now, now.plusMinutes(45), now, now.plusMinutes(1))
        }
        val model = store.classModel(window.classCode) ?: run {
            status("No model for class ${window.classCode} — import again"); return
        }
        if (!test) store.markDone(window.key)
        val wake = (getSystemService(Context.POWER_SERVICE) as PowerManager)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ssas:capture").apply { acquire(15 * 60 * 1000L) }
        LiveState.capturing = true
        status("Taking attendance · ${window.classCode}")
        Thread.sleep(1500) // give the screen time to release its camera preview
        if (config.sound) Sounds.start()

        val agg = AttendanceAggregator(model.students.size, config.capture.min_valid_frames)
        var cameraProblem: String? = null
        val started = System.currentTimeMillis()
        val closesAt = started + java.time.Duration.between(now.coerceAtLeast(window.opens), window.closes).toMillis()
            .coerceAtLeast(30_000L)
        try {
            FramePipeline(store.modelsDir,
                detectorFile = config.models["detector"]?.file ?: "det_10g.onnx",
                embedderFile = config.models["embedder"]?.file ?: "w600k_r50.onnx",
                poseFile = config.models["pose"]?.file ?: "rtmo-s.onnx").use { pipeline ->
                var camera: CameraController? = null
                try {
                    for (shot in config.capture.shots_s) {
                        val at = started + shot * 1000L
                        if (at >= closesAt) break
                        val wait = at - System.currentTimeMillis()
                        if (wait > 0) Thread.sleep(wait)
                        if (camera == null) {
                            camera = runCatching {
                                CameraController(this).also { it.open(); Thread.sleep(2500) } // let exposure settle
                            }.onFailure { cameraProblem = it.message }.getOrNull()
                            if (camera == null) {
                                agg.add(org.ssas.board.core.FrameObservation(valid = false))
                                continue
                            }
                        }
                        val jpeg = try { camera.takeJpeg() } catch (e: CameraUnavailable) {
                            cameraProblem = e.message
                            camera.close(); camera = null
                            agg.add(org.ssas.board.core.FrameObservation(valid = false))
                            continue
                        }
                        val (img, bmp) = ImageConvert.fromJpeg(jpeg) ?: continue
                        val a = pipeline.analyse(img, model)
                        if (!a.health.ok) cameraProblem = a.health.reason
                        agg.add(a.observation, a.scores)
                        LiveState.frame = scaledForScreen(bmp)
                        LiveState.overlay = LiveState.Overlay(img.width, img.height, a.faces, a.people)
                        LiveState.changed()
                        bmp.recycle()
                        val present = (0 until model.students.size).count { agg.isPresent(it) }
                        status("Taking attendance · ${window.classCode} · $present / ${model.students.size} recognised")
                        if (agg.allPresent() && agg.validFrames >= 1) break
                    }
                } finally {
                    camera?.close()
                }
            }
        } finally {
            if (wake.isHeld) wake.release()
        }
        if (config.sound) Sounds.end()
        val result = agg.result()
        val payload = ResultPayload.build(config, window, model, result, LocalDateTime.now().truncatedTo(ChronoUnit.SECONDS).toString(),
            BuildInfo.version(this), if (result.validFrames == 0) cameraProblem ?: "no usable picture" else null)
        store.saveResult(payload, test)
        store.lastCapture = "${window.classCode} ${window.date} P${window.period}: " +
            "${result.statuses.count { it.name == "PRESENT" }} present, " +
            "${result.statuses.count { it.name == "ABSENT" }} absent, " +
            "${result.statuses.count { it.name == "NEEDS_REVIEW" }} to review" +
            (if (result.validFrames == 0) " (no camera picture)" else "") + if (test) " [test]" else ""
        status("Done · ${store.lastCapture}")
        if (!test) safely { Uploader(config).flush(store.pending()) }
    }

    private fun scaledForScreen(bmp: android.graphics.Bitmap): android.graphics.Bitmap {
        val w = 1280
        val h = (bmp.height * w.toFloat() / bmp.width).toInt()
        return android.graphics.Bitmap.createScaledBitmap(bmp, w, h, true)
    }

    private fun heartbeatAndUpload() {
        val config = store.config() ?: return
        val up = Uploader(config)
        if (!up.enabled) return
        val next = Schedule(config).next(LocalDateTime.now())
        val body = buildJsonObject {
            put("board_code", config.board_code)
            put("app_version", BuildInfo.version(this@AttendanceService))
            put("armed", armed)
            put("last_capture", store.lastCapture ?: "")
            put("last_error", store.lastError ?: "")
            put("next_capture", next?.opens?.toString() ?: "")
            put("pending", store.pending().size)
            put("time", LocalDateTime.now().truncatedTo(ChronoUnit.SECONDS).toString())
        }.toString()
        runCatching { up.post("/api/v1/heartbeat", body) }
        up.flush(store.pending())
    }

    private fun status(text: String) {
        LiveState.status = text
        LiveState.changed()
        val nm = getSystemService(NotificationManager::class.java)
        nm.notify(NOTIFICATION_ID, notification(text))
    }

    private fun notification(text: String): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CHANNEL) == null) {
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "Attendance", NotificationManager.IMPORTANCE_MIN))
        }
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        return Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.presence_video_online)
            .setContentTitle("SSAS Board")
            .setContentText(text)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
    }

    private fun goForeground(text: String) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification(text), ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA)
        } else {
            startForeground(NOTIFICATION_ID, notification(text))
        }
    }

    companion object {
        const val TAG = "SSAS"
        const val CHANNEL = "ssas"
        const val NOTIFICATION_ID = 1
        const val ACTION_TEST = "org.ssas.board.TEST_CAPTURE"
        @Volatile var armed = false
            private set

        fun start(context: Context, test: Boolean = false) {
            val i = Intent(context, AttendanceService::class.java)
            if (test) i.action = ACTION_TEST
            context.startForegroundService(i)
        }
    }
}

object BuildInfo {
    fun version(context: Context): String =
        runCatching { context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: "?" }.getOrDefault("?")
}

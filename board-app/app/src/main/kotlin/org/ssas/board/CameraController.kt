package org.ssas.board

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.ImageFormat
import android.graphics.SurfaceTexture
import android.hardware.camera2.CameraAccessException
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.media.ImageReader
import android.os.Handler
import android.os.HandlerThread
import android.util.Size
import android.view.Surface
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

class CameraUnavailable(message: String) : Exception(message)

/**
 * Small Camera2 wrapper: a low-resolution repeating stream (keeps exposure right and feeds the preview)
 * plus full-resolution JPEG stills on demand. Blocking calls; use from a background thread.
 */
class CameraController(private val context: Context) : AutoCloseable {
    private val manager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
    private val thread = HandlerThread("ssas-camera").apply { start() }
    private val handler = Handler(thread.looper)
    private var device: CameraDevice? = null
    private var session: CameraCaptureSession? = null
    private var jpegReader: ImageReader? = null
    private var yuvReader: ImageReader? = null
    @Volatile var lastError: String? = null
        private set
    /** Width / height of the preview frames (set by [open]). */
    @Volatile var previewAspect: Float = 16f / 9f
        private set

    /** Prefer an external (USB) camera, then a front camera, then anything. */
    fun pickCamera(): String? {
        val ids = runCatching { manager.cameraIdList.toList() }.getOrDefault(emptyList())
        fun facing(id: String) = runCatching { manager.getCameraCharacteristics(id).get(CameraCharacteristics.LENS_FACING) }.getOrNull()
        return ids.firstOrNull { facing(it) == CameraCharacteristics.LENS_FACING_EXTERNAL }
            ?: ids.firstOrNull { facing(it) == CameraCharacteristics.LENS_FACING_FRONT }
            ?: ids.firstOrNull()
    }

    private fun largest(sizes: Array<Size>?): Size? = sizes?.maxByOrNull { it.width.toLong() * it.height }

    private fun closest(sizes: Array<Size>?, w: Int): Size? = sizes?.minByOrNull { kotlin.math.abs(it.width - w) }

    /**
     * Open the camera. [previewSurface] (optional) shows the live picture; [onPreviewFrame] receives
     * low-resolution YUV frames (optional).
     */
    @SuppressLint("MissingPermission")
    fun open(previewTexture: SurfaceTexture? = null, onPreviewFrame: ((android.media.Image) -> Unit)? = null, withStills: Boolean = true) {
        val id = pickCamera() ?: throw CameraUnavailable("No camera found (is the board showing another input such as OPS/HDMI?)")
        val chars = manager.getCameraCharacteristics(id)
        val map = chars.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
            ?: throw CameraUnavailable("Camera $id has no stream configuration")
        val jpegSize = largest(map.getOutputSizes(ImageFormat.JPEG))
        val yuvSize = closest(map.getOutputSizes(ImageFormat.YUV_420_888), 960) ?: Size(640, 480)
        previewAspect = yuvSize.width.toFloat() / yuvSize.height

        val opened = CountDownLatch(1)
        val error = AtomicReference<String?>(null)
        manager.openCamera(id, object : CameraDevice.StateCallback() {
            override fun onOpened(camera: CameraDevice) { device = camera; opened.countDown() }
            override fun onDisconnected(camera: CameraDevice) {
                lastError = "Camera taken by another app or disconnected"
                error.set(lastError); camera.close(); device = null; opened.countDown()
            }
            override fun onError(camera: CameraDevice, code: Int) {
                lastError = when (code) {
                    ERROR_CAMERA_IN_USE, ERROR_MAX_CAMERAS_IN_USE -> "Camera is being used by another app"
                    ERROR_CAMERA_DISABLED -> "Camera is disabled (permission or policy)"
                    else -> "Camera error $code"
                }
                error.set(lastError); camera.close(); device = null; opened.countDown()
            }
        }, handler)
        if (!opened.await(8, TimeUnit.SECONDS)) throw CameraUnavailable("Camera did not open in time")
        val dev = device ?: throw CameraUnavailable(error.get() ?: "Camera could not be opened")

        val surfaces = ArrayList<Surface>()
        yuvReader = ImageReader.newInstance(yuvSize.width, yuvSize.height, ImageFormat.YUV_420_888, 2).apply {
            setOnImageAvailableListener({ r ->
                val img = r.acquireLatestImage() ?: return@setOnImageAvailableListener
                try { onPreviewFrame?.invoke(img) } finally { img.close() }
            }, handler)
            surfaces.add(surface)
        }
        if (withStills && jpegSize != null) {
            jpegReader = ImageReader.newInstance(jpegSize.width, jpegSize.height, ImageFormat.JPEG, 2).also { surfaces.add(it.surface) }
        }
        var previewSurface: Surface? = null
        if (previewTexture != null) {
            previewTexture.setDefaultBufferSize(yuvSize.width, yuvSize.height)
            previewSurface = Surface(previewTexture).also { surfaces.add(it) }
        }

        val configured = CountDownLatch(1)
        @Suppress("DEPRECATION")
        dev.createCaptureSession(surfaces, object : CameraCaptureSession.StateCallback() {
            override fun onConfigured(s: CameraCaptureSession) { session = s; configured.countDown() }
            override fun onConfigureFailed(s: CameraCaptureSession) { lastError = "Camera session failed"; configured.countDown() }
        }, handler)
        if (!configured.await(8, TimeUnit.SECONDS) || session == null) throw CameraUnavailable(lastError ?: "Camera session failed")

        val repeat = dev.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW).apply {
            addTarget(yuvReader!!.surface)
            previewSurface?.let { addTarget(it) }
            set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO)
        }.build()
        session!!.setRepeatingRequest(repeat, null, handler)
    }

    /** Take one full-resolution JPEG; returns its bytes. */
    fun takeJpeg(timeoutSec: Long = 6): ByteArray {
        val s = session ?: throw CameraUnavailable(lastError ?: "Camera is not open")
        val reader = jpegReader ?: throw CameraUnavailable("This camera cannot take still pictures")
        val dev = device ?: throw CameraUnavailable(lastError ?: "Camera is not open")
        val result = AtomicReference<ByteArray?>(null)
        val done = CountDownLatch(1)
        reader.setOnImageAvailableListener({ r ->
            r.acquireLatestImage()?.use { img ->
                val buf = img.planes[0].buffer
                result.set(ByteArray(buf.remaining()).also { buf.get(it) })
            }
            done.countDown()
        }, handler)
        try {
            val req = dev.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE).apply {
                addTarget(reader.surface)
                set(CaptureRequest.JPEG_QUALITY, 92.toByte())
            }.build()
            s.capture(req, null, handler)
        } catch (e: CameraAccessException) {
            throw CameraUnavailable(e.message ?: "Camera access error")
        } catch (e: IllegalStateException) {
            throw CameraUnavailable(lastError ?: "Camera was closed")
        }
        if (!done.await(timeoutSec, TimeUnit.SECONDS)) throw CameraUnavailable(lastError ?: "No picture from the camera")
        return result.get() ?: throw CameraUnavailable("Empty picture")
    }

    override fun close() {
        runCatching { session?.close() }
        runCatching { device?.close() }
        runCatching { jpegReader?.close() }
        runCatching { yuvReader?.close() }
        session = null; device = null; jpegReader = null; yuvReader = null
        thread.quitSafely()
    }
}

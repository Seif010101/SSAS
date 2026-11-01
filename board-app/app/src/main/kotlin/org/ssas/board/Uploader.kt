package org.ssas.board

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.ssas.board.core.BoardConfig
import org.ssas.board.core.Hashing
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.cert.X509Certificate
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/**
 * Sends results and heartbeats to the server (text only), always over HTTPS.
 *
 * - With a certificate fingerprint in board.json, the server's certificate must match it exactly (a server on the
 *   local network with its own certificate).
 * - Without one, the normal public certificates are trusted (a VPS with a Let's Encrypt certificate).
 *
 * What the screen does with each server answer (the server side is server/ssas_server/api.py):
 *   2xx / 409 (already there) -> delete the pending copy
 *   400 / 413 / 422 (broken)  -> move it to rejected/ and never resend it
 *   403 (not registered yet)  -> keep it, try again later, carry on with the others
 *   anything else / no answer -> keep everything, try again in 5 minutes
 */
class Uploader(private val config: BoardConfig, private val rejectedDir: File? = null) {
    private val url = config.server.url.trim()

    /** Only https:// addresses: the screen's token must never travel in clear text. */
    val enabled get() = url.startsWith("https://", ignoreCase = true) && config.server.token.isNotBlank()

    /** Why nothing can be sent, or null (also null when no server is set: results then go out by USB). */
    val problem: String?
        get() = when {
            url.isBlank() -> null
            !url.startsWith("https://", ignoreCase = true) -> "The server address must start with https:// — nothing is sent"
            config.server.token.isBlank() -> "No server key in board.json — export again from SSAS Studio"
            else -> null
        }

    data class Answer(val code: Int, val message: String)

    private fun connection(path: String): HttpURLConnection {
        val conn = URL(url.trimEnd('/') + path).openConnection() as HttpsURLConnection
        conn.connectTimeout = 10_000
        conn.readTimeout = 15_000
        val pin = config.server.cert_sha256.lowercase().replace(":", "").trim()
        if (pin.isNotEmpty()) {
            val tm = object : X509TrustManager {
                override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
                override fun checkServerTrusted(chain: Array<out X509Certificate>, authType: String?) {
                    val leaf = Hashing.sha256Hex(chain[0].encoded)
                    if (leaf != pin) throw java.security.cert.CertificateException("Server certificate does not match the fingerprint")
                }
                override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
            }
            val ctx = SSLContext.getInstance("TLS")
            ctx.init(null, arrayOf<TrustManager>(tm), null)
            conn.sslSocketFactory = ctx.socketFactory
            conn.setHostnameVerifier { _, _ -> true } // the pinned certificate is the identity check
        }
        conn.setRequestProperty("Authorization", "Bearer ${config.server.token}")
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        return conn
    }

    fun post(path: String, json: String): Answer {
        check(enabled) { problem ?: "No server set" }
        val conn = connection(path)
        return try {
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.outputStream.use { it.write(json.toByteArray(Charsets.UTF_8)) }
            val code = conn.responseCode
            val body = runCatching {
                (if (code >= 400) conn.errorStream else conn.inputStream)?.use { it.readBytes().toString(Charsets.UTF_8) }
            }.getOrNull().orEmpty()
            Answer(code, detail(body))
        } finally {
            conn.disconnect()
        }
    }

    /** Upload the pending results, oldest first; returns how many the server took. [onProblem] gets a short message. */
    fun flush(pending: List<File>, onProblem: (String) -> Unit = {}): Int {
        if (!enabled) return 0
        var sent = 0
        for (f in pending) {
            val answer = runCatching { post("/api/v1/results", f.readText()) }.getOrElse {
                onProblem("Server not reachable: ${it.message ?: it.javaClass.simpleName}")
                return sent
            }
            when (answer.code) {
                in 200..299, 409 -> { f.delete(); sent++ }
                400, 413, 422 -> {
                    onProblem("${f.name} refused by the server: ${answer.message}")
                    val moved = rejectedDir?.let { dir -> dir.mkdirs(); f.renameTo(File(dir, f.name)) } ?: false
                    if (!moved) f.delete()
                }
                403 -> onProblem("${f.name}: ${answer.message}")
                else -> { onProblem("Server answered ${answer.code}: ${answer.message}"); return sent }
            }
        }
        return sent
    }

    private fun detail(body: String): String = runCatching {
        Json.parseToJsonElement(body).jsonObject["detail"]!!.jsonPrimitive.content
    }.getOrElse { body }.take(300)
}

package org.ssas.board

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
 * Sends results and heartbeats to the server (only text). When the board file has a certificate
 * fingerprint, the server certificate must match it (for a school server with its own certificate).
 */
class Uploader(private val config: BoardConfig) {
    val enabled get() = config.server.url.isNotBlank() && config.server.token.isNotBlank()

    private fun connection(path: String): HttpURLConnection {
        val url = URL(config.server.url.trimEnd('/') + path)
        val conn = url.openConnection() as HttpURLConnection
        conn.connectTimeout = 10_000
        conn.readTimeout = 15_000
        val pin = config.server.cert_sha256.lowercase().replace(":", "")
        if (conn is HttpsURLConnection && pin.isNotBlank()) {
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
            conn.setHostnameVerifier { _, _ -> true } // identity is checked by the pinned certificate
        }
        conn.setRequestProperty("Authorization", "Bearer ${config.server.token}")
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        return conn
    }

    fun post(path: String, json: String): Int {
        val conn = connection(path)
        return try {
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.outputStream.use { it.write(json.toByteArray(Charsets.UTF_8)) }
            conn.responseCode
        } finally {
            conn.disconnect()
        }
    }

    /** Upload all pending result files; returns how many were accepted. */
    fun flush(pending: List<File>): Int {
        if (!enabled) return 0
        var sent = 0
        for (f in pending) {
            val code = runCatching { post("/api/v1/results", f.readText()) }.getOrDefault(-1)
            if (code in 200..299 || code == 409) { // 409 = already received
                f.delete()
                sent++
            } else {
                break
            }
        }
        return sent
    }
}

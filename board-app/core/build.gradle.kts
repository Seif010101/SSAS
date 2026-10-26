import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("org.jetbrains.kotlin.jvm")
    id("org.jetbrains.kotlin.plugin.serialization")
}

val onnxruntimeVersion = "1.20.0"

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
}

dependencies {
    api("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    // The Android app brings onnxruntime-android (same ai.onnxruntime API); the JVM tests use the desktop build.
    compileOnly("com.microsoft.onnxruntime:onnxruntime:$onnxruntimeVersion")
    testImplementation("com.microsoft.onnxruntime:onnxruntime:$onnxruntimeVersion")
    testImplementation(kotlin("test"))
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.3")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
    systemProperty("ssas.models", System.getenv("SSAS_MODELS_DIR") ?: rootProject.file("../.models").absolutePath)
    testLogging { events("passed", "skipped", "failed"); showStandardStreams = true }
}

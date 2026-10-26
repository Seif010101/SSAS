import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val appVersion = (System.getenv("SSAS_VERSION") ?: "0.1.0").removePrefix("v")
val appVersionCode = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()

android {
    namespace = "org.ssas.board"
    compileSdk = 35

    defaultConfig {
        applicationId = "org.ssas.board"
        minSdk = 26
        targetSdk = 33
        versionCode = appVersionCode
        versionName = appVersion
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a") }
    }

    signingConfigs {
        create("release") {
            // A private key can be given by the build (secret); otherwise the public test key in keystore/ is used.
            val ks = System.getenv("SSAS_KEYSTORE_FILE")
            storeFile = file(ks ?: "../keystore/ssas-public.jks")
            storePassword = System.getenv("SSAS_KEYSTORE_PASSWORD") ?: "ssas-public"
            keyAlias = System.getenv("SSAS_KEY_ALIAS") ?: "ssas"
            keyPassword = System.getenv("SSAS_KEY_PASSWORD") ?: "ssas-public"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
        debug {
            signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    lint {
        // The boards run Android 13 and the app is installed from USB, not from Google Play.
        checkReleaseBuilds = false
        abortOnError = false
    }

    packaging {
        resources { excludes += setOf("META-INF/*.kotlin_module", "META-INF/versions/**") }
    }
}

kotlin {
    compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
}

dependencies {
    implementation(project(":core"))
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.20.0")
}

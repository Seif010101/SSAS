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
        // 29: lets the board read the USB stick directly (most boards have no system folder picker).
        targetSdk = 29
        versionCode = appVersionCode
        versionName = appVersion
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a") }
    }

    // The signing key never lives in the repository. CI passes it in from GitHub Secrets (see CONTRIBUTING.md).
    // A local build without these variables is signed with the Android debug key, which is fine for testing only.
    val keystore = System.getenv("SSAS_KEYSTORE_FILE")
    signingConfigs {
        if (keystore != null) {
            create("release") {
                storeFile = file(keystore)
                storePassword = System.getenv("SSAS_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("SSAS_KEY_ALIAS")
                keyPassword = System.getenv("SSAS_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release") ?: signingConfigs.getByName("debug")
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

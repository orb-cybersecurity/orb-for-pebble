// Orb for Pebble: Core's kotlin-speex built from source, in place of the Maven artifact
// io.github.coredevices.speex:speex, whose AAR carries a prebuilt libspeex_codec.so.
// The source is the submodule third_party/kotlin-speex, pinned to the commit Core published
// as the version libpebble3 uses. The native library is built by :speex-native.
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.kotlin.multiplatform)
    alias(libs.plugins.androidKotlinMultiplatformLibrary)
}

val speexSource = rootDir.resolve("../third_party/kotlin-speex/library/src")

kotlin {
    android {
        namespace = "orb.speex"
        compileSdk = libs.versions.android.compileSdk.get().toInt()
        minSdk = libs.versions.android.minSdk.get().toInt()

        compilerOptions {
            jvmTarget.set(JvmTarget.JVM_17)
        }
    }

    iosArm64()

    iosSimulatorArm64()

    sourceSets {
        commonMain {
            kotlin.srcDir(speexSource.resolve("commonMain/kotlin"))
        }
        androidMain {
            kotlin.srcDir(speexSource.resolve("androidMain/kotlin"))
            dependencies {
                implementation(project(":speex-native"))
            }
        }
    }
}

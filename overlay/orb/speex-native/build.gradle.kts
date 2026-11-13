// Orb for Pebble: builds libspeex_codec.so for :speex from third_party/kotlin-speex with
// Core's own CMake file. A plain Android library, because the KMP Android library plugin
// has no NDK support (Core splits cactus the same way).
plugins {
    alias(libs.plugins.android.library)
}

val repoRoot = rootDir.parentFile

android {
    namespace = "orb.speexnative"
    compileSdk = libs.versions.android.compileSdk.get().toInt()
    // The NDK Core built its published library with. F-Droid's recipe pins the same one,
    // since another NDK produces different bytes.
    ndkVersion = "28.1.13356709"

    defaultConfig {
        minSdk = libs.versions.android.minSdk.get().toInt()
        externalNativeBuild {
            cmake {
                // No debug info, and no build paths in the output, so the library comes out
                // the same on any machine and the APK can be built reproducibly. Release
                // builds use CMake's RelWithDebInfo, whose -g would come after cFlags. The
                // linker strips what the NDK's static C++ runtime brings, as Core's build
                // does, so packaging (which leaves .so files unstripped) needs no NDK.
                val flags = "-ffile-prefix-map=${repoRoot.absolutePath}=."
                cFlags += flags
                cppFlags += flags
                arguments += listOf(
                    "-DCMAKE_C_FLAGS_RELWITHDEBINFO=-O2 -g0 -DNDEBUG",
                    "-DCMAKE_CXX_FLAGS_RELWITHDEBINFO=-O2 -g0 -DNDEBUG",
                    "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,--strip-all",
                )
            }
        }
    }
    externalNativeBuild {
        cmake {
            path = repoRoot.resolve("third_party/kotlin-speex/speex/CMakeLists.txt")
            version = "3.22.1"
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

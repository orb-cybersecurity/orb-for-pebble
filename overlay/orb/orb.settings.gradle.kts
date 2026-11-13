// Orb for Pebble: wires the stand-in modules under orb/ into Core's build.
// Applied from the end of settings.gradle.kts by apply.py.

listOf("firebase-stubs", "kmpnotifier-stubs", "speex", "speex-native").forEach { name ->
    include(":$name")
    project(":$name").projectDir = rootDir.resolve("orb/$name")
}

// Every project resolves these rules, because the replaced artifacts are transitive
// dependencies of everything above the module that declares them.
gradle.lifecycle.beforeProject {
    configurations.configureEach {
        resolutionStrategy.dependencySubstitution {
            listOf(
                "dev.gitlive:firebase-auth",
                "dev.gitlive:firebase-firestore",
                "dev.gitlive:firebase-storage",
                "dev.gitlive:firebase-common-internal",
                "dev.gitlive:firebase-crashlytics",
            ).forEach { substitute(module(it)).using(project(":firebase-stubs")) }
            substitute(module("io.github.mirzemehdi:kmpnotifier"))
                .using(project(":kmpnotifier-stubs"))
            // Built from source; see orb/speex.
            substitute(module("io.github.coredevices.speex:speex")).using(project(":speex"))
        }
        // Nothing may bring these back transitively.
        listOf(
            "com.google.firebase",
            "com.google.android.gms",
            "com.google.android.play",
            "com.google.android.libraries.identity.googleid",
            "com.google.android.datatransport",
            "com.mixpanel.android",
        ).forEach { exclude(mapOf("group" to it)) }
    }
}

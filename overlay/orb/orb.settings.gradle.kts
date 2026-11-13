// Orb for Pebble: wires the modules Orb builds from source, under orb/, into Core's build.
// Applied from the end of settings.gradle.kts by apply.py.

listOf("speex", "speex-native").forEach { name ->
    include(":$name")
    project(":$name").projectDir = rootDir.resolve("orb/$name")
}

// Every project resolves these rules, because the replaced artifacts are transitive
// dependencies of everything above the module that declares them.
gradle.lifecycle.beforeProject {
    configurations.configureEach {
        resolutionStrategy.dependencySubstitution {
            // Built from source; see orb/speex.
            substitute(module("io.github.coredevices.speex:speex")).using(project(":speex"))
        }
        // Nothing may bring these back transitively.
        listOf(
            "com.google.firebase",
            "dev.gitlive",
            "com.google.android.gms",
            "com.google.android.play",
            "com.google.android.libraries.identity.googleid",
            "com.google.android.datatransport",
            "com.mixpanel.android",
        ).forEach { exclude(mapOf("group" to it)) }
    }
}

# Orb for Pebble.

# The health library's Google Fit fallback needs Google Play services. Orb never enables it,
# so let R8 treat the switch as constant and drop the fallback.
-assumevalues class com.viktormykhailiv.kmp.health.HealthManagerFactoryOptions {
    boolean getUseGoogleFit() return false;
}
-dontwarn com.google.android.gms.**

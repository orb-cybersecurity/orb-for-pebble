package theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.graphics.Color
import com.russhwolf.settings.Settings
import coreapp.util.generated.resources.Res
import coreapp.util.generated.resources.black
import coreapp.util.generated.resources.dark
import coreapp.util.generated.resources.light
import coreapp.util.generated.resources.system
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.jetbrains.compose.resources.StringResource
import org.koin.compose.koinInject
import theme.CoreAppTheme.Companion.asCoreAppTheme

// Orb: GrapheneOS's Material 3 theme in place of Core's orange. GrapheneOS publishes its
// branding as Material Design 3 from source colour #0053A3 (github.com/GrapheneOS/branding-extra);
// these are that theme's light and dark roles. Generator: design/theme.py in the Orb repository.
val grapheneSource = Color(0xFF0053A3)

// Kept under Core's names so screens that use them directly follow the new accent.
val coreOrange = Color(0xFF1A5EAE)
val coreGrey = Color(0xFF1A1B1E)
val coreDarkGrey = Color(0xFF343538)
val coreDarkGreen = Color(0xFF157a30)

val greyScheme = darkColorScheme(
    primary = Color(0xFFA9C7FF),
    onPrimary = Color(0xFF003063),
    primaryContainer = Color(0xFF00468B),
    onPrimaryContainer = Color(0xFFD6E3FF),
    secondary = Color(0xFFBCC7DE),
    onSecondary = Color(0xFF263143),
    secondaryContainer = Color(0xFF3D475A),
    onSecondaryContainer = Color(0xFFD8E3FB),
    tertiary = Color(0xFFDDBBE3),
    onTertiary = Color(0xFF3F2747),
    tertiaryContainer = Color(0xFF573D5E),
    onTertiaryContainer = Color(0xFFFAD7FF),
    error = Color(0xFFFFB4AB),
    onError = Color(0xFF690005),
    errorContainer = Color(0xFF93000A),
    onErrorContainer = Color(0xFFFFDAD6),
    background = Color(0xFF1A1B1E),
    onBackground = Color(0xFFE3E2E6),
    surface = Color(0xFF1A1B1E),
    onSurface = Color(0xFFE3E2E6),
    surfaceVariant = Color(0xFF43474E),
    onSurfaceVariant = Color(0xFFC4C6CF),
    outline = Color(0xFF8E9099),
    outlineVariant = Color(0xFF43474E),
    inverseSurface = Color(0xFFE3E2E6),
    inverseOnSurface = Color(0xFF2F3033),
    inversePrimary = Color(0xFF1A5EAE),
    scrim = Color(0xFF000000),
    surfaceDim = Color(0xFF121316),
    surfaceBright = Color(0xFF38393C),
    surfaceContainerLowest = Color(0xFF0D0E11),
    surfaceContainerLow = Color(0xFF1A1B1E),
    surfaceContainer = Color(0xFF1E2023),
    surfaceContainerHigh = Color(0xFF292A2D),
    surfaceContainerHighest = Color(0xFF343538),
)
// Containers must ascend lowest -> highest, and surfaceContainer must clear `surface`: it is what
// menus and popups paint themselves, so matching the page behind them leaves them with no edge.
val blackScheme = greyScheme.copy(
    background = Color.Black,
    surface = Color.Black,
    scrim = Color.Black,
    surfaceDim = Color.Black,
    surfaceBright = coreDarkGrey,
    surfaceContainerLowest = Color.Black,
    surfaceContainerLow = Color(0xFF0D0D0D),
    surfaceContainer = Color(0xFF141414),
    surfaceContainerHigh = Color(0xFF1F1F1F),
    surfaceContainerHighest = coreDarkGrey,
)
val lightScheme = lightColorScheme(
    primary = Color(0xFF1A5EAE),
    onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFD6E3FF),
    onPrimaryContainer = Color(0xFF001B3D),
    secondary = Color(0xFF545F73),
    onSecondary = Color(0xFFFFFFFF),
    secondaryContainer = Color(0xFFD8E3FB),
    onSecondaryContainer = Color(0xFF111C2D),
    tertiary = Color(0xFF705577),
    onTertiary = Color(0xFFFFFFFF),
    tertiaryContainer = Color(0xFFFAD7FF),
    onTertiaryContainer = Color(0xFF291230),
    error = Color(0xFFBA1A1A),
    onError = Color(0xFFFFFFFF),
    errorContainer = Color(0xFFFFDAD6),
    onErrorContainer = Color(0xFF410002),
    background = Color(0xFFFDFBFF),
    onBackground = Color(0xFF1A1B1E),
    surface = Color(0xFFFDFBFF),
    onSurface = Color(0xFF1A1B1E),
    surfaceVariant = Color(0xFFE0E2EC),
    onSurfaceVariant = Color(0xFF43474E),
    outline = Color(0xFF74777F),
    outlineVariant = Color(0xFFC4C6CF),
    inverseSurface = Color(0xFF2F3033),
    inverseOnSurface = Color(0xFFF1F0F4),
    inversePrimary = Color(0xFFA9C7FF),
    scrim = Color(0xFF000000),
    surfaceDim = Color(0xFFDAD9DD),
    surfaceBright = Color(0xFFFAF9FD),
    surfaceContainerLowest = Color(0xFFFFFFFF),
    surfaceContainerLow = Color(0xFFF4F3F7),
    surfaceContainer = Color(0xFFEFEDF1),
    surfaceContainerHigh = Color(0xFFE9E7EB),
    surfaceContainerHighest = Color(0xFFE3E2E6),
)

// Onboarding: white on GrapheneOS's source blue, as Core's was white on its orange.
val onboardingScheme = lightColorScheme(
    primary = Color.White,
    onPrimary = Color.Black,
    primaryContainer = Color.White,
    onPrimaryContainer = grapheneSource,
    secondary = Color.White,
    onSecondary = grapheneSource,
    secondaryContainer = Color.White,
    onSecondaryContainer = grapheneSource,
    tertiary = Color.White,
    onTertiary = grapheneSource,
    background = grapheneSource,
    onBackground = Color.White,
    surface = grapheneSource,
    onSurface = Color.White,
    surfaceVariant = grapheneSource,
    onSurfaceVariant = Color.White.copy(alpha = 0.8f),
    outline = Color.White.copy(alpha = 0.5f),
    outlineVariant = Color.White.copy(alpha = 0.3f),
    scrim = grapheneSource,
    surfaceContainer = grapheneSource,
    surfaceContainerHighest = Color.White.copy(alpha = 0.15f),
    error = Color(0xFFFFB4AB),
    onError = Color.Black,
    errorContainer = Color(0xFFFFB4AB),
    onErrorContainer = Color.Black,
)

val lightExtendedColors = ExtendedColors(
    primary20 = Color(0xFF003063),
    onPrimary20 = Color(0xFFFFFFFF),
    warning = warningLight,
    onWarning = onWarningLight,
    success = successLight,
    onSuccess = onSuccessLight,
)

val darkExtendedColors = ExtendedColors(
    primary20 = Color(0xFFA9C7FF),
    onPrimary20 = Color(0xFF003063),
    warning = warningDark,
    onWarning = onWarningDark,
    success = successDark,
    onSuccess = onSuccessDark,
)

@Immutable
data class ColorFamily(
    val color: Color,
    val onColor: Color,
    val colorContainer: Color,
    val onColorContainer: Color
)

enum class CoreAppTheme(val resource: StringResource, val key: String) {
    Light(Res.string.light, "light"),
    Dark(Res.string.dark, "dark"),
    Black(Res.string.black, "black"),
    System(Res.string.system, "system"),
    ;

    companion object {
        fun String?.asCoreAppTheme(): CoreAppTheme =
            entries.firstOrNull { it.key == this } ?: System
    }
}

enum class CoreAppColorScheme(val isDark: Boolean) {
    Light(false),
    Grey(true),
    Black(true),
}

@Composable
fun currentColorScheme(): CoreAppColorScheme {
    val themeProvider: ThemeProvider = koinInject()
    val theme by themeProvider.theme.collectAsState()
    val systemInDarkTheme = isSystemInDarkTheme()
    val colorScheme = remember(theme, systemInDarkTheme) {
        when (theme) {
            CoreAppTheme.Light -> CoreAppColorScheme.Light
            CoreAppTheme.Dark -> CoreAppColorScheme.Grey
            CoreAppTheme.Black -> CoreAppColorScheme.Black
            CoreAppTheme.System -> if (systemInDarkTheme) CoreAppColorScheme.Grey else CoreAppColorScheme.Light
        }
    }
    return colorScheme
}

@Composable
fun AppTheme(
    content: @Composable() () -> Unit
) {
    val colorScheme = currentColorScheme()
    val extendedColors = if (colorScheme.isDark) darkExtendedColors else lightExtendedColors
    setStatusBarTheme(colorScheme)
    val materialColorScheme = when (colorScheme) {
        CoreAppColorScheme.Light -> lightScheme
        CoreAppColorScheme.Grey -> greyScheme
        CoreAppColorScheme.Black -> blackScheme
    }
    CompositionLocalProvider(LocalExtendedColors provides extendedColors) {
        MaterialTheme(
            colorScheme = materialColorScheme,
            typography = AppTypography(),
            content = content
        )
    }
}

expect @Composable fun setStatusBarTheme(colorScheme: CoreAppColorScheme)

interface ThemeProvider {
    val theme: StateFlow<CoreAppTheme>
    fun setTheme(theme: CoreAppTheme)
}

class RealThemeProvider(
    private val settings: Settings,
) : ThemeProvider {
    private val _theme = MutableStateFlow(getTheme())
    override val theme: StateFlow<CoreAppTheme> = _theme.asStateFlow()

    private fun getTheme(): CoreAppTheme {
        val key = settings.getStringOrNull(THEME_SETTINGS_KEY)
        return key.asCoreAppTheme()
    }

    override fun setTheme(theme: CoreAppTheme) {
        settings.putString(THEME_SETTINGS_KEY, theme.key)
        _theme.value = theme
    }

    companion object {
        private const val THEME_SETTINGS_KEY = "current_theme"
    }
}

object ExtendedTheme {
    val colors: ExtendedColors
        @Composable
        get() = LocalExtendedColors.current
}
package io.rebble.libpebblecommon.pebblekit

import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class CompanionAuthorizationTest {
    @Test fun everyControlRequiresBothAssociationAndGrant() = runTest {
        assertFalse(authorizedCompanion(emptyList(), listOf("companion")) { true })
        assertFalse(authorizedCompanion(listOf("other"), listOf("companion")) { error("must not ask") })
        assertFalse(authorizedCompanion(listOf("companion"), emptyList()) { true })
        assertFalse(authorizedCompanion(listOf("companion"), listOf("companion")) { false })
        assertTrue(authorizedCompanion(listOf("companion"), listOf("companion")) { true })
    }
}

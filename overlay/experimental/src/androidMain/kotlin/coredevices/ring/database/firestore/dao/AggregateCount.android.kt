package coredevices.ring.database.firestore.dao

import dev.gitlive.firebase.firestore.CollectionReference

// Orb: there is no Firestore to count documents in.
actual suspend fun CollectionReference.count(): Int = 0

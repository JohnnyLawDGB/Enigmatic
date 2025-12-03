# Android build notes

The repository's Android client build can fail on newer Android Gradle Plugin
(AGP) versions with an error similar to:

```
Could not find method abiFilters() for arguments [[arm64-v8a]] on object of type
com.android.build.gradle.internal.dsl.NdkOptions.
```

AGP 8+ exposes `abiFilters` as a mutable collection rather than a vararg-style
method. Update the `ndk` block in `android/app/build.gradle` (or any other
module) to mutate the collection instead of invoking it like a function:

```groovy
android {
    defaultConfig {
        ndk {
            abiFilters.add("arm64-v8a")
            // or: abiFilters += listOf("arm64-v8a", "armeabi-v7a")
        }
    }
}
```

This aligns with Gradle 8 and AGP 8's DSL changes and resolves the
`abiFilters()` missing method error during `assembleDebug`.

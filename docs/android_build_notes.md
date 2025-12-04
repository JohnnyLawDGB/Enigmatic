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

## External native build configuration

If your local `android/app/build.gradle` still contains merge-conflict markers
around the `externalNativeBuild` block (for example, pointing at
`../jni/CMakeLists.txt`), prefer the configuration that leaves the `cmake`
settings commented out. The repository does not ship a `jni` directory or a
`CMakeLists.txt`, and the Android build only packages prebuilt libraries from
`src/main/jniLibs`. A minimal block that matches the current project layout
looks like this:

```groovy
    externalNativeBuild {
        cmake {
            // If you actually add JNI sources and a CMakeLists, provide the
            // path here. Otherwise keep it commented out so Gradle just
            // packages the existing binaries in src/main/jniLibs.
            // path file("../jni/CMakeLists.txt")

            // scripts/build-android.sh already sets ABI/platform flags for the
            // prebuilt libraries, so Gradle does not need extra arguments.
        }
    }
```

This removes the conflict markers while keeping the build aligned with the
repository's prebuilt native binaries.

# Twin — Claude Handoff / Engineering Debug Record

## 1. Project

Repository: fobinathaniel2-ops/Twin
Branch: main
Goal: Twin is intended to provide "two of everything" by creating isolated app spaces on Android. The original implementation attempts to use Android Managed Profiles (work profiles) rather than pretending a normal app can create arbitrary Android users.

## 2. Current state

The original `twin.zip` project archive used as the starting project was created by Claude and was subsequently uploaded/provided for this workflow. The current CI process extracts that archive, creates the Flutter build project, restores the native Android files, and applies the provisioning patch before compiling.

The GitHub Actions Android build is working.

Latest successful commit:
202c6c0221561acd7e138e809376af9a2969c238
Message: Wire managed-profile rejection to working sandbox fallback

Latest successful workflow:
Run #20 — 37566436654
Workflow: Build Android APK
Result: success
All steps passed:
- checkout
- Flutter setup
- project extraction/preparation
- native Android restoration
- provisioning patch
- Flutter dependencies
- APK build
- APK upload
- GitHub release

Important: build success does NOT prove Android managed-profile provisioning works on the user's physical device.

## 3. Original problem

The Twin UI initially showed:
- Two of everything.
- No ads, ever
- No internet permission
- Clones stay on this phone
- Create clone space disabled
- Android is currently not allowing profile setup.

When attempting managed-profile creation, Android displayed:
"Can't add work profile — A work profile can't be added to this device. If you have questions, contact your IT admin."

This strongly indicates an Android framework/device eligibility restriction, although Twin's provisioning implementation still had to be validated.

## 4. Architecture chosen

Native Android Managed Profile is the primary implementation.

Reason:
A regular Android application cannot simply create another peer Android user/profile and install arbitrary APKs inside that profile. Android's framework controls managed-profile provisioning.

A true app-contained sandbox/virtual Android environment would be a substantially different architecture involving virtualization/containerization and would have significant compatibility/security constraints.

Therefore:
1. Try the official Managed Profile route.
2. Detect provisioning rejection.
3. Show a fallback capability screen rather than falsely claiming a full clone sandbox exists.

## 5. Android provisioning work completed

The workflow dynamically creates a Flutter project and restores native Android files before compiling. This was important because earlier patches modified archive/native source files that were NOT the Android project actually compiled by CI.

The workflow now patches:
extracted/twin/src/android/app/src/main/kotlin/com/example/twin
and
extracted/twin/src/android/app/src/main/res/xml

The patch script is:
scripts/patch_android_provisioning.py

It creates/restores these native components:
- GetProvisioningModeActivity.kt
- PolicyComplianceActivity.kt
- ProvisionActivity.kt placeholder
- TwinDeviceAdminReceiver.kt
- ProvisioningDiagnostics.kt
- SandboxActivity.kt

The Android manifest is patched to include:
- GET_PROVISIONING_MODE activity
- ADMIN_POLICY_COMPLIANCE activity
- TwinDeviceAdminReceiver with DEVICE_ADMIN_ENABLED metadata
- SandboxActivity

The provisioning intent uses:
DevicePolicyManager.ACTION_PROVISION_MANAGED_PROFILE

and supplies:
DevicePolicyManager.EXTRA_PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME

with:
ComponentName(this, TwinDeviceAdminReceiver::class.java)

## 6. Android 12+ provisioning requirements addressed

Android 12+ requires DPCs to support:
- ACTION_GET_PROVISIONING_MODE
- ACTION_ADMIN_POLICY_COMPLIANCE

GetProvisioningModeActivity was implemented to respect:
EXTRA_PROVISIONING_ALLOWED_PROVISIONING_MODES

PolicyComplianceActivity returns RESULT_OK.

Do NOT regress this back to the old ACTION_PROVISION_MANAGED_DEVICE-only approach.

## 7. Important failed approach

An earlier patch forced:
isProvisioningAllowed(...) = true

This was wrong and was removed.

Commit that restored the correct behavior:
1c326681f0a9dce52dc2e4ae4fb0e0ac5f1228ed

The correct implementation uses:
dpm().isProvisioningAllowed(DevicePolicyManager.ACTION_PROVISION_MANAGED_PROFILE)

Do not bypass Android's eligibility check merely to hide the error.

## 8. Provisioning diagnostics

ProvisioningDiagnostics.kt reports:
- whether FEATURE_MANAGED_USERS exists
- whether managed-profile provisioning is currently allowed
- number of associated profiles
- whether Twin is profile owner
- whether Twin is device owner

This is intended to distinguish:
A. device/framework eligibility problem
B. provisioning implementation problem
C. already-provisioned/broken profile state

## 9. Sandbox fallback

SandboxActivity currently provides a truthful capability/fallback screen.

It does NOT claim that a normal Android app can run arbitrary APKs as separate peer apps inside its own process.

It reports managed-user support and provisioning status and explains that Android/OEM-controlled profile/clone mechanisms are platform controlled.

The latest commit also wires the fallback:
- If isProvisioningAllowed(...) is false before launching provisioning, SandboxActivity opens.
- If provisioning is launched but returns a non-RESULT_OK result, SandboxActivity opens.

Provisioning request code:
9917

## 10. Failed CI attempt

Commit:
e5b4e65ed61e0eb3980392affcf3105fa059a9c2

Failed because the patch script attempted to inject fallback code into a MainActivity branch that did not match the actual generated source:
"managed-profile provisioning branch was not found"

This was corrected in:
8463e9b0567dfbccd974af51509cd422d112bc38

Then final fallback wiring was completed in:
202c6c0221561acd7e138e809376af9a2969c238

## 11. Relevant official Android facts

Android's DevicePolicyManager documentation says:
- ACTION_PROVISION_MANAGED_PROFILE starts managed-profile provisioning.
- isProvisioningAllowed(action) reports whether provisioning is possible.
- RESULT_CANCELED can indicate that a provisioning precondition was not met.
- Android 12+ requires the provisioning-mode and policy-compliance activities for modern DPC provisioning.

Official reference:
https://developer.android.com/reference/android/app/admin/DevicePolicyManager

Android 12 enterprise behavior:
https://developer.android.com/work/versions/android-12

## 12. What Claude should investigate next if the APK still fails

Do NOT immediately rewrite the entire project.

First establish exactly which layer is failing:

### A. Inspect actual MainActivity
Confirm:
- the provisioning intent action
- admin ComponentName
- request code 9917
- preflight isProvisioningAllowed check
- onActivityResult fallback
- imports
- lifecycle behavior

### B. Inspect generated Android project
The CI project is generated dynamically. Make sure any fix targets the generated project that is actually compiled.

### C. Inspect Android device state
The physical-device error may be caused by:
- managed profile/user already existing or partially provisioned
- OEM policy restrictions
- device management/enterprise restrictions
- unsupported managed-user configuration
- Android/OEM provisioning state
- device policy management role configuration
- Samsung/other OEM restrictions
- other framework preconditions

Do not assume all such failures are caused by Twin.

### D. Use TestDPC as a diagnostic comparison
If possible on a development/test device, compare whether Android's official/reference DPC provisioning path can create a work profile.

If TestDPC also cannot create one, the problem is very likely device/OS/OEM eligibility rather than Twin's UI.

### E. Do not fake a work profile
Do not force isProvisioningAllowed() to true.
Do not claim successful cloning when Android rejected profile creation.
Do not use hidden/system-only permissions intended for Android's device-policy role unless the app is actually eligible for them.

## 13. If Managed Profile is impossible

Design a real alternative architecture rather than a cosmetic fallback.

Potential direction:
- app-level isolated workspace
- controlled app/plugin model
- or a genuine virtualization/container architecture

But first determine whether the product requirement is:
1. duplicate selected apps with independent data, or
2. provide a full second Android environment.

These are very different engineering problems.

A normal APK cannot silently become a second Android OS/user environment.

## 14. Key commits

5fa0cda6f096cbfed75a3e2563b0f13a08149c73
- Corrected patch target to the generated Flutter Android project.

1c326681f0a9dce52dc2e4ae4fb0e0ac5f1228ed
- Removed incorrect offline/forced provisioning eligibility.

e5b4e65ed61e0eb3980392affcf3105fa059a9c2
- First diagnostics + sandbox attempt; CI failed due to MainActivity branch mismatch.

8463e9b0567dfbccd974af51509cd422d112bc38
- Added safe provisioning diagnostics and SandboxActivity.

202c6c0221561acd7e138e809376af9a2969c238
- Wired managed-profile rejection to SandboxActivity.
- This is the current main commit.

## 15. Current objective for Claude

If the physical device still rejects the profile:

1. Read the current repository, especially scripts/patch_android_provisioning.py, .github/workflows/build-apk.yml, and generated/native Android sources.
2. Reproduce the provisioning flow logically against current Android API requirements.
3. Identify whether the failure is:
   - code/configuration,
   - manifest/DPC registration,
   - Android framework eligibility,
   - OEM restriction,
   - or product architecture mismatch.
4. If code is wrong, make the smallest robust fix and verify CI.
5. If the device itself forbids managed profiles, stop trying to bypass the framework and design a technically honest alternative.
6. Preserve the no-internet/no-ad/local-first product requirements unless a deliberate architecture change is agreed.
7. Never remove diagnostics merely to make the UI appear successful.

## 16. Handoff note

The project has already gone through multiple CI iterations. The most important lesson is that successful compilation and successful Android profile provisioning are separate milestones.

The latest CI run is green. The next evidence needed is the behavior of the latest APK on the target Android device, especially whether:
- the Android work-profile error still appears, and
- whether the new SandboxActivity actually opens after rejection.

If it does, focus on the device/framework eligibility boundary instead of endlessly changing Flutter UI code.

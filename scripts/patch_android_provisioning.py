from pathlib import Path
import xml.etree.ElementTree as ET

# This step runs after the workflow has restored the native files into the
# generated Flutter Android project. Patch the files that Gradle actually builds.
root = Path(".")
android_root = root / "android/app/src/main"
kotlin_dir = android_root / "kotlin/com/example/twin"
res_xml = android_root / "res/xml"
kotlin_dir.mkdir(parents=True, exist_ok=True)
res_xml.mkdir(parents=True, exist_ok=True)

# Diagnostic + fallback layer:
# - Report the Android-managed provisioning state instead of pretending it can be bypassed.
# - If Android blocks managed-profile provisioning, open a sandbox capability screen.
#   This does NOT claim to execute arbitrary APKs inside Twin: Android does not expose a
#   normal-app API for creating OEM clone profiles or running third-party APKs as peers
#   inside another app. OEM clone profiles are platform-managed.
(kotlin_dir / "ProvisioningDiagnostics.kt").write_text("""package com.example.twin

import android.app.admin.DevicePolicyManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.UserManager

object ProvisioningDiagnostics {
    data class State(
        val managedUsersSupported: Boolean,
        val provisioningAllowed: Boolean,
        val associatedProfiles: Int,
        val isProfileOwner: Boolean,
        val isDeviceOwner: Boolean
    )

    fun read(context: Context): State {
        val pm = context.packageManager
        val dpm = context.getSystemService(DevicePolicyManager::class.java)
        val um = context.getSystemService(UserManager::class.java)
        val profiles = try {
            um.userProfiles.size
        } catch (_: SecurityException) {
            1
        }

        return State(
            managedUsersSupported =
                pm.hasSystemFeature(PackageManager.FEATURE_MANAGED_USERS),
            provisioningAllowed =
                dpm.isProvisioningAllowed(
                    DevicePolicyManager.ACTION_PROVISION_MANAGED_PROFILE
                ),
            associatedProfiles = profiles,
            isProfileOwner = dpm.isProfileOwnerApp(context.packageName),
            isDeviceOwner = dpm.isDeviceOwnerApp(context.packageName)
        )
    }

    fun summary(context: Context): String {
        val s = read(context)
        return buildString {
            append("Managed profiles supported: ")
            append(if (s.managedUsersSupported) "yes" else "no")
            append("\\nProvisioning currently allowed: ")
            append(if (s.provisioningAllowed) "yes" else "no")
            append("\\nAssociated Android profiles: ")
            append(s.associatedProfiles)
            append("\\nTwin profile owner: ")
            append(if (s.isProfileOwner) "yes" else "no")
            append("\\nTwin device owner: ")
            append(if (s.isDeviceOwner) "yes" else "no")
        }
    }
}
""")

(kotlin_dir / "SandboxActivity.kt").write_text("""package com.example.twin

import android.app.Activity
import android.os.Bundle
import android.os.Build
import android.widget.LinearLayout
import android.widget.TextView

class SandboxActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val diagnostics = ProvisioningDiagnostics.read(this)
        val title = TextView(this).apply {
            text = "Twin sandbox fallback"
            textSize = 22f
            setPadding(48, 48, 48, 24)
        }

        val body = TextView(this).apply {
            textSize = 16f
            setPadding(48, 8, 48, 48)
            text = buildString {
                append("Android is blocking managed-profile creation on this device.\\n\\n")
                append(ProvisioningDiagnostics.summary(this@SandboxActivity))
                append("\\n\\n")
                if (Build.VERSION.SDK_INT >= 35) {
                    append("Android exposes clone/private profile types on newer releases, ")
                    append("but creation and the full clone experience are controlled by ")
                    append("the system/OEM. Twin cannot safely create one as a normal app.\\n\\n")
                }
                append("Twin will not fake a second Android app environment. The fallback ")
                append("is a capability/diagnostic screen until a supported profile path ")
                append("is available.")
            }
        }

        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(title)
            addView(body)
        })
    }
}
""")

(kotlin_dir / "GetProvisioningModeActivity.kt").write_text("""package com.example.twin

import android.app.Activity
import android.app.admin.DevicePolicyManager
import android.content.Intent
import android.os.Bundle

class GetProvisioningModeActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val allowed = intent?.getIntegerArrayListExtra(
            DevicePolicyManager.EXTRA_PROVISIONING_ALLOWED_PROVISIONING_MODES
        )
        val mode = DevicePolicyManager.PROVISIONING_MODE_MANAGED_PROFILE
        if (allowed != null && !allowed.contains(mode)) {
            setResult(RESULT_CANCELED)
            finish()
            return
        }
        setResult(
            RESULT_OK,
            Intent().putExtra(DevicePolicyManager.EXTRA_PROVISIONING_MODE, mode)
        )
        finish()
    }
}
""")

(kotlin_dir / "PolicyComplianceActivity.kt").write_text("""package com.example.twin

import android.app.Activity
import android.os.Bundle

class PolicyComplianceActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setResult(RESULT_OK)
        finish()
    }
}
""")

# Keep this class only as a non-provisioning placeholder. The system
# ManagedProvisioning component owns ACTION_PROVISION_MANAGED_PROFILE.
(kotlin_dir / "ProvisionActivity.kt").write_text("""package com.example.twin

import android.app.Activity
import android.os.Bundle

class ProvisionActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setResult(RESULT_CANCELED)
        finish()
    }
}
""")

(kotlin_dir / "TwinDeviceAdminReceiver.kt").write_text("""package com.example.twin

import android.app.admin.DeviceAdminReceiver

class TwinDeviceAdminReceiver : DeviceAdminReceiver()
""")

manifest = android_root / "AndroidManifest.xml"
ns = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", ns)
tree = ET.parse(manifest)
m = tree.getroot()
app = m.find("application")
if app is None:
    raise SystemExit("generated AndroidManifest.xml has no <application>")

def attr(node, name):
    return node.get("{" + ns + "}" + name)

# Do not let Twin claim ACTION_PROVISION_MANAGED_PROFILE.
for n in list(app.findall("activity")):
    if attr(n, "name") in (".ProvisionActivity", "com.example.twin.ProvisionActivity"):
        app.remove(n)

def ensure_activity(name, action):
    node = None
    for n in app.findall("activity"):
        if attr(n, "name") in ("." + name, "com.example.twin." + name):
            node = n
            break
    if node is None:
        node = ET.SubElement(app, "activity")
    node.set("{" + ns + "}name", "." + name)
    node.set("{" + ns + "}exported", "true")
    node.set("{" + ns + "}permission", "android.permission.BIND_DEVICE_ADMIN")
    for filt in list(node.findall("intent-filter")):
        node.remove(filt)
    filt = ET.SubElement(node, "intent-filter")
    a = ET.SubElement(filt, "action")
    a.set("{" + ns + "}name", action)
    c = ET.SubElement(filt, "category")
    c.set("{" + ns + "}name", "android.intent.category.DEFAULT")

ensure_activity("GetProvisioningModeActivity", "android.app.action.GET_PROVISIONING_MODE")
ensure_activity("PolicyComplianceActivity", "android.app.action.ADMIN_POLICY_COMPLIANCE")

receiver = None
for n in app.findall("receiver"):
    if attr(n, "name") in (".TwinDeviceAdminReceiver", "com.example.twin.TwinDeviceAdminReceiver"):
        receiver = n
        break
if receiver is None:
    receiver = ET.SubElement(app, "receiver")
receiver.set("{" + ns + "}name", ".TwinDeviceAdminReceiver")
receiver.set("{" + ns + "}exported", "false")
receiver.set("{" + ns + "}permission", "android.permission.BIND_DEVICE_ADMIN")

enabled = any(
    attr(a, "name") == "android.app.action.DEVICE_ADMIN_ENABLED"
    for filt in receiver.findall("intent-filter")
    for a in filt.findall("action")
)
if not enabled:
    filt = ET.SubElement(receiver, "intent-filter")
    a = ET.SubElement(filt, "action")
    a.set("{" + ns + "}name", "android.app.action.DEVICE_ADMIN_ENABLED")

md = None
for n in receiver.findall("meta-data"):
    if attr(n, "name") == "android.app.device_admin":
        md = n
        break
if md is None:
    md = ET.SubElement(receiver, "meta-data")
md.set("{" + ns + "}name", "android.app.device_admin")
md.set("{" + ns + "}resource", "@xml/device_admin")

main_activity = kotlin_dir / "MainActivity.kt"
if not main_activity.exists():
    raise SystemExit("generated MainActivity.kt not found")

main_text = main_activity.read_text()
old_check = "dpm().isProvisioningAllowed(DevicePolicyManager.ACTION_PROVISION_MANAGED_PROFILE)"
if old_check not in main_text:
    raise SystemExit("managed-profile provisioning eligibility check was not found")

old_intent = "val i = Intent(DevicePolicyManager.ACTION_PROVISION_MANAGED_PROFILE)"
if old_intent not in main_text:
    raise SystemExit("managed-profile provisioning intent was not found")

# The device-admin component is required for managed-profile provisioning.
# Do not bypass DevicePolicyManager.isProvisioningAllowed(): Android owns
# the final eligibility decision for the device/user.
if "EXTRA_PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME" not in main_text:
    main_text = main_text.replace(
        old_intent,
        old_intent + """
                            i.putExtra(
                                DevicePolicyManager.EXTRA_PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME,
                                android.content.ComponentName(this, TwinDeviceAdminReceiver::class.java)
                            )""",
        1,
    )

if old_check not in main_text:
    raise SystemExit("managed-profile provisioning eligibility check was removed")
if "EXTRA_PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME" not in main_text:
    raise SystemExit("managed-profile admin component extra was not added")

# Add a native diagnostic/fallback screen when Android rejects provisioning.
# Keep the eligibility check itself intact; the OS remains the authority.
if "Twin sandbox fallback" not in main_text:
    needle = "if (!" + old_check + ") {"
    if needle not in main_text:
        # Be tolerant of whitespace/formatting in the generated source.
        import re
        match = re.search(r"if\s*\(!dpm\(\)\.isProvisioningAllowed\(DevicePolicyManager\.ACTION_PROVISION_MANAGED_PROFILE\)\)\s*\{", main_text)
        if not match:
            raise SystemExit("managed-profile provisioning branch was not found")
        start, end = match.span()
    else:
        start, end = main_text.index(needle), main_text.index(needle) + len(needle)

    replacement = main_text[start:end] + """
                            startActivity(Intent(this, SandboxActivity::class.java))
"""
    main_text = main_text[:start] + replacement + main_text[end:]

# Ensure the fallback activity is declared.
ensure_activity_simple = None
sandbox_node = None
for n in app.findall("activity"):
    if attr(n, "name") in (".SandboxActivity", "com.example.twin.SandboxActivity"):
        sandbox_node = n
        break
if sandbox_node is None:
    sandbox_node = ET.SubElement(app, "activity")
sandbox_node.set("{" + ns + "}name", ".SandboxActivity")
sandbox_node.set("{" + ns + "}exported", "false")

main_activity.write_text(main_text)
tree.write(manifest, encoding="utf-8", xml_declaration=True)

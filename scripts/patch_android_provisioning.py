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

main_activity.write_text(main_text)
tree.write(manifest, encoding="utf-8", xml_declaration=True)

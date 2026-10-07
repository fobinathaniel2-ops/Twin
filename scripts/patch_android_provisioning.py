from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(".")
(root / "kotlin/ProvisionActivity.kt").write_text("""package com.example.twin

import android.app.Activity
import android.app.admin.DevicePolicyManager
import android.content.Intent
import android.os.Bundle

class ProvisionActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        when (intent?.action) {
            DevicePolicyManager.ACTION_GET_PROVISIONING_MODE -> {
                val result = Intent().apply {
                    putExtra(
                        DevicePolicyManager.EXTRA_PROVISIONING_MODE,
                        DevicePolicyManager.PROVISIONING_MODE_MANAGED_PROFILE
                    )
                }
                setResult(RESULT_OK, result)
                finish()
            }
            DevicePolicyManager.ACTION_ADMIN_POLICY_COMPLIANCE -> {
                setResult(RESULT_OK)
                finish()
            }
            DevicePolicyManager.ACTION_PROVISION_MANAGED_PROFILE -> {
                setResult(RESULT_OK)
                finish()
            }
            else -> {
                setResult(RESULT_CANCELED)
                finish()
            }
        }
    }
}
""")

(root / "kotlin/TwinDeviceAdminReceiver.kt").write_text("""package com.example.twin

import android.app.admin.DeviceAdminReceiver

class TwinDeviceAdminReceiver : DeviceAdminReceiver()
""")

manifest = root / "AndroidManifest.xml"
ns = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", ns)
tree = ET.parse(manifest)
m = tree.getroot()
app = m.find("application")
if app is None:
    raise SystemExit("AndroidManifest.xml has no <application>")

def attr(node, name):
    return node.get("{" + ns + "}" + name)

pa = None
for n in app.findall("activity"):
    if attr(n, "name") in (".ProvisionActivity", "com.example.twin.ProvisionActivity"):
        pa = n
        break
if pa is None:
    pa = ET.SubElement(app, "activity")
pa.set("{" + ns + "}name", ".ProvisionActivity")
pa.set("{" + ns + "}exported", "true")

actions = {
    "android.app.action.GET_PROVISIONING_MODE",
    "android.app.action.ADMIN_POLICY_COMPLIANCE",
    "android.app.action.PROVISION_MANAGED_PROFILE",
}
found = False
for filt in pa.findall("intent-filter"):
    have = {attr(a, "name") for a in filt.findall("action")}
    if actions.issubset(have):
        found = True
        break
if not found:
    filt = ET.SubElement(pa, "intent-filter")
    for action in actions:
        a = ET.SubElement(filt, "action")
        a.set("{" + ns + "}name", action)

receiver = None
for n in app.findall("receiver"):
    if attr(n, "name") in (".TwinDeviceAdminReceiver", "com.example.twin.TwinDeviceAdminReceiver"):
        receiver = n
        break
if receiver is None:
    receiver = ET.SubElement(app, "receiver")
receiver.set("{" + ns + "}name", ".TwinDeviceAdminReceiver")
receiver.set("{" + ns + "}exported", "true")
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

tree.write(manifest, encoding="utf-8", xml_declaration=True)

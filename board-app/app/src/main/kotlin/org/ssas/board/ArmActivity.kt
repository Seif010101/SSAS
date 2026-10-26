package org.ssas.board

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.os.Bundle

/** Invisible screen that (re)starts the camera service while the app counts as "visible", then closes. */
class ArmActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            AttendanceService.start(this)
        }
        finish()
    }
}

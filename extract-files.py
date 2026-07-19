#!/usr/bin/env -S PYTHONPATH=../../../tools/extract-utils python3
#
# SPDX-FileCopyrightText: 2024 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#

from functools import partial
import struct

from extract_utils.fixups_blob import (
    blob_fixup,
    blob_fixups_user_type,
)
from extract_utils.fixups_lib import (
    lib_fixups,
    lib_fixups_user_type,
)
from extract_utils.main import (
    ExtractUtils,
    ExtractUtilsModule,
)

namespace_imports = [
    'hardware/mediatek',
    'hardware/mediatek/libaedv',
    'hardware/xiaomi',
    'vendor/xiaomi/mt6895-common',
]

lib_fixups: lib_fixups_user_type = {
    **lib_fixups,
}

def scale_aw8697_firmware(scale, ctx, file, file_path, *args, **kwargs):
    """
    Scale all vibration waveforms in the AW8697 firmware file by a given factor.
    Clamps values to signed 8-bit range [-128,127] and updates the firmware checksum.
    """
    with open(file_path, 'rb') as f:
        data = bytearray(f.read())

    if len(data) < 0x31:
        raise ValueError("Firmware file too small")

    # Parse descriptor table
    start0 = (data[0x05] << 8) | data[0x06]
    starts = [start0]
    ends = []
    pos = 0x07
    while pos + 1 <= 0x30:
        end_addr = (data[pos] << 8) | data[pos+1]
        ends.append(end_addr)
        pos += 2
        if pos + 1 > 0x30:
            break
        start_addr = (data[pos] << 8) | data[pos+1]
        starts.append(start_addr)
        pos += 2

    if len(starts) != len(ends):
        raise ValueError("Mismatched start/end count in descriptor table")

    # Scale each waveform's sample data
    for s, e in zip(starts, ends):
        start_file = s - 0x07FC
        end_file = e - 0x07FC
        if start_file < 0 or end_file >= len(data) or start_file > end_file:
            continue

        raw = data[start_file:end_file+1]
        # Convert unsigned bytes to signed values
        samples = [b if b < 128 else b - 256 for b in raw]
        # Scale and clamp
        new_samples = []
        for v in samples:
            nv = int(round(v * scale))
            if nv > 127:
                nv = 127
            elif nv < -128:
                nv = -128
            new_samples.append(nv)
        # Convert back to unsigned bytes
        new_bytes = bytes((nv + 256) % 256 for nv in new_samples)
        data[start_file:end_file+1] = new_bytes

    # Recompute and update checksum (sum of bytes 2..end)
    checksum = sum(data[2:]) & 0xFFFF
    data[0] = (checksum >> 8) & 0xFF
    data[1] = checksum & 0xFF

    with open(file_path, 'wb') as f:
        f.write(data)

blob_fixups: blob_fixups_user_type = {
    'vendor/bin/mi_thermald': blob_fixup()
        .binary_regex_replace(b'%d/on', b'%d/..'),
    'vendor/etc/sensors/hals.conf': blob_fixup()
        .regex_replace('android.hardware.sensors@2.X-subhal-mediatek.so', 'android.hardware.sensors@2.0-subhal-impl-1.0.so')
        .regex_replace('sensors.touch.detect.so', 'sensors.dynamic_sensor_hal.so'),
    'vendor/etc/libnfc-nci.conf': blob_fixup()
        .regex_replace('NFC_DEBUG_ENABLED=1', 'NFC_DEBUG_ENABLED=0'),
    'vendor/etc/libnfc-nxp.conf': blob_fixup()
        .regex_replace('(NXPLOG_.*_LOGLEVEL)=0x03', '\\1=0x02')
        .regex_replace('NFC_DEBUG_ENABLED=1', 'NFC_DEBUG_ENABLED=0'),
    'vendor/lib64/hw/audio.primary.mediatek.so': blob_fixup()
        .replace_needed('libstagefright_foundation.so', 'libstagefright_foundation-v33.so')
        .replace_needed('libalsautils.so', 'libalsautils-v31.so')
        .replace_needed('libtinyxml2.so', 'libtinyxml2-v34.so'),
    ('vendor/lib64/mt6895/libmtkcam_stdutils.so', 'vendor/lib64/hw/mt6895/android.hardware.camera.provider@2.6-impl-mediatek.so'): blob_fixup()
        .replace_needed('libutils.so', 'libutils-v32.so'),
    ('vendor/lib64/mt6895/libcam.hal3a.so', 'vendor/lib64/mt6895/libcam.hal3a.ctrl.so', 'vendor/lib64/mt6895/libmtkcam_request_requlator.so'): blob_fixup()
        .add_needed('libprocessgroup_shim.so'),
    'vendor/lib64/libalhLDC.so': blob_fixup()
        .clear_symbol_version('AHardwareBuffer_allocate')
        .clear_symbol_version('AHardwareBuffer_describe')
        .clear_symbol_version('AHardwareBuffer_lock')
        .clear_symbol_version('AHardwareBuffer_release')
        .clear_symbol_version('AHardwareBuffer_unlock'),
    ('vendor/lib64/lib3a.ae.pipe.so', 'vendor/lib64/mt6895/libaaa_toneutil.so', 'vendor/lib64/mt6895/lib3a.flash.so', 'vendor/lib64/mt6895/lib3a.sensors.color.so', 'vendor/lib64/mt6895/lib3a.sensors.flicker.so'): blob_fixup()
        .add_needed('liblog.so'),
    ('vendor/bin/hw/vendor.dolby.hardware.dms@2.0-service'): blob_fixup()
       .add_needed('libstagefright_foundation-v33.so'),
    'vendor/firmware/aw8697_haptic.bin': blob_fixup()
        .call(partial(scale_aw8697_firmware, 1.5)),
}  # fmt: skip

module = ExtractUtilsModule(
    'xaga',
    'xiaomi',
    blob_fixups=blob_fixups,
    lib_fixups=lib_fixups,
    namespace_imports=namespace_imports,
    add_firmware_proprietary_file=True,
)

if __name__ == '__main__':
    utils = ExtractUtils.device_with_common(
        module, 'mt6895-common', module.vendor
    )
    utils.run()

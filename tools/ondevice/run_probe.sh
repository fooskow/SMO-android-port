#!/usr/bin/env bash
# Install the probe on the attached device, start it, wait for "PROBE DONE" (10 min), print its log; fail unless both ok.
set -u
APK="$1"
adb install -r "$APK"
adb logcat -c
adb shell am start -n com.thorbuild.probe/.ProbeActivity
for i in $(seq 1 120); do
  sleep 5
  if adb logcat -d -s PROBE:I | grep -q "PROBE DONE"; then break; fi
done
adb logcat -d -s PROBE:I | sed 's/^.*PROBE *: //'
adb logcat -d -s PROBE:I | grep -q "PROBE RESULT clang=ok python=ok"

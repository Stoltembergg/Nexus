#!/bin/sh
# system_profiler for the Darling prefix: reports the emulated Mac SMBIOS
# hardware/software overview and the host's real display and network hardware.
# Installed as /usr/sbin/system_profiler by tools/install-darling-system-profiler.py.
host="${DARLING_SYSTEM_ROOT:-/Volumes/SystemRoot}"
xml=0
types=
while [ $# -gt 0 ]; do
 case "$1" in
  -xml) xml=1;;
  -detailLevel|-timeout) shift;;
  -listDataTypes) printf 'Available Datatypes:\nSPAirPortDataType\nSPDisplaysDataType\nSPEthernetDataType\nSPHardwareDataType\nSPSoftwareDataType\n'; exit 0;;
  SP*DataType) types="$types $1";;
 esac
 shift
done
[ -n "$types" ] || types=" SPHardwareDataType SPSoftwareDataType SPDisplaysDataType SPEthernetDataType SPAirPortDataType"

SMBIOS_MODEL="MacBookPro16,1"
SMBIOS_MACHINE_NAME="MacBook Pro"
SMBIOS_SERIAL_NUMBER="C02C84ZUMD6N"
SMBIOS_PLATFORM_UUID="A84E7B2C-5D91-4A3E-8F12-6C49B0E2D7A1"
SMBIOS_PROVISIONING_UDID="00008006-002C7B4EA8915D"
SMBIOS_BOOT_ROM_VERSION="2020.41.1.0.0 (iBridge: 21.16.1069.0.0,0)"
SMBIOS_SMC_VERSION="2.58f15"
SMBIOS_CPU_TYPE="8-Core Intel Core i9"
SMBIOS_CPU_SPEED="2.4 GHz"
SMBIOS_PACKAGES="1"
SMBIOS_CORES="8"
SMBIOS_MEMORY="16 GB"

for smbios_conf in "${DARLING_SMBIOS_CONF:-}" "/private/etc/darling-smbios.conf" "/etc/darling-smbios.conf"; do
 [ -n "$smbios_conf" ] && [ -r "$smbios_conf" ] || continue
 while IFS='=' read -r key val || [ -n "$key" ]; do
  case "$key" in
   ''|'#'*) continue ;;
  esac
  val="${val#\"}"
  val="${val%\"}"
  val="${val#\'}"
  val="${val%\'}"
  case "$key" in
   SMBIOS_MODEL) [ -n "$val" ] && SMBIOS_MODEL="$val" ;;
   SMBIOS_MACHINE_NAME) [ -n "$val" ] && SMBIOS_MACHINE_NAME="$val" ;;
   SMBIOS_SERIAL_NUMBER) [ -n "$val" ] && SMBIOS_SERIAL_NUMBER="$val" ;;
   SMBIOS_PLATFORM_UUID) [ -n "$val" ] && SMBIOS_PLATFORM_UUID="$val" ;;
   SMBIOS_PROVISIONING_UDID) [ -n "$val" ] && SMBIOS_PROVISIONING_UDID="$val" ;;
   SMBIOS_BOOT_ROM_VERSION) [ -n "$val" ] && SMBIOS_BOOT_ROM_VERSION="$val" ;;
   SMBIOS_SMC_VERSION) [ -n "$val" ] && SMBIOS_SMC_VERSION="$val" ;;
   SMBIOS_CPU_TYPE) [ -n "$val" ] && SMBIOS_CPU_TYPE="$val" ;;
   SMBIOS_CPU_SPEED) [ -n "$val" ] && SMBIOS_CPU_SPEED="$val" ;;
   SMBIOS_PACKAGES) [ -n "$val" ] && SMBIOS_PACKAGES="$val" ;;
   SMBIOS_CORES) [ -n "$val" ] && SMBIOS_CORES="$val" ;;
   SMBIOS_MEMORY) [ -n "$val" ] && SMBIOS_MEMORY="$val" ;;
  esac
 done < "$smbios_conf"
 break
done

escape() { sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }

pci_name() { # vendor device (hex without 0x) -> "Vendor Model"
 for ids in "$host/usr/share/hwdata/pci.ids" "$host/usr/share/misc/pci.ids"; do
  [ -r "$ids" ] || continue
  awk -v v="$1" -v d="$2" '
   /^[0-9a-f][0-9a-f][0-9a-f][0-9a-f]  / { found = ($1 == v); if (found) { vendor = $0; sub(/^[0-9a-f]+  /, "", vendor) } next }
   found && /^\t[0-9a-f][0-9a-f][0-9a-f][0-9a-f]  / && $1 == d { model = $0; sub(/^\t[0-9a-f]+  /, "", model); exit }
   END {
    if (v == "1002") vendor = "AMD"; else if (v == "10de") vendor = "NVIDIA"; else if (v == "8086") vendor = "Intel"
    if (match(model, /\[[^]]*\]/)) model = substr(model, RSTART + 1, RLENGTH - 2)
    if (vendor != "" && model != "") print vendor " " model; else if (vendor != "") print vendor " Graphics"
   }' "$ids"
  return
 done
}

displays() { # one line per GPU: vendor|device|vram MB or empty|name
 for card in "$host"/sys/class/drm/card[0-9] "$host"/sys/class/drm/card[0-9][0-9]; do
  [ -r "$card/device/vendor" ] || continue
  vendor=$(sed 's/^0x//' "$card/device/vendor"); device=$(sed 's/^0x//' "$card/device/device")
  vram=
  if [ -r "$card/device/mem_info_vram_total" ]; then
   vram=$(awk '{ printf "%d", $1 / 1048576 }' "$card/device/mem_info_vram_total")
  fi
  name=$(pci_name "$vendor" "$device"); [ -n "$name" ] || name="Display"
  echo "$vendor|$device|$vram|$name"
 done
}

interfaces() { # $1 = wired|wireless; physical host interfaces only
 for path in "$host"/sys/class/net/*; do
  [ -e "$path/device" ] || continue
  if [ -d "$path/wireless" ] || [ -e "$path/phy80211" ]; then kind=wireless; else kind=wired; fi
  [ "$kind" = "$1" ] && basename "$path"
 done
}

if [ "$xml" = 1 ]; then
 echo '<?xml version="1.0" encoding="UTF-8"?>'
 echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
 echo '<plist version="1.0">'
 echo '<array>'
 for type in $types; do
  echo ' <dict>'
  echo "  <key>_dataType</key><string>$type</string>"
  echo '  <key>_items</key>'
  echo '  <array>'
  case "$type" in
   SPHardwareDataType)
    esc_model=$(printf '%s' "$SMBIOS_MODEL" | escape)
    esc_machine=$(printf '%s' "$SMBIOS_MACHINE_NAME" | escape)
    esc_cpu=$(printf '%s' "$SMBIOS_CPU_TYPE" | escape)
    esc_speed=$(printf '%s' "$SMBIOS_CPU_SPEED" | escape)
    esc_mem=$(printf '%s' "$SMBIOS_MEMORY" | escape)
    esc_rom=$(printf '%s' "$SMBIOS_BOOT_ROM_VERSION" | escape)
    esc_smc=$(printf '%s' "$SMBIOS_SMC_VERSION" | escape)
    esc_serial=$(printf '%s' "$SMBIOS_SERIAL_NUMBER" | escape)
    esc_uuid=$(printf '%s' "$SMBIOS_PLATFORM_UUID" | escape)
    esc_udid=$(printf '%s' "$SMBIOS_PROVISIONING_UDID" | escape)
    echo '   <dict>'
    echo '    <key>_name</key><string>hardware_overview</string>'
    echo "    <key>boot_rom_version</key><string>$esc_rom</string>"
    echo "    <key>cpu_type</key><string>$esc_cpu</string>"
    echo "    <key>current_processor_speed</key><string>$esc_speed</string>"
    echo '    <key>l2_cache_core</key><string>256 KB</string>'
    echo '    <key>l3_cache</key><string>16 MB</string>'
    echo "    <key>machine_model</key><string>$esc_model</string>"
    echo "    <key>machine_name</key><string>$esc_machine</string>"
    echo "    <key>number_processors</key><integer>$SMBIOS_CORES</integer>"
    echo "    <key>packages</key><integer>$SMBIOS_PACKAGES</integer>"
    echo "    <key>physical_memory</key><string>$esc_mem</string>"
    echo "    <key>platform_UUID</key><string>$esc_uuid</string>"
    echo "    <key>provisioning_UDID</key><string>$esc_udid</string>"
    echo "    <key>serial_number</key><string>$esc_serial</string>"
    echo "    <key>SMC_version_system</key><string>$esc_smc</string>"
    echo '   </dict>';;
   SPSoftwareDataType)
    esc_user=$(printf '%s' "${USER:-root}" | escape)
    echo '   <dict>'
    echo '    <key>_name</key><string>os_overview</string>'
    echo '    <key>boot_mode</key><string>normal_boot</string>'
    echo '    <key>boot_volume</key><string>Macintosh HD</string>'
    echo '    <key>kernel_version</key><string>Darwin 23.6.0</string>'
    echo '    <key>local_host_name</key><string>MacBook-Pro</string>'
    echo '    <key>os_version</key><string>macOS 14.7 (23H124)</string>'
    echo '    <key>secure_vm</key><string>secure_vm_enabled</string>'
    echo '    <key>system_integrity</key><string>integrity_enabled</string>'
    echo "    <key>user_name</key><string>$esc_user</string>"
    echo '   </dict>';;
   SPDisplaysDataType)
    displays | while IFS='|' read -r vendor device vram name; do
     name=$(printf '%s' "$name" | escape)
     echo '   <dict>'
     echo "    <key>_name</key><string>$name</string>"
     echo '    <key>spdisplays_bus</key><string>spdisplays_builtin</string>'
     echo "    <key>spdisplays_device-id</key><string>0x$device</string>"
     echo "    <key>spdisplays_vendor</key><string>${name%% *} (0x$vendor)</string>"
     [ -z "$vram" ] || echo "    <key>spdisplays_vram</key><string>$vram MB</string>"
     echo "    <key>sppci_model</key><string>$name</string>"
     echo '    <key>sppci_device_type</key><string>spdisplays_gpu</string>'
     echo '   </dict>'
    done;;
   SPEthernetDataType)
    interfaces wired | while read -r name; do
     echo '   <dict>'
     echo '    <key>_name</key><string>ethernet</string>'
     echo "    <key>spethernet_BSD_Name</key><string>$name</string>"
     echo '   </dict>'
    done;;
   SPAirPortDataType)
    echo '   <dict>'
    echo '    <key>spairport_airport_interfaces</key>'
    echo '    <array>'
    interfaces wireless | while read -r name; do
     echo '     <dict>'
     echo "      <key>_name</key><string>$name</string>"
     echo '      <key>spairport_wireless_card_type</key><string>Wi-Fi</string>'
     echo '     </dict>'
    done
    echo '    </array>'
    echo '   </dict>';;
  esac
  echo '  </array>'
  echo ' </dict>'
 done
 echo '</array>'
 echo '</plist>'
 exit 0
fi

for type in $types; do
 case "$type" in
  SPHardwareDataType)
   printf 'Hardware:\n\n    Hardware Overview:\n\n'
   printf '      Model Name: %s\n' "$SMBIOS_MACHINE_NAME"
   printf '      Model Identifier: %s\n' "$SMBIOS_MODEL"
   printf '      Processor Name: %s\n' "$SMBIOS_CPU_TYPE"
   printf '      Processor Speed: %s\n' "$SMBIOS_CPU_SPEED"
   printf '      Number of Processors: %s\n' "$SMBIOS_PACKAGES"
   printf '      Total Number of Cores: %s\n' "$SMBIOS_CORES"
   printf '      L2 Cache (per Core): 256 KB\n'
   printf '      L3 Cache: 16 MB\n'
   printf '      Hyper-Threading Technology: Enabled\n'
   printf '      Memory: %s\n' "$SMBIOS_MEMORY"
   printf '      Boot ROM Version: %s\n' "$SMBIOS_BOOT_ROM_VERSION"
   printf '      SMC Version (system): %s\n' "$SMBIOS_SMC_VERSION"
   printf '      Serial Number (system): %s\n' "$SMBIOS_SERIAL_NUMBER"
   printf '      Hardware UUID: %s\n' "$SMBIOS_PLATFORM_UUID"
   printf '      Provisioning UDID: %s\n\n' "$SMBIOS_PROVISIONING_UDID"
   ;;
  SPSoftwareDataType)
   printf 'Software:\n\n    System Software Overview:\n\n'
   printf '      System Version: macOS 14.7 (23H124)\n'
   printf '      Kernel Version: Darwin 23.6.0\n'
   printf '      Boot Volume: Macintosh HD\n'
   printf '      Boot Mode: Normal\n'
   printf '      Computer Name: MacBook-Pro\n'
   printf '      User Name: %s\n' "${USER:-root}"
   printf '      Secure Virtual Memory: Enabled\n'
   printf '      System Integrity Protection: Enabled\n\n'
   ;;
  SPDisplaysDataType)
   printf 'Graphics/Displays:\n\n'
   displays | while IFS='|' read -r vendor device vram name; do
    printf '    %s:\n\n      Chipset Model: %s\n      Type: GPU\n      Bus: Built-In\n' "$name" "$name"
    [ -z "$vram" ] || printf '      VRAM (Total): %s MB\n' "$vram"
    printf '      Vendor: %s (0x%s)\n      Device ID: 0x%s\n\n' "${name%% *}" "$vendor" "$device"
   done;;
  SPEthernetDataType)
   printf 'Ethernet Cards:\n\n'
   interfaces wired | while read -r name; do
    printf '    ethernet:\n\n      Type: Ethernet Controller\n      BSD name: %s\n\n' "$name"
   done;;
  SPAirPortDataType)
   printf 'Wi-Fi:\n\n      Interfaces:\n'
   interfaces wireless | while read -r name; do
    printf '        %s:\n          Card Type: Wi-Fi\n\n' "$name"
   done;;
 esac
done

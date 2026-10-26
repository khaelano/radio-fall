#!/usr/bin/env bash
set -euo pipefail

PROFILE="${CSI_AP_PROFILE:-csi-processor-ap}"
SSID="${CSI_AP_SSID:-csi-processor-ap}"
CHANNEL="${CSI_AP_CHANNEL:-11}"
ADDRESS="${CSI_AP_ADDRESS:-192.168.50.1/24}"
UDP_PORT="${CSI_AP_UDP_PORT:-5500}"
ZONE="${CSI_AP_FIREWALL_ZONE:-csi-sensing}"
INTERFACE="${CSI_AP_INTERFACE:-}"

usage() {
    cat <<'EOF'
Usage: tools/csi_ap.sh {up|down|status} [--interface IFACE]

Environment overrides: CSI_AP_SSID, CSI_AP_PASSWORD, CSI_AP_CHANNEL,
CSI_AP_ADDRESS, CSI_AP_UDP_PORT, CSI_AP_INTERFACE, CSI_AP_PROFILE.
EOF
}

if [[ $# -lt 1 ]]; then
    usage >&2
    exit 2
fi

ACTION="$1"
shift
while [[ $# -gt 0 ]]; do
    case "$1" in
        --interface)
            [[ $# -ge 2 ]] || { echo "--interface requires a value" >&2; exit 2; }
            INTERFACE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "$INTERFACE" ]]; then
    INTERFACE="$(nmcli -t -f DEVICE,TYPE device status \
        | awk -F: '$2 == "wifi" { print $1; exit }')"
fi
[[ -n "$INTERFACE" ]] || { echo "no Wi-Fi interface found" >&2; exit 1; }

case "$ACTION" in
    up)
        password="${CSI_AP_PASSWORD:-}"
        if [[ -z "$password" ]]; then
            read -r -s -p "CSI AP WPA2 password (at least 8 characters): " password
            printf '\n' >&2
        fi
        if [[ ${#password} -lt 8 ]]; then
            echo "CSI AP password must contain at least 8 characters" >&2
            exit 1
        fi

        if ! nmcli -t -f NAME connection show | grep -Fxq "$PROFILE"; then
            nmcli connection add \
                type wifi \
                ifname "$INTERFACE" \
                con-name "$PROFILE" \
                autoconnect no \
                ssid "$SSID"
        fi
        nmcli connection modify "$PROFILE" \
            connection.interface-name "$INTERFACE" \
            connection.autoconnect no \
            802-11-wireless.mode ap \
            802-11-wireless.band bg \
            802-11-wireless.channel "$CHANNEL" \
            802-11-wireless.ssid "$SSID" \
            802-11-wireless-security.key-mgmt wpa-psk \
            802-11-wireless-security.psk "$password" \
            ipv4.method shared \
            ipv4.addresses "$ADDRESS" \
            ipv6.method disabled \
            connection.zone "$ZONE"

        if firewall-cmd --state >/dev/null 2>&1; then
            firewall-cmd --permanent --new-zone="$ZONE" >/dev/null 2>&1 || true
            firewall-cmd --permanent --zone="$ZONE" --set-target=DROP >/dev/null
            firewall-cmd --permanent --zone="$ZONE" --add-service=dhcp >/dev/null
            firewall-cmd --permanent --zone="$ZONE" --add-service=dns >/dev/null
            firewall-cmd --permanent --zone="$ZONE" --add-port="${UDP_PORT}/udp" >/dev/null
            firewall-cmd --reload >/dev/null
        fi

        nmcli connection up "$PROFILE" ifname "$INTERFACE"
        echo "CSI AP active: SSID=$SSID channel=$CHANNEL address=${ADDRESS%%/*} UDP=$UDP_PORT"
        ;;
    down)
        nmcli connection down "$PROFILE" >/dev/null 2>&1 || true
        echo "CSI AP stopped; NetworkManager may reconnect the normal Wi-Fi profile."
        ;;
    status)
        nmcli -f GENERAL.STATE,GENERAL.CONNECTION,802-11-wireless.ssid,802-11-wireless.channel,ipv4.addresses connection show "$PROFILE" 2>/dev/null \
            || echo "CSI AP profile does not exist: $PROFILE"
        ;;
    *)
        echo "unknown action: $ACTION" >&2
        usage >&2
        exit 2
        ;;
esac

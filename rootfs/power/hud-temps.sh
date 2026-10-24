#!/bin/sh
# Keep the existing MangoHud output, discover sensors by their stable types.
cpu=
bat=
for zone in /sys/class/thermal/thermal_zone*; do
    [ -r "$zone/type" ] || continue
    read -r type < "$zone/type" || continue
    case "$type" in
        cpuss-0-0-thermal) read -r cpu < "$zone/temp" ;;
        qcom-battmgr-bat|battery) read -r bat < "$zone/temp" ;;
    esac
done
# Some kernels expose the battery temperature only through power_supply.
if [ -z "$bat" ]; then
    for supply in qcom-battmgr-bat battery; do
        path=/sys/class/power_supply/$supply/temp
        [ -r "$path" ] || continue
        read -r value < "$path" || continue
        case "$value" in ''|*[!0-9-]*) continue ;; esac
        bat=$((value * 100)) # power_supply uses tenths of a degree.
        break
    done
fi
awk -v c="$cpu" -v b="$bat" 'BEGIN {
    cs = (c ~ /^-?[0-9]+$/) ? sprintf("%d", c / 1000) : "--"
    bs = (b ~ /^-?[0-9]+$/) ? sprintf("%d", b / 1000) : "--"
    printf "T %s/%s°C", cs, bs
}'

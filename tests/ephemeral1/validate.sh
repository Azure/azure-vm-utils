#!/bin/bash
#
# Sanity check the presence of ephemeral1 NVMe disk over
# a large number of reboots and reallocations.
#

wait_for_ssh() {
    while ! ssh $ip echo ready; do
        sleep 1
    done
}

check_ephemeral1() {
    [[ "$(ssh $ip -- mount | grep -c ephemeral1)" == "1" ]]
    ssh $ip -- test -L /dev/disk/azure/local/by-index/1
    ssh $ip -- test -L /dev/disk/azure/local/by-name/nvme-150G-1
}

usage() {
    echo "usage $0 --name <name> --rg <rg> --ip <ip>"
}

name=""
rg=""
ip=""

# Parse options
while true; do
    case "$1" in
        --name)
            name="$2"
            shift 2
            ;;
        --rg)
            rg="$2"
            shift 2
            ;;
        --ip)
            ip="$2"
            shift 2
            ;;
        --)
            shift
            break
            ;;
        *)
            break
            ;;
    esac
done

if [[ -z "$name" || -z "$rg" || -z "$ip" ]]; then
    usage
    exit 1
fi

set -eu -o pipefail
echo "name=$name rg=$rg ip=$ip"
set -x


for i in $(seq 1 100); do
    echo "round $i"

    az vm stop -g $rg -n $name
    az vm start -g $rg -n $name
    wait_for_ssh
    check_ephemeral1

    ssh $ip -- sudo reboot || true
    wait_for_ssh
    check_ephemeral1

    az vm deallocate -g $rg -n $name
    az vm start -g $rg -n $name
    wait_for_ssh
    check_ephemeral1

    ssh $ip -- sudo reboot || true
    wait_for_ssh
    check_ephemeral1
done

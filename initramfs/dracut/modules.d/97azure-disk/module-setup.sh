#!/usr/bin/bash
# called by dracut
check() {
    return 0
}

# called by dracut
depends() {
    return 0
}

# called by dracut
install() {
    inst_multiple azure-nvme-id cut readlink
    inst_rules 80-azure-disk.rules
}

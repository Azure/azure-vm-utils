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
    inst_rules 10-azure-unmanaged-sriov.rules
}

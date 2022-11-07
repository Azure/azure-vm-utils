# lpt

## Install

With poetry:
```
poetry install
```

With pip:
```
pip install https://github.com/azure/azure-vm-utils/zipball/main#subdirectory=lpt
```

## Run analysis using existing logs

```
lpt analyze --journal-path tests/data/one-boot/journal.txt --cloudinit-log-path tests/data/one-boot/cloud-init.log
lpt analyze-cloudinit --cloudinit-log-path tests/data/one-boot/cloud-init.log
lpt analyze-journal --journal-path tests/data/one-boot/journal.txt
```

## Run analysis on local system

```
lpt analyze
lpt analyze --boot
```

## Graph system dependencies

```
lpt graph --service ssh.service --filter-conditional-result-no --filter-service systemd-journald.socket
```

## Remote anaylsis

```
lpt --debug --ssh-host <host> --ssh-user <user> analyze
```

## Remote anaylsis with proxy/jump

```
lpt --debug --ssh-proxy-host <jump-host> --ssh-proxy-user <jump-user> --ssh-host <host> --ssh-user <user> analyze
```

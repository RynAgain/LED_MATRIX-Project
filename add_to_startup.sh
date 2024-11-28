#!/bin/bash

# Add install_and_update.sh to the boot sequence using cron
(crontab -l 2>/dev/null; echo "@reboot /bin/bash $(pwd)/install_and_update.sh") | crontab -

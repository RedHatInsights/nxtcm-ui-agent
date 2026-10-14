#!/bin/bash
set -e

echo "nxtcm-ui-agent" > /home/botuser/app/.instance-id

# Pre-install Node 24 for nxtcm-components (engines.node >=24.15).
# Under readOnlyRootFilesystem, runtime `nvm install` only works if /usr/local/nvm
# is a writable volume; baking 24 at image build reduces that dependency.
export NVM_DIR=/usr/local/nvm
if [ -s "$NVM_DIR/nvm.sh" ]; then
  # shellcheck disable=SC1090
  . "$NVM_DIR/nvm.sh"
  nvm install 24
fi

# Instance-specific packages and tools go here:
# dnf install -y --nodocs <package>
# pip3.12 install <package>
# npm install -g <package>

echo "Instance setup complete: nxtcm-ui-agent"

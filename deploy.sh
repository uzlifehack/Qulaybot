#!/bin/bash
cd /root/qulay
git add -A
git commit -m "auto update $(date +%Y%m%d_%H%M)"
git push
systemctl restart qulaybot

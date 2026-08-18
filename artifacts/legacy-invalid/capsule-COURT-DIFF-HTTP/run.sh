#!/bin/bash
set -e
echo "SpecProof Bug Capsule Replay"
echo "Finding: COURT-DIFF-HTTP"
echo "Severity: MAJOR"
echo ""
echo "To replay this finding:"
echo "  cd capsules\capsule-COURT-DIFF-HTTP"
echo "  specproof verify --repo <repo> --base <base>"
echo "  --head <head> --spec requirement.json"

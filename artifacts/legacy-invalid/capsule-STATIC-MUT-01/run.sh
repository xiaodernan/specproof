#!/bin/bash
set -e
echo "SpecProof Bug Capsule Replay"
echo "Finding: STATIC-MUT-01"
echo "Severity: BLOCKER"
echo ""
echo "To replay this finding:"
echo "  cd capsules\capsule-STATIC-MUT-01"
echo "  specproof verify --repo <repo> --base <base>"
echo "  --head <head> --spec requirement.json"

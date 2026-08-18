$ErrorActionPreference = "Continue"
$hostRepo = (Join-Path $env:USERPROFILE ".m2\repository")
$demo = "D:\experim\specproof-clean-clone-gate\demo\spring-backend"
Write-Output "== seeding volume from $hostRepo =="
docker run --rm -v specproof-maven-cache:/root/.m2 -v "${hostRepo}:/host-m2:ro" maven:3.9-eclipse-temurin-21 sh -c "mkdir -p /root/.m2/repository && cp -a /host-m2/. /root/.m2/repository/"
Write-Output "SEED_EXIT=$LASTEXITCODE"
Write-Output "== verifying offline test-compile (network none) =="
docker run --rm --network none -v specproof-maven-cache:/root/.m2 -v "${demo}:/work" -w /work maven:3.9-eclipse-temurin-21 mvn -q -o test-compile 2>&1 | Select-Object -Last 8
Write-Output "VERIFY_EXIT=$LASTEXITCODE"

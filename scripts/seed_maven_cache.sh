#!/usr/bin/env bash
# Seed the Maven cache volume the non-root sandbox builds from.
#
# This is the ONE owner of the CI sequence that used to be inlined three
# times (tests-with-infra, eval-golden-cases, nightly-eval). The copies were
# kept in step by hand, and both recent incidents in that step were
# one-copy-only fixes (#499's comment-swallow note, #521's nightly note).
# The Windows counterpart for local runs is scripts/seed_sandbox_cache.ps1.
#
# The volume is the same one sandbox/runner.py mounts; it reads the same knob,
# so a job that renames the volume cannot seed one and build from another.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
BACKEND="$ROOT/demo/spring-backend"
WARMUP="$ROOT/scripts/seed_maven_cache_warmup"
VOLUME=${SPECPROOF_SANDBOX_M2_VOLUME:-specproof-maven-cache-1000}
IMAGE=maven:3.9-eclipse-temurin-21

# The sandbox runs as uid 1000; the volume root must belong to it.
docker volume create "$VOLUME"
docker run --rm -v "$VOLUME:/m2" "$IMAGE" sh -c "chown -R 1000:1000 /m2"

# Network is available here and nowhere in the sandbox run.
#
# `dependency:go-offline` alone is NOT enough (#530): it resolves the POM's
# declared dependencies and plugins but leaves out artifacts a real build
# still needs. Measured on a fresh volume: netty, jaxb-runtime,
# jackson-dataformat-yaml and byte-buddy were absent, and the surefire
# JUnit-platform provider was never fetched. The sandbox's offline
# `mvn -o test` then died in dependency resolution BEFORE running a single
# test — on both base and head — and the eval read that as "no defect".
docker run --rm --user 1000:1000 \
  -e MAVEN_USER_HOME=/home/maven/.m2 -e MAVEN_OPTS="-Duser.home=/home/maven" \
  -v "$VOLUME:/home/maven/.m2" -v "$BACKEND:/work:ro" -w /work \
  "$IMAGE" mvn -q -DskipTests dependency:go-offline

# Seed the phase the differential actually runs: `mvn test` with surefire
# resolving its provider. A one-test warmup class makes the run non-vacuous
# (a selector matching nothing never resolves the provider). The build runs
# in a throwaway copy so target/ stays out of the repository.
#
# The second invocation is the self-check: the SAME phase, offline, must
# execute that test from the volume alone. A zero-test offline run exits 0,
# so the surefire summary is asserted — if anything the differential needs
# is missing, this seeding step fails here with the real Maven error instead
# of surfacing as a silent recall collapse in the eval job.
docker run --rm --user 1000:1000 \
  -e MAVEN_USER_HOME=/home/maven/.m2 -e MAVEN_OPTS="-Duser.home=/home/maven" \
  -v "$VOLUME:/home/maven/.m2" -v "$BACKEND:/src:ro" -v "$WARMUP:/warmup:ro" \
  "$IMAGE" sh -c '
    set -e
    mkdir -p /tmp/work && cp -a /src/. /tmp/work/ && cd /tmp/work
    mkdir -p src/test/java/com/specproof/demo
    cp /warmup/SpecProofSeedWarmupTest.java src/test/java/com/specproof/demo/
    mvn -q -B -Dtest=SpecProofSeedWarmupTest -DfailIfNoTests=false test
    mvn -B -o -Dtest=SpecProofSeedWarmupTest -DfailIfNoTests=false test \
      > /tmp/offline.log 2>&1 \
      || { tail -n 40 /tmp/offline.log; exit 1; }
    grep -q "Tests run: 1," /tmp/offline.log \
      || { tail -n 40 /tmp/offline.log; echo "offline run executed no test" >&2; exit 1; }
  '

# *.jar is git-ignored, so the wrapper jar must be fetched for mvnw.
curl -fsSL -o "$BACKEND/.mvn/wrapper/maven-wrapper.jar" \
  https://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper/3.3.2/maven-wrapper-3.3.2.jar

# mvnw is committed 100644 (Windows drops the exec bit); `sh mvnw` needs none.
docker run --rm --user 1000:1000 \
  -e MAVEN_USER_HOME=/home/maven/.m2 -e MAVEN_OPTS="-Duser.home=/home/maven" \
  -v "$VOLUME:/home/maven/.m2" -v "$BACKEND:/work:ro" -w /work \
  "$IMAGE" sh mvnw -q -v

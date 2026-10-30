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
VOLUME=${SPECPROOF_SANDBOX_M2_VOLUME:-specproof-maven-cache-1000}
IMAGE=maven:3.9-eclipse-temurin-21

# The sandbox runs as uid 1000; the volume root must belong to it.
docker volume create "$VOLUME"
docker run --rm -v "$VOLUME:/m2" "$IMAGE" sh -c "chown -R 1000:1000 /m2"

# Network is available here and nowhere in the sandbox run.
docker run --rm --user 1000:1000 \
  -e MAVEN_USER_HOME=/home/maven/.m2 -e MAVEN_OPTS="-Duser.home=/home/maven" \
  -v "$VOLUME:/home/maven/.m2" -v "$BACKEND:/work:ro" -w /work \
  "$IMAGE" mvn -q -DskipTests dependency:go-offline

# *.jar is git-ignored, so the wrapper jar must be fetched for mvnw.
curl -fsSL -o "$BACKEND/.mvn/wrapper/maven-wrapper.jar" \
  https://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper/3.3.2/maven-wrapper-3.3.2.jar

# mvnw is committed 100644 (Windows drops the exec bit); `sh mvnw` needs none.
docker run --rm --user 1000:1000 \
  -e MAVEN_USER_HOME=/home/maven/.m2 -e MAVEN_OPTS="-Duser.home=/home/maven" \
  -v "$VOLUME:/home/maven/.m2" -v "$BACKEND:/work:ro" -w /work \
  "$IMAGE" sh mvnw -q -v

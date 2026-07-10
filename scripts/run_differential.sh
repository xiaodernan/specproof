#!/bin/bash
# P0.5-C6: Differential JUnit test execution (Base vs Head)
# Run from: demo/spring-backend/
# Creates temp worktrees, applies test infra, runs tests, compares results.

set -e

REPO_DIR="$(pwd)"
BASE_DIR=$(mktemp -d /tmp/specproof-base-XXXXXX)
HEAD_DIR=$(mktemp -d /tmp/specproof-head-XXXXXX)
trap "rm -rf $BASE_DIR $HEAD_DIR; git worktree prune 2>/dev/null" EXIT

echo "=== P0.5-C6: Differential JUnit Test Execution ==="
echo ""

# Step 1: Create worktrees
echo "[1/5] Creating isolated worktrees..."
git worktree add --detach "$BASE_DIR" base
git worktree add --detach "$HEAD_DIR" head-v1
echo "  Base worktree: $BASE_DIR"
echo "  Head worktree: $HEAD_DIR"

# Step 2: Apply test infrastructure patches to both worktrees
echo "[2/5] Applying test infrastructure patches..."

for WS in "$BASE_DIR" "$HEAD_DIR"; do
    echo "  Patching: $WS"

    # a) application-test.yml: add sql init mode never
    YML="$WS/src/test/resources/application-test.yml"
    if ! grep -q "sql.init.mode" "$YML" 2>/dev/null; then
        sed -i '1s/^/spring:\n  sql:\n    init:\n      mode: never\n/' "$YML"
    fi

    # b) SecurityConfig: change authenticated() to permitAll()
    SEC="$WS/src/main/java/com/specproof/demo/config/SecurityConfig.java"
    sed -i 's/\.anyRequest()\.authenticated()/.anyRequest().permitAll()/' "$SEC"

    # c) TestMockBeansConfig.java
    TC_DIR="$WS/src/test/java/com/specproof/demo/config"
    mkdir -p "$TC_DIR"
    cat > "$TC_DIR/TestMockBeansConfig.java" << 'TESTCFG'
package com.specproof.demo.config;

import org.mockito.Mockito;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.data.redis.core.StringRedisTemplate;

@TestConfiguration
public class TestMockBeansConfig {

    @Bean
    @Primary
    public ConnectionFactory mockConnectionFactory() {
        return Mockito.mock(ConnectionFactory.class);
    }

    @Bean
    @Primary
    public RabbitTemplate mockRabbitTemplate() {
        return Mockito.mock(RabbitTemplate.class);
    }

    @Bean
    @Primary
    public StringRedisTemplate mockStringRedisTemplate() {
        return Mockito.mock(StringRedisTemplate.class);
    }
}
TESTCFG

    # d) UserControllerTest: add @Import
    TESTFILE="$WS/src/test/java/com/specproof/demo/UserControllerTest.java"
    if ! grep -q "TestMockBeansConfig" "$TESTFILE" 2>/dev/null; then
        sed -i 's/^import com\.fasterxml\.jackson\.databind\.ObjectMapper;/import com.fasterxml.jackson.databind.ObjectMapper;\nimport com.specproof.demo.config.TestMockBeansConfig;\nimport org.springframework.context.annotation.Import;/' "$TESTFILE"
        sed -i 's/@ActiveProfiles("test")/@ActiveProfiles("test")\n@Import(TestMockBeansConfig.class)/' "$TESTFILE"
    fi

done
echo "  Patches applied"

# Step 3: Compile both
echo "[3/5] Compiling tests..."
export JAVA_HOME="${JAVA_HOME:-$HOME/apps/jdk-21.0.11+10}"

(cd "$BASE_DIR" && ./mvnw test-compile -q 2>&1) && echo "  Base: compile OK" || { echo "  Base: compile FAILED"; exit 1; }
(cd "$HEAD_DIR" && ./mvnw test-compile -q 2>&1) && echo "  Head: compile OK" || { echo "  Head: compile FAILED"; exit 1; }

# Step 4: Run tests (only the auth-specific test)
echo "[4/5] Running changeEmailWithoutAuthShouldReturn401 on both..."

BASE_EXIT=0
HEAD_EXIT=0

(cd "$BASE_DIR" && ./mvnw test -pl . "-Dtest=UserControllerTest#changeEmailWithoutAuthShouldReturn401" -q 2>&1) || BASE_EXIT=$?
echo "  Base exit code: $BASE_EXIT"

(cd "$HEAD_DIR" && ./mvnw test -pl . "-Dtest=UserControllerTest#changeEmailWithoutAuthShouldReturn401" -q 2>&1) || HEAD_EXIT=$?
echo "  Head exit code: $HEAD_EXIT"

# Step 5: Determine verdict
echo ""
echo "============================================"
echo "RESULTS"
echo "============================================"

# Display check: does each version have @PreAuthorize?
BASE_HAS_AUTH=$(grep -c "@PreAuthorize" "$BASE_DIR/src/main/java/com/specproof/demo/controller/UserController.java" 2>/dev/null || echo 0)
HEAD_HAS_AUTH=$(grep -c "@PreAuthorize" "$HEAD_DIR/src/main/java/com/specproof/demo/controller/UserController.java" 2>/dev/null || echo 0)

echo "  Static check:"
echo "    Base @PreAuthorize count: $BASE_HAS_AUTH"
echo "    Head @PreAuthorize count: $HEAD_HAS_AUTH"

echo "  Runtime check (unauthChangeEmail → expect 401):"
echo "    Base (with @PreAuthorize):    exit=$BASE_EXIT"
echo "    Head (without @PreAuthorize): exit=$HEAD_EXIT"

if [ "$BASE_HAS_AUTH" -gt 0 ] && [ "$HEAD_HAS_AUTH" -eq 0 ]; then
    if [ "$BASE_EXIT" -eq 0 ] && [ "$HEAD_EXIT" -ne 0 ]; then
        VERDICT="REGRESSION CONFIRMED"
        DETAIL="Static diff detects removed @PreAuthorize AND runtime test confirms: passes in Base (401 enforced), fails in Head (401 not enforced → 200)"
    elif [ "$BASE_EXIT" -eq 0 ] && [ "$HEAD_EXIT" -eq 0 ]; then
        VERDICT="REGRESSION (static only)"
        DETAIL="Static diff detects removed @PreAuthorize, but runtime test passes in both. SecurityConfig filter chain may mask method-level regression."
    else
        VERDICT="NEEDS INVESTIGATION"
        DETAIL="Unexpected test results"
    fi
else
    VERDICT="INCONCLUSIVE"
    DETAIL="Static check did not find expected @PreAuthorize difference"
fi

echo ""
echo "  VERDICT: $VERDICT"
echo "  Detail:  $DETAIL"
echo ""

# Cleanup
rm -rf "$BASE_DIR" "$HEAD_DIR"
git worktree prune 2>/dev/null

echo "Done."
echo ""

if [ "$BASE_EXIT" -eq 0 ] && [ "$HEAD_EXIT" -ne 0 ]; then
    exit 0
else
    exit 0  # Don't fail — the verdict is the output
fi

package com.specproof.demo.probe;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Static, thread-safe recorder of RabbitTemplate publish attempts.
 *
 * Machine-readable probe artifact (written by {@link #writeArtifact()} to
 * target/specproof-probe.json — stable path, read back by the differential
 * pipeline after the Maven JVM exits):
 * <pre>
 * {
 *   "probe_version": 1,
 *   "publish_count": 1,
 *   "outcome": "success" | "error",
 *   "payloads": [ { "exchange": ..., "routingKey": ...,
 *                   "type": ..., "timestamp": ... | null, "failed": ... } ]
 * }
 * </pre>
 * The timestamp is read reflectively via getTimestamp() so the recorder
 * stays independent of the demo event classes; payloads without that
 * accessor record null.
 */
public final class ProbePublishRecorder {

    public static final String ARTIFACT_REL = "target/specproof-probe.json";
    public static final int PROBE_VERSION = 1;

    private static final Object LOCK = new Object();
    private static final List<Map<String, Object>> RECORDS = new ArrayList<>();
    private static String outcome = "success";

    private ProbePublishRecorder() {
    }

    /** Record one publish attempt (before any injected failure fires). */
    public static void record(
            String exchange, String routingKey, Object payload, boolean failed) {
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("exchange", exchange);
        entry.put("routingKey", routingKey);
        entry.put("type", payload == null ? "null" : payload.getClass().getSimpleName());
        entry.put("timestamp", timestampOf(payload));
        entry.put("failed", failed);
        synchronized (LOCK) {
            RECORDS.add(entry);
        }
    }

    /** Operation outcome observed by the probe test: "success" or "error". */
    public static void markOutcome(String value) {
        synchronized (LOCK) {
            outcome = value;
        }
    }

    /** Reset the recorder before each probe test method. */
    public static void clear() {
        synchronized (LOCK) {
            RECORDS.clear();
            outcome = "success";
        }
    }

    /** Write the machine-readable artifact to target/specproof-probe.json. */
    public static void writeArtifact() {
        List<Map<String, Object>> payloads;
        String currentOutcome;
        synchronized (LOCK) {
            payloads = new ArrayList<>(RECORDS);
            currentOutcome = outcome;
        }
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("probe_version", PROBE_VERSION);
        root.put("publish_count", payloads.size());
        root.put("outcome", currentOutcome);
        root.put("payloads", Collections.unmodifiableList(payloads));
        try {
            Files.createDirectories(Path.of("target"));
            new ObjectMapper().writerWithDefaultPrettyPrinter()
                    .writeValue(Path.of(ARTIFACT_REL).toFile(), root);
        } catch (Exception failure) {
            throw new IllegalStateException(
                    "Failed to write SpecProof probe artifact: " + failure.getMessage(),
                    failure);
        }
    }

    private static String timestampOf(Object payload) {
        if (payload == null) {
            return null;
        }
        try {
            Method getter = payload.getClass().getMethod("getTimestamp");
            Object value = getter.invoke(payload);
            return value == null ? null : String.valueOf(value);
        } catch (ReflectiveOperationException missing) {
            return null;
        }
    }
}

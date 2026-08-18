package dev.specproof.controlplane.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;

/**
 * Constant-time X-Hub-Signature-256 verification. Fail-closed: with no
 * configured secret the verifier throws and the endpoint returns 503 —
 * a webhook without a shared secret is never processed.
 */
@Component
public class GithubWebhookVerifier {

    /** Raised when the shared secret is not configured (refuse, never pass). */
    public static class SecretNotConfiguredException extends RuntimeException {
        public SecretNotConfiguredException() {
            super("GITHUB_WEBHOOK_SECRET not configured - refusing webhook");
        }
    }

    private static final String PREFIX = "sha256=";
    private final byte[] secret;

    public GithubWebhookVerifier(
            @Value("${specproof.github.webhook-secret:}") String configuredSecret) {
        this.secret = configuredSecret == null
                ? new byte[0]
                : configuredSecret.getBytes(StandardCharsets.UTF_8);
    }

    public boolean verify(byte[] body, String signatureHeader) {
        if (secret.length == 0) {
            throw new SecretNotConfiguredException();
        }
        if (signatureHeader == null || !signatureHeader.startsWith(PREFIX)) {
            return false;
        }
        byte[] expected;
        try {
            expected = hexDecode(signatureHeader.substring(PREFIX.length()));
        } catch (IllegalArgumentException e) {
            return false;
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return MessageDigest.isEqual(expected, mac.doFinal(body));
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("HMAC-SHA256 unavailable", e);
        }
    }

    static byte[] hexDecode(String hex) {
        if (hex.length() % 2 != 0) {
            throw new IllegalArgumentException("odd hex length");
        }
        byte[] out = new byte[hex.length() / 2];
        for (int i = 0; i < out.length; i++) {
            int hi = Character.digit(hex.charAt(i * 2), 16);
            int lo = Character.digit(hex.charAt(i * 2 + 1), 16);
            if (hi < 0 || lo < 0) {
                throw new IllegalArgumentException("non-hex character");
            }
            out[i] = (byte) ((hi << 4) | lo);
        }
        return out;
    }
}

package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import org.springframework.stereotype.Component;

/** Канонические снимки, точные JSON-значения и криптографические секреты сессий. */
@Component
class Json {
    final ObjectMapper mapper;

    Json(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    JsonNode read(String text) {
        try {
            return mapper.readTree(text);
        } catch (Exception ex) {
            throw new IllegalStateException("Stored JSON is invalid", ex);
        }
    }

    JsonNode tree(Object value) {
        return mapper.valueToTree(value);
    }

    String write(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (Exception ex) {
            throw new IllegalStateException(ex);
        }
    }

    String canonical(JsonNode node) {
        return write(sorted(node));
    }

    private JsonNode sorted(JsonNode node) {
        if (node.isObject()) {
            ObjectNode result = mapper.createObjectNode();
            var keys = new TreeSet<String>();
            node.fieldNames().forEachRemaining(keys::add);
            keys.forEach(key -> result.set(key, sorted(node.get(key))));
            return result;
        }
        if (node.isArray()) {
            var result = mapper.createArrayNode();
            node.forEach(value -> result.add(sorted(value)));
            return result;
        }
        return node;
    }

    ObjectNode merge(JsonNode original, JsonNode patch) {
        var result = (ObjectNode) original.deepCopy();
        patch.fields()
                .forEachRemaining(
                        entry -> {
                            var value = entry.getValue();
                            String key = entry.getKey();
                            if (value.isNull()) result.remove(key);
                            else if (value.isObject() && result.path(key).isObject())
                                result.set(key, merge(result.get(key), value));
                            else result.set(key, value.deepCopy());
                        });
        return result;
    }

    static String hash(String value) {
        return hash(value.getBytes(StandardCharsets.UTF_8));
    }

    static String hash(byte[] value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }

    static String token() {
        byte[] data = new byte[32];
        new SecureRandom().nextBytes(data);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(data);
    }
}

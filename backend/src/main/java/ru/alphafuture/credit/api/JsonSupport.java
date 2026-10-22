package ru.alphafuture.credit.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;
import java.util.TreeSet;

@Component
public class JsonSupport {
    private final ObjectMapper mapper;
    private final SecureRandom random = new SecureRandom();
    public JsonSupport(ObjectMapper mapper) { this.mapper = mapper; }
    public JsonNode read(String value) {
        try { return mapper.readTree(value); }
        catch (Exception ex) { throw new IllegalStateException("Invalid stored JSON", ex); }
    }
    public JsonNode tree(Object value) { return mapper.valueToTree(value); }
    public String write(Object value) {
        try { return mapper.writeValueAsString(value); }
        catch (Exception ex) { throw new IllegalStateException("Cannot serialize JSON", ex); }
    }
    public String canonical(JsonNode node) {
        if (node.isObject()) {
            ObjectNode result = mapper.createObjectNode();
            var keys = new TreeSet<String>();
            node.fieldNames().forEachRemaining(keys::add);
            keys.forEach(k -> result.set(k, read(canonical(node.get(k)))));
            return write(result);
        }
        if (node.isArray()) {
            var array = mapper.createArrayNode();
            node.forEach(n -> array.add(read(canonical(n))));
            return write(array);
        }
        return write(node);
    }
    public JsonNode merge(JsonNode original, JsonNode patch) {
        if (!patch.isObject()) return patch.deepCopy();
        ObjectNode result = original != null && original.isObject()
            ? (ObjectNode) original.deepCopy() : mapper.createObjectNode();
        patch.fields().forEachRemaining(e -> {
            if (e.getValue().isNull()) result.remove(e.getKey());
            else result.set(e.getKey(), merge(result.get(e.getKey()), e.getValue()));
        });
        return result;
    }
    public String token() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }
    public static String hash(String value) { return hash(value.getBytes(StandardCharsets.UTF_8)); }
    public static String hash(byte[] value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value)); }
        catch (Exception ex) { throw new IllegalStateException(ex); }
    }
}

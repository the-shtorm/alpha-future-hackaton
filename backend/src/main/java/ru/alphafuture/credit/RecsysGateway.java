package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.JsonNode;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** Серверный HTTP-клиент внешней Recsys; модель и сборка текстов остаются у её команды. */
@Component
class RecsysGateway {
    static class Unavailable extends RuntimeException {}

    static class InvalidResponse extends RuntimeException {}

    private final String url;
    private final String apiKey;
    private final int timeout;
    private final Json json;

    RecsysGateway(
            @Value("${cabinet.recsys.url:}") String url,
            @Value("${cabinet.recsys.api-key:}") String apiKey,
            @Value("${cabinet.recsys.timeout-ms:5000}") int timeout,
            Json json) {
        this.url = url.trim();
        this.apiKey = apiKey;
        this.timeout = Math.max(100, Math.min(10000, timeout));
        this.json = json;
        if (!this.url.isEmpty()) {
            URI uri = URI.create(this.url);
            if (!java.util.Set.of("http", "https").contains(uri.getScheme())
                    || uri.getHost() == null
                    || uri.getUserInfo() != null)
                throw new IllegalArgumentException(
                        "RECSYS_URL must be an HTTP(S) endpoint without user info");
        }
    }

    boolean configured() {
        return !url.isEmpty();
    }

    JsonNode rank(Object request) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) URI.create(url).toURL().openConnection();
            connection.setConnectTimeout(timeout);
            connection.setReadTimeout(timeout);
            connection.setInstanceFollowRedirects(false);
            connection.setRequestMethod("POST");
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setRequestProperty("Accept", "application/json");
            if (!apiKey.isBlank())
                connection.setRequestProperty("Authorization", "Bearer " + apiKey);
            byte[] bytes = json.write(request).getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(bytes.length);
            try (var output = connection.getOutputStream()) {
                output.write(bytes);
            }
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) throw new Unavailable();
            String contentType = connection.getContentType();
            if (contentType == null
                    || !contentType.toLowerCase(java.util.Locale.ROOT).contains("application/json"))
                throw new InvalidResponse();
            try (var input = connection.getInputStream()) {
                byte[] body = input.readNBytes(1048577);
                if (body.length > 1048576) throw new InvalidResponse();
                try {
                    return json.mapper.readTree(body);
                } catch (Exception ex) {
                    throw new InvalidResponse();
                }
            }
        } catch (InvalidResponse | Unavailable ex) {
            throw ex;
        } catch (IOException ex) {
            throw new Unavailable();
        } finally {
            if (connection != null) connection.disconnect();
        }
    }
}

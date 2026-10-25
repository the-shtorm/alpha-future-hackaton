package ru.alphafuture.credit;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.*;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.Flow;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** Ограниченный внутренний клиент SBA: connect 500 мс, общий deadline 2 с, 64 КиБ. */
@Component
class ScoringGateway {
    static class Failure extends RuntimeException {
        final String code;

        Failure(String code) {
            super(code);
            this.code = code;
        }
    }

    private static final Set<String> FIELDS =
            Set.of(
                    "schemaVersion",
                    "requestId",
                    "sbaDefaultProbability",
                    "score",
                    "modelVersion",
                    "featureVersion",
                    "calibrationVersion",
                    "domainStatus",
                    "isDemo",
                    "warnings");
    private final String url;
    private final String key;
    private final ObjectMapper mapper;
    private final HttpClient client;

    ScoringGateway(
            @Value("${cabinet.scoring.url:}") String url,
            @Value("${cabinet.scoring.api-key:}") String key,
            Json json) {
        this.url = url.trim();
        this.key = key;
        mapper =
                json.mapper
                        .copy()
                        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                        .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
        client =
                HttpClient.newBuilder()
                        .version(HttpClient.Version.HTTP_1_1)
                        .connectTimeout(Duration.ofMillis(500))
                        .followRedirects(HttpClient.Redirect.NEVER)
                        .build();
        if (!this.url.isEmpty()) {
            URI uri = URI.create(this.url);
            if (!Set.of("http", "https").contains(uri.getScheme())
                    || uri.getHost() == null
                    || uri.getUserInfo() != null)
                throw new IllegalArgumentException(
                        "SCORING_URL must be an HTTP(S) endpoint without user info");
        }
    }

    ScoringExchange.Output evaluate(ScoringExchange.Input input) {
        if (url.isEmpty() || key.isBlank()) throw new Failure("SCORING_UNAVAILABLE");
        CompletableFuture<HttpResponse<byte[]>> pending = null;
        try {
            var request =
                    HttpRequest.newBuilder(URI.create(url))
                            .timeout(Duration.ofSeconds(2))
                            .header("Authorization", "Bearer " + key)
                            .header("Content-Type", "application/json")
                            .header("Accept", "application/json")
                            .POST(
                                    HttpRequest.BodyPublishers.ofString(
                                            mapper.writeValueAsString(input)))
                            .build();
            pending = client.sendAsync(request, info -> new BoundedBody());
            var response = pending.get(2, TimeUnit.SECONDS);
            if (response.statusCode() != 200) throw new Failure("SCORING_UNAVAILABLE");
            if (!response.headers()
                    .firstValue("Content-Type")
                    .orElse("")
                    .toLowerCase(Locale.ROOT)
                    .startsWith("application/json")) throw new Failure("SCORING_INVALID_RESPONSE");
            return validate(mapper.readTree(response.body()), input.requestId());
        } catch (Failure ex) {
            throw ex;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new Failure("SCORING_UNAVAILABLE");
        } catch (Exception ex) {
            throw new Failure("SCORING_UNAVAILABLE");
        } finally {
            if (pending != null && !pending.isDone()) pending.cancel(true);
        }
    }

    ScoringExchange.Output validate(JsonNode node, UUID expected) {
        try {
            var names = new HashSet<String>();
            node.fieldNames().forEachRemaining(names::add);
            if (!node.isObject()
                    || !names.equals(FIELDS)
                    || !node.path("schemaVersion").asText().equals(ScoringExchange.SCHEMA)
                    || !node.path("requestId").asText().equals(expected.toString())
                    || !node.path("sbaDefaultProbability").isNumber()
                    || !node.path("score").isIntegralNumber()
                    || !node.path("score").canConvertToInt()
                    || !node.path("isDemo").isBoolean()
                    || !node.path("isDemo").booleanValue()
                    || !Set.of("IN_RANGE", "EXTRAPOLATION")
                            .contains(node.path("domainStatus").asText())
                    || !node.path("featureVersion").asText().equals("sba-features-1")
                    || !node.path("warnings").isArray())
                throw new Failure("SCORING_INVALID_RESPONSE");
            var p = node.get("sbaDefaultProbability").decimalValue();
            if (p.signum() < 0
                    || p.compareTo(java.math.BigDecimal.ONE) > 0
                    || ScoringExchange.score(p) != node.get("score").intValue())
                throw new Failure("SCORING_INVALID_RESPONSE");
            for (String field : List.of("modelVersion", "calibrationVersion"))
                if (!node.get(field).isTextual()
                        || node.get(field).asText().isBlank()
                        || node.get(field).asText().length() > 120)
                    throw new Failure("SCORING_INVALID_RESPONSE");
            var warnings = new ArrayList<String>();
            for (var value : node.get("warnings")) {
                if (!value.isTextual() || value.asText().isBlank() || value.asText().length() > 120)
                    throw new Failure("SCORING_INVALID_RESPONSE");
                warnings.add(value.asText());
            }
            return new ScoringExchange.Output(
                    ScoringExchange.SCHEMA,
                    expected,
                    p,
                    node.get("score").intValue(),
                    node.get("modelVersion").asText(),
                    "sba-features-1",
                    node.get("calibrationVersion").asText(),
                    node.get("domainStatus").asText(),
                    true,
                    List.copyOf(warnings));
        } catch (Failure ex) {
            throw ex;
        } catch (Exception ex) {
            throw new Failure("SCORING_INVALID_RESPONSE");
        }
    }

    private static class BoundedBody implements HttpResponse.BodySubscriber<byte[]> {
        private final CompletableFuture<byte[]> result = new CompletableFuture<>();
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        private Flow.Subscription subscription;

        public CompletionStage<byte[]> getBody() {
            return result;
        }

        public void onSubscribe(Flow.Subscription value) {
            subscription = value;
            value.request(1);
        }

        public void onNext(List<ByteBuffer> buffers) {
            for (var buffer : buffers) {
                if (bytes.size() + buffer.remaining() > 65536) {
                    subscription.cancel();
                    result.completeExceptionally(new Failure("SCORING_INVALID_RESPONSE"));
                    return;
                }
                byte[] part = new byte[buffer.remaining()];
                buffer.get(part);
                bytes.writeBytes(part);
            }
            subscription.request(1);
        }

        public void onError(Throwable error) {
            result.completeExceptionally(error);
        }

        public void onComplete() {
            result.complete(bytes.toByteArray());
        }
    }
}

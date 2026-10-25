package ru.alphafuture.credit;

import com.sun.net.httpserver.HttpServer;
import java.math.BigDecimal;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Управляемый настоящий HTTP stub; синтетические вероятности не являются SBA-моделью. */
class ScoringStub implements AutoCloseable {
    final HttpServer server;
    final AtomicInteger calls = new AtomicInteger();
    volatile String probability = "0.05";
    volatile String alternativeProbability;
    volatile String modelVersion = "fixture-sba-v1";
    volatile boolean switchVersion;
    volatile int status = 200;
    volatile String body;
    volatile long delay;
    volatile String authorization;
    volatile com.fasterxml.jackson.databind.JsonNode lastRequest;

    ScoringStub() {
        try {
            server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext(
                    "/evaluate",
                    exchange -> {
                        int count = calls.incrementAndGet();
                        authorization = exchange.getRequestHeaders().getFirst("Authorization");
                        lastRequest =
                                TestData.MAPPER.readTree(exchange.getRequestBody().readAllBytes());
                        if (delay > 0)
                            try {
                                Thread.sleep(delay);
                            } catch (InterruptedException ex) {
                                Thread.currentThread().interrupt();
                            }
                        String value =
                                count > 1 && alternativeProbability != null
                                        ? alternativeProbability
                                        : probability;
                        String response =
                                body != null
                                        ? body
                                        : TestData.JSON.write(
                                                Map.of(
                                                        "schemaVersion",
                                                        "sba-scoring-1",
                                                        "requestId",
                                                        lastRequest.path("requestId").asText(),
                                                        "sbaDefaultProbability",
                                                        new BigDecimal(value),
                                                        "score",
                                                        ScoringExchange.score(
                                                                new BigDecimal(value)),
                                                        "modelVersion",
                                                        switchVersion && count > 1
                                                                ? "fixture-changed"
                                                                : modelVersion,
                                                        "featureVersion",
                                                        "sba-features-1",
                                                        "calibrationVersion",
                                                        "fixture-sigmoid",
                                                        "domainStatus",
                                                        "EXTRAPOLATION",
                                                        "isDemo",
                                                        true,
                                                        "warnings",
                                                        List.of(
                                                                "SBA_US_TO_RU_DEMO",
                                                                "RATE_OUT_OF_RANGE")));
                        byte[] bytes = response.getBytes(StandardCharsets.UTF_8);
                        exchange.getResponseHeaders().set("Content-Type", "application/json");
                        exchange.sendResponseHeaders(status, bytes.length);
                        try (var stream = exchange.getResponseBody()) {
                            stream.write(bytes);
                        }
                    });
            server.start();
        } catch (Exception ex) {
            throw new IllegalStateException(ex);
        }
    }

    String url() {
        return "http://127.0.0.1:" + server.getAddress().getPort() + "/evaluate";
    }

    void reset() {
        calls.set(0);
        probability = "0.05";
        alternativeProbability = null;
        switchVersion = false;
        status = 200;
        body = null;
        delay = 0;
    }

    public void close() {
        server.stop(0);
    }
}

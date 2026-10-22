package ru.alphafuture.credit.api;

import java.util.List;

public class ApiException extends RuntimeException {
    public record Issue(String field, String code, String message) {}
    public final int status;
    public final String code;
    public final List<Issue> errors;

    public ApiException(int status, String code, String message) {
        this(status, code, message, List.of());
    }
    public ApiException(int status, String code, String message, List<Issue> errors) {
        super(message);
        this.status = status;
        this.code = code;
        this.errors = errors;
    }
    public static ApiException notFound() { return new ApiException(404, "NOT_FOUND", "Объект не найден"); }
    public static ApiException conflict() { return new ApiException(409, "VERSION_CONFLICT", "Данные изменились. Обновите форму"); }
    public static ApiException invalid(String field, String message) {
        return new ApiException(400, "INVALID_INPUT", "Проверьте поля запроса", List.of(new Issue(field, "INVALID", message)));
    }
}

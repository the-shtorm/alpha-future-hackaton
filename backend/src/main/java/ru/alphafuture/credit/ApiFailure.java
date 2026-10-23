package ru.alphafuture.credit;

import java.util.*;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.*;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

/** Публичная ошибка API без SQL, секретов и серверных путей. */
class ApiFailure extends RuntimeException {
    final int status;
    final String code;
    final List<String> fields;

    ApiFailure(int status, String code, String message, String... fields) {
        super(message);
        this.status = status;
        this.code = code;
        this.fields = List.of(fields);
    }

    static ApiFailure invalid(String field, String message) {
        return new ApiFailure(400, "INVALID_INPUT", message, field);
    }

    static ApiFailure missing() {
        return new ApiFailure(404, "NOT_FOUND", "Объект не найден");
    }

    static ApiFailure conflict() {
        return new ApiFailure(
                409, "STATE_CONFLICT", "Устаревшая версия или недопустимое состояние");
    }
}

/** Единый формат ошибок, включая ошибки парсинга и валидации. */
@RestControllerAdvice
class ApiErrors {
    @ExceptionHandler(ApiFailure.class)
    ResponseEntity<ProblemDetail> failure(ApiFailure ex) {
        var problem =
                ProblemDetail.forStatusAndDetail(
                        HttpStatusCode.valueOf(ex.status), ex.getMessage());
        problem.setTitle(ex.code);
        problem.setProperty("code", ex.code);
        problem.setProperty("fields", ex.fields);
        return ResponseEntity.status(ex.status).body(problem);
    }

    @ExceptionHandler({
        HttpMessageNotReadableException.class,
        MethodArgumentTypeMismatchException.class,
        MethodArgumentNotValidException.class
    })
    ResponseEntity<ProblemDetail> input(Exception ex) {
        return failure(ApiFailure.invalid("request", "Некорректный формат запроса"));
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    ResponseEntity<ProblemDetail> constraint(Exception ex) {
        return failure(ApiFailure.conflict());
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<ProblemDetail> size(Exception ex) {
        return failure(new ApiFailure(413, "FILE_TOO_LARGE", "Максимум 10 MB"));
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ProblemDetail> unexpected(Exception ex) {
        if (ex instanceof org.springframework.web.ErrorResponse e)
            return failure(
                    new ApiFailure(
                            e.getStatusCode().value(),
                            "HTTP_ERROR",
                            "Запрос не может быть обработан"));
        org.slf4j.LoggerFactory.getLogger(ApiErrors.class).error("Backend failure", ex);
        return failure(new ApiFailure(500, "INTERNAL_ERROR", "Не удалось выполнить операцию"));
    }
}

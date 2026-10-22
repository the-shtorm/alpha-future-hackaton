package ru.alphafuture.credit.api;

import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.servlet.resource.NoResourceFoundException;
import org.springframework.web.bind.ServletRequestBindingException;

@RestControllerAdvice
public class ApiErrors {
    @ExceptionHandler(ApiException.class)
    ResponseEntity<ProblemDetail> api(ApiException ex) {
        var problem = ProblemDetail.forStatusAndDetail(org.springframework.http.HttpStatusCode.valueOf(ex.status), ex.getMessage());
        problem.setProperty("code", ex.code);
        problem.setProperty("errors", ex.errors);
        return ResponseEntity.status(ex.status).body(problem);
    }
    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> bean(MethodArgumentNotValidException ex) {
        return api(new ApiException(400, "INVALID_INPUT", "Проверьте поля запроса",
            ex.getBindingResult().getFieldErrors().stream()
                .map(e -> new ApiException.Issue(e.getField(), "INVALID", e.getDefaultMessage())).toList()));
    }
    @ExceptionHandler({HttpMessageNotReadableException.class, MethodArgumentTypeMismatchException.class,
        HandlerMethodValidationException.class, ServletRequestBindingException.class})
    ResponseEntity<ProblemDetail> malformed(Exception ex) {
        return api(new ApiException(400, "INVALID_INPUT", "Некорректный формат запроса"));
    }
    @ExceptionHandler(DataIntegrityViolationException.class)
    ResponseEntity<ProblemDetail> constraint(Exception ex) {
        return api(new ApiException(409, "STATE_CONFLICT", "Операция противоречит текущему состоянию данных"));
    }
    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<ProblemDetail> tooLarge(Exception ex) {
        return api(new ApiException(413, "FILE_TOO_LARGE", "Максимальный размер файла — 10 MB"));
    }
    @ExceptionHandler(NoResourceFoundException.class)
    ResponseEntity<ProblemDetail> missing(Exception ex) { return api(ApiException.notFound()); }
    @ExceptionHandler(Exception.class)
    ResponseEntity<ProblemDetail> unexpected(Exception ex) {
        if (ex instanceof org.springframework.web.ErrorResponse error) {
            return api(new ApiException(error.getStatusCode().value(), "HTTP_ERROR", "Запрос не может быть обработан"));
        }
        LoggerFactory.getLogger(ApiErrors.class).error("Unhandled API failure: {}", ex.getClass().getName());
        return api(new ApiException(500, "INTERNAL_ERROR", "Не удалось выполнить операцию"));
    }
}

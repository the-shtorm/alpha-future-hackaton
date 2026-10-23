package ru.alphafuture.credit;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

/** REST-команды клиента и банка; служебные владельцы и статусы не принимаются из формы. */
@RestController
class CabinetController {
    record Create(
            @NotNull UUID profileId,
            @NotNull @PositiveOrZero Long expectedProfileVersion,
            @NotNull JsonNode answers) {}

    record Refresh(
            @NotNull @PositiveOrZero Long expectedVersion,
            @NotNull @PositiveOrZero Long expectedProfileVersion) {}

    record CounterAccept(
            @NotNull UUID proposalId,
            @NotBlank @Pattern(regexp = "[0-9a-f]{64}") String termsSha256,
            boolean confirmed) {}

    record Patch(@NotNull @PositiveOrZero Long expectedVersion, @NotNull JsonNode answers) {}

    record Submission(@NotNull @PositiveOrZero Long expectedVersion, boolean confirmed) {}

    record Confirmation(boolean confirmed) {}

    record Accept(@NotNull UUID offerId, boolean confirmed) {}

    record Decision(
            @NotNull DataPolicy.Kind kind,
            @NotBlank @Size(max = 2000) String reason,
            @Size(max = 64) List<@NotBlank @Size(max = 120) String> missingFields) {}

    record Review(@NotBlank String result, @NotBlank @Size(max = 2000) String reason) {}

    private final ApplicationService apps;
    private final Catalog catalog;
    private final Documents documents;

    CabinetController(ApplicationService apps, Catalog catalog, Documents documents) {
        this.apps = apps;
        this.catalog = catalog;
        this.documents = documents;
    }

    @GetMapping("/products")
    Map<String, Object> products(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "12") int size) {
        return catalog.list(page, size);
    }

    @GetMapping("/products/{id}")
    Catalog.Product product(@PathVariable UUID id) {
        return catalog.get(id, true);
    }

    @GetMapping("/forms/application")
    Map<String, Object> form() {
        return Map.of(
                "formVersion",
                FormPolicy.APPLICATION_VERSION,
                "fields",
                FormPolicy.fields(FormPolicy.Stage.APPLICATION),
                "transferredFields",
                FormPolicy.TRANSFER_FIELDS);
    }

    @GetMapping("/forms/preliminary")
    Map<String, Object> preliminaryForm() {
        return Map.of(
                "formVersion",
                FormPolicy.PRELIMINARY_VERSION,
                "fields",
                FormPolicy.fields(FormPolicy.Stage.PRELIMINARY),
                "conditionalFields",
                List.of(
                        "registration.country",
                        "business.region",
                        "business.ipAgeYears",
                        "security.collateralReady",
                        "security.guarantorReady",
                        "business.marketplaceMonths",
                        "business.bankAccountMonths"));
    }

    @PostMapping("/applications/{id}/refresh-preliminary")
    ApplicationService.Draft refresh(@PathVariable UUID id, @Valid @RequestBody Refresh body) {
        return apps.refreshPreliminary(id, body.expectedVersion(), body.expectedProfileVersion());
    }

    @PostMapping("/applications/{id}/counteroffers/accept")
    Map<String, Object> acceptCounter(
            @PathVariable UUID id, @Valid @RequestBody CounterAccept body) {
        confirm(body.confirmed());
        return apps.acceptCounteroffer(id, body.proposalId(), body.termsSha256());
    }

    @PostMapping("/applications")
    ApplicationService.Draft create(@Valid @RequestBody Create body) {
        return apps.create(body.profileId(), body.expectedProfileVersion(), body.answers());
    }

    @GetMapping("/applications")
    Map<String, Object> list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return apps.list(false, page, size);
    }

    @GetMapping("/applications/{id}")
    ApplicationService.Draft get(@PathVariable UUID id) {
        return apps.get(id);
    }

    @PatchMapping("/applications/{id}")
    ApplicationService.Draft patch(@PathVariable UUID id, @Valid @RequestBody Patch body) {
        return apps.patch(id, body.expectedVersion(), body.answers());
    }

    @PostMapping("/applications/{id}/validate")
    Map<String, Object> validate(@PathVariable UUID id) {
        return apps.validate(id);
    }

    @PostMapping("/applications/{id}/submit")
    Map<String, Object> submit(
            @PathVariable UUID id,
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody Submission body) {
        confirm(body.confirmed());
        return apps.submit(id, body.expectedVersion(), key);
    }

    @GetMapping({"/applications/{id}/journey", "/applications/{id}/status"})
    Map<String, Object> journey(@PathVariable UUID id) {
        return apps.journey(id);
    }

    @GetMapping("/applications/{id}/revisions/{revision}")
    Map<String, Object> revision(@PathVariable UUID id, @PathVariable UUID revision) {
        return apps.revision(id, revision);
    }

    @GetMapping("/applications/{id}/requirements")
    List<Map<String, Object>> requirements(@PathVariable UUID id) {
        return apps.requirements(id);
    }

    @PostMapping(
            value = "/applications/{id}/documents",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Map<String, Object> upload(
            @PathVariable UUID id,
            @RequestParam @Size(max = 64) String typeCode,
            @RequestPart MultipartFile file) {
        return apps.upload(id, typeCode, file);
    }

    @GetMapping("/applications/{id}/documents/{version}")
    ResponseEntity<byte[]> download(@PathVariable UUID id, @PathVariable UUID version) {
        apps.get(id);
        var row = documents.metadata(id, version);
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(row.get("media_type").toString()))
                .header("Content-Disposition", "attachment; filename=\"document\"")
                .header("X-Content-Type-Options", "nosniff")
                .body(documents.read(id, version));
    }

    @GetMapping("/applications/{id}/financial-evidence")
    List<Map<String, Object>> financialEvidence(@PathVariable UUID id) {
        return apps.financialEvidence(id);
    }

    @PostMapping("/applications/{id}/financial-evidence")
    Map<String, Object> financialEvidence(
            @PathVariable UUID id, @Valid @RequestBody FinancialEvidence.Input input) {
        return apps.addFinancialEvidence(id, input);
    }

    @PostMapping("/bank/applications/{id}/financial-evidence/{evidence}/review")
    Map<String, String> financialReview(
            @PathVariable UUID id, @PathVariable UUID evidence, @Valid @RequestBody Review input) {
        apps.reviewFinancialEvidence(id, evidence, input.result(), input.reason());
        return Map.of("status", "ok");
    }

    @GetMapping("/bank/applications")
    Map<String, Object> queue(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return apps.list(true, page, size);
    }

    @PostMapping("/bank/applications/{id}/assign")
    ApplicationService.Draft assign(@PathVariable UUID id) {
        return apps.assign(id);
    }

    @PostMapping("/bank/applications/{id}/process")
    Map<String, Object> process(@PathVariable UUID id) {
        return apps.process(id);
    }

    @PostMapping("/bank/applications/{id}/decisions")
    Map<String, Object> decision(@PathVariable UUID id, @Valid @RequestBody Decision body) {
        return apps.humanDecision(
                id,
                new ApplicationService.HumanDecision(
                        body.kind(), body.reason(), body.missingFields()));
    }

    @PostMapping("/bank/applications/{id}/documents/{version}/review")
    Map<String, String> review(
            @PathVariable UUID id, @PathVariable UUID version, @Valid @RequestBody Review body) {
        apps.reviewDocument(id, version, body.result(), body.reason());
        return Map.of("status", "ok");
    }

    @PostMapping("/applications/{id}/offers/accept")
    Map<String, Object> accept(@PathVariable UUID id, @Valid @RequestBody Accept body) {
        confirm(body.confirmed());
        return apps.accept(id, body.offerId());
    }

    @PostMapping("/applications/{id}/contract/sign")
    Map<String, Object> sign(@PathVariable UUID id, @RequestBody Confirmation body) {
        confirm(body.confirmed());
        return apps.sign(id);
    }

    @PostMapping("/bank/applications/{id}/disburse")
    Map<String, Object> disburse(@PathVariable UUID id, @RequestBody Confirmation body) {
        confirm(body.confirmed());
        return apps.disburse(id);
    }

    private void confirm(boolean value) {
        if (!value)
            throw ApiFailure.invalid("confirmed", "Нужно явное подтверждение владельца операции");
    }
}

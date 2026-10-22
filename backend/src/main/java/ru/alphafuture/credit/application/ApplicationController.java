package ru.alphafuture.credit.application;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/applications")
public class ApplicationController {
    private final ApplicationService applications;
    private final DocumentService documents;
    public ApplicationController(ApplicationService applications,DocumentService documents) { this.applications=applications;this.documents=documents; }
    public record Create(@NotNull UUID profileId,@NotNull UUID partyId) {}
    public record Patch(@NotNull @PositiveOrZero Long expectedVersion,@NotNull JsonNode answers) {}
    public record Submit(@NotNull @PositiveOrZero Long expectedVersion,@NotNull Boolean confirmed) {}
    @PostMapping @ResponseStatus(HttpStatus.CREATED)
    public ApplicationService.Application create(@Valid @RequestBody Create request,@RequestHeader(value="X-Profile-Token",required=false) String token) {
        return applications.create(request.profileId(),token,request.partyId());
    }
    @GetMapping
    public Map<String,Object> list(@RequestParam(defaultValue="0") int page,@RequestParam(defaultValue="12") int size) { return applications.list(page,size); }
    @GetMapping("/{id}")
    public ApplicationService.Application get(@PathVariable UUID id) { return applications.get(id,false,false,false); }
    @PatchMapping("/{id}")
    public ApplicationService.Application patch(@PathVariable UUID id,@Valid @RequestBody Patch request) { return applications.patch(id,request.expectedVersion(),request.answers()); }
    @GetMapping("/{id}/requirements")
    public List<Map<String,Object>> requirements(@PathVariable UUID id) { return applications.requirements(id); }
    @PostMapping(value="/{id}/documents",consumes="multipart/form-data") @ResponseStatus(HttpStatus.CREATED)
    public Map<String,Object> upload(@PathVariable UUID id,@RequestParam UUID requirementId,@RequestParam MultipartFile file) throws IOException {
        return documents.upload(id,requirementId,file);
    }
    @GetMapping("/{id}/documents/{versionId}")
    public ResponseEntity<ByteArrayResource> download(@PathVariable UUID id,@PathVariable UUID versionId) throws IOException { return documents.download(id,versionId); }
    @PostMapping("/{id}/validate")
    public Map<String,Object> validate(@PathVariable UUID id) { return applications.validate(id); }
    @GetMapping("/{id}/validation-results")
    public List<Map<String,Object>> results(@PathVariable UUID id) { return applications.results(id); }
    @GetMapping("/{id}/status")
    public Map<String,Object> status(@PathVariable UUID id) { return applications.status(id); }
    @PostMapping("/{id}/submit")
    public Map<String,Object> submit(@PathVariable UUID id,@RequestHeader("Idempotency-Key") String key,@Valid @RequestBody Submit request) {
        return applications.submit(id,request.expectedVersion(),request.confirmed(),key);
    }
}

package com.cro.report.api;
import com.cro.report.api.ReportDtos.*; import com.cro.report.service.ReportService; import jakarta.validation.Valid;
import org.springframework.http.*; import org.springframework.web.bind.annotation.*;
@RestController @RequestMapping("/api/reports") public class ReportController {
 private final ReportService service; public ReportController(ReportService s){service=s;}
 @PostMapping public ResponseEntity<ReportView> create(@Valid @RequestBody CreateReport in){return ResponseEntity.status(HttpStatus.CREATED).body(service.create(in));}
 @GetMapping("/{id}") public ReportView get(@PathVariable String id){return service.get(id);}
 @GetMapping("/{id}/fields") public Object fields(@PathVariable String id){return service.get(id).fields();}
 @PostMapping("/{id}/extract") public ResponseEntity<JobAccepted> extract(@PathVariable String id){return ResponseEntity.accepted().body(service.extract(id));}
 @PostMapping("/{id}/generate") public ResponseEntity<JobAccepted> generate(@PathVariable String id){var x=service.generate(id);return ResponseEntity.status("BLOCKED".equals(x.status())?HttpStatus.CONFLICT:HttpStatus.ACCEPTED).body(x);}
}

